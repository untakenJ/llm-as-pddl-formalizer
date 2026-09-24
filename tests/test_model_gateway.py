from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.configuration.config import MODEL_GATEWAY_SCRIPT
from agent_formalizer.workspace import AgentWorkspace


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


class ScriptedUpstreamHandler(BaseHTTPRequestHandler):
    responses: list[tuple[int, object | bytes, dict[str, str]]] = []
    calls = 0

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0") or 0)
        self.rfile.read(length)
        if type(self).responses:
            status, value, headers = type(self).responses.pop(0)
        else:
            status, value, headers = 500, {"error": "script exhausted"}, {}
        payload = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        if not any(name.lower() == "content-type" for name in headers):
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for name, header_value in headers.items():
            self.send_header(name, header_value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ModelGatewayTests(unittest.TestCase):
    def test_output_policy_real_http_cloud_and_vllm_retry_and_length(self):
        from agent_formalizer.configuration.model_capabilities import resolve_output_policy
        for dynamic, input_error in ((False, False), (True, False), (True, True)):
            with self.subTest(dynamic=dynamic, input_error=input_error):
                calls = []
                token_calls = []
                class BudgetUpstream(BaseHTTPRequestHandler):
                    def do_POST(self):
                        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                        status = 200
                        if self.path == '/tokenize':
                            token_calls.append(payload)
                            status = 429 if len(token_calls) == 1 else 200
                            result = {'count': 10000, 'max_model_len': 262144}
                            if input_error:
                                status, result = 400, {'error': {'type': 'invalid_request_error', 'message': 'invalid messages'}}
                        else:
                            calls.append(payload)
                            status = 503 if len(calls) == 1 else 200
                            result = {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}], 'forwarded': payload}
                        body = json.dumps(result).encode()
                        self.send_response(status)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    def log_message(self, *args):
                        pass
                try:
                    upstream = ThreadingHTTPServer(('127.0.0.1', 0), BudgetUpstream)
                except PermissionError as exc:
                    self.skipTest(f'sandbox forbids local sockets: {exc}')
                thread = threading.Thread(target=upstream.serve_forever, daemon=True)
                thread.start()
                process = None
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        key = Path(tmp) / 'key'
                        key.write_text('fake-key')
                        policy = resolve_output_policy('self-hosted/Qwen/Qwen3.8-27B' if dynamic else 'google-vertex/gemini-3.1-flash-lite', 'model_max')
                        policy['model'] = 'openai/gpt-test'  # Explicit mocked service, not a production alias.
                        port = free_port()
                        process = subprocess.Popen([os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                            env=self._gateway_env(upstream_port=upstream.server_port, gateway_port=port,
                                key_file=key, request_overrides={'output_token_policy': policy}),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                        base = f'http://127.0.0.1:{port}'
                        self._wait_for_gateway(base, process)
                        payload = {'model': 'gpt-test', 'messages': [{'role': 'user', 'content': 'unchanged'}], 'max_tokens': 8192}
                        req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
                        if input_error:
                            with self.assertRaises(urllib.error.HTTPError) as rejected:
                                urllib.request.urlopen(req, timeout=10)
                            self.assertEqual(rejected.exception.code, 400)
                            rejected.exception.close()
                            self.assertEqual(len(token_calls), 1)
                            self.assertEqual(calls, [])
                            with urllib.request.urlopen(base + '/__benchmark__/ledger', timeout=5) as response:
                                row = json.loads(response.read())['ledger'][0]
                            self.assertEqual(row['routing_class'], 'container')
                            self.assertEqual(row['routing_reason'], 'tokenizer_input_rejected')
                            continue
                        with urllib.request.urlopen(req, timeout=10) as response:
                            out = json.loads(response.read())
                        self.assertEqual(out['forwarded']['max_tokens'], 252144 if dynamic else 65536)
                        self.assertEqual(out['forwarded']['messages'], payload['messages'])
                        self.assertEqual(out['choices'][0]['finish_reason'], 'length')
                        self.assertEqual(len(calls), 2)  # 503 retried; length never resampled.
                        self.assertEqual(calls[0], calls[1])
                        self.assertEqual(len(token_calls), 2 if dynamic else 0)  # Count is reused after model 503.
                        with urllib.request.urlopen(base + '/__benchmark__/ledger', timeout=5) as response:
                            ledger = json.loads(response.read())['ledger']
                        self.assertEqual(len(ledger), 1)
                        self.assertEqual(ledger[0]['request_overrides_applied']['output_tokens']['effective_max_output_tokens'], 252144 if dynamic else 65536)
                        self.assertNotEqual(ledger[0]['incoming_request_body_sha256'], ledger[0]['request_body_sha256'])
                finally:
                    if process is not None:
                        process.terminate()
                        process.wait(timeout=10)
                        process.stderr.close()
                    upstream.shutdown()
                    upstream.server_close()
                    thread.join(timeout=5)

    def _gateway_env(
        self,
        *,
        upstream_port: int,
        gateway_port: int,
        key_file: Path,
        max_retries: int = 5,
        max_action_steps: int = 20,
        max_model_calls: int | None = None,
        request_overrides: dict | None = None,
        provider: str = "openai",
        reasoning_dir: Path | None = None,
    ) -> dict[str, str]:
        if max_model_calls is None:
            max_model_calls = min(10, max_action_steps)
        env = {
            **os.environ,
            "PDDL_GATEWAY_UPSTREAM_ORIGIN": f"http://127.0.0.1:{upstream_port}",
            "PDDL_GATEWAY_MAX_MODEL_CALLS": str(max_model_calls),
            "PDDL_GATEWAY_MAX_ACTION_STEPS": str(max_action_steps),
            "PDDL_GATEWAY_PORT": str(gateway_port),
            "PDDL_GATEWAY_API_KEY_FILE": str(key_file),
            "PDDL_GATEWAY_AUTH_MODE": "bearer",
            "PDDL_GATEWAY_PROVIDER": provider,
            "PDDL_GATEWAY_ALLOWED_MODELS": json.dumps(["gpt-test"]),
            "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES": json.dumps(["/v1"]),
            "PDDL_GATEWAY_MAX_TRANSIENT_RETRIES": str(max_retries),
            "PDDL_GATEWAY_TRANSIENT_BACKOFF_SECONDS": json.dumps(
                [0] * max(1, max_retries)
            ),
            "PDDL_GATEWAY_REQUEST_OVERRIDES": json.dumps(
                request_overrides or {}
            ),
        }
        if reasoning_dir is not None:
            env["PDDL_GATEWAY_REASONING_PATH"] = str(
                reasoning_dir / "provider_reasoning.jsonl"
            )
            env["PDDL_GATEWAY_REASONING_STATUS_PATH"] = str(
                reasoning_dir / "reasoning_capture_status.json"
            )
        env.pop("PDDL_GATEWAY_API_KEY", None)
        return env

    def test_gateway_applies_temperature_to_openai_and_native_gemini_requests(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        UpstreamHandler.calls = 0
        UpstreamHandler.authorizations = []
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    request_overrides={"temperature": 0.1},
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                requests = [
                    (
                        "/v1/chat/completions",
                        {"model": "gpt-test", "messages": []},
                        {"temperature": 0.1},
                    ),
                    (
                        "/v1/models/gpt-test:streamGenerateContent",
                        {"contents": [], "generationConfig": {"topP": 0.95}},
                        {
                            "generationConfig": {
                                "topP": 0.95,
                                "temperature": 0.1,
                            }
                        },
                    ),
                ]
                for path, payload, expected in requests:
                    request = urllib.request.Request(
                        f"{base}{path}",
                        data=json.dumps(payload).encode(),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    response = json.loads(
                        urllib.request.urlopen(request, timeout=5).read()
                    )
                    forwarded = json.loads(response["body"])
                    for key, value in expected.items():
                        self.assertEqual(forwarded[key], value)

                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(
                    status["ledger"][0]["request_overrides_applied"],
                    {"temperature": 0.1},
                )
                self.assertEqual(
                    status["ledger"][1]["request_overrides_applied"],
                    {"generationConfig.temperature": 0.1},
                )
                self.assertNotEqual(
                    status["ledger"][0]["incoming_request_body_sha256"],
                    status["ledger"][0]["request_body_sha256"],
                )
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def _wait_for_gateway(self, base: str, process: subprocess.Popen) -> None:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"{base}/__benchmark__/health", timeout=1)
                return
            except OSError:
                time.sleep(0.05)
        self.fail(f"gateway failed to start: {process.stderr.read()}")

    @staticmethod
    def _tool_response(count: int) -> dict:
        return {
            "id": "chatcmpl-tools",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"call-{index}",
                                "type": "function",
                                "function": {
                                    "name": "write_file",
                                    "arguments": "{}",
                                },
                            }
                            for index in range(count)
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

    @staticmethod
    def _gemini_tool_response(count: int) -> dict:
        return {
            "candidates": [
                {
                    "index": 0,
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": f"write_file_{index}",
                                    "args": {},
                                }
                            }
                            for index in range(count)
                        ],
                    },
                    "finishReason": "STOP",
                }
            ]
        }

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
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            env = {
                **os.environ,
                "PDDL_GATEWAY_UPSTREAM_ORIGIN": (
                    f"http://127.0.0.1:{upstream.server_port}"
                ),
                "PDDL_GATEWAY_MAX_MODEL_CALLS": "2",
                "PDDL_GATEWAY_MAX_ACTION_STEPS": "10",
                "PDDL_GATEWAY_PORT": str(gateway_port),
                "PDDL_GATEWAY_API_KEY_FILE": str(key_file),
                "PDDL_GATEWAY_AUTH_MODE": "bearer",
                "PDDL_GATEWAY_ALLOWED_MODELS": json.dumps(["gpt-test"]),
                "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES": json.dumps(["/v1"]),
            }
            env.pop("PDDL_GATEWAY_API_KEY", None)
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
                        urllib.request.urlopen(
                            f"{base}/__benchmark__/health", timeout=1
                        )
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
                    response = json.loads(
                        urllib.request.urlopen(request, timeout=5).read()
                    )
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
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["model_calls"], 2)
                self.assertEqual(status["tool_calls"], 0)
                self.assertEqual(status["action_steps"], 2)
                self.assertEqual(status["request_attempts"], 5)
                self.assertEqual(status["rejected_calls"], 3)
                self.assertEqual(status["upstream_attempts"], 2)
                self.assertEqual(status["transient_retries"], 0)
                self.assertEqual(status["ledger"][-1]["rejection"], "model_call_limit")
                self.assertEqual(
                    status["ledger"][-1]["error_source"], "benchmark_gateway"
                )
                self.assertIsNone(status["ledger"][-1]["routing_class"])
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

    def test_gateway_counts_model_and_tool_calls_as_action_steps(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        ScriptedUpstreamHandler.calls = 0
        ScriptedUpstreamHandler.responses = [
            (200, [self._gemini_tool_response(2)], {}),
        ]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    max_action_steps=3,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                response = json.loads(
                    urllib.request.urlopen(request, timeout=5).read()
                )
                self.assertEqual(
                    len(response[0]["candidates"][0]["content"]["parts"]), 2
                )

                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 429)

                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["model_calls"], 1)
                self.assertEqual(status["tool_calls"], 2)
                self.assertEqual(status["action_steps"], 3)
                self.assertEqual(status["remaining_action_steps"], 0)
                self.assertTrue(status["action_step_limit_reached"])
                self.assertEqual(
                    status["ledger"][-1]["rejection"], "action_step_limit"
                )
                self.assertEqual(ScriptedUpstreamHandler.calls, 1)
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_gateway_counts_gemini_sse_tool_calls_once(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        ScriptedUpstreamHandler.calls = 0
        event = json.dumps(self._gemini_tool_response(2)).encode()
        ScriptedUpstreamHandler.responses = [
            (
                200,
                b"data: " + event + b"\n\ndata: [DONE]\n\n",
                {"Content-Type": "text/event-stream"},
            ),
        ]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    max_action_steps=3,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                response = urllib.request.urlopen(request, timeout=5)
                self.assertEqual(
                    response.headers.get_content_type(), "text/event-stream"
                )
                self.assertIn(b"data:", response.read())

                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["model_calls"], 1)
                self.assertEqual(status["tool_calls"], 2)
                self.assertEqual(status["action_steps"], 3)
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_gateway_rejects_tool_batch_that_would_exceed_action_budget(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        ScriptedUpstreamHandler.calls = 0
        ScriptedUpstreamHandler.responses = [
            (200, self._tool_response(2), {}),
        ]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    max_action_steps=2,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
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
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["model_calls"], 1)
                self.assertEqual(status["tool_calls"], 0)
                self.assertEqual(status["action_steps"], 1)
                self.assertTrue(status["action_step_limit_reached"])
                self.assertEqual(status["ledger"][0]["proposed_tool_calls"], 2)
                self.assertEqual(
                    status["ledger"][0]["rejection"], "action_step_limit"
                )
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_deepseek_reasoning_is_kept_even_when_response_is_not_delivered(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        response = self._tool_response(2)
        response["choices"][0]["message"]["reasoning_content"] = (
            "reasoning returned before rejected tool batch"
        )
        ScriptedUpstreamHandler.calls = 0
        ScriptedUpstreamHandler.responses = [(200, response, {})]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_file = root / "gateway-key"
            key_file.write_text("gateway-test-secret")
            reasoning_dir = root / "reasoning"
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    max_action_steps=2,
                    provider="deepseek",
                    reasoning_dir=reasoning_dir,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 429)

                rows = [
                    json.loads(line)
                    for line in (reasoning_dir / "provider_reasoning.jsonl")
                    .read_text()
                    .splitlines()
                ]
                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                capture_status = json.loads(
                    (reasoning_dir / "reasoning_capture_status.json").read_text()
                )
                self.assertEqual(
                    rows[0]["text"],
                    "reasoning returned before rejected tool batch",
                )
                self.assertEqual(
                    rows[-1]["downstream_state"],
                    "not_delivered_action_budget",
                )
                self.assertEqual(
                    status["ledger"][0]["reasoning_fragments_captured"], 1
                )
                self.assertEqual(
                    status["reasoning_capture"]["fragments_captured"], 1
                )
                self.assertEqual(capture_status["write_errors"], 0)
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_gemini_native_thought_is_captured_without_changing_response(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"thought": True, "text": "gemini readable thought"},
                            {"text": "gemini final answer"},
                            {"thoughtSignature": "opaque-signature"},
                        ]
                    }
                }
            ]
        }
        ScriptedUpstreamHandler.calls = 0
        ScriptedUpstreamHandler.responses = [(200, response, {})]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_file = root / "gateway-key"
            key_file.write_text("gateway-test-secret")
            reasoning_dir = root / "reasoning"
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    provider="gemini",
                    reasoning_dir=reasoning_dir,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/models/gpt-test:generateContent",
                    data=json.dumps({"contents": []}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                delivered = json.loads(urllib.request.urlopen(request, timeout=5).read())
                self.assertEqual(delivered, response)

                # The response body can reach the client before the handler's
                # final evidence/ledger writes. Wait for completion, not an
                # arbitrary sleep or a partially appended reasoning file.
                for _ in range(100):
                    with urllib.request.urlopen(f"{base}/__benchmark__/ledger", timeout=2) as reply:
                        finalized = json.load(reply).get("ledger", [])
                    if finalized:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("gateway did not finalize the response ledger")

                rows = [
                    json.loads(line)
                    for line in (reasoning_dir / "provider_reasoning.jsonl")
                    .read_text()
                    .splitlines()
                ]
                fragments = [
                    row for row in rows if row["record_type"] == "reasoning_fragment"
                ]
                self.assertEqual(
                    [row["text"] for row in fragments],
                    ["gemini readable thought"],
                )
                self.assertNotIn("gemini final answer", json.dumps(fragments))
                self.assertNotIn("opaque-signature", json.dumps(fragments))
                self.assertEqual(rows[-1]["downstream_state"], "forwarded_complete")
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_workspace_keeps_secret_out_of_docker_argv(self):
        secret = "must-not-appear-in-process-arguments"
        adapter = SimpleNamespace(
            model_gateway=lambda: {
                "upstream_origin": "https://api.example.test",
                "max_model_calls": 3,
                "max_action_steps": 7,
                "auth_mode": "bearer",
                "allowed_models": ["test-model"],
                "allowed_path_prefixes": ["/v1"],
                "transient_error_policy": {
                    "max_retries": 5,
                    "backoff_seconds": [1, 2, 4, 8, 16],
                    "max_retry_after_seconds": 60,
                    "retryable_http_statuses": [408, 429, 502, 503, 504, 529],
                },
            },
            model_gateway_secret=lambda: secret,
        )
        workspace = AgentWorkspace("case", "credential-argv-test", adapter)
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch(
            "agent_formalizer.workspace.subprocess.run", return_value=completed
        ) as run:
            workspace._start_model_gateway()
            first_command = run.call_args_list[0].args[0]
            serialized = json.dumps(first_command)
            self.assertNotIn(secret, serialized)
            self.assertIn("PDDL_GATEWAY_API_KEY_FILE", serialized)
            self.assertNotIn("PDDL_GATEWAY_API_KEY=", serialized)
            secret_path = workspace._gateway_secret_dir / "api-key"
            self.assertEqual(secret_path.read_text(), secret)
            self.assertEqual(
                stat.S_IMODE(secret_path.stat().st_mode),
                0o600,
            )
        workspace._cleanup_gateway_secret()
        workspace._cleanup_gateway_control()

    def test_workspace_finalizes_native_exit_and_persists_settlement(self):
        workspace = AgentWorkspace(
            "case", "native-exit-test", SimpleNamespace()
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace._gateway_started = True
            workspace._gateway_native_exit_path = root / "native-harness-exited"
            workspace._gateway_evidence_dir = root / "evidence"
            workspace._gateway_evidence_dir.mkdir()
            acknowledgement = json.dumps(
                {"status": "native_harness_exited", "active_requests": 1}
            )
            completed = subprocess.CompletedProcess([], 0, acknowledgement, "")
            with patch(
                "agent_formalizer.workspace.subprocess.run",
                return_value=completed,
            ), patch.object(
                workspace,
                "_read_gateway_control",
                side_effect=[{"in_flight_requests": 1}, {"in_flight_requests": 0}],
            ), patch("agent_formalizer.workspace.time.sleep"):
                report = workspace.finalize_model_gateway_after_native_exit(
                    wait_seconds=0.1
                )

            self.assertEqual(report["status"], "settled")
            self.assertTrue(workspace._gateway_native_exit_path.is_file())
            saved = json.loads(
                (workspace._gateway_evidence_dir / "native_exit_finalization.json")
                .read_text()
            )
            self.assertEqual(saved["final_control"]["in_flight_requests"], 0)

    def test_transient_errors_are_transparent_and_use_one_logical_call(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        ScriptedUpstreamHandler.calls = 0
        ScriptedUpstreamHandler.responses = [
            (429, {"error": {"type": "rate_limit"}}, {"Retry-After": "0"}),
            (503, {"error": {"type": "overloaded"}}, {"Retry-After": "0"}),
            (500, {"error": {"type": "internal_error"}}, {"Retry-After": "0"}),
            (200, {"ok": True}, {}),
            (400, {"error": {"type": "invalid_request_error"}}, {}),
        ]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(
                    json.loads(urllib.request.urlopen(request, timeout=5).read()),
                    {"ok": True},
                )
                invalid_request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test", "bad": True}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(invalid_request, timeout=5)
                self.assertEqual(caught.exception.code, 400)

                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["model_calls"], 2)
                self.assertEqual(status["upstream_attempts"], 5)
                self.assertEqual(status["transient_retries"], 3)
                self.assertEqual(status["forwarded_calls"], 2)
                self.assertEqual(status["ledger"][0]["transient_retry_count"], 3)
                self.assertEqual(
                    [row["status"] for row in status["ledger"][0]["upstream_attempts"]],
                    [429, 503, 500, 200],
                )
                self.assertEqual(status["ledger"][1]["routing_class"], "container")
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_exhausted_transient_error_marks_gateway_terminal(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        ScriptedUpstreamHandler.calls = 0
        ScriptedUpstreamHandler.responses = [
            (429, {"error": {"type": "rate_limit"}}, {"Retry-After": "0"}),
            (429, {"error": {"type": "rate_limit"}}, {"Retry-After": "0"}),
            (429, {"error": {"type": "rate_limit"}}, {"Retry-After": "0"}),
        ]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    max_retries=2,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 503)
                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["model_calls"], 1)
                self.assertEqual(status["upstream_attempts"], 3)
                self.assertEqual(status["transient_retries"], 2)
                self.assertEqual(
                    status["terminal_infra_error"]["reason"],
                    "provider_transient_exhausted",
                )
            finally:
                process.terminate()
                process.wait(timeout=10)
                if process.stderr:
                    process.stderr.close()
                upstream.shutdown()
                upstream.server_close()
                thread.join(timeout=5)

    def test_provider_quota_429_uses_the_same_bounded_retry_policy(self):
        try:
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedUpstreamHandler)
        except PermissionError as exc:
            self.skipTest(f"sandbox forbids local sockets: {exc}")
        ScriptedUpstreamHandler.calls = 0
        quota_response = (
            429,
            {
                "error": {
                    "type": "insufficient_quota",
                    "message": "billing credit balance exhausted",
                }
            },
            {"Retry-After": "0"},
        )
        ScriptedUpstreamHandler.responses = [
            quota_response,
            quota_response,
            quota_response,
        ]
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        gateway_port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / "gateway-key"
            key_file.write_text("gateway-test-secret")
            process = subprocess.Popen(
                [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
                env=self._gateway_env(
                    upstream_port=upstream.server_port,
                    gateway_port=gateway_port,
                    key_file=key_file,
                    max_retries=2,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            base = f"http://127.0.0.1:{gateway_port}"
            try:
                self._wait_for_gateway(base, process)
                request = urllib.request.Request(
                    f"{base}/v1/chat/completions",
                    data=json.dumps({"model": "gpt-test"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 503)
                status = json.loads(
                    urllib.request.urlopen(
                        f"{base}/__benchmark__/ledger", timeout=5
                    ).read()
                )
                self.assertEqual(status["upstream_attempts"], 3)
                self.assertEqual(status["transient_retries"], 2)
                self.assertEqual(
                    status["terminal_infra_error"]["reason"],
                    "provider_transient_exhausted",
                )
                self.assertEqual(
                    [
                        row["classification"]
                        for row in status["ledger"][0]["upstream_attempts"]
                    ],
                    ["transparent_transient"] * 3,
                )
                self.assertEqual(
                    [
                        row["status"]
                        for row in status["ledger"][0]["upstream_attempts"]
                    ],
                    [429, 429, 429],
                )
                self.assertEqual(
                    [
                        row["retry_delay_seconds"]
                        for row in status["ledger"][0]["upstream_attempts"]
                    ],
                    [0.0, 0.0, None],
                )
                self.assertTrue(
                    all(
                        row["timestamp"]
                        and row["duration_ms"] >= 0
                        for row in status["ledger"][0]["upstream_attempts"]
                    )
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
