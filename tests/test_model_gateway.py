from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_formalizer.config import MODEL_GATEWAY_SCRIPT


class UpstreamHandler(BaseHTTPRequestHandler):
    calls = 0
    authorizations: list[str | None] = []

    def do_POST(self):
        type(self).calls += 1
        type(self).authorizations.append(self.headers.get("authorization"))
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length)
        payload = json.dumps({"path": self.path, "body": body.decode()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ModelGatewayTests(unittest.TestCase):
    def test_gateway_forwards_only_up_to_model_call_budget(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        UpstreamHandler.calls = 0
        UpstreamHandler.authorizations = []
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        env = {
            **os.environ,
            "PDDL_GATEWAY_UPSTREAM_ORIGIN": (
                f"http://127.0.0.1:{upstream.server_port}"
            ),
            "PDDL_GATEWAY_MAX_MODEL_CALLS": "2",
            "PDDL_GATEWAY_PORT": str(gateway_port),
            "PDDL_GATEWAY_API_KEY": "gateway-test-secret",
            "PDDL_GATEWAY_AUTH_MODE": "bearer",
            "PDDL_GATEWAY_ALLOWED_MODELS": json.dumps(["gpt-test"]),
            "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES": json.dumps(["/v1"]),
        }
        process = subprocess.Popen(
            [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        base = f"http://127.0.0.1:{gateway_port}"
        try:
            for _ in range(50):
                try:
                    urllib.request.urlopen(f"{base}/__benchmark__/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                self.fail(f"gateway failed to start: {process.stderr.read()}")

            for path, model in (
                ("/v1/chat/completions", "wrong-model"),
                ("/admin/delete", "gpt-test"),
            ):
                rejected = urllib.request.Request(
                    f"{base}{path}",
                    data=json.dumps({"model": model}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(rejected, timeout=5)
                self.assertEqual(caught.exception.code, 403)

            for index in range(2):
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps(
                        {"model": "gpt-test", "request": index}
                    ).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                response = json.loads(urllib.request.urlopen(request, timeout=5).read())
                self.assertEqual(response["path"], "/v1/chat/completions")

            request = urllib.request.Request(
                f"{base}/v1/chat/completions",
                data=json.dumps({"model": "gpt-test"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 429)

            status = json.loads(
                urllib.request.urlopen(f"{base}/__benchmark__/status", timeout=5).read()
            )
            self.assertEqual(status["model_calls"], 2)
            self.assertEqual(status["request_attempts"], 5)
            self.assertEqual(status["rejected_calls"], 3)
            self.assertEqual(UpstreamHandler.calls, 2)
            self.assertEqual(
                UpstreamHandler.authorizations,
                ["Bearer gateway-test-secret", "Bearer gateway-test-secret"],
            )
        finally:
            process.terminate()
            process.wait(timeout=10)
            if process.stderr:
                process.stderr.close()
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
