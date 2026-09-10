"""Provider-specific extraction and durable capture of readable reasoning.

This module is mounted beside ``model_gateway.py`` in the gateway sidecar.  It
only extracts response fields whose provider wire semantics identify them as
readable reasoning/thinking content.  It never changes the response delivered
to a harness and never infers whether that harness parsed or exposed a field.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1

_PROVIDER_ALIASES = {
    "google": "gemini",
    "google-vertex": "gemini",
}

_EXTRACTOR_IDS = {
    "deepseek": [
        "openai-compatible-reasoning-content-v1",
        "deepseek-responses-reasoning-text-v1",
    ],
    "gemini": [
        "openai-compatible-reasoning-content-v1",
        "gemini-generate-content-thought-part-v1",
        "gemini-interactions-thought-summary-v1",
    ],
}


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalized_reasoning_provider(provider: str) -> str:
    value = str(provider or "").strip().lower()
    return _PROVIDER_ALIASES.get(value, value)


def reasoning_capture_capability(provider: str) -> dict[str, Any]:
    normalized = normalized_reasoning_provider(provider)
    extractors = list(_EXTRACTOR_IDS.get(normalized, []))
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": str(provider or "unknown"),
        "normalized_provider": normalized or "unknown",
        "support": "implemented" if extractors else "not_implemented",
        "extractor_ids": extractors,
        "captures": "provider_response_readable_reasoning_only",
        "agent_visibility": "not_inferred_or_modified",
    }


def _walk_dicts(value: Any, path: str = "$") -> Iterable[tuple[str, dict]]:
    if isinstance(value, dict):
        yield path, value
        for key, nested in value.items():
            yield from _walk_dicts(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk_dicts(nested, f"{path}[{index}]")


def _readable_values(value: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        if value:
            yield path, value
        return
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text:
            yield f"{path}.text", text
        return
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if isinstance(item, str) and item:
            yield item_path, item
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text:
                yield f"{item_path}.text", text


def _explicit_reasoning_fields(payload: Any) -> list[dict[str, str]]:
    """Extract explicit readable fields shared by compatible transports."""
    result: list[dict[str, str]] = []
    for path, item in _walk_dicts(payload):
        for key in ("reasoning_content", "reasoningContent"):
            if key not in item:
                continue
            for source_path, text in _readable_values(item[key], f"{path}.{key}"):
                result.append(
                    {
                        "extractor_id": "openai-compatible-reasoning-content-v1",
                        "source_path": source_path,
                        "text": text,
                    }
                )
    return result


def _deepseek_reasoning(payload: Any) -> list[dict[str, str]]:
    result = _explicit_reasoning_fields(payload)
    if not isinstance(payload, dict):
        return result

    event_type = str(payload.get("type") or "")
    if event_type == "response.reasoning_text.delta":
        delta = payload.get("delta")
        if isinstance(delta, str) and delta:
            result.append(
                {
                    "extractor_id": "deepseek-responses-reasoning-text-v1",
                    "source_path": "$.delta",
                    "text": delta,
                }
            )

    # A streamed ``response.completed`` event may contain a complete nested
    # response after all deltas. Only inspect a top-level non-stream response
    # here so faithful delta capture is not duplicated.
    output = payload.get("output")
    if isinstance(output, list):
        for output_index, item in enumerate(output):
            if not isinstance(item, dict) or item.get("type") != "reasoning":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_index, part in enumerate(content):
                if (
                    not isinstance(part, dict)
                    or part.get("type") != "reasoning_text"
                ):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    result.append(
                        {
                            "extractor_id": (
                                "deepseek-responses-reasoning-text-v1"
                            ),
                            "source_path": (
                                f"$.output[{output_index}].content"
                                f"[{content_index}].text"
                            ),
                            "text": text,
                        }
                    )
    return result


def _gemini_reasoning(payload: Any) -> list[dict[str, str]]:
    result = _explicit_reasoning_fields(payload)
    for path, item in _walk_dicts(payload):
        if item.get("thought") is True:
            text = item.get("text")
            if isinstance(text, str) and text:
                result.append(
                    {
                        "extractor_id": "gemini-generate-content-thought-part-v1",
                        "source_path": f"{path}.text",
                        "text": text,
                    }
                )

    if not isinstance(payload, dict):
        return result

    steps = payload.get("steps")
    if isinstance(steps, list):
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("type") != "thought":
                continue
            for source_path, text in _readable_values(
                step.get("summary"), f"$.steps[{step_index}].summary"
            ):
                result.append(
                    {
                        "extractor_id": "gemini-interactions-thought-summary-v1",
                        "source_path": source_path,
                        "text": text,
                    }
                )

    step = payload.get("step")
    if isinstance(step, dict) and step.get("type") == "thought":
        for source_path, text in _readable_values(
            step.get("summary"), "$.step.summary"
        ):
            result.append(
                {
                    "extractor_id": "gemini-interactions-thought-summary-v1",
                    "source_path": source_path,
                    "text": text,
                }
            )

    delta = payload.get("delta")
    if isinstance(delta, dict) and delta.get("type") == "thought_summary":
        for source_path, text in _readable_values(
            delta.get("content"), "$.delta.content"
        ):
            result.append(
                {
                    "extractor_id": "gemini-interactions-thought-summary-v1",
                    "source_path": source_path,
                    "text": text,
                }
            )
    return result


_PROVIDER_EXTRACTORS = {
    "deepseek": _deepseek_reasoning,
    "gemini": _gemini_reasoning,
}


def extract_reasoning_fragments(provider: str, payload: Any) -> list[dict[str, str]]:
    """Return exact readable fragments and their response JSON locations."""
    normalized = normalized_reasoning_provider(provider)
    extractor = _PROVIDER_EXTRACTORS.get(normalized)
    if extractor is None:
        return []
    candidates = extractor(payload)

    # Extractors can overlap on compatibility payloads. Preserve the first
    # semantic classification while removing exact path/text duplicates.
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        identity = (candidate["source_path"], candidate["text"])
        if identity in seen:
            continue
        seen.add(identity)
        result.append(candidate)
    return result


class ProviderReasoningRecorder:
    """Append reasoning fragments and maintain a content-free health record."""

    def __init__(
        self,
        provider: str,
        records_path: str | Path | None,
        status_path: str | Path | None,
    ):
        self.capability = reasoning_capture_capability(provider)
        self.records_path = Path(records_path) if records_path else None
        self.status_path = Path(status_path) if status_path else None
        self._lock = threading.Lock()
        self._fragments = 0
        self._characters = 0
        self._utf8_bytes = 0
        self._boundaries = 0
        self._write_errors = 0
        self._capture_errors = 0
        self._last_error_type: str | None = None
        self._response_fragments: dict[str, tuple[int, int]] = {}
        with self._lock:
            self._write_status_locked()

    @property
    def enabled(self) -> bool:
        return (
            self.capability["support"] == "implemented"
            and self.records_path is not None
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict[str, Any]:
        return {
            **self.capability,
            "persistence": (
                "enabled"
                if self.enabled
                else "not_configured"
                if self.capability["support"] == "implemented"
                else "not_implemented"
            ),
            "records_file": self.records_path.name if self.records_path else None,
            "fragments_captured": self._fragments,
            "characters_captured": self._characters,
            "utf8_bytes_captured": self._utf8_bytes,
            "response_boundaries": self._boundaries,
            "responses_with_reasoning": len(self._response_fragments),
            "write_errors": self._write_errors,
            "capture_errors": self._capture_errors,
            "last_error_type": self._last_error_type,
            "updated_at": _now(),
        }

    def _record_write_error_locked(self, exc: BaseException) -> None:
        self._write_errors += 1
        self._last_error_type = type(exc).__name__

    def record_capture_error(self, exc: BaseException) -> dict[str, int]:
        """Record an extractor/observer failure without affecting delivery."""
        with self._lock:
            write_errors_before = self._write_errors
            self._capture_errors += 1
            self._last_error_type = type(exc).__name__
            self._write_status_locked()
            return {
                "capture_errors": 1,
                "write_errors": self._write_errors - write_errors_before,
            }

    def _write_status_locked(self) -> None:
        if self.status_path is None:
            return
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.parent.chmod(0o700)
            # AgentWorkspace pre-creates this host-owned file. Updating it in
            # place preserves ownership when the sidecar itself runs as root,
            # so the benchmark runner can later collect the 0600 artifact.
            self.status_path.write_text(
                json.dumps(self._status_locked(), ensure_ascii=False, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            self.status_path.chmod(0o600)
        except OSError as exc:
            self._record_write_error_locked(exc)

    def _append_locked(self, record: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            self.records_path.parent.mkdir(parents=True, exist_ok=True)
            self.records_path.parent.chmod(0o700)
            with self.records_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.records_path.chmod(0o600)
            return True
        except OSError as exc:
            self._record_write_error_locked(exc)
            return False

    @staticmethod
    def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "response_id",
            "logical_call_index",
            "physical_attempt",
            "model",
            "api_path",
            "streaming",
            "payload_sequence",
        }
        return {key: context.get(key) for key in allowed if key in context}

    def capture_payload(
        self, payload: Any, *, context: dict[str, Any]
    ) -> dict[str, int]:
        try:
            fragments = extract_reasoning_fragments(
                self.capability["normalized_provider"], payload
            )
        except Exception as exc:
            return self.record_capture_error(exc)
        written = 0
        characters = 0
        utf8_bytes = 0
        response_id = str(context.get("response_id") or "unknown")
        with self._lock:
            errors_before = self._write_errors
            for fragment in fragments:
                text = fragment["text"]
                encoded = text.encode("utf-8")
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "reasoning_fragment",
                    "captured_at": _now(),
                    "provider": self.capability["provider"],
                    "normalized_provider": self.capability["normalized_provider"],
                    **self._safe_context(context),
                    "extractor_id": fragment["extractor_id"],
                    "source_path": fragment["source_path"],
                    "text": text,
                    "text_characters": len(text),
                    "text_utf8_bytes": len(encoded),
                    "text_sha256": hashlib.sha256(encoded).hexdigest(),
                    "agent_visibility": "not_inferred_by_gateway",
                }
                if not self._append_locked(record):
                    continue
                written += 1
                characters += len(text)
                utf8_bytes += len(encoded)
            if written:
                self._fragments += written
                self._characters += characters
                self._utf8_bytes += utf8_bytes
                old_fragments, old_characters = self._response_fragments.get(
                    response_id, (0, 0)
                )
                self._response_fragments[response_id] = (
                    old_fragments + written,
                    old_characters + characters,
                )
            self._write_status_locked()
            return {
                "fragments": written,
                "characters": characters,
                "utf8_bytes": utf8_bytes,
                "write_errors": self._write_errors - errors_before,
            }

    def record_boundary(
        self,
        *,
        context: dict[str, Any],
        response_complete: bool,
        downstream_state: str,
    ) -> dict[str, int]:
        if self.capability["support"] != "implemented":
            return {"write_errors": 0}
        response_id = str(context.get("response_id") or "unknown")
        with self._lock:
            errors_before = self._write_errors
            fragments, characters = self._response_fragments.get(response_id, (0, 0))
            record = {
                "schema_version": SCHEMA_VERSION,
                "record_type": "response_boundary",
                "captured_at": _now(),
                "provider": self.capability["provider"],
                "normalized_provider": self.capability["normalized_provider"],
                **self._safe_context(context),
                "response_complete": bool(response_complete),
                "downstream_state": downstream_state,
                "reasoning_fragments": fragments,
                "reasoning_characters": characters,
                "agent_visibility": "not_inferred_by_gateway",
            }
            if self._append_locked(record):
                self._boundaries += 1
            self._write_status_locked()
            return {"write_errors": self._write_errors - errors_before}
