from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.claws import get_adapter
from agent_formalizer.configuration.benchmark_profile import (
    load_benchmark_profile,
)
from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter
from agent_formalizer.orchestrator import run_one_problem
from agent_formalizer.configuration.config import PROVIDER_API_BASE

DOMAIN = """(define (domain mock)
  (:requirements :strips)
  (:predicates (ready))
  (:action noop :parameters () :precondition (ready) :effect (ready)))"""
PROBLEM = """(define (problem p01)
  (:domain mock)
  (:init (ready))
  (:goal (ready)))"""
FINAL_TEXT = json.dumps({"domain file": DOMAIN, "problem file": PROBLEM})
REASONING_TEXT = "Provider-returned reasoning retained for evidence."


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen_tool_sets: list[set[str]] = []
    stream_lock = threading.Lock()
    active_streams = 0
    request_arrived_during_stream = False

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(
                {
                    "object": "list",
                    "data": [{"id": "gpt-4o-mini", "object": "model"}],
                }
            )
        else:
            self._json({"error": {"message": "not found"}}, status=404)

    def do_POST(self):
        with type(self).stream_lock:
            if type(self).active_streams:
                type(self).request_arrived_during_stream = True
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        names = {
            tool.get("function", {}).get("name")
            for tool in body.get("tools", [])
            if isinstance(tool, dict)
        }
        self.seen_tool_sets.append({name for name in names if name})
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json({"error": {"message": f"unsupported path {self.path}"}}, status=404)
            return
        if body.get("stream"):
            self._stream_chat_completion(body.get("model", "gpt-4o-mini"))
        else:
            self._json(
                self._chat_completion(body.get("model", "gpt-4o-mini"), body)
            )

    def _chat_completion(self, model: str, request: dict) -> dict:
        prompt_text = json.dumps(request.get("messages", []))
        content = (
            json.dumps(
                {
                    "reasoning": "The mock files are internally consistent.",
                    "domain_file": DOMAIN,
                    "problem_file": PROBLEM,
                }
            )
            if "Minimum Formalizer Agent" in prompt_text
            else FINAL_TEXT
        )
        message = {"role": "assistant", "content": content}
        if os.environ.get("E2E_PROVIDER") == "deepseek":
            message["reasoning_content"] = REASONING_TEXT
        return {
            "id": "chatcmpl-pddl-benchmark",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20,
            },
        }

    def _stream_chat_completion(self, model: str) -> None:
        with type(self).stream_lock:
            type(self).active_streams += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        long_duration = float(
            os.environ.get("E2E_STREAM_DURATION_SECONDS", "0")
        )
        interval = 5.0
        event_count = (
            max(2, int(long_duration / interval) + 2)
            if long_duration > 0
            else 1
        )
        width = max(1, (len(FINAL_TEXT) + event_count - 1) // event_count)
        segments = [
            FINAL_TEXT[index : index + width]
            for index in range(0, len(FINAL_TEXT), width)
        ]
        chunks = [
            {
                "id": "chatcmpl-pddl-benchmark",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            **({"role": "assistant"} if index == 0 else {}),
                            **(
                                {"reasoning_content": REASONING_TEXT}
                                if index == 0
                                and os.environ.get("E2E_PROVIDER") == "deepseek"
                                else {}
                            ),
                            "content": segment,
                        },
                        "finish_reason": None,
                    }
                ],
            }
            for index, segment in enumerate(segments)
        ]
        chunks.append(
            {
                "id": "chatcmpl-pddl-benchmark",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            }
        )
        try:
            for index, chunk in enumerate(chunks):
                if long_duration > 0 and index:
                    time.sleep(interval)
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                if (
                    long_duration <= 0
                    and os.environ.get("E2E_STREAMING") == "1"
                    and index == 0
                ):
                    time.sleep(0.25)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        finally:
            with type(self).stream_lock:
                type(self).active_streams -= 1

    def _json(self, value: dict, status: int = 200) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


@unittest.skipUnless(
    os.environ.get("RUN_HARNESS_E2E_TESTS") == "1",
    "set RUN_HARNESS_E2E_TESTS=1 to run Docker end-to-end harness tests",
)
class HarnessEndToEndTests(unittest.TestCase):
    def test_all_adapters_reach_formalizer_output(self):
        e2e_provider = os.environ.get("E2E_PROVIDER", "openai")
        if e2e_provider not in {"openai", "deepseek"}:
            self.fail(f"unsupported E2E_PROVIDER: {e2e_provider}")
        server = ThreadingHTTPServer(("0.0.0.0", 0), FakeOpenAIHandler)
        FakeOpenAIHandler.seen_tool_sets = []
        FakeOpenAIHandler.active_streams = 0
        FakeOpenAIHandler.request_arrived_during_stream = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://host.docker.internal:{server.server_port}/v1"
        host_endpoint = f"http://127.0.0.1:{server.server_port}/v1"
        env = {
            "OPENAI_API_KEY": "local-test-key",
            "OPENAI_BASE_URL": endpoint,
            "DEEPSEEK_API_KEY": "local-test-key",
        }
        try:
            with (
                patch.dict(os.environ, env, clear=False),
                patch.dict(
                    PROVIDER_API_BASE,
                    {
                        "openai": endpoint,
                        "openrouter": endpoint,
                        "deepseek": endpoint,
                    },
                ),
                TemporaryDirectory() as out_dir,
            ):
                names = (
                    [os.environ["E2E_ADAPTER"]]
                    if os.environ.get("E2E_ADAPTER")
                    else (
                        "openclaw", "hermes", "nanobot", "zeroclaw", "generic",
                        *(() if e2e_provider == "deepseek" else ("minimum",)),
                    )
                )
                minimum_profile = load_benchmark_profile(
                    HISTORICAL_PROFILES_DIR
                    / (
                        "native_safety_streaming_minimum_agent.json"
                        if os.environ.get("E2E_STREAMING") == "1"
                        else "native_safety_minimum_agent.json"
                    )
                )
                streaming_profile = (
                    load_benchmark_profile(
                        HISTORICAL_PROFILES_DIR
                        / "native_safety_streaming_native_clean.json"
                    )
                    if os.environ.get("E2E_STREAMING") == "1"
                    else None
                )
                adapters = []
                for name in names:
                    adapters.append(
                        get_adapter(
                            name,
                            model=(
                                "deepseek/deepseek-chat"
                                if e2e_provider == "deepseek"
                                else (
                                    "openrouter/gpt-4o-mini"
                                    if name == "openclaw"
                                    else "openai/gpt-4o-mini"
                                )
                            ),
                            timeout=max(
                                90,
                                int(
                                    float(
                                        os.environ.get(
                                            "E2E_STREAM_DURATION_SECONDS", "0"
                                        )
                                    )
                                    + 120
                                ),
                            ),
                            max_action_steps=3,
                            max_model_calls=3,
                            allow_final_message_recovery=(
                                False if name == "minimum" else True
                            ),
                            api_key="local-test-key",
                            benchmark_profile=(
                                minimum_profile
                                if name == "minimum"
                                else streaming_profile
                            ),
                        )
                    )
                for adapter in adapters:
                    with self.subTest(adapter=adapter.name):
                        PROVIDER_API_BASE["openai"] = (
                            host_endpoint
                            if adapter.name == "minimum"
                            else endpoint
                        )
                        PROVIDER_API_BASE["deepseek"] = endpoint
                        request_start = len(FakeOpenAIHandler.seen_tool_sets)
                        result = run_one_problem(
                            adapter,
                            "blocksworld",
                            "Heavily_Templated_BlocksWorld-100",
                            "p01",
                            out_dir_root=out_dir,
                            model_label=f"mock-{adapter.name}",
                        )
                        diagnostic = ""
                        if result.agent_result:
                            for path in (
                                result.agent_result.stdout_path,
                                result.agent_result.stderr_path,
                            ):
                                if path and path.is_file():
                                    diagnostic += path.read_text(errors="replace")
                        self.assertEqual(
                            result.status,
                            "ok",
                            f"{result.error}; agent={result.agent_result}; {diagnostic}",
                        )
                        self.assertIn(result.extraction_source, {"file", "parsed"})
                        self.assertIn("(domain mock)", result.domain_file or "")
                        qualified_label = result.model_label
                        problem_dir = (
                            Path(out_dir)
                            / "llm-as-formalizer-agent"
                            / "blocksworld"
                            / "Heavily_Templated_BlocksWorld-100"
                            / qualified_label
                            / "p01"
                        )
                        self.assertTrue(
                            (problem_dir / f"p01_{qualified_label}_df.pddl").is_file()
                        )
                        self.assertTrue(
                            (problem_dir / f"p01_{qualified_label}_pf.pddl").is_file()
                        )
                        self.assertTrue((problem_dir / "metadata.json").is_file())
                        metadata = json.loads(
                            (problem_dir / "metadata.json").read_text()
                        )
                        execution_dir = (
                            problem_dir / "executions" / "execution-001"
                        )
                        analysis_manifest_path = (
                            execution_dir / "analysis_evidence_manifest.json"
                        )
                        self.assertTrue(analysis_manifest_path.is_file())
                        analysis_manifest_bytes = analysis_manifest_path.read_bytes()
                        analysis_manifest = json.loads(analysis_manifest_bytes)
                        analysis_record = metadata["evidence"]["optional_evidence"][
                            "analysis_evidence_manifest"
                        ]
                        self.assertEqual(
                            analysis_manifest["manifest_status"], "complete"
                        )
                        self.assertEqual(analysis_manifest["harness"], adapter.name)
                        self.assertEqual(analysis_record["status"], "complete")
                        self.assertEqual(
                            analysis_record["sha256"],
                            hashlib.sha256(analysis_manifest_bytes).hexdigest(),
                        )
                        for raw_file in analysis_manifest["raw_evidence"]["files"]:
                            if raw_file["status"] == "ok":
                                self.assertEqual(len(raw_file["sha256"]), 64)
                                self.assertGreaterEqual(raw_file["bytes"], 0)
                                self.assertIn("record_count_kind", raw_file)
                        usage = metadata["agent"]["usage"]
                        expected_calls = 2 if adapter.name == "minimum" else 1
                        self.assertEqual(usage["input"], 10 * expected_calls)
                        self.assertEqual(usage["output"], 10 * expected_calls)
                        self.assertEqual(usage["cacheRead"], 0)
                        self.assertEqual(usage["total"], 20 * expected_calls)
                        if adapter.name == "nanobot":
                            self.assertEqual(usage["providerTokens"], 20)
                            self.assertEqual(usage["estimatedTokens"], 0)
                            session_dir = (
                                problem_dir
                                / "executions"
                                / "execution-001"
                                / "sessions"
                            )
                            usage_report = json.loads(
                                (session_dir / "usage.json").read_text()
                            )
                            self.assertEqual(
                                usage_report["measurement"],
                                "provider-reported",
                            )
                            self.assertTrue(
                                (session_dir / "nanobot.jsonl").is_file()
                            )
                        gateway = metadata["evidence"]["model_gateway_summary"]
                        self.assertGreater(gateway["model_calls"], 0)
                        self.assertLessEqual(
                            gateway["model_calls"], gateway["max_model_calls"],
                        )
                        if e2e_provider == "deepseek":
                            reasoning_path = (
                                execution_dir
                                / "gateway"
                                / "provider_reasoning.jsonl"
                            )
                            capture_status_path = (
                                execution_dir
                                / "gateway"
                                / "reasoning_capture_status.json"
                            )
                            self.assertEqual(
                                stat.S_IMODE(reasoning_path.stat().st_mode), 0o600
                            )
                            reasoning_rows = [
                                json.loads(line)
                                for line in reasoning_path.read_text().splitlines()
                                if line
                            ]
                            fragments = [
                                row
                                for row in reasoning_rows
                                if row["record_type"] == "reasoning_fragment"
                            ]
                            self.assertEqual(
                                [row["text"] for row in fragments],
                                [REASONING_TEXT] * gateway["model_calls"],
                            )
                            capture_status = json.loads(
                                capture_status_path.read_text()
                            )
                            self.assertEqual(capture_status["write_errors"], 0)
                            self.assertEqual(
                                analysis_manifest["provider_analysis_observation"][
                                    "status"
                                ],
                                "text_observed",
                            )
                            self.assertEqual(
                                analysis_manifest["analysis_attribution"]["status"],
                                "api_readable_analysis_captured",
                            )
                        if os.environ.get("E2E_STREAMING") == "1":
                            self.assertEqual(
                                gateway["streaming_mode"], "native_streaming"
                            )
                        self.assertEqual(
                            len(metadata["evidence"]["provenance"]["effective_config_sha256"]), 64
                        )
                        self.assertEqual(
                            len(metadata["evidence"]["provenance"]["prompt_sha256"]), 64
                        )
                        self.assertEqual(
                            len(metadata["evidence"]["provenance"]
                                ["transport_payload_sha256"]), 64
                        )
                        self.assertEqual(
                            metadata["evidence"]["provenance"]
                            ["effective_config_sha256"],
                            metadata["evidence"]["provenance"]
                            ["materialized_config_sha256"],
                        )
                        ledger_path = (
                            problem_dir / "executions" / "execution-001" /
                            "model_call_ledger.jsonl"
                        )
                        ledger = [
                            json.loads(line)
                            for line in ledger_path.read_text().splitlines()
                            if line
                        ]
                        self.assertTrue(any(
                            row.get("counted") and row.get("request_body_sha256")
                            for row in ledger
                        ))
                        if os.environ.get("E2E_STREAMING") == "1":
                            self.assertTrue(
                                all(
                                    row.get("stream_completed")
                                    for row in ledger
                                    if row.get("counted") and row.get("status") == 200
                                )
                            )
                            self.assertFalse(
                                FakeOpenAIHandler.request_arrived_during_stream
                            )
                        self.assertIn(
                            "harness_runtime", metadata["evidence"]["provenance"]
                        )
                        tool_sets = FakeOpenAIHandler.seen_tool_sets[request_start:]
                        exposed = set().union(*tool_sets) if tool_sets else set()
                        if adapter.name == "minimum":
                            self.assertFalse(exposed)
                            self.assertEqual(gateway["tool_calls"], 0)
                            self.assertEqual(gateway["model_calls"], 2)
                            self.assertEqual(
                                metadata["evidence"]["actions"]["fixed_solver_calls"],
                                0,
                            )
                        else:
                            self.assertTrue(
                                exposed, f"{adapter.name} sent no tool schema"
                            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
