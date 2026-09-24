from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_formalizer.configuration.config import MODEL_GATEWAY_SCRIPT

# model_gateway is intentionally a standalone sidecar entrypoint whose policy
# is validated at import. Supply a harmless unit-test policy for direct access
# to its incremental observer; integration tests launch fresh subprocesses.
os.environ.setdefault("PDDL_GATEWAY_UPSTREAM_ORIGIN", "http://127.0.0.1:9")
os.environ.setdefault("PDDL_GATEWAY_API_KEY", "observer-unit-test")
os.environ.setdefault("PDDL_GATEWAY_ALLOWED_MODELS", '["gpt-test"]')
os.environ.setdefault("PDDL_GATEWAY_ALLOWED_PATH_PREFIXES", '["/v1"]')
from agent_formalizer.gateways.model_gateway import StreamToolObserver


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class StreamingUpstream(BaseHTTPRequestHandler):
    scripts: list[list[tuple[bytes, float]]] = []
    calls = 0
    content_length: int | None = None
    cancelled = threading.Event()

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0") or 0)
        self.rfile.read(length)
        script = type(self).scripts.pop(0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        if type(self).content_length is not None:
            self.send_header("Content-Length", str(type(self).content_length))
        self.end_headers()
        try:
            for payload, delay in script:
                if delay:
                    time.sleep(delay)
                self.wfile.write(payload)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            type(self).cancelled.set()

    def log_message(self, format, *args):
        return


class RetryUpstream(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0") or 0)
        self.rfile.read(length)
        if type(self).calls == 1:
            payload = b'{"error":{"type":"overloaded"}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(payload)
            return
        event = (
            b'data: {"choices":[{"delta":{"content":"ok"},'
            b'"finish_reason":"stop"}]}\n\n'
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(event)))
        self.end_headers()
        self.wfile.write(event)

    def log_message(self, format, *args):
        return


class PreHeaderDisconnectUpstream(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0") or 0)
        self.rfile.read(length)
        if type(self).calls == 1:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        event = (
            b'data: {"choices":[{"delta":{"content":"recovered"},'
            b'"finish_reason":"stop"}]}\n\n'
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(event)))
        self.end_headers()
        self.wfile.write(event)

    def log_message(self, format, *args):
        return


class ConcurrentUpstream(BaseHTTPRequestHandler):
    calls = 0
    barrier = threading.Barrier(2)

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("content-length", "0") or 0)
        self.rfile.read(length)
        type(self).barrier.wait(timeout=5)
        calls = [
            {"index": index, "id": f"call-{index}"}
            for index in range(2)
        ]
        event = (
            b"data: "
            + json.dumps(
                {"choices": [{"index": 0, "delta": {"tool_calls": calls},
                              "finish_reason": "tool_calls"}]}
            ).encode()
            + b"\n\n"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(event)))
        self.end_headers()
        self.wfile.write(event)

    def log_message(self, format, *args):
        return


class PeriodicUpstream(BaseHTTPRequestHandler):
    duration_seconds = 0.0
    interval_seconds = 5.0

    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or 0)
        self.rfile.read(length)
        count = math.ceil(type(self).duration_seconds / type(self).interval_seconds) + 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for index in range(count):
            if index:
                time.sleep(type(self).interval_seconds)
            event = (
                b"data: "
                + json.dumps(
                    {"choices": [{"delta": {"content": str(index)},
                                  "finish_reason": (
                                      "stop" if index == count - 1 else None
                                  )}]}
                ).encode()
                + b"\n\n"
            )
            self.wfile.write(event)
            self.wfile.flush()

    def log_message(self, format, *args):
        return


@contextmanager
def running_gateway(
    handler,
    *,
    max_actions: int = 20,
    delivery: str = "native_streaming",
    provider: str = "openai",
    reasoning_dir: Path | None = None,
):
    try:
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    except PermissionError as exc:
        raise unittest.SkipTest(f"sandbox forbids local sockets: {exc}") from exc
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    gateway_port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        key = root / "key"
        key.write_text("stream-test-key")
        control = root / "control.json"
        cancel = root / "benchmark-cancelled"
        env = {
            **os.environ,
            "PDDL_GATEWAY_UPSTREAM_ORIGIN": (
                f"http://127.0.0.1:{upstream.server_port}"
            ),
            "PDDL_GATEWAY_MAX_MODEL_CALLS": str(min(10, max_actions)),
            "PDDL_GATEWAY_MAX_ACTION_STEPS": str(max_actions),
            "PDDL_GATEWAY_PORT": str(gateway_port),
            "PDDL_GATEWAY_LISTEN_HOST": "127.0.0.1",
            "PDDL_GATEWAY_API_KEY_FILE": str(key),
            "PDDL_GATEWAY_AUTH_MODE": "bearer",
            "PDDL_GATEWAY_PROVIDER": provider,
            "PDDL_GATEWAY_ALLOWED_MODELS": json.dumps(["gpt-test"]),
            "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES": json.dumps(["/v1"]),
            "PDDL_GATEWAY_MAX_TRANSIENT_RETRIES": "1",
            "PDDL_GATEWAY_TRANSIENT_BACKOFF_SECONDS": "[0]",
            "PDDL_GATEWAY_CONTROL_FILE": str(control),
            "PDDL_GATEWAY_BENCHMARK_CANCEL_FILE": str(cancel),
            "PDDL_GATEWAY_RESPONSE_DELIVERY": delivery,
            "PDDL_GATEWAY_STREAM_CHUNK_BYTES": "32",
        }
        if reasoning_dir is not None:
            env["PDDL_GATEWAY_REASONING_PATH"] = str(
                reasoning_dir / "provider_reasoning.jsonl"
            )
            env["PDDL_GATEWAY_REASONING_STATUS_PATH"] = str(
                reasoning_dir / "reasoning_capture_status.json"
            )
        env.pop("PDDL_GATEWAY_API_KEY", None)
        process = subprocess.Popen(
            [os.sys.executable, str(MODEL_GATEWAY_SCRIPT)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        base = f"http://127.0.0.1:{gateway_port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/__benchmark__/health", timeout=1)
                break
            except OSError:
                time.sleep(0.02)
        else:
            raise AssertionError(process.stderr.read())
        try:
            yield base, upstream, process, control, cancel
        finally:
            process.terminate()
            process.wait(timeout=10)
            if process.stderr:
                process.stderr.close()
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=5)


def _request(base: str):
    return urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps({"model": "gpt-test", "stream": True}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )


def _ledger(base: str) -> dict:
    return json.loads(
        urllib.request.urlopen(base + "/__benchmark__/ledger", timeout=5).read()
    )


class StreamObserverTests(unittest.TestCase):
    def test_fragmented_provider_tool_formats_are_deduplicated(self):
        payloads = [
            {
                "choices": [
                    {"index": 0, "delta": {"tool_calls": [{"index": 0}]}}
                ]
            },
            {
                "choices": [
                    {"index": 0, "delta": {"tool_calls": [{"index": 0}]}}
                ]
            },
            {
                "candidates": [
                    {"index": 0, "content": {"parts": [{"functionCall": {"name": "f"}}]}}
                ]
            },
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "tool-1"},
            },
            {
                "type": "response.output_item.added",
                "output_index": 2,
                "item": {"type": "function_call", "call_id": "call-2"},
            },
            {
                "type": "response.output_item.done",
                "output_index": 2,
                "item": {"type": "function_call", "call_id": "call-2"},
            },
        ]
        observer = StreamToolObserver("text/event-stream")
        wire = b"".join(
            b"data: " + json.dumps(payload).encode() + b"\n\n"
            for payload in payloads
        ) + b"data: [DONE]\n\n"
        for byte in wire:
            observer.feed(bytes([byte]))
        observer.finish()
        self.assertEqual(observer.provisional_tool_calls, 4)

    def test_clean_sse_eof_without_provider_terminal_is_incomplete(self):
        from agent_formalizer.gateways.model_gateway import StreamObservationError

        observer = StreamToolObserver("text/event-stream")
        observer.feed(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
        with self.assertRaisesRegex(StreamObservationError, "provider terminal"):
            observer.finish()
        self.assertFalse(observer.provider_terminal_observed)

    def test_malformed_sse_data_is_not_a_completion_marker(self):
        from agent_formalizer.gateways.model_gateway import StreamObservationError

        observer = StreamToolObserver("text/event-stream")
        observer.feed(b"data: {not-json}\n\n")
        observer.feed(b"data: [DONE]\n\n")
        with self.assertRaisesRegex(StreamObservationError, "malformed"):
            observer.finish()

    def test_openai_usage_only_final_event_is_a_provider_terminal(self):
        observer = StreamToolObserver("text/event-stream")
        observer.feed(
            b'data: {"choices":[],"usage":{"prompt_tokens":3,'
            b'"completion_tokens":0,"total_tokens":3}}\n\n'
        )
        observer.finish()
        self.assertTrue(observer.provider_terminal_observed)
        self.assertEqual(observer.provider_terminal_type, "usage_final")

    def test_sse_observer_buffer_is_bounded(self):
        observer = StreamToolObserver("text/event-stream")
        from agent_formalizer.gateways.model_gateway import (
            STREAM_EVENT_BUFFER_BYTES,
            StreamObservationError,
        )

        with self.assertRaises(StreamObservationError):
            observer.feed(b"x" * (STREAM_EVENT_BUFFER_BYTES + 1))


class StreamingGatewayTests(unittest.TestCase):
    def test_streaming_gemini_interactions_thought_summaries_are_captured(self):
        events = [
            (
                b'event: step.start\n'
                b'data: {"event_type":"step.start","index":0,"step":'
                b'{"type":"thought","summary":[{"type":"text","text":'
                b'"initial thought"}]}}\n\n'
            ),
            (
                b'event: step.delta\n'
                b'data: {"event_type":"step.delta","index":0,"delta":'
                b'{"type":"thought_summary","content":{"type":"text",'
                b'"text":" continued"}}}\n\n'
            ),
            (
                b'event: step.start\n'
                b'data: {"event_type":"step.start","index":1,"step":'
                b'{"type":"model_output","content":[{"type":"text",'
                b'"text":"final answer"}]}}\n\n'
            ),
            b"event: done\ndata: [DONE]\n\n",
        ]
        StreamingUpstream.scripts = [[(event, 0) for event in events]]
        StreamingUpstream.content_length = sum(map(len, events))
        with tempfile.TemporaryDirectory() as tmp:
            reasoning_dir = Path(tmp) / "reasoning"
            with running_gateway(
                StreamingUpstream,
                provider="gemini",
                reasoning_dir=reasoning_dir,
            ) as (base, *_):
                delivered = urllib.request.urlopen(_request(base), timeout=5).read()
                rows = [
                    json.loads(line)
                    for line in (reasoning_dir / "provider_reasoning.jsonl")
                    .read_text()
                    .splitlines()
                ]

        self.assertEqual(delivered, b"".join(events))
        fragments = [row for row in rows if row["record_type"] == "reasoning_fragment"]
        self.assertEqual(
            [row["text"] for row in fragments],
            ["initial thought", " continued"],
        )
        self.assertNotIn("final answer", json.dumps(fragments))

    def test_streaming_deepseek_reasoning_is_captured_without_changing_bytes(self):
        reasoning_events = [
            b'data: {"choices":[{"delta":{"reasoning_content":"first "}}]}\n\n',
            b'data: {"choices":[{"delta":{"reasoning_content":"second"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
        StreamingUpstream.scripts = [[(event, 0) for event in reasoning_events]]
        StreamingUpstream.content_length = sum(map(len, reasoning_events))
        StreamingUpstream.cancelled.clear()
        with tempfile.TemporaryDirectory() as tmp:
            reasoning_dir = Path(tmp) / "reasoning"
            with running_gateway(
                StreamingUpstream,
                provider="deepseek",
                reasoning_dir=reasoning_dir,
            ) as (base, *_):
                delivered = urllib.request.urlopen(_request(base), timeout=5).read()
                ledger = _ledger(base)
                rows = [
                    json.loads(line)
                    for line in (reasoning_dir / "provider_reasoning.jsonl")
                    .read_text()
                    .splitlines()
                ]

        self.assertEqual(delivered, b"".join(reasoning_events))
        fragments = [row for row in rows if row["record_type"] == "reasoning_fragment"]
        self.assertEqual([row["text"] for row in fragments], ["first ", "second"])
        self.assertEqual(rows[-1]["downstream_state"], "forwarded_complete")
        self.assertTrue(rows[-1]["response_complete"])
        self.assertEqual(
            ledger["ledger"][0]["reasoning_fragments_captured"], 2
        )

    def setUp(self):
        StreamingUpstream.calls = 0
        StreamingUpstream.cancelled = threading.Event()
        StreamingUpstream.content_length = None

    def test_first_event_arrives_before_provider_finishes_and_bytes_match(self):
        first = b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        second = (
            b'data: {"choices":[{"delta":{"content":"b"},'
            b'"finish_reason":"stop"}]}\n\n'
        )
        StreamingUpstream.scripts = [[(first, 0), (second, 0.35)]]
        with running_gateway(StreamingUpstream) as (base, *_):
            started = time.monotonic()
            response = urllib.request.urlopen(_request(base), timeout=5)
            first_event = response.readline() + response.readline()
            first_elapsed = time.monotonic() - started
            body = first_event + response.read()
            total_elapsed = time.monotonic() - started
            status = _ledger(base)

        self.assertEqual(body, first + second)
        self.assertLess(first_elapsed, 0.25)
        self.assertGreater(total_elapsed, 0.3)
        row = status["ledger"][0]
        self.assertTrue(row["stream_completed"])
        self.assertTrue(row["downstream_committed"])
        self.assertEqual(row["upstream_bytes"], len(body))
        self.assertEqual(row["downstream_bytes"], len(body))
        self.assertTrue(row["transport_stream_completed"])
        self.assertTrue(row["provider_terminal_observed"])
        self.assertEqual(row["provider_terminal_type"], "choices.finish_reason")

    def test_v4_buffered_mode_remains_atomic_and_byte_preserving(self):
        first = b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        second = b'data: {"choices":[{"delta":{"content":"b"}}]}\n\n'
        StreamingUpstream.scripts = [[(first, 0), (second, 0.35)]]
        with running_gateway(
            StreamingUpstream, delivery="buffered_atomic"
        ) as (base, *_):
            started = time.monotonic()
            response = urllib.request.urlopen(_request(base), timeout=5)
            body = response.read()
            elapsed = time.monotonic() - started
            status = _ledger(base)

        self.assertEqual(body, first + second)
        self.assertGreater(elapsed, 0.3)
        self.assertEqual(status["streaming_mode"], "buffered_atomic")

    def test_soft_threshold_delivers_complete_tool_batch_then_rejects_next(self):
        calls = [
            {
                "id": f"call-{index}",
                "type": "function",
                "function": {"name": "f", "arguments": "{}"},
            }
            for index in range(3)
        ]
        event = (
            b"data: "
            + json.dumps(
                {"choices": [{"index": 0, "delta": {"tool_calls": calls},
                              "finish_reason": "tool_calls"}]}
            ).encode()
            + b"\n\n"
        )
        StreamingUpstream.scripts = [[(event, 0)]]
        with running_gateway(StreamingUpstream, max_actions=2) as (base, *_):
            self.assertEqual(urllib.request.urlopen(_request(base)).read(), event)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(_request(base))
            status = _ledger(base)

        self.assertEqual(caught.exception.code, 429)
        self.assertEqual(StreamingUpstream.calls, 1)
        self.assertEqual(status["model_calls"], 1)
        self.assertEqual(status["tool_calls"], 3)
        self.assertEqual(status["final_action_steps"], 4)
        self.assertEqual(status["action_step_overshoot"], 2)
        self.assertEqual(status["overshoot_causing_logical_call"], 1)
        self.assertEqual(status["max_tool_batch_size"], 3)

    def test_clean_http_eof_without_provider_terminal_invalidates_stream(self):
        event = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        StreamingUpstream.content_length = len(event)
        StreamingUpstream.scripts = [[(event, 0)]]
        with running_gateway(StreamingUpstream) as (base, *_):
            self.assertEqual(urllib.request.urlopen(_request(base)).read(), event)
            for _ in range(100):
                status = _ledger(base)
                if (
                    status["ledger"]
                    and status["ledger"][0].get("lifecycle_status") == "terminal"
                ):
                    break
                time.sleep(0.01)

        row = status["ledger"][0]
        self.assertTrue(row["transport_stream_completed"])
        self.assertFalse(row["provider_terminal_observed"])
        self.assertFalse(row["stream_completed"])
        self.assertEqual(
            status["terminal_infra_error"]["reason"],
            "post_commit_stream_failure",
        )

    def test_native_exit_keeps_active_request_in_collection_ledger(self):
        first = b'data: {"choices":[{"delta":{"content":"tail"}}]}\n\n'
        later = b"data: [DONE]\n\n"
        StreamingUpstream.scripts = [[(first, 0), (later, 0.5)]]
        with running_gateway(StreamingUpstream) as (base, *_):
            parsed = urllib.parse.urlsplit(base)
            sock = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
            request_body = json.dumps(
                {"model": "gpt-test", "stream": True}
            ).encode()
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\n"
                + f"Host: {parsed.hostname}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(request_body)}\r\n\r\n".encode()
                + request_body
            )
            received = b""
            while first not in received:
                received += sock.recv(4096)
            request = urllib.request.Request(
                base + "/__benchmark__/native-exit",
                data=b"",
                method="POST",
            )
            acknowledgement = json.loads(
                urllib.request.urlopen(request, timeout=5).read()
            )
            status = _ledger(base)
            sock.close()

        self.assertEqual(acknowledgement["active_requests"], 1)
        self.assertTrue(status["native_harness_exited"])
        self.assertEqual(status["in_flight_requests"], 1)
        self.assertEqual(
            status["ledger"][0]["lifecycle_status"],
            "in_flight_at_collection",
        )

    def test_precommit_retry_keeps_one_logical_call(self):
        RetryUpstream.calls = 0
        with running_gateway(RetryUpstream) as (base, *_):
            body = urllib.request.urlopen(_request(base)).read()
            status = _ledger(base)
        self.assertIn(b"ok", body)
        self.assertEqual(RetryUpstream.calls, 2)
        self.assertEqual(status["model_calls"], 1)
        self.assertEqual(status["upstream_attempts"], 2)
        self.assertEqual(status["transient_retries"], 1)

    def test_preheader_transport_disconnect_retries_same_logical_call(self):
        PreHeaderDisconnectUpstream.calls = 0
        with running_gateway(PreHeaderDisconnectUpstream) as (base, *_):
            body = urllib.request.urlopen(_request(base), timeout=5).read()
            status = _ledger(base)
        self.assertIn(b"recovered", body)
        self.assertEqual(PreHeaderDisconnectUpstream.calls, 2)
        self.assertEqual(status["model_calls"], 1)
        self.assertEqual(status["transient_retries"], 1)

    def test_postcommit_incomplete_body_publishes_terminal_invalidator(self):
        event = (
            b'data: {"choices":[{"index":0,"delta":{"reasoning_content":'
            b'"retained before failure","tool_calls":'
            b'[{"index":0,"id":"partial-call"}]}}]}\n\n'
        )
        StreamingUpstream.content_length = len(event) + 100
        StreamingUpstream.scripts = [[(event, 0)]]
        with tempfile.TemporaryDirectory() as tmp:
            reasoning_dir = Path(tmp) / "reasoning"
            with running_gateway(
                StreamingUpstream,
                provider="deepseek",
                reasoning_dir=reasoning_dir,
            ) as (base, _, _, control, _):
                response = urllib.request.urlopen(_request(base), timeout=5)
                self.assertEqual(response.read(), event)
                for _ in range(100):
                    value = json.loads(control.read_text()) if control.is_file() else {}
                    if value.get("terminal_infra_error"):
                        break
                    time.sleep(0.01)
                status = _ledger(base)
                reasoning_rows = [
                    json.loads(line)
                    for line in (reasoning_dir / "provider_reasoning.jsonl")
                    .read_text()
                    .splitlines()
                ]

        self.assertEqual(
            status["terminal_infra_error"]["reason"],
            "post_commit_stream_failure",
        )
        row = status["ledger"][0]
        self.assertTrue(row["partial_response"])
        self.assertFalse(row["stream_completed"])
        self.assertEqual(row["provisional_tool_calls"], 1)
        self.assertEqual(row["committed_tool_calls"], 0)
        self.assertEqual(status["tool_calls"], 0)
        self.assertEqual(row["termination_initiator"], "upstream_or_gateway")
        self.assertEqual(reasoning_rows[0]["text"], "retained before failure")
        self.assertFalse(reasoning_rows[-1]["response_complete"])
        self.assertEqual(reasoning_rows[-1]["downstream_state"], "forwarded_partial")

    def test_committed_structured_transient_event_invalidates_execution(self):
        first = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        error = b'data: {"type":"error","error":{"type":"rate_limit"}}\n\n'
        StreamingUpstream.content_length = len(first) + len(error)
        StreamingUpstream.scripts = [[(first, 0), (error, 0.05)]]
        with running_gateway(StreamingUpstream) as (base, *_):
            delivered = urllib.request.urlopen(_request(base)).read()
            self.assertTrue(delivered.startswith(first))
            self.assertLess(len(delivered), len(first) + len(error))
            for _ in range(100):
                status = _ledger(base)
                if (
                    status["ledger"]
                    and status["ledger"][0].get("lifecycle_status") == "terminal"
                ):
                    break
                time.sleep(0.01)

        self.assertEqual(
            status["terminal_infra_error"]["reason"],
            "post_commit_stream_failure",
        )
        self.assertEqual(
            status["ledger"][0]["termination_initiator"],
            "upstream_or_gateway",
        )

    def test_downstream_cancel_is_valid_and_closes_upstream(self):
        first = b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        later = b'data: {"choices":[{"delta":{"content":"b"}}]}\n\n'
        StreamingUpstream.scripts = [[(first, 0), (later, 0.15), (later, 0.15)]]
        with running_gateway(StreamingUpstream) as (base, _, _, _, _):
            parsed = urllib.parse.urlsplit(base)
            sock = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
            request_body = json.dumps({"model": "gpt-test", "stream": True}).encode()
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\n"
                + f"Host: {parsed.hostname}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(request_body)}\r\n\r\n".encode()
                + request_body
            )
            sock.recv(4096)
            sock.close()
            for _ in range(100):
                status = _ledger(base)
                if (
                    status["ledger"]
                    and status["ledger"][0].get("lifecycle_status") == "terminal"
                ):
                    break
                time.sleep(0.01)

        self.assertIsNone(status["terminal_infra_error"])
        row = status["ledger"][0]
        self.assertTrue(row["client_cancelled"])
        self.assertEqual(row["termination_initiator"], "downstream_client")

    def test_deadline_race_is_valid_and_flagged_ambiguous(self):
        event = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        StreamingUpstream.content_length = len(event) + 100
        StreamingUpstream.scripts = [[(event, 0), (b"", 0.2)]]
        with running_gateway(StreamingUpstream) as (base, _, _, _, cancel):
            response = urllib.request.urlopen(_request(base), timeout=5)
            cancel.write_text("benchmark_deadline\n")
            self.assertEqual(response.read(), event)
            for _ in range(100):
                status = _ledger(base)
                if (
                    status["ledger"]
                    and status["ledger"][0].get("lifecycle_status") == "terminal"
                ):
                    break
                time.sleep(0.01)

        self.assertIsNone(status["terminal_infra_error"])
        row = status["ledger"][0]
        self.assertTrue(row["benchmark_cancelled"])
        self.assertTrue(row["ambiguous_stream_termination"])
        self.assertEqual(row["termination_initiator"], "ambiguous")

    def test_true_pre_event_silence_adds_no_heartbeat(self):
        event = b'data: {"choices":[{"delta":{"content":"late"}}]}\n\n'
        StreamingUpstream.scripts = [[(event, 0.4)]]
        with running_gateway(StreamingUpstream) as (base, *_):
            parsed = urllib.parse.urlsplit(base)
            sock = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
            body = json.dumps({"model": "gpt-test", "stream": True}).encode()
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\n"
                + f"Host: {parsed.hostname}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            sock.settimeout(0.15)
            with self.assertRaises(socket.timeout):
                sock.recv(1)
            sock.close()
            for _ in range(100):
                status = _ledger(base)
                if (
                    status["ledger"]
                    and status["ledger"][0].get("lifecycle_status") == "terminal"
                ):
                    break
                time.sleep(0.01)

        self.assertIsNone(status["terminal_infra_error"])
        self.assertTrue(status["ledger"][0]["client_cancelled"])
        self.assertEqual(status["ledger"][0]["downstream_bytes"], 0)

    def test_concurrent_admitted_requests_finish_and_record_overshoot(self):
        ConcurrentUpstream.calls = 0
        ConcurrentUpstream.barrier = threading.Barrier(2)
        bodies: list[bytes] = []
        errors: list[BaseException] = []
        with running_gateway(ConcurrentUpstream, max_actions=3) as (base, *_):
            def invoke():
                try:
                    bodies.append(urllib.request.urlopen(_request(base), timeout=5).read())
                except BaseException as exc:  # surfaced by the assertion below
                    errors.append(exc)

            threads = [threading.Thread(target=invoke) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(_request(base), timeout=5)
            status = _ledger(base)

        self.assertEqual(errors, [])
        self.assertEqual(len(bodies), 2)
        self.assertEqual(ConcurrentUpstream.calls, 2)
        self.assertEqual(status["model_calls"], 2)
        self.assertEqual(status["tool_calls"], 4)
        self.assertEqual(status["final_action_steps"], 6)
        self.assertEqual(status["action_step_overshoot"], 3)
        self.assertEqual(status["in_flight_at_threshold_crossing"], 2)

    @unittest.skipUnless(
        float(os.environ.get("PDDL_RUN_LONG_STREAM_SECONDS", "0")) > 0,
        "set PDDL_RUN_LONG_STREAM_SECONDS for the >120-second stream canary",
    )
    def test_periodic_progress_survives_longer_than_native_idle_window(self):
        PeriodicUpstream.duration_seconds = float(
            os.environ["PDDL_RUN_LONG_STREAM_SECONDS"]
        )
        PeriodicUpstream.interval_seconds = 5.0
        arrival_times: list[float] = []
        with running_gateway(PeriodicUpstream) as (base, *_):
            started = time.monotonic()
            response = urllib.request.urlopen(_request(base), timeout=10)
            while True:
                line = response.readline()
                if not line:
                    break
                if line.startswith(b"data:"):
                    arrival_times.append(time.monotonic())
            elapsed = time.monotonic() - started
            status = _ledger(base)

        gaps = [
            later - earlier
            for earlier, later in zip(arrival_times, arrival_times[1:])
        ]
        self.assertGreaterEqual(elapsed, PeriodicUpstream.duration_seconds)
        self.assertTrue(gaps)
        self.assertLess(max(gaps), 7.0)
        self.assertTrue(status["ledger"][0]["stream_completed"])

    @unittest.skipUnless(
        float(os.environ.get("PDDL_RUN_LONG_SILENCE_SECONDS", "0")) > 0,
        "set PDDL_RUN_LONG_SILENCE_SECONDS for the >120-second silence canary",
    )
    def test_true_long_silence_preserves_native_client_timeout(self):
        silence = float(os.environ["PDDL_RUN_LONG_SILENCE_SECONDS"])
        event = b'data: {"choices":[{"delta":{"content":"too-late"}}]}\n\n'
        StreamingUpstream.scripts = [[(event, silence)]]
        with running_gateway(StreamingUpstream) as (base, *_):
            parsed = urllib.parse.urlsplit(base)
            sock = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
            body = json.dumps({"model": "gpt-test", "stream": True}).encode()
            sock.sendall(
                b"POST /v1/chat/completions HTTP/1.1\r\n"
                + f"Host: {parsed.hostname}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            sock.settimeout(max(0.1, silence - 1.0))
            started = time.monotonic()
            with self.assertRaises(socket.timeout):
                sock.recv(1)
            native_timeout_elapsed = time.monotonic() - started
            sock.close()
            for _ in range(300):
                status = _ledger(base)
                if (
                    status["ledger"]
                    and status["ledger"][0].get("lifecycle_status") == "terminal"
                ):
                    break
                time.sleep(0.01)

        self.assertGreaterEqual(native_timeout_elapsed, silence - 1.5)
        self.assertIsNone(status["terminal_infra_error"])
        row = status["ledger"][0]
        self.assertTrue(row["client_cancelled"])
        self.assertEqual(row["downstream_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
