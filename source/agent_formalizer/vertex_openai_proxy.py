"""Loopback-only auth shim for Vertex's OpenAI-compatible endpoint.

Some harnesses always emit ``Authorization: Bearer`` while Google Cloud API
keys must be sent as ``x-goog-api-key``. This process runs inside the disposable
benchmark container, strips that incompatible header, and streams the request
to the project-qualified Vertex endpoint. The key is read only from the
container environment and is never written to config or logs.
"""

from __future__ import annotations

import http.server
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8765


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required environment variable {name}")
    return value


API_KEY = _required("PDDL_BENCHMARK_API_KEY")
PROJECT = _required("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
UPSTREAM_ORIGIN = os.environ.get(
    "GOOGLE_VERTEX_BASE_URL", "https://aiplatform.googleapis.com"
).rstrip("/")

_origin = urllib.parse.urlparse(UPSTREAM_ORIGIN)
if _origin.scheme != "https" or not (
    _origin.hostname == "aiplatform.googleapis.com"
    or (_origin.hostname or "").endswith("-aiplatform.googleapis.com")
):
    raise RuntimeError("GOOGLE_VERTEX_BASE_URL must be an official HTTPS Vertex origin")

ALLOWED_PREFIX = (
    f"/v1/projects/{urllib.parse.quote(PROJECT, safe='-._~')}"
    f"/locations/{urllib.parse.quote(LOCATION, safe='-._~')}/endpoints/openapi"
)

_REQUEST_HEADER_BLOCKLIST = {
    "authorization",
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "proxy-connection",
    "transfer-encoding",
}
_RESPONSE_HEADER_BLOCKLIST = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "transfer-encoding",
    "upgrade",
}


class VertexProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, _format: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        self._forward()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        self._forward()

    def _forward(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if not (
            parsed.path == ALLOWED_PREFIX
            or parsed.path.startswith(f"{ALLOWED_PREFIX}/")
        ):
            self.send_error(404, "path outside the configured Vertex endpoint")
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in _REQUEST_HEADER_BLOCKLIST
        }
        headers["x-goog-api-key"] = API_KEY

        request = urllib.request.Request(
            f"{UPSTREAM_ORIGIN}{self.path}",
            data=body,
            headers=headers,
            method=self.command,
        )
        try:
            upstream = urllib.request.urlopen(request, timeout=600)
        except urllib.error.HTTPError as exc:
            upstream = exc
        except Exception as exc:
            self.send_error(502, f"Vertex request failed: {type(exc).__name__}")
            return

        try:
            self.send_response(upstream.status)
            for name, value in upstream.headers.items():
                if name.lower() not in _RESPONSE_HEADER_BLOCKLIST:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()
            self.close_connection = True


def main() -> None:
    server = http.server.ThreadingHTTPServer(
        (LISTEN_HOST, LISTEN_PORT), VertexProxyHandler
    )
    server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"vertex proxy startup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
