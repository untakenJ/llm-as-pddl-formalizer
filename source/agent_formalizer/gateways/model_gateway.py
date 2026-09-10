"""Fixed-route model gateway with benchmark-owned action accounting.

One route/model-valid request admitted by the gateway is one logical model
call.  Invalid or budget-rejected requests are recorded separately but do not
spend that counter.  Every structured tool invocation delivered in a
successful model response is one tool call.
``action_steps`` is their sum.  Provider transport attempts made by this
process are physical attempts and never spend additional action budget.

Only errors classified by the versioned benchmark policy as
external/transient are retried here; request/model errors are returned
unchanged so the native harness can react to them.
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import http.client
import json
import os
import re
import signal
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Host subprocesses use a fixed environment without PYTHONPATH. Flat sidecar
# mounts retain the sibling-module imports below and need no repository tree.
if not __package__:
    package_dir = Path(__file__).resolve().parent.parent
    if (package_dir / "__init__.py").is_file():
        sys.path.insert(0, str(package_dir.parent))

try:
    from agent_formalizer.external_calls import Action, Decision, RetryController, RetryPolicy
    from agent_formalizer.external_calls.model import classify_response, retryable_transport, structured_error_codes
    from agent_formalizer.external_calls.control import ToolControl, NativeDeadlineExpired
    from agent_formalizer.external_calls.checkpoint import RequestCheckpoint
    from agent_formalizer.external_calls import ExternalCallInvalid
except ModuleNotFoundError:  # standalone sidecar mount
    from external_calls import Action, Decision, RetryController, RetryPolicy
    from external_calls.model import classify_response, retryable_transport, structured_error_codes
    from external_calls.control import ToolControl, NativeDeadlineExpired
    from external_calls.checkpoint import RequestCheckpoint
    from external_calls import ExternalCallInvalid

try:
    from agent_formalizer.results.provider_reasoning import ProviderReasoningRecorder
except ModuleNotFoundError:  # standalone sidecar mount
    from provider_reasoning import ProviderReasoningRecorder
try:
    from agent_formalizer.infra_diagnostics import InfraDiagnosticsRecorder
except ModuleNotFoundError:  # standalone sidecar mount
    from infra_diagnostics import InfraDiagnosticsRecorder


UPSTREAM_ORIGIN = os.environ["PDDL_GATEWAY_UPSTREAM_ORIGIN"].rstrip("/")
MAX_MODEL_CALLS = int(os.environ.get("PDDL_GATEWAY_MAX_MODEL_CALLS", "50"))
MAX_ACTION_STEPS = int(os.environ.get("PDDL_GATEWAY_MAX_ACTION_STEPS", "200"))
AUTH_MODE = os.environ.get("PDDL_GATEWAY_AUTH_MODE", "bearer")
_api_key_file = os.environ.get("PDDL_GATEWAY_API_KEY_FILE")
if _api_key_file:
    try:
        API_KEY = Path(_api_key_file).read_text()
    except OSError as exc:
        raise SystemExit(f"cannot read gateway API key file: {exc}") from exc
else:
    # Backward-compatible for direct gateway tests and non-Docker embedding.
    API_KEY = os.environ.get("PDDL_GATEWAY_API_KEY", "")
os.environ.pop("PDDL_GATEWAY_API_KEY", None)
LISTEN_PORT = int(os.environ.get("PDDL_GATEWAY_PORT", "8766"))
LISTEN_HOST = os.environ.get("PDDL_GATEWAY_LISTEN_HOST", "0.0.0.0")
ALLOWED_MODELS = frozenset(json.loads(os.environ.get("PDDL_GATEWAY_ALLOWED_MODELS", "[]")))
ALLOWED_PATH_PREFIXES = tuple(
    json.loads(os.environ.get("PDDL_GATEWAY_ALLOWED_PATH_PREFIXES", "[]"))
)
MAX_TRANSIENT_RETRIES = int(
    os.environ.get("PDDL_GATEWAY_MAX_TRANSIENT_RETRIES", "5")
)
TRANSIENT_BACKOFF_SECONDS = tuple(
    float(value)
    for value in json.loads(
        os.environ.get(
            "PDDL_GATEWAY_TRANSIENT_BACKOFF_SECONDS", "[1, 2, 4, 8, 16]"
        )
    )
)
MAX_RETRY_AFTER_SECONDS = float(
    os.environ.get("PDDL_GATEWAY_MAX_RETRY_AFTER_SECONDS", "60")
)
RETRYABLE_HTTP_STATUSES = frozenset(
    int(value)
    for value in json.loads(
        os.environ.get(
            "PDDL_GATEWAY_RETRYABLE_HTTP_STATUSES",
            "[408, 429, 502, 503, 504, 520, 521, 522, 523, 524, 525, 529]",
        )
    )
)
CONTROL_FILE = os.environ.get("PDDL_GATEWAY_CONTROL_FILE")
BENCHMARK_CANCEL_FILE = os.environ.get("PDDL_GATEWAY_BENCHMARK_CANCEL_FILE")
LOGICAL_CONTROL_FILE = os.environ.get("PDDL_GATEWAY_LOGICAL_CONTROL_FILE")
EXTERNAL_CALL_TIMING = os.environ.get("PDDL_GATEWAY_EXTERNAL_CALL_TIMING", "logical-deadline-v1")
LOGICAL_CONTROL_LOCK = threading.Lock()
RESPONSE_DELIVERY = os.environ.get(
    "PDDL_GATEWAY_RESPONSE_DELIVERY", "buffered_atomic"
)
GATEWAY_PROVIDER = os.environ.get("PDDL_GATEWAY_PROVIDER", "unknown")
REASONING_PATH = os.environ.get("PDDL_GATEWAY_REASONING_PATH")
REASONING_STATUS_PATH = os.environ.get("PDDL_GATEWAY_REASONING_STATUS_PATH")
INFRA_DIAGNOSTICS_CONFIG = os.environ.get(
    "PDDL_GATEWAY_INFRA_DIAGNOSTICS_CONFIG"
)
STREAM_CHUNK_BYTES = int(os.environ.get("PDDL_GATEWAY_STREAM_CHUNK_BYTES", "16384"))
STREAM_EVENT_BUFFER_BYTES = int(
    os.environ.get("PDDL_GATEWAY_STREAM_EVENT_BUFFER_BYTES", str(1024 * 1024))
)
try:
    REQUEST_OVERRIDES = json.loads(
        os.environ.get("PDDL_GATEWAY_REQUEST_OVERRIDES", "{}")
    )
except json.JSONDecodeError as exc:
    raise SystemExit(f"invalid PDDL_GATEWAY_REQUEST_OVERRIDES: {exc}") from exc

_TRANSIENT_500_CODES = frozenset(
    {
        "internal_error",
        "overloaded",
        "server_error",
        "service_unavailable",
        "temporarily_unavailable",
    }
)
_TRANSIENT_STREAM_CODES = _TRANSIENT_500_CODES | frozenset(
    {"rate_limit", "rate_limit_error", "timeout", "upstream_timeout"}
)

_origin = urlsplit(UPSTREAM_ORIGIN)
if _origin.scheme not in {"http", "https"} or not _origin.hostname:
    raise SystemExit("PDDL_GATEWAY_UPSTREAM_ORIGIN must be an HTTP(S) origin")
if not API_KEY:
    raise SystemExit("gateway API key is required")
if AUTH_MODE not in {"bearer", "x_api_key", "x_goog_api_key"}:
    raise SystemExit(f"unsupported gateway auth mode: {AUTH_MODE}")
if not ALLOWED_MODELS or not ALLOWED_PATH_PREFIXES:
    raise SystemExit("allowed model and path lists must be non-empty")
if MAX_TRANSIENT_RETRIES < 0:
    raise SystemExit("PDDL_GATEWAY_MAX_TRANSIENT_RETRIES must be non-negative")
if MAX_MODEL_CALLS <= 0 or MAX_ACTION_STEPS <= 0:
    raise SystemExit("model-call and action-step limits must be positive")
if MAX_MODEL_CALLS > MAX_ACTION_STEPS:
    raise SystemExit("model-call limit cannot exceed action-step limit")
if not TRANSIENT_BACKOFF_SECONDS or any(
    value < 0 for value in TRANSIENT_BACKOFF_SECONDS
):
    raise SystemExit("transient backoff values must be a non-empty non-negative list")
if MAX_RETRY_AFTER_SECONDS < 0:
    raise SystemExit("PDDL_GATEWAY_MAX_RETRY_AFTER_SECONDS must be non-negative")
if not isinstance(REQUEST_OVERRIDES, dict):
    raise SystemExit("PDDL_GATEWAY_REQUEST_OVERRIDES must be a JSON object")
if set(REQUEST_OVERRIDES) - {"temperature"}:
    raise SystemExit("unsupported model gateway request override")
if "temperature" in REQUEST_OVERRIDES and (
    isinstance(REQUEST_OVERRIDES["temperature"], bool)
    or not isinstance(REQUEST_OVERRIDES["temperature"], (int, float))
    or not 0 < float(REQUEST_OVERRIDES["temperature"]) <= 2
):
    raise SystemExit("temperature request override must be in (0, 2]")
if RESPONSE_DELIVERY not in {"buffered_atomic", "native_streaming"}:
    raise SystemExit("unsupported PDDL_GATEWAY_RESPONSE_DELIVERY")
if STREAM_CHUNK_BYTES <= 0 or STREAM_EVENT_BUFFER_BYTES <= 0:
    raise SystemExit("stream chunk and event buffer sizes must be positive")


REASONING_RECORDER = ProviderReasoningRecorder(
    GATEWAY_PROVIDER,
    REASONING_PATH,
    REASONING_STATUS_PATH,
)
try:
    INFRA_DIAGNOSTICS = InfraDiagnosticsRecorder.from_config_path(
        INFRA_DIAGNOSTICS_CONFIG
    )
except ValueError as exc:
    raise SystemExit(f"invalid infrastructure diagnostics config: {exc}") from exc


def _apply_request_overrides(
    body: bytes | None,
    *,
    content_type: str,
    parsed_path: str,
) -> tuple[bytes | None, dict]:
    """Apply audited generation overrides to JSON request payloads.

    OpenAI-compatible endpoints accept ``temperature`` at the payload root.
    Native Gemini ``generateContent`` endpoints use
    ``generationConfig.temperature``.
    """
    if not REQUEST_OVERRIDES:
        return body, {}
    if body is None or "json" not in content_type.lower():
        raise ValueError("generation overrides require a JSON request body")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("generation overrides require valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("generation overrides require a JSON object")

    applied: dict = {}
    if "temperature" in REQUEST_OVERRIDES:
        temperature = float(REQUEST_OVERRIDES["temperature"])
        if re.search(r":(?:stream)?generateContent$", parsed_path, re.IGNORECASE):
            generation = payload.setdefault("generationConfig", {})
            if not isinstance(generation, dict):
                raise ValueError("generationConfig must be an object")
            generation["temperature"] = temperature
            applied["generationConfig.temperature"] = temperature
        else:
            payload["temperature"] = temperature
            applied["temperature"] = temperature
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        applied,
    )


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class State:
    lock = threading.Lock()
    request_attempts = 0
    model_calls = 0
    tool_calls = 0
    in_flight_requests = 0
    active_committed_streams = 0
    max_tool_batch_size = 0
    final_tool_batch_size = 0
    overshoot_causing_logical_call: int | None = None
    in_flight_at_threshold_crossing: int | None = None
    action_step_limit_reached = False
    rejected_calls = 0
    forwarded_calls = 0
    upstream_attempts = 0
    transient_retries = 0
    transient_events = 0
    active_infra_pauses = 0
    infra_pause_started_monotonic: float | None = None
    infra_pause_started_unix: float | None = None
    infra_pause_seconds = 0.0
    terminal_infra_error: dict | None = None
    ledger: list[dict] = []


def _pause_seconds_locked() -> float:
    value = State.infra_pause_seconds
    if State.infra_pause_started_monotonic is not None:
        value += time.monotonic() - State.infra_pause_started_monotonic
    return max(0.0, value)


def _control_value_locked() -> dict:
    return {
        "schema_version": 1,
        "updated_at": _now(),
        "pause_requested": State.active_infra_pauses > 0,
        "action_step_limit_reached": State.action_step_limit_reached,
        "pause_started_unix": State.infra_pause_started_unix,
        "infra_pause_seconds": round(_pause_seconds_locked(), 6),
        "terminal_infra_error": State.terminal_infra_error,
        "active_committed_streams": State.active_committed_streams,
    }


def _publish_control_locked() -> None:
    if not CONTROL_FILE:
        return
    path = Path(CONTROL_FILE)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(_control_value_locked(), sort_keys=True) + "\n")
        os.replace(temporary, path)
    except OSError:
        # The HTTP status endpoint remains a fallback evidence source.  A host
        # monitor that cannot read the control file treats that as infra error.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _begin_infra_pause() -> None:
    with State.lock:
        if State.active_infra_pauses == 0:
            State.infra_pause_started_monotonic = time.monotonic()
            State.infra_pause_started_unix = time.time()
        State.active_infra_pauses += 1
        _publish_control_locked()


def _end_infra_pause() -> None:
    with State.lock:
        if State.active_infra_pauses <= 0:
            return
        State.active_infra_pauses -= 1
        if State.active_infra_pauses == 0:
            if State.infra_pause_started_monotonic is not None:
                State.infra_pause_seconds += (
                    time.monotonic() - State.infra_pause_started_monotonic
                )
            State.infra_pause_started_monotonic = None
            State.infra_pause_started_unix = None
        _publish_control_locked()


def _set_terminal_infra_error(value: dict) -> None:
    with State.lock:
        if State.terminal_infra_error is None:
            State.terminal_infra_error = value
        _publish_control_locked()


def _structured_error_codes(body: bytes) -> set[str]:
    return structured_error_codes(body)


def _response_bytes_for_accounting(body: bytes, headers) -> bytes:
    encoding = (headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip":
        try:
            return gzip.decompress(body)
        except (OSError, EOFError):
            return b""
    return body


def _iter_structured_response_payloads(body: bytes, headers):
    """Yield JSON/SSE response payloads without retaining request content."""
    content = _response_bytes_for_accounting(body, headers)
    content_type = (headers.get("Content-Type") or "").lower()
    if "text/event-stream" in content_type:
        normalized = content.replace(b"\r\n", b"\n")
        for event in normalized.split(b"\n\n"):
            data_lines = [
                line[5:].lstrip(b" ")
                for line in event.split(b"\n")
                if line.startswith(b"data:")
            ]
            if not data_lines:
                continue
            data = b"\n".join(data_lines).strip()
            if not data or data == b"[DONE]":
                continue
            try:
                yield json.loads(data)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return
    try:
        yield json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return


def _reasoning_context(
    ledger: dict,
    *,
    physical_attempt: int,
    streaming: bool,
    payload_sequence: int | None = None,
) -> dict:
    response_id = (
        f"logical-{ledger.get('index') or 'uncounted'}-"
        f"physical-{physical_attempt}"
    )
    value = {
        "response_id": response_id,
        "logical_call_index": ledger.get("index"),
        "physical_attempt": physical_attempt,
        "model": ledger.get("model"),
        "api_path": ledger.get("path"),
        "streaming": streaming,
    }
    if payload_sequence is not None:
        value["payload_sequence"] = payload_sequence
    return value


def _merge_reasoning_report(ledger: dict, report: dict) -> None:
    ledger["reasoning_fragments_captured"] += int(report.get("fragments", 0) or 0)
    ledger["reasoning_characters_captured"] += int(
        report.get("characters", 0) or 0
    )
    ledger["reasoning_utf8_bytes_captured"] += int(
        report.get("utf8_bytes", 0) or 0
    )
    ledger["reasoning_capture_write_errors"] += int(
        report.get("write_errors", 0) or 0
    )
    ledger["reasoning_capture_errors"] += int(
        report.get("capture_errors", 0) or 0
    )


def _capture_buffered_reasoning(
    body: bytes,
    headers,
    ledger: dict,
    *,
    physical_attempt: int,
) -> dict:
    context = _reasoning_context(
        ledger,
        physical_attempt=physical_attempt,
        streaming=False,
    )
    try:
        for sequence, payload in enumerate(
            _iter_structured_response_payloads(body, headers), start=1
        ):
            report = REASONING_RECORDER.capture_payload(
                payload,
                context={**context, "payload_sequence": sequence},
            )
            _merge_reasoning_report(ledger, report)
    except Exception as exc:
        _merge_reasoning_report(
            ledger, REASONING_RECORDER.record_capture_error(exc)
        )
    return context


def _record_reasoning_boundary(
    ledger: dict,
    *,
    context: dict,
    response_complete: bool,
    downstream_state: str,
) -> None:
    try:
        report = REASONING_RECORDER.record_boundary(
            context=context,
            response_complete=response_complete,
            downstream_state=downstream_state,
        )
    except Exception as exc:
        report = REASONING_RECORDER.record_capture_error(exc)
    _merge_reasoning_report(ledger, report)


def _tool_call_keys_from_payload(payload: object) -> set[tuple]:
    """Return stable keys for common OpenAI, Anthropic, and Gemini tool calls."""
    keys: set[tuple] = set()
    if isinstance(payload, list):
        for item in payload:
            keys.update(_tool_call_keys_from_payload(item))
        return keys
    if not isinstance(payload, dict):
        return keys

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice_position, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            choice_index = choice.get("index", choice_position)
            for field in ("message", "delta"):
                message = choice.get(field)
                if not isinstance(message, dict):
                    continue
                calls = message.get("tool_calls")
                if isinstance(calls, list):
                    for call_position, call in enumerate(calls):
                        if not isinstance(call, dict):
                            continue
                        call_index = call.get("index", call_position)
                        keys.add(("openai-chat", choice_index, call_index))
                if isinstance(message.get("function_call"), dict):
                    keys.add(("openai-function", choice_index))

    output = payload.get("output")
    if isinstance(output, list):
        for position, item in enumerate(output):
            if not isinstance(item, dict):
                continue
            if item.get("type") in {
                "function_call",
                "custom_tool_call",
                "computer_call",
            }:
                keys.add(
                    (
                        "openai-response",
                        item.get("call_id") or item.get("id") or position,
                    )
                )

    content = payload.get("content")
    if isinstance(content, list):
        for position, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"tool_use", "server_tool_use"}:
                keys.add(
                    (
                        "anthropic",
                        block.get("id") or block.get("index") or position,
                    )
                )

    if payload.get("type") == "content_block_start":
        block = payload.get("content_block")
        if isinstance(block, dict) and block.get("type") in {
            "tool_use",
            "server_tool_use",
        }:
            keys.add(
                (
                    "anthropic",
                    block.get("id") or payload.get("index"),
                )
            )

    item = payload.get("item")
    if (
        isinstance(item, dict)
        and payload.get("type") in {
            "response.output_item.added",
            "response.output_item.done",
        }
        and item.get("type")
        in {"function_call", "custom_tool_call", "computer_call"}
    ):
        keys.add(
            (
                "openai-response",
                item.get("call_id") or item.get("id") or payload.get("output_index"),
            )
        )

    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate_position, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            candidate_index = candidate.get("index", candidate_position)
            candidate_content = candidate.get("content")
            if not isinstance(candidate_content, dict):
                continue
            parts = candidate_content.get("parts")
            if not isinstance(parts, list):
                continue
            for part_position, part in enumerate(parts):
                if not isinstance(part, dict):
                    continue
                call = part.get("functionCall") or part.get("function_call")
                if isinstance(call, dict):
                    keys.add(
                        (
                            "gemini",
                            candidate_index,
                            part_position,
                        )
                    )
    return keys


def _count_response_tool_calls(body: bytes, headers) -> int:
    """Count structured tool invocations in JSON or SSE model responses."""
    content = _response_bytes_for_accounting(body, headers)
    content_type = (headers.get("Content-Type") or "").lower()
    keys: set[tuple] = set()
    if "text/event-stream" in content_type:
        for line in content.splitlines():
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if not data or data == b"[DONE]":
                continue
            try:
                payload = json.loads(data)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            keys.update(_tool_call_keys_from_payload(payload))
        return len(keys)
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 0
    return len(_tool_call_keys_from_payload(payload))


class StreamObservationError(RuntimeError):
    """Incremental audit state could not remain bounded or well-formed."""


class DownstreamCancelled(ConnectionError):
    """The harness closed its response stream before provider completion."""


class StreamToolObserver:
    """Observe provider events without altering the forwarded byte stream."""

    def __init__(self, content_type: str, payload_observer=None):
        self.is_sse = "text/event-stream" in content_type.lower()
        self._buffer = bytearray()
        self.tool_call_keys: set[tuple] = set()
        self.events = 0
        self.transient_error_reason: str | None = None
        self.provider_usage: dict[str, int | float] = {}
        self._payload_observer = payload_observer

    @property
    def provisional_tool_calls(self) -> int:
        return len(self.tool_call_keys)

    def _observe_payload(self, payload: object) -> None:
        self.events += 1
        if self._payload_observer is not None:
            self._payload_observer(payload, self.events)
        self.tool_call_keys.update(_tool_call_keys_from_payload(payload))
        if not isinstance(payload, dict):
            return
        for usage_key in ("usage", "usageMetadata"):
            usage = payload.get(usage_key)
            if not isinstance(usage, dict):
                continue
            for name, value in usage.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self.provider_usage[f"{usage_key}.{name}"] = value
        event_type = str(payload.get("type") or "").lower()
        error_value = payload.get("error")
        directly_error_shaped = isinstance(error_value, (dict, str)) or (
            event_type in {"error", "response.error"}
        )
        if not directly_error_shaped:
            return
        codes = _structured_error_codes(
            json.dumps(payload, separators=(",", ":")).encode()
        )
        if codes & _TRANSIENT_STREAM_CODES:
            self.transient_error_reason = "upstream_structured_stream_error"

    def _observe_sse_event(self, event: bytes) -> None:
        data_lines = []
        for line in event.replace(b"\r\n", b"\n").split(b"\n"):
            if line.startswith(b"data:"):
                data_lines.append(line[5:].lstrip(b" "))
        if not data_lines:
            return
        data = b"\n".join(data_lines).strip()
        if not data or data == b"[DONE]":
            self.events += 1
            return
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Unknown provider event data is still a semantic event. It is
            # forwarded byte-for-byte and cannot contribute a structured call.
            self.events += 1
            return
        self._observe_payload(payload)

    def feed(self, chunk: bytes) -> int:
        """Return semantic events completed by this chunk."""
        before = self.events
        if not chunk:
            return 0
        if not self.is_sse:
            self._buffer.extend(chunk)
            if len(self._buffer) > STREAM_EVENT_BUFFER_BYTES:
                raise StreamObservationError("JSON response exceeds observer buffer")
            return 1

        self._buffer.extend(chunk)
        if len(self._buffer) > STREAM_EVENT_BUFFER_BYTES:
            raise StreamObservationError("SSE event exceeds observer buffer")
        while True:
            match = re.search(br"\r?\n\r?\n", self._buffer)
            if match is None:
                break
            end = match.end()
            event = bytes(self._buffer[: match.start()])
            del self._buffer[:end]
            self._observe_sse_event(event)
        return self.events - before

    def finish(self) -> None:
        if self.is_sse:
            if self._buffer.strip():
                self._observe_sse_event(bytes(self._buffer))
            self._buffer.clear()
            return
        try:
            payload = json.loads(self._buffer)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StreamObservationError(
                "successful JSON response ended with invalid JSON"
            ) from exc
        self._observe_payload(payload)
        self._buffer.clear()


def _benchmark_cancelled() -> bool:
    return bool(BENCHMARK_CANCEL_FILE and Path(BENCHMARK_CANCEL_FILE).is_file())


def _classify_upstream_response(status: int, body: bytes) -> tuple[str, str]:
    decision = classify_response(status, body, RETRYABLE_HTTP_STATUSES)
    route = "transparent_transient" if decision.action == Action.RETRY else "container"
    return route, decision.reason


def _is_retryable_transport_error(exc: BaseException) -> bool:
    return retryable_transport(exc)


def _retry_after_seconds(headers, retry_index: int) -> float:
    return _RETRY_POLICY.delay(retry_index, headers)


_RETRY_POLICY = RetryPolicy(
    MAX_TRANSIENT_RETRIES, TRANSIENT_BACKOFF_SECONDS, MAX_RETRY_AFTER_SECONDS,
)


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/__benchmark__/health":
            self._json({"status": "ok"})
            return
        if self.path == "/__benchmark__/status":
            self._json(self._status(include_ledger=False))
            return
        if self.path == "/__benchmark__/ledger":
            self._json(self._status(include_ledger=True))
            return
        self._forward(count_attempt=False)

    def do_POST(self):
        self._forward(count_attempt=True)

    def do_PUT(self):
        self._forward(count_attempt=True)

    def do_PATCH(self):
        self._forward(count_attempt=True)

    def do_DELETE(self):
        self._forward(count_attempt=True)

    def do_OPTIONS(self):
        self._forward(count_attempt=False)

    @staticmethod
    def _status(*, include_ledger: bool) -> dict:
        admitted_counted = False
        with State.lock:
            action_steps = State.model_calls + State.tool_calls
            value = {
                "model_calls": State.model_calls,
                "tool_calls": State.tool_calls,
                "action_steps": action_steps,
                "request_attempts": State.request_attempts,
                "forwarded_calls": State.forwarded_calls,
                "rejected_calls": State.rejected_calls,
                "upstream_attempts": State.upstream_attempts,
                "transient_retries": State.transient_retries,
                "transient_events": State.transient_events,
                "pause_requested": State.active_infra_pauses > 0,
                "infra_pause_seconds": round(_pause_seconds_locked(), 6),
                "terminal_infra_error": State.terminal_infra_error,
                "max_model_calls": MAX_MODEL_CALLS,
                "max_action_steps": MAX_ACTION_STEPS,
                "remaining_model_calls": max(
                    0, MAX_MODEL_CALLS - State.model_calls
                ),
                "remaining_action_steps": max(
                    0, MAX_ACTION_STEPS - action_steps
                ),
                "action_step_limit_reached": State.action_step_limit_reached,
                "streaming_mode": RESPONSE_DELIVERY,
                "action_step_admission_threshold": MAX_ACTION_STEPS,
                "final_action_steps": action_steps,
                "action_step_overshoot": max(0, action_steps - MAX_ACTION_STEPS),
                "max_tool_batch_size": State.max_tool_batch_size,
                "final_tool_batch_size": State.final_tool_batch_size,
                "overshoot_causing_logical_call": (
                    State.overshoot_causing_logical_call
                ),
                "in_flight_at_threshold_crossing": (
                    State.in_flight_at_threshold_crossing
                ),
                "in_flight_requests": State.in_flight_requests,
                "active_committed_streams": State.active_committed_streams,
                "reasoning_capture": REASONING_RECORDER.status(),
                "infra_diagnostics": INFRA_DIAGNOSTICS.status(),
                "transient_policy": {
                    "max_retries": MAX_TRANSIENT_RETRIES,
                    "backoff_seconds": list(TRANSIENT_BACKOFF_SECONDS),
                    "max_retry_after_seconds": MAX_RETRY_AFTER_SECONDS,
                    "retryable_http_statuses": sorted(RETRYABLE_HTTP_STATUSES),
                },
            }
            if include_ledger:
                value["ledger"] = list(State.ledger)
        return value

    def _forward(self, *, count_attempt: bool) -> None:
        started = time.monotonic()
        parsed_path = urlsplit(self.path).path
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else None
        incoming_body = body
        model = None
        if body and "json" in self.headers.get("content-type", "").lower():
            try:
                payload = json.loads(body)
                if isinstance(payload, dict) and isinstance(payload.get("model"), str):
                    model = payload["model"]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        if model is None:
            match = re.search(r"/models/([^/:?]+)", parsed_path)
            if match:
                model = unquote(match.group(1))
        try:
            body, applied_request_overrides = _apply_request_overrides(
                body,
                content_type=self.headers.get("content-type", ""),
                parsed_path=parsed_path,
            )
        except ValueError as exc:
            self._json(
                {
                    "error": {
                        "type": "benchmark_request_override_error",
                        "message": str(exc),
                    }
                },
                status=400,
            )
            return

        ledger = {
            "index": None,
            "timestamp": _now(),
            "method": self.command,
            "path": parsed_path,
            "model": model,
            "counted": count_attempt,
            "forwarded": False,
            "status": None,
            "rejection": None,
            "error_source": None,
            "routing_class": None,
            "routing_reason": None,
            "transient_retry_count": 0,
            "tool_calls": 0,
            "proposed_tool_calls": 0,
            "provisional_tool_calls": 0,
            "committed_tool_calls": 0,
            "partial_tool_calls_observed": False,
            "final_tool_batch_size": 0,
            "action_steps_after": None,
            "action_step_overshoot": 0,
            "streaming_mode": RESPONSE_DELIVERY,
            "response_headers_at": None,
            "first_upstream_body_at": None,
            "first_downstream_body_at": None,
            "last_upstream_body_at": None,
            "last_downstream_body_at": None,
            "upstream_bytes": 0,
            "downstream_bytes": 0,
            "upstream_events": 0,
            "downstream_events": 0,
            "stream_completed": False,
            "downstream_committed": False,
            "termination_initiator": None,
            "partial_response": False,
            "client_cancelled": False,
            "benchmark_cancelled": False,
            "ambiguous_stream_termination": False,
            "provider_usage_observed": {},
            "reasoning_capture_supported": (
                REASONING_RECORDER.capability["support"] == "implemented"
            ),
            "reasoning_fragments_captured": 0,
            "reasoning_characters_captured": 0,
            "reasoning_utf8_bytes_captured": 0,
            "reasoning_capture_write_errors": 0,
            "reasoning_capture_errors": 0,
            "upstream_attempts": [],
            "request_overrides_applied": applied_request_overrides,
            "incoming_request_body_sha256": (
                hashlib.sha256(incoming_body).hexdigest()
                if incoming_body is not None
                else None
            ),
            "request_body_sha256": (
                hashlib.sha256(body).hexdigest() if body is not None else None
            ),
        }
        with State.lock:
            if count_attempt:
                State.request_attempts += 1
                ledger["index"] = State.request_attempts

            rejection = None
            rejection_status = 403
            if not any(
                parsed_path == prefix.rstrip("/")
                or parsed_path.startswith(prefix.rstrip("/") + "/")
                for prefix in ALLOWED_PATH_PREFIXES
            ):
                rejection = "path_not_allowed"
            elif count_attempt and model is None:
                rejection = "model_missing"
            elif model is not None and model not in ALLOWED_MODELS:
                rejection = "model_not_allowed"
            elif count_attempt and RESPONSE_DELIVERY == "native_streaming":
                # v5 uses a soft complete-batch threshold. Model-call guard is
                # checked first, then committed action steps. Already admitted
                # concurrent requests are allowed to finish.
                if State.model_calls >= MAX_MODEL_CALLS:
                    rejection = "model_call_limit"
                    rejection_status = 429
                elif State.model_calls + State.tool_calls >= MAX_ACTION_STEPS:
                    rejection = "action_step_limit"
                    rejection_status = 429
                    State.action_step_limit_reached = True
                    _publish_control_locked()
                else:
                    State.model_calls += 1
                    State.in_flight_requests += 1
                    admitted_counted = True
                    ledger["action_steps_after"] = (
                        State.model_calls + State.tool_calls
                    )
            elif count_attempt and State.action_step_limit_reached:
                rejection = "action_step_limit"
                rejection_status = 429
            elif count_attempt and (
                State.model_calls + State.tool_calls >= MAX_ACTION_STEPS
            ):
                rejection = "action_step_limit"
                rejection_status = 429
                State.action_step_limit_reached = True
                _publish_control_locked()
            elif count_attempt and State.model_calls >= MAX_MODEL_CALLS:
                rejection = "model_call_limit"
                rejection_status = 429
            elif count_attempt:
                # Reserve the slot before forwarding so concurrent requests
                # cannot exceed the guard.
                State.model_calls += 1
                State.in_flight_requests += 1
                admitted_counted = True
                ledger["action_steps_after"] = (
                    State.model_calls + State.tool_calls
                )
            if rejection:
                State.rejected_calls += 1
                ledger["rejection"] = rejection
                ledger["error_source"] = "benchmark_gateway"
                ledger["status"] = rejection_status
                ledger["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
                State.ledger.append(ledger)

        if rejection:
            self._json(
                {
                    "error": {
                        "type": f"benchmark_{rejection}",
                        "message": f"Benchmark model gateway rejected request: {rejection}",
                    }
                },
                status=rejection_status,
            )
            return

        with State.lock:
            terminal = State.terminal_infra_error
        if terminal is not None:
            ledger["routing_class"] = "terminal_infrastructure"
            ledger["routing_reason"] = terminal.get("reason")
            ledger["error_source"] = "benchmark_gateway"
            ledger["status"] = 503
            ledger["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
            with State.lock:
                State.ledger.append(ledger)
            self._terminal_json(terminal)
            return

        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower()
            not in {
                "host", "content-length", "connection", "proxy-connection",
                "authorization", "x-api-key", "x-goog-api-key", "accept-encoding",
            }
        }
        # Accounting must see the structured JSON/SSE bytes.  Asking the
        # provider for identity encoding avoids silently missing tool calls in
        # an unsupported content encoding.
        headers["Accept-Encoding"] = "identity"
        if AUTH_MODE == "bearer":
            headers["Authorization"] = f"Bearer {API_KEY}"
        elif AUTH_MODE == "x_api_key":
            headers["x-api-key"] = API_KEY
        else:
            headers["x-goog-api-key"] = API_KEY

        port = _origin.port or (443 if _origin.scheme == "https" else 80)
        connection_cls = (
            http.client.HTTPSConnection
            if _origin.scheme == "https"
            else http.client.HTTPConnection
        )
        response_started = False
        pause_owned = False
        logical_pause_started: float | None = None
        logical_pause_seconds = 0.0
        logical_control = None
        logical_lock_owned = False
        physical_started = time.monotonic()
        checkpoint = None
        if LOGICAL_CONTROL_FILE and EXTERNAL_CALL_TIMING == "call-checkpoint-v1":
            ledger["checkpoint_events"] = []
            checkpoint = RequestCheckpoint(body, event=ledger["checkpoint_events"].append)

        def begin_owned_pause() -> None:
            nonlocal pause_owned, logical_pause_started
            if pause_owned:
                return
            _begin_infra_pause()
            pause_owned = True
            logical_pause_started = time.monotonic()
            if logical_control is not None:
                try:
                    logical_control.begin()
                finally:
                    ledger["timing_control_call_id"] = logical_control.state.get("call_id")

        def end_owned_pause() -> None:
            nonlocal pause_owned, logical_pause_started, logical_pause_seconds
            if not pause_owned:
                return
            charge = 0.0
            if logical_control is not None:
                charge = max(0.0, time.monotonic() - physical_started)
                ledger["external_call_timing"] = EXTERNAL_CALL_TIMING
                ledger["accepted_call_seconds"] = charge
                # Set before finishing: a native deadline may cancel delivery.
                pause_owned = False
                try:
                    receipt = logical_control.finish(charge)
                    ledger["external_call_timing_mode"] = receipt.get("timing_mode", "isolated_escrow")
                    charge = receipt.get("charged_seconds", charge)
                    if checkpoint is not None:
                        checkpoint.commit()
                except NativeDeadlineExpired as exc:
                    charge = exc.receipt.get("charged_seconds", charge)
                    raise
                finally:
                    ledger["charged_call_seconds"] = charge
                    _end_infra_pause()
                    if logical_pause_started is not None:
                        logical_pause_seconds += max(0.0, time.monotonic() - logical_pause_started - charge)
                        logical_pause_started = None
                    with State.lock:
                        State.infra_pause_seconds = max(0.0, State.infra_pause_seconds - charge)
                        _publish_control_locked()
                return
            _end_infra_pause()
            pause_owned = False
            if logical_pause_started is not None:
                logical_pause_seconds += max(0.0, time.monotonic() - logical_pause_started - charge)
                logical_pause_started = None
        try:
            if LOGICAL_CONTROL_FILE:
                if checkpoint is None:
                    if not LOGICAL_CONTROL_LOCK.acquire(blocking=False):
                        _set_terminal_infra_error({"reason": "external_call_stream_overlap", "source": EXTERNAL_CALL_TIMING})
                        return
                    logical_lock_owned = True
                logical_control = ToolControl(LOGICAL_CONTROL_FILE, cancelled=_benchmark_cancelled,
                                              independent=checkpoint is not None)
                begin_owned_pause()
            recovery = RetryController(_RETRY_POLICY)
            for upstream_index in range(1, _RETRY_POLICY.max_retries + 2):
                physical_started = time.monotonic()
                connection = connection_cls(_origin.hostname, port, timeout=600)
                upstream = None
                physical = {
                    "attempt": upstream_index,
                    "timestamp": _now(),
                    "status": None,
                    "classification": None,
                    "reason": None,
                    "retry_delay_seconds": None,
                }
                with State.lock:
                    State.upstream_attempts += 1
                try:
                    connection.request(
                        self.command, self.path, body=checkpoint.body if checkpoint else body, headers=headers
                    )
                    upstream = connection.getresponse()
                    physical["status"] = upstream.status

                    if upstream.status >= 400:
                        error_body = upstream.read()
                        route, reason = _classify_upstream_response(
                            upstream.status, error_body
                        )
                        physical["classification"] = route
                        physical["reason"] = reason
                        ledger["status"] = upstream.status
                        ledger["error_source"] = "upstream_provider"
                        ledger["routing_class"] = route
                        ledger["routing_reason"] = reason

                        INFRA_DIAGNOSTICS.observe_provider_response(
                            model=model,
                            status_code=upstream.status,
                            headers=dict(upstream.getheaders()),
                            body=error_body,
                            routing_class=route,
                            routing_reason=reason,
                            retryable=(route == "transparent_transient"),
                            duration_ms=round(
                                (time.monotonic() - physical_started) * 1000, 3
                            ),
                            correlation={
                                "logical_call_sequence": ledger["index"],
                                "physical_attempt_sequence": upstream_index,
                                "transient_retry_count": ledger[
                                    "transient_retry_count"
                                ],
                            },
                        )

                        if route == "terminal_infrastructure":
                            if not pause_owned:
                                begin_owned_pause()
                            terminal = {
                                "reason": reason,
                                "status": upstream.status,
                                "logical_request_index": ledger["index"],
                                "retry_count": ledger["transient_retry_count"],
                                "recorded_at": _now(),
                            }
                            _set_terminal_infra_error(terminal)
                            physical["duration_ms"] = round(
                                (time.monotonic() - physical_started) * 1000, 3
                            )
                            ledger["upstream_attempts"].append(physical)
                            response_started = True
                            self._terminal_json(terminal)
                            return

                        if route == "transparent_transient":
                            with State.lock:
                                State.transient_events += 1
                            retry_action, delay = recovery.decide(
                                Decision(Action.RETRY, reason), headers=upstream.headers,
                            )
                            if retry_action == Action.RETRY:
                                if checkpoint is not None:
                                    checkpoint.discard(reason)
                                    logical_control.publish(rollback_count=checkpoint.discarded)
                                if not pause_owned:
                                    begin_owned_pause()
                                ledger["transient_retry_count"] += 1
                                physical["retry_delay_seconds"] = delay
                                with State.lock:
                                    State.transient_retries += 1
                                physical["duration_ms"] = round(
                                    (time.monotonic() - physical_started) * 1000, 3
                                )
                                ledger["upstream_attempts"].append(physical)
                                time.sleep(delay)
                                continue

                            if not pause_owned:
                                begin_owned_pause()
                            terminal = {
                                "reason": "provider_transient_exhausted",
                                "last_error": reason,
                                "status": upstream.status,
                                "logical_request_index": ledger["index"],
                                "retry_count": ledger["transient_retry_count"],
                                "recorded_at": _now(),
                            }
                            ledger["routing_class"] = "terminal_infrastructure"
                            ledger["routing_reason"] = terminal["reason"]
                            _set_terminal_infra_error(terminal)
                            physical["duration_ms"] = round(
                                (time.monotonic() - physical_started) * 1000, 3
                            )
                            ledger["upstream_attempts"].append(physical)
                            response_started = True
                            self._terminal_json(terminal)
                            return

                        if pause_owned:
                            end_owned_pause()
                        ledger["forwarded"] = True
                        with State.lock:
                            State.forwarded_calls += 1
                        response_started = True
                        self._send_buffered_upstream(upstream, error_body)
                        physical["duration_ms"] = round(
                            (time.monotonic() - physical_started) * 1000, 3
                        )
                        ledger["upstream_attempts"].append(physical)
                        return

                    physical["classification"] = "container"
                    physical["reason"] = "upstream_response"
                    ledger["routing_class"] = "container"
                    ledger["routing_reason"] = "upstream_response"
                    ledger["status"] = upstream.status
                    INFRA_DIAGNOSTICS.observe_provider_response(
                        model=model,
                        status_code=upstream.status,
                        headers=dict(upstream.getheaders()),
                        body=None,
                        routing_class="container",
                        routing_reason="upstream_response",
                        retryable=False,
                        duration_ms=round(
                            (time.monotonic() - physical_started) * 1000, 3
                        ),
                        correlation={
                            "logical_call_sequence": ledger["index"],
                            "physical_attempt_sequence": upstream_index,
                            "transient_retry_count": ledger[
                                "transient_retry_count"
                            ],
                        },
                    )
                    if RESPONSE_DELIVERY == "native_streaming":
                        self._send_streaming_upstream(
                            upstream,
                            ledger,
                            count_attempt=count_attempt,
                            on_commit=end_owned_pause,
                            physical_attempt=upstream_index,
                        )
                        response_started = True
                        physical["duration_ms"] = round(
                            (time.monotonic() - physical_started) * 1000, 3
                        )
                        ledger["upstream_attempts"].append(physical)
                        return

                    response_body = upstream.read()
                    reasoning_context = _reasoning_context(
                        ledger,
                        physical_attempt=upstream_index,
                        streaming=False,
                    )
                    if count_attempt:
                        reasoning_context = _capture_buffered_reasoning(
                            response_body,
                            upstream.headers,
                            ledger,
                            physical_attempt=upstream_index,
                        )
                    proposed_tool_calls = _count_response_tool_calls(
                        response_body, upstream.headers
                    )
                    ledger["proposed_tool_calls"] = proposed_tool_calls
                    action_rejection = False
                    if count_attempt and proposed_tool_calls:
                        with State.lock:
                            projected = (
                                State.model_calls
                                + State.tool_calls
                                + proposed_tool_calls
                            )
                            if projected > MAX_ACTION_STEPS:
                                State.action_step_limit_reached = True
                                _publish_control_locked()
                                action_rejection = True
                            else:
                                State.tool_calls += proposed_tool_calls
                                ledger["tool_calls"] = proposed_tool_calls
                                ledger["action_steps_after"] = (
                                    State.model_calls + State.tool_calls
                                )
                    if action_rejection:
                        ledger["rejection"] = "action_step_limit"
                        ledger["error_source"] = "benchmark_gateway"
                        ledger["routing_class"] = None
                        ledger["routing_reason"] = None
                        ledger["status"] = 429
                        with State.lock:
                            State.rejected_calls += 1
                        if count_attempt:
                            _record_reasoning_boundary(
                                ledger,
                                context=reasoning_context,
                                response_complete=True,
                                downstream_state="not_delivered_action_budget",
                            )
                        response_started = True
                        self._json(
                            {
                                "error": {
                                    "type": "benchmark_action_step_limit",
                                    "message": (
                                        "Benchmark action-step budget cannot "
                                        "admit this tool-call batch."
                                    ),
                                }
                            },
                            status=429,
                        )
                        physical["duration_ms"] = round(
                            (time.monotonic() - physical_started) * 1000, 3
                        )
                        ledger["upstream_attempts"].append(physical)
                        return
                    if pause_owned:
                        end_owned_pause()
                    ledger["forwarded"] = True
                    with State.lock:
                        State.forwarded_calls += 1
                    response_started = True
                    buffered_forward_complete = False
                    try:
                        self._send_buffered_upstream(upstream, response_body)
                        buffered_forward_complete = True
                    finally:
                        if count_attempt:
                            _record_reasoning_boundary(
                                ledger,
                                context=reasoning_context,
                                response_complete=True,
                                downstream_state=(
                                    "forwarded_complete"
                                    if buffered_forward_complete
                                    else "forwarding_failed"
                                ),
                            )
                    physical["duration_ms"] = round(
                        (time.monotonic() - physical_started) * 1000, 3
                    )
                    ledger["upstream_attempts"].append(physical)
                    return
                except Exception as exc:
                    if isinstance(exc, (NativeDeadlineExpired, ExternalCallInvalid)):
                        raise
                    response_started = response_started or bool(
                        ledger["downstream_committed"]
                    )
                    physical["error_type"] = type(exc).__name__
                    ledger["error_source"] = "upstream_transport"
                    if isinstance(exc, DownstreamCancelled):
                        benchmark_cancelled = _benchmark_cancelled()
                        ledger["client_cancelled"] = not benchmark_cancelled
                        ledger["benchmark_cancelled"] = benchmark_cancelled
                        ledger["termination_initiator"] = (
                            "benchmark_deadline"
                            if benchmark_cancelled
                            else "downstream_client"
                        )
                        ledger["partial_response"] = bool(
                            ledger["downstream_committed"]
                        )
                        physical["classification"] = "container"
                        physical["reason"] = "downstream_cancelled"
                        physical["duration_ms"] = round(
                            (time.monotonic() - physical_started) * 1000, 3
                        )
                        ledger["upstream_attempts"].append(physical)
                        return
                    if RESPONSE_DELIVERY == "native_streaming" and response_started:
                        if _benchmark_cancelled():
                            # Direct upstream evidence raced a benchmark-owned
                            # deadline. Keep the native outcome and flag it for
                            # manual audit instead of result-selective retry.
                            ledger["benchmark_cancelled"] = True
                            ledger["ambiguous_stream_termination"] = True
                            ledger["termination_initiator"] = "ambiguous"
                            ledger["partial_response"] = True
                            physical["classification"] = "container"
                            physical["reason"] = "ambiguous_stream_termination"
                            physical["duration_ms"] = round(
                                (time.monotonic() - physical_started) * 1000, 3
                            )
                            ledger["upstream_attempts"].append(physical)
                            return
                        terminal = {
                            "reason": "post_commit_stream_failure",
                            "stream_error_type": type(exc).__name__,
                            "logical_request_index": ledger["index"],
                            "retry_count": ledger["transient_retry_count"],
                            "recorded_at": _now(),
                        }
                        ledger["status"] = None
                        ledger["routing_class"] = "terminal_infrastructure"
                        ledger["routing_reason"] = terminal["reason"]
                        ledger["termination_initiator"] = "upstream_or_gateway"
                        ledger["partial_response"] = True
                        physical["classification"] = "terminal_infrastructure"
                        physical["reason"] = terminal["reason"]
                        physical["duration_ms"] = round(
                            (time.monotonic() - physical_started) * 1000, 3
                        )
                        ledger["upstream_attempts"].append(physical)
                        INFRA_DIAGNOSTICS.observe_transport_error(
                            model=model,
                            error=exc,
                            routing_class="terminal_infrastructure",
                            routing_reason=terminal["reason"],
                            retryable=False,
                            duration_ms=physical["duration_ms"],
                            correlation={
                                "logical_call_sequence": ledger["index"],
                                "physical_attempt_sequence": upstream_index,
                                "transient_retry_count": ledger[
                                    "transient_retry_count"
                                ],
                            },
                        )
                        _set_terminal_infra_error(terminal)
                        return
                    safe_transport_retry = (
                        _is_retryable_transport_error(exc) and not response_started
                    )
                    physical["classification"] = (
                        "transparent_transient"
                        if safe_transport_retry
                        else "container"
                    )
                    physical["reason"] = (
                        "upstream_transport_error"
                        if safe_transport_retry
                        else (
                            "partial_response_transport_error"
                            if response_started
                            else "non_retryable_gateway_error"
                        )
                    )
                    physical["duration_ms"] = round(
                        (time.monotonic() - physical_started) * 1000, 3
                    )
                    ledger["upstream_attempts"].append(physical)
                    INFRA_DIAGNOSTICS.observe_transport_error(
                        model=model,
                        error=exc,
                        routing_class=physical["classification"],
                        routing_reason=physical["reason"],
                        retryable=safe_transport_retry,
                        duration_ms=physical["duration_ms"],
                        correlation={
                            "logical_call_sequence": ledger["index"],
                            "physical_attempt_sequence": upstream_index,
                            "transient_retry_count": ledger[
                                "transient_retry_count"
                            ],
                        },
                    )
                    if safe_transport_retry:
                        with State.lock:
                            State.transient_events += 1
                        retry_action, delay = recovery.decide(
                            Decision(Action.RETRY, "upstream_transport"),
                        )
                        if retry_action == Action.RETRY:
                            if checkpoint is not None:
                                checkpoint.discard("upstream_transport")
                                logical_control.publish(rollback_count=checkpoint.discarded)
                            if not pause_owned:
                                begin_owned_pause()
                            ledger["transient_retry_count"] += 1
                            physical["retry_delay_seconds"] = delay
                            with State.lock:
                                State.transient_retries += 1
                            time.sleep(delay)
                            continue
                        if not pause_owned:
                            begin_owned_pause()
                        terminal = {
                            "reason": "provider_transient_exhausted",
                            "last_error": "upstream_transport_error",
                            "status": None,
                            "logical_request_index": ledger["index"],
                            "retry_count": ledger["transient_retry_count"],
                            "recorded_at": _now(),
                        }
                        ledger["status"] = 503
                        ledger["routing_class"] = "terminal_infrastructure"
                        ledger["routing_reason"] = terminal["reason"]
                        _set_terminal_infra_error(terminal)
                        response_started = True
                        self._terminal_json(terminal)
                        return
                    raise
                finally:
                    connection.close()
        except NativeDeadlineExpired:
            ledger["native_deadline"] = True
            ledger["routing_class"] = "container"
            ledger["routing_reason"] = "native_deadline"
            ledger["termination_initiator"] = "native_deadline"
        except ExternalCallInvalid as exc:
            if exc.reason != "external_call_cancelled":
                _set_terminal_infra_error({"reason": exc.reason, "source": EXTERNAL_CALL_TIMING,
                                           "evidence": exc.evidence})
            ledger["routing_reason"] = exc.reason
        except Exception as exc:
            ledger["status"] = 502
            ledger["routing_class"] = "container"
            ledger["routing_reason"] = "benchmark_gateway_error"
            ledger["error_source"] = "benchmark_gateway"
            ledger["gateway_error_type"] = type(exc).__name__
            INFRA_DIAGNOSTICS.observe_gateway_error(
                model=model,
                error=exc,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                correlation={
                    "logical_call_sequence": ledger["index"],
                    "physical_attempt_sequence": None,
                    "transient_retry_count": ledger["transient_retry_count"],
                },
            )
            if LOGICAL_CONTROL_FILE:
                _set_terminal_infra_error({"reason": "external_call_control_failed", "source": EXTERNAL_CALL_TIMING})
            elif not response_started and not self.wfile.closed:
                try:
                    self._json(
                        {
                            "error": {
                                "type": "benchmark_gateway_error",
                                "message": str(exc),
                            }
                        },
                        status=502,
                    )
                except Exception:
                    pass
        finally:
            with State.lock:
                terminal_active = State.terminal_infra_error is not None
            if logical_control is not None and pause_owned:
                # Never turn incomplete recovery into a deliverable call in a
                # finally block. The monitor owns fail-closed termination.
                if ledger.get("client_cancelled") or ledger.get("benchmark_cancelled") or ledger.get("native_deadline"):
                    logical_control.publish(phase="cancelled", pause_requested=False)
                    _end_infra_pause()
                    pause_owned = False
                    ledger["cancelled_before_settlement"] = True
                elif not terminal_active and not State.action_step_limit_reached and not _benchmark_cancelled():
                    _set_terminal_infra_error({"reason": "external_call_control_failed", "source": EXTERNAL_CALL_TIMING})
            elif pause_owned and not terminal_active:
                end_owned_pause()
            live_logical_pause = (
                time.monotonic() - logical_pause_started
                if logical_pause_started is not None
                else 0.0
            )
            ledger["infra_pause_seconds"] = round(
                logical_pause_seconds + live_logical_pause, 6
            )
            ledger["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
            with State.lock:
                if admitted_counted:
                    State.in_flight_requests = max(0, State.in_flight_requests - 1)
                State.ledger.append(ledger)
            if logical_control is not None and ledger.get("native_deadline"):
                logical_control.publish(phase="native_done")
            if logical_lock_owned:
                LOGICAL_CONTROL_LOCK.release()
            self.close_connection = True

    def _commit_stream_tool_batch(
        self, ledger: dict, tool_calls: int, *, count_attempt: bool
    ) -> None:
        ledger["proposed_tool_calls"] = tool_calls
        ledger["provisional_tool_calls"] = tool_calls
        ledger["final_tool_batch_size"] = tool_calls
        if not count_attempt:
            return
        with State.lock:
            before = State.model_calls + State.tool_calls
            State.tool_calls += tool_calls
            State.max_tool_batch_size = max(State.max_tool_batch_size, tool_calls)
            State.final_tool_batch_size = tool_calls
            after = State.model_calls + State.tool_calls
            if (
                before < MAX_ACTION_STEPS <= after
                and State.in_flight_at_threshold_crossing is None
            ):
                State.in_flight_at_threshold_crossing = State.in_flight_requests
            if (
                after > MAX_ACTION_STEPS
                and State.overshoot_causing_logical_call is None
            ):
                State.overshoot_causing_logical_call = ledger["index"]
            ledger["tool_calls"] = tool_calls
            ledger["committed_tool_calls"] = tool_calls
            ledger["action_steps_after"] = after
            ledger["action_step_overshoot"] = max(0, after - MAX_ACTION_STEPS)

    def _send_streaming_upstream(
        self,
        upstream,
        ledger: dict,
        *,
        count_attempt: bool,
        on_commit,
        physical_attempt: int,
    ) -> None:
        """Tee a successful response with a one-semantic-event commit boundary."""
        content_type = upstream.headers.get("Content-Type") or ""
        reasoning_context = _reasoning_context(
            ledger,
            physical_attempt=physical_attempt,
            streaming=True,
        )

        def observe_reasoning(payload: object, payload_sequence: int) -> None:
            if not count_attempt:
                return
            try:
                report = REASONING_RECORDER.capture_payload(
                    payload,
                    context={
                        **reasoning_context,
                        "payload_sequence": payload_sequence,
                    },
                )
            except Exception as exc:
                report = REASONING_RECORDER.record_capture_error(exc)
            _merge_reasoning_report(ledger, report)

        observer = StreamToolObserver(content_type, observe_reasoning)
        pending = bytearray()
        committed = False

        def commit_downstream() -> None:
            nonlocal committed
            if committed:
                return
            if LOGICAL_CONTROL_FILE:
                on_commit()  # Settle TTFT and native deadlines BEFORE headers/body.
            self.send_response(upstream.status, upstream.reason)
            self._copy_upstream_headers(upstream, content_length=None)
            self.end_headers()
            ledger["response_headers_at"] = _now()
            ledger["downstream_committed"] = True
            ledger["forwarded"] = True
            committed = True
            with State.lock:
                State.forwarded_calls += 1
                State.active_committed_streams += 1
                _publish_control_locked()
            if not LOGICAL_CONTROL_FILE:
                on_commit()

        def write_downstream(chunk: bytes, semantic_events: int) -> None:
            if not chunk:
                return
            try:
                self.wfile.write(chunk)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
                raise DownstreamCancelled(str(exc)) from exc
            timestamp = _now()
            if ledger["first_downstream_body_at"] is None:
                ledger["first_downstream_body_at"] = timestamp
            ledger["last_downstream_body_at"] = timestamp
            ledger["downstream_bytes"] += len(chunk)
            ledger["downstream_events"] += semantic_events

        try:
            while True:
                if observer.is_sse:
                    # One provider line is the smallest useful SSE read. This
                    # avoids waiting to fill an arbitrary byte chunk when a
                    # complete sparse event is already available.
                    chunk = upstream.readline(STREAM_EVENT_BUFFER_BYTES + 1)
                else:
                    reader = getattr(upstream, "read1", None)
                    chunk = (
                        reader(STREAM_CHUNK_BYTES)
                        if reader is not None
                        else upstream.read(STREAM_CHUNK_BYTES)
                    )
                if not chunk:
                    remaining = getattr(upstream, "length", None)
                    if isinstance(remaining, int) and remaining > 0:
                        raise http.client.IncompleteRead(b"", remaining)
                    break
                timestamp = _now()
                if ledger["first_upstream_body_at"] is None:
                    ledger["first_upstream_body_at"] = timestamp
                ledger["last_upstream_body_at"] = timestamp
                ledger["upstream_bytes"] += len(chunk)
                events = observer.feed(chunk)
                ledger["upstream_events"] += events
                ledger["provisional_tool_calls"] = (
                    observer.provisional_tool_calls
                )
                ledger["partial_tool_calls_observed"] = bool(
                    observer.provisional_tool_calls
                )
                ledger["provider_usage_observed"] = dict(observer.provider_usage)
                if observer.transient_error_reason:
                    raise ConnectionError(observer.transient_error_reason)

                if not committed:
                    pending.extend(chunk)
                    if len(pending) > STREAM_EVENT_BUFFER_BYTES:
                        raise StreamObservationError(
                            "first semantic response event exceeds commit buffer"
                        )
                    # Non-SSE data is a semantic body chunk. SSE commits only
                    # after a complete data event, never on comments/heartbeats.
                    if events or (not observer.is_sse and pending):
                        commit_downstream()
                        write_downstream(bytes(pending), max(1, events))
                        pending.clear()
                else:
                    write_downstream(chunk, events)

            observer.finish()
            ledger["upstream_events"] = observer.events
            ledger["downstream_events"] = observer.events if committed else 0
            ledger["provisional_tool_calls"] = observer.provisional_tool_calls
            ledger["partial_tool_calls_observed"] = bool(
                observer.provisional_tool_calls
            )
            ledger["provider_usage_observed"] = dict(observer.provider_usage)
            if observer.transient_error_reason:
                raise ConnectionError(observer.transient_error_reason)
            if not committed:
                # A successful empty body is a complete container-visible
                # response. There is no event to retry or synthesize.
                commit_downstream()
                if pending:
                    write_downstream(bytes(pending), observer.events)
            ledger["stream_completed"] = True
            ledger["termination_initiator"] = "normal_completion"
            self._commit_stream_tool_batch(
                ledger,
                observer.provisional_tool_calls,
                count_attempt=count_attempt,
            )
        except DownstreamCancelled:
            raise
        except Exception:
            ledger["partial_response"] = committed
            raise
        finally:
            if count_attempt:
                _record_reasoning_boundary(
                    ledger,
                    context=reasoning_context,
                    response_complete=bool(ledger["stream_completed"]),
                    downstream_state=(
                        "forwarded_complete"
                        if ledger["stream_completed"] and committed
                        else "forwarded_partial"
                        if committed
                        else "not_delivered"
                    ),
                )
            if committed:
                with State.lock:
                    State.active_committed_streams = max(
                        0, State.active_committed_streams - 1
                    )
                    _publish_control_locked()

    def _copy_upstream_headers(self, upstream, *, content_length: int | None) -> None:
        for name, value in upstream.getheaders():
            if name.lower() in {
                "transfer-encoding", "connection", "keep-alive", "content-length"
            }:
                continue
            self.send_header(name, value)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.send_header("Connection", "close")

    def _send_buffered_upstream(self, upstream, body: bytes) -> None:
        self.send_response(upstream.status, upstream.reason)
        self._copy_upstream_headers(upstream, content_length=len(body))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _terminal_json(self, terminal: dict) -> None:
        if LOGICAL_CONTROL_FILE:
            # This condition uses acknowledged host-owned invalidation, not
            # a synthetic provider response or a timing-based delivery grace.
            self.close_connection = True
            return
        # Give the host control-file monitor a short window to freeze the agent
        # before a first-attempt terminal error could become visible inside the
        # container. Exhausted retries are already paused, so this is only a
        # small synchronization grace period for other terminal infra errors.
        if CONTROL_FILE:
            time.sleep(0.1)
        self._json(
            {
                "error": {
                    "type": "benchmark_provider_infrastructure_invalid",
                    "message": "Provider infrastructure prevented a valid model response.",
                    "reason": terminal.get("reason"),
                }
            },
            status=503,
        )

    def _json(self, value: dict, status: int = 200) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    if LOGICAL_CONTROL_FILE:
        ToolControl(LOGICAL_CONTROL_FILE)  # Fail startup if private control is unavailable.
    with State.lock:
        _publish_control_locked()
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), GatewayHandler)

    def _terminate(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        INFRA_DIAGNOSTICS.close(timeout=2.0)
