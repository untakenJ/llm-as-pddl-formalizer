"""Fixed-route model gateway: secret boundary, request guard, and ledger."""

from __future__ import annotations

import datetime
import hashlib
import http.client
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit


UPSTREAM_ORIGIN = os.environ["PDDL_GATEWAY_UPSTREAM_ORIGIN"].rstrip("/")
MAX_MODEL_CALLS = int(os.environ.get("PDDL_GATEWAY_MAX_MODEL_CALLS", "50"))
AUTH_MODE = os.environ.get("PDDL_GATEWAY_AUTH_MODE", "bearer")
API_KEY = os.environ.get("PDDL_GATEWAY_API_KEY", "")
LISTEN_PORT = int(os.environ.get("PDDL_GATEWAY_PORT", "8766"))
ALLOWED_MODELS = frozenset(json.loads(os.environ.get("PDDL_GATEWAY_ALLOWED_MODELS", "[]")))
ALLOWED_PATH_PREFIXES = tuple(
    json.loads(os.environ.get("PDDL_GATEWAY_ALLOWED_PATH_PREFIXES", "[]"))
)

_origin = urlsplit(UPSTREAM_ORIGIN)
if _origin.scheme not in {"http", "https"} or not _origin.hostname:
    raise SystemExit("PDDL_GATEWAY_UPSTREAM_ORIGIN must be an HTTP(S) origin")
if not API_KEY:
    raise SystemExit("PDDL_GATEWAY_API_KEY is required")
if AUTH_MODE not in {"bearer", "x_api_key", "x_goog_api_key"}:
    raise SystemExit(f"unsupported gateway auth mode: {AUTH_MODE}")
if not ALLOWED_MODELS or not ALLOWED_PATH_PREFIXES:
    raise SystemExit("allowed model and path lists must be non-empty")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class State:
    lock = threading.Lock()
    request_attempts = 0
    budget_consumed = 0
    rejected_calls = 0
    forwarded_calls = 0
    ledger: list[dict] = []


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
            value = {
                "model_calls": State.budget_consumed,
                "request_attempts": State.request_attempts,
                "forwarded_calls": State.forwarded_calls,
                "rejected_calls": State.rejected_calls,
                "max_model_calls": MAX_MODEL_CALLS,
                "remaining_calls": max(0, MAX_MODEL_CALLS - State.budget_consumed),
            }
            if include_ledger:
                value["ledger"] = list(State.ledger)
        return value

    def _forward(self, *, count_attempt: bool) -> None:
        started = time.monotonic()
        parsed_path = urlsplit(self.path).path
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else None
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
            elif count_attempt and State.budget_consumed >= MAX_MODEL_CALLS:
                rejection = "model_call_limit"
                rejection_status = 429
            elif count_attempt:
                # Reserve the slot before forwarding so concurrent requests
                # cannot exceed the guard.
                State.budget_consumed += 1
            if rejection:
                State.rejected_calls += 1
                ledger["rejection"] = rejection
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

        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower()
            not in {
                "host", "content-length", "connection", "proxy-connection",
                "authorization", "x-api-key", "x-goog-api-key",
            }
        }
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
        connection = connection_cls(_origin.hostname, port, timeout=600)
        response_started = False
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            upstream = connection.getresponse()
            ledger["forwarded"] = True
            ledger["status"] = upstream.status
            with State.lock:
                State.forwarded_calls += 1
            self.send_response(upstream.status, upstream.reason)
            response_started = True
            for name, value in upstream.getheaders():
                if name.lower() in {
                    "transfer-encoding", "connection", "keep-alive", "content-length"
                }:
                    continue
                self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = upstream.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception as exc:
            ledger["status"] = 502
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
            ledger["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
            with State.lock:
                State.ledger.append(ledger)
            connection.close()
            self.close_connection = True

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
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), GatewayHandler).serve_forever()
