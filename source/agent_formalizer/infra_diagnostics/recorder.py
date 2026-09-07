"""Non-blocking, fail-open provider and gateway diagnostics recorder."""

from __future__ import annotations

import datetime
import hashlib
import json
import queue
import threading
from pathlib import Path
from typing import Any, Mapping

from .redaction import redact, safe_response_headers
from .registry import (
    GENERIC_HANDLER_ID,
    canonical_provider_id,
    create_handler,
    resolve_handler_id,
)
from .storage import JsonlDiagnosticStorage
from .types import DiagnosticProjection, ProviderResponseSnapshot


SCHEMA_VERSION = 1
_STOP = object()


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _retry_after_ms(headers: Mapping[str, str]) -> int | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0, round(float(value) * 1000))
    except (TypeError, ValueError):
        return None


class InfraDiagnosticsRecorder:
    """Own one execution's bounded diagnostic queue and JSONL writer."""

    def __init__(self, runtime_config: Mapping[str, Any] | None = None):
        config = dict(runtime_config or {})
        self.enabled = bool(config.get("enabled", False))
        self.provider = canonical_provider_id(str(config.get("provider", "unknown")))
        self.mode = str(config.get("mode", "off"))
        self.capture_success_metadata = bool(
            config.get("capture_success_metadata", False)
        )
        self.capture_transport_errors = bool(
            config.get("capture_transport_errors", False)
        )
        self.capture_gateway_internal_errors = bool(
            config.get("capture_gateway_internal_errors", False)
        )
        self.correlation = dict(config.get("correlation") or {})
        self.operational_config_sha256 = config.get("operational_config_sha256")
        self.max_event_bytes = int(config.get("max_event_bytes", 65536))
        self._lock = threading.Lock()
        self._counts = {
            "events_seen": 0,
            "events_queued": 0,
            "events_written": 0,
            "events_dropped": 0,
            "events_truncated": 0,
            "handler_failures": 0,
            "storage_failures": 0,
            "bytes_written": 0,
        }
        self._queue: queue.Queue = queue.Queue(maxsize=256)
        self._thread: threading.Thread | None = None
        self._storage: JsonlDiagnosticStorage | None = None
        self.handler_id: str | None = None
        self._handler = None
        self._fallback = None
        self._closed = False

        if not self.enabled:
            return
        if self.mode not in {"off", "metadata", "structured", "raw"}:
            raise ValueError(f"unsupported infra diagnostics mode: {self.mode}")
        requested_handler = config.get("handler")
        self.handler_id = resolve_handler_id(
            self.provider,
            str(requested_handler) if requested_handler is not None else None,
        )
        self._handler = create_handler(self.handler_id)
        self._fallback = create_handler(GENERIC_HANDLER_ID)
        required_storage = {
            "event_path",
            "manifest_path",
            "run_budget_path",
            "max_run_bytes",
        }
        missing_storage = required_storage - set(config)
        if missing_storage:
            raise ValueError(
                "infra diagnostics runtime config is missing: "
                + ", ".join(sorted(missing_storage))
            )
        try:
            self._storage = JsonlDiagnosticStorage(
                event_path=config["event_path"],
                manifest_path=config["manifest_path"],
                run_budget_path=config["run_budget_path"],
                max_event_bytes=self.max_event_bytes,
                max_run_bytes=int(config["max_run_bytes"]),
            )
        except OSError:
            # A declared handler/configuration error is fail-fast, but an
            # unavailable diagnostic sink is optional and must not prevent the
            # gateway from serving the measured request.
            self._bump("storage_failures")
            self._storage = None
        self._safe_write_manifest(closed=False)
        self._thread = threading.Thread(
            target=self._worker,
            name="infra-diagnostics-writer",
            daemon=True,
        )
        self._thread.start()

    @classmethod
    def from_config_path(cls, path: str | Path | None):
        if not path:
            return cls()
        config_path = Path(path)
        try:
            value = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load infra diagnostics runtime config: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("infra diagnostics runtime config must be an object")
        return cls(value)

    def _bump(self, field: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[field] += amount

    def _snapshot_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def status(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "enabled": self.enabled,
            "provider": self.provider,
            "mode": self.mode,
            "handler": self.handler_id,
            "operational_config_sha256": self.operational_config_sha256,
            "closed": self._closed,
            **self._snapshot_counts(),
        }

    def _safe_write_manifest(self, *, closed: bool) -> None:
        if self._storage is None:
            return
        try:
            self._storage.write_manifest(
                {
                    **self.status(),
                    "closed": closed,
                    "updated_at": _now(),
                }
            )
        except Exception:
            self._bump("storage_failures")

    def _enqueue(self, snapshot: ProviderResponseSnapshot) -> None:
        if not self.enabled or self._closed:
            return
        self._bump("events_seen")
        try:
            self._queue.put_nowait(snapshot)
            self._bump("events_queued")
        except queue.Full:
            self._bump("events_dropped")
        except Exception:
            self._bump("events_dropped")

    def _make_snapshot(
        self,
        *,
        event_type: str,
        model: str | None,
        status_code: int | None,
        headers: Mapping[str, str] | None,
        body: bytes | None,
        error_type: str | None,
        error_message: str | None,
        routing_class: str | None,
        routing_reason: str | None,
        retryable: bool | None,
        duration_ms: float | None,
        correlation: Mapping[str, Any] | None,
    ) -> ProviderResponseSnapshot:
        safe_headers = safe_response_headers(headers or {})
        original_bytes = len(body) if body is not None else 0
        bounded_body = body[: self.max_event_bytes] if body is not None else None
        merged_correlation = {**self.correlation, **dict(correlation or {})}
        return ProviderResponseSnapshot(
            event_type=event_type,
            provider=self.provider,
            model=model,
            status_code=status_code,
            headers=safe_headers,
            body=bounded_body,
            body_sha256=hashlib.sha256(body).hexdigest() if body is not None else None,
            body_original_bytes=original_bytes,
            body_truncated=bool(body is not None and len(bounded_body) < original_bytes),
            error_type=error_type,
            error_message=error_message,
            routing_class=routing_class,
            routing_reason=routing_reason,
            retryable=retryable,
            retry_after_ms=_retry_after_ms(safe_headers),
            duration_ms=duration_ms,
            observed_at=_now(),
            correlation=merged_correlation,
        )

    def observe_provider_response(
        self,
        *,
        model: str | None,
        status_code: int,
        headers: Mapping[str, str],
        body: bytes | None,
        routing_class: str | None,
        routing_reason: str | None,
        retryable: bool | None,
        duration_ms: float | None,
        correlation: Mapping[str, Any],
    ) -> None:
        try:
            if self.mode == "off":
                return
            if status_code < 400 and not self.capture_success_metadata:
                return
            self._enqueue(
                self._make_snapshot(
                    event_type="provider_response",
                    model=model,
                    status_code=status_code,
                    headers=headers,
                    body=body if status_code >= 400 else None,
                    error_type=None,
                    error_message=None,
                    routing_class=routing_class,
                    routing_reason=routing_reason,
                    retryable=retryable,
                    duration_ms=duration_ms,
                    correlation=correlation,
                )
            )
        except Exception:
            self._bump("events_dropped")

    def observe_transport_error(
        self,
        *,
        model: str | None,
        error: BaseException,
        routing_class: str | None,
        routing_reason: str | None,
        retryable: bool | None,
        duration_ms: float | None,
        correlation: Mapping[str, Any],
    ) -> None:
        if not self.capture_transport_errors:
            return
        try:
            self._enqueue(
                self._make_snapshot(
                    event_type="upstream_transport_error",
                    model=model,
                    status_code=None,
                    headers=None,
                    body=None,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    routing_class=routing_class,
                    routing_reason=routing_reason,
                    retryable=retryable,
                    duration_ms=duration_ms,
                    correlation=correlation,
                )
            )
        except Exception:
            self._bump("events_dropped")

    def observe_gateway_error(
        self,
        *,
        model: str | None,
        error: BaseException,
        duration_ms: float | None,
        correlation: Mapping[str, Any],
    ) -> None:
        if not self.capture_gateway_internal_errors:
            return
        try:
            self._enqueue(
                self._make_snapshot(
                    event_type="gateway_internal_error",
                    model=model,
                    status_code=None,
                    headers=None,
                    body=None,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    routing_class="container",
                    routing_reason="benchmark_gateway_error",
                    retryable=False,
                    duration_ms=duration_ms,
                    correlation=correlation,
                )
            )
        except Exception:
            self._bump("events_dropped")

    @staticmethod
    def _raw_payload(snapshot: ProviderResponseSnapshot) -> dict[str, Any] | None:
        if snapshot.body is None:
            return None
        content_type = snapshot.headers.get("content-type", "").lower()
        if "json" in content_type:
            try:
                decoded: Any = json.loads(
                    snapshot.body.decode("utf-8", errors="replace")
                )
            except json.JSONDecodeError:
                decoded = None
            value = (
                {
                    "content_type": content_type or None,
                    "body_json": decoded,
                }
                if decoded is not None
                else {
                    "content_type": content_type or None,
                    "body_text": snapshot.body.decode("utf-8", errors="replace"),
                }
            )
        elif content_type.startswith("text/"):
            value = {
                "content_type": content_type or None,
                "body_text": snapshot.body.decode("utf-8", errors="replace"),
            }
        else:
            value = {
                "content_type": content_type or None,
                "binary_body_omitted": True,
            }
        value.update(
            {
                "body_sha256": snapshot.body_sha256,
                "original_bytes": snapshot.body_original_bytes,
                "truncated": snapshot.body_truncated,
            }
        )
        return value

    def _projection(self, snapshot: ProviderResponseSnapshot) -> DiagnosticProjection:
        if self.mode == "metadata" or snapshot.event_type != "provider_response":
            return DiagnosticProjection(normalized={}, provider_payload={})
        try:
            projection = self._handler.project(snapshot)
        except Exception as exc:
            self._bump("handler_failures")
            self._write_handler_failure(snapshot, exc)
            projection = self._fallback.project(snapshot)
        if self.mode == "raw":
            return DiagnosticProjection(
                normalized=projection.normalized,
                provider_payload=projection.provider_payload,
                raw_payload=self._raw_payload(snapshot),
            )
        return projection

    def _base_event(
        self,
        snapshot: ProviderResponseSnapshot,
        projection: DiagnosticProjection,
    ) -> dict[str, Any]:
        normalized = {
            "provider": snapshot.provider,
            "model": snapshot.model,
            "outcome": "error" if snapshot.event_type != "provider_response" or (
                snapshot.status_code is not None and snapshot.status_code >= 400
            ) else "success",
            "http_status": snapshot.status_code,
            "routing_class": snapshot.routing_class,
            "routing_reason": snapshot.routing_reason,
            "retryable": snapshot.retryable,
            "retry_after_ms": snapshot.retry_after_ms,
            "duration_ms": snapshot.duration_ms,
            "error_type": snapshot.error_type,
            "error_message": snapshot.error_message,
            **dict(projection.normalized),
        }
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_type": snapshot.event_type,
            "timestamp": snapshot.observed_at,
            "correlation": dict(snapshot.correlation),
            "normalized": normalized,
            "provider": {snapshot.provider: dict(projection.provider_payload)},
            "diagnostics": {
                "handler": self.handler_id,
                "mode": self.mode,
                "operational_config_sha256": self.operational_config_sha256,
                "body_sha256": snapshot.body_sha256,
                "body_original_bytes": snapshot.body_original_bytes,
                "body_truncated": snapshot.body_truncated,
            },
        }
        if projection.raw_payload is not None:
            event["raw"] = dict(projection.raw_payload)
        redacted, paths = redact(event)
        redacted["diagnostics"]["redacted_fields"] = paths
        return redacted

    def _append(self, event: dict[str, Any]) -> None:
        if self._storage is None:
            self._bump("events_dropped")
            return
        try:
            status, size, truncated = self._storage.append(event)
        except Exception:
            self._bump("storage_failures")
            self._bump("events_dropped")
            return
        if status == "written":
            self._bump("events_written")
            self._bump("bytes_written", size)
            if truncated:
                self._bump("events_truncated")
        else:
            self._bump("events_dropped")
            if status == "event_too_large":
                self._bump("events_truncated")

    def _write_handler_failure(
        self, snapshot: ProviderResponseSnapshot, error: BaseException
    ) -> None:
        event, _ = redact(
            {
                "schema_version": SCHEMA_VERSION,
                "event_type": "diagnostic_handler_failure",
                "timestamp": _now(),
                "correlation": dict(snapshot.correlation),
                "normalized": {
                    "provider": snapshot.provider,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
                "provider": {},
                "diagnostics": {
                    "handler": self.handler_id,
                    "fallback": GENERIC_HANDLER_ID,
                    "mode": self.mode,
                },
            }
        )
        self._append(event)

    def _worker(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                self._safe_write_manifest(closed=False)
                continue
            if item is _STOP:
                self._queue.task_done()
                break
            try:
                projection = self._projection(item)
                self._append(self._base_event(item, projection))
            except Exception:
                self._bump("events_dropped")
            finally:
                self._queue.task_done()
            self._safe_write_manifest(closed=False)
        self._safe_write_manifest(closed=True)

    def close(self, *, timeout: float = 2.0) -> None:
        if not self.enabled or self._closed:
            self._closed = True
            return
        self._closed = True
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            self._bump("events_dropped")
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(_STOP)
            except (queue.Empty, queue.Full):
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))
        self._safe_write_manifest(closed=bool(thread is None or not thread.is_alive()))
