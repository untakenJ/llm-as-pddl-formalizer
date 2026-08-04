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
import errno
import gzip
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import threading
import time
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


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
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return set()
    codes: set[str] = set()

    def visit(item) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if key.lower() in {"code", "error_code", "reason", "type"} and isinstance(
                    nested, str
                ):
                    codes.add(nested.strip().lower())
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return codes


def _response_bytes_for_accounting(body: bytes, headers) -> bytes:
    encoding = (headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip":
        try:
            return gzip.decompress(body)
        except (OSError, EOFError):
            return b""
    return body


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
                    "anthropic-stream",
                    payload.get("index"),
                    block.get("id"),
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
                "openai-response-stream",
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
                            call.get("id") or call.get("name"),
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


def _classify_upstream_response(status: int, body: bytes) -> tuple[str, str]:
    """Return routing class and stable reason without inspecting model quality."""
    if status in RETRYABLE_HTTP_STATUSES:
        return "transparent_transient", f"upstream_http_{status}"
    # 500 is deliberately conditional: providers sometimes wrap deterministic
    # invalid-request errors in a 500 response.
    if status == 500 and _structured_error_codes(body) & _TRANSIENT_500_CODES:
        return "transparent_transient", "upstream_structured_internal_error"
    return "container", "upstream_response"


def _is_retryable_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return False
    return isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            socket.gaierror,
            socket.timeout,
            http.client.RemoteDisconnected,
            http.client.IncompleteRead,
            http.client.BadStatusLine,
            http.client.LineTooLong,
        ),
    ) or (
        isinstance(exc, ssl.SSLError)
        and "certificate verify failed" not in str(exc).lower()
    ) or (
        isinstance(exc, OSError)
        and exc.errno
        in {
            errno.ECONNABORTED,
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.ENETUNREACH,
            errno.EPIPE,
            errno.ETIMEDOUT,
        }
    )


def _retry_after_seconds(headers, retry_index: int) -> float:
    raw = headers.get("Retry-After") if headers is not None else None
    parsed: float | None = None
    if raw:
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            try:
                parsed = parsedate_to_datetime(raw).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                parsed = None
    if parsed is not None:
        return round(max(0.0, min(MAX_RETRY_AFTER_SECONDS, parsed)), 6)
    index = min(retry_index, len(TRANSIENT_BACKOFF_SECONDS) - 1)
    return TRANSIENT_BACKOFF_SECONDS[index]


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
            "action_steps_after": None,
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
            elif count_attempt and State.action_step_limit_reached:
                rejection = "action_step_limit"
                rejection_status = 429
            elif (
                count_attempt
                and State.model_calls + State.tool_calls >= MAX_ACTION_STEPS
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

        def begin_owned_pause() -> None:
            nonlocal pause_owned, logical_pause_started
            if pause_owned:
                return
            _begin_infra_pause()
            pause_owned = True
            logical_pause_started = time.monotonic()

        def end_owned_pause() -> None:
            nonlocal pause_owned, logical_pause_started, logical_pause_seconds
            if not pause_owned:
                return
            _end_infra_pause()
            pause_owned = False
            if logical_pause_started is not None:
                logical_pause_seconds += time.monotonic() - logical_pause_started
                logical_pause_started = None
        try:
            for upstream_index in range(1, MAX_TRANSIENT_RETRIES + 2):
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
                        self.command, self.path, body=body, headers=headers
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
                            if upstream_index <= MAX_TRANSIENT_RETRIES:
                                if not pause_owned:
                                    begin_owned_pause()
                                delay = _retry_after_seconds(
                                    upstream.headers,
                                    ledger["transient_retry_count"],
                                )
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
                    response_body = upstream.read()
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
                    self._send_buffered_upstream(upstream, response_body)
                    physical["duration_ms"] = round(
                        (time.monotonic() - physical_started) * 1000, 3
                    )
                    ledger["upstream_attempts"].append(physical)
                    return
                except Exception as exc:
                    physical["error_type"] = type(exc).__name__
                    ledger["error_source"] = "upstream_transport"
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
                    if safe_transport_retry:
                        with State.lock:
                            State.transient_events += 1
                        if upstream_index <= MAX_TRANSIENT_RETRIES:
                            if not pause_owned:
                                begin_owned_pause()
                            delay = _retry_after_seconds(
                                None, ledger["transient_retry_count"]
                            )
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
        except Exception as exc:
            ledger["status"] = 502
            ledger["routing_class"] = "container"
            ledger["routing_reason"] = "benchmark_gateway_error"
            ledger["error_source"] = "benchmark_gateway"
            ledger["gateway_error_type"] = type(exc).__name__
            if not response_started and not self.wfile.closed:
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
            if pause_owned and not terminal_active:
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
                State.ledger.append(ledger)
            self.close_connection = True

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
    with State.lock:
        _publish_control_locked()
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), GatewayHandler).serve_forever()
