"""Small allowlist-only HTTP CONNECT proxy for controlled-web conditions."""

from __future__ import annotations

import http.client
import json
import os
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


PORT = int(os.environ.get("PDDL_WEB_GATEWAY_PORT", "8767"))
ALLOWLIST = tuple(
    item.lower().rstrip(".")
    for item in json.loads(os.environ.get("PDDL_WEB_GATEWAY_ALLOWLIST", "[]"))
)
if not ALLOWLIST:
    raise SystemExit("controlled-web proxy requires a non-empty allowlist")


def allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(
        host == rule
        or (rule.startswith("*.") and host.endswith(rule[1:]) and host != rule[2:])
        for rule in ALLOWLIST
    )


class State:
    lock = threading.Lock()
    allowed_requests = 0
    rejected_requests = 0


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/__benchmark__/health":
            self._json({"status": "ok"})
            return
        if self.path == "/__benchmark__/status":
            with State.lock:
                value = {
                    "allowlist": list(ALLOWLIST),
                    "allowed_requests": State.allowed_requests,
                    "rejected_requests": State.rejected_requests,
                }
            self._json(value)
            return
        self._http_forward()

    def do_POST(self):
        self._http_forward()

    def do_PUT(self):
        self._http_forward()

    def do_PATCH(self):
        self._http_forward()

    def do_DELETE(self):
        self._http_forward()

    def do_HEAD(self):
        self._http_forward()

    def do_CONNECT(self):
        host, sep, raw_port = self.path.rpartition(":")
        if not sep:
            host, raw_port = self.path, "443"
        if not allowed(host):
            self._reject(host)
            return
        try:
            upstream = socket.create_connection((host, int(raw_port)), timeout=30)
        except (OSError, ValueError):
            self.send_error(502, "allowlisted upstream unavailable")
            return
        with State.lock:
            State.allowed_requests += 1
        self.send_response(200, "Connection Established")
        self.end_headers()
        sockets = (self.connection, upstream)
        try:
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                if exceptional or not readable:
                    break
                for source in readable:
                    data = source.recv(64 * 1024)
                    if not data:
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)
        finally:
            upstream.close()

    def _http_forward(self) -> None:
        target = urlsplit(self.path)
        host = target.hostname or self.headers.get("host", "").split(":", 1)[0]
        if not host or not allowed(host):
            self._reject(host or "<missing>")
            return
        port = target.port or 80
        path = target.path or "/"
        if target.query:
            path += "?" + target.query
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in {"host", "connection", "proxy-connection"}
        }
        upstream = http.client.HTTPConnection(host, port, timeout=60)
        try:
            upstream.request(self.command, path, body=body, headers=headers)
            response = upstream.getresponse()
            with State.lock:
                State.allowed_requests += 1
            payload = response.read()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() not in {"connection", "transfer-encoding", "content-length"}:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except OSError:
            self.send_error(502, "allowlisted upstream unavailable")
        finally:
            upstream.close()
            self.close_connection = True

    def _reject(self, host: str) -> None:
        with State.lock:
            State.rejected_requests += 1
        self._json(
            {"error": "benchmark_web_host_not_allowed", "host": host}, status=403
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
    ThreadingHTTPServer(("0.0.0.0", PORT), Proxy).serve_forever()
