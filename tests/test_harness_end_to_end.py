from __future__ import annotations

import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_formalizer.claws import get_adapter
from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter
from agent_formalizer.orchestrator import run_one_problem
from agent_formalizer.config import PROVIDER_API_BASE

DOMAIN = """(define (domain mock)
  (:requirements :strips)
  (:predicates (ready))
  (:action noop :parameters () :precondition (ready) :effect (ready)))"""
PROBLEM = """(define (problem p01)
  (:domain mock)
  (:init (ready))
  (:goal (ready)))"""
FINAL_TEXT = json.dumps({"domain file": DOMAIN, "problem file": PROBLEM})


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen_tool_sets: list[set[str]] = []

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
            self._json(self._chat_completion(body.get("model", "gpt-4o-mini")))

    def _chat_completion(self, model: str) -> dict:
        return {
            "id": "chatcmpl-pddl-benchmark",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": FINAL_TEXT},
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
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        chunks = [
            {
                "id": "chatcmpl-pddl-benchmark",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": FINAL_TEXT},
                        "finish_reason": None,
                    }
                ],
            },
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
            },
        ]
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

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
        server = ThreadingHTTPServer(("0.0.0.0", 0), FakeOpenAIHandler)
        FakeOpenAIHandler.seen_tool_sets = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://host.docker.internal:{server.server_port}/v1"
        env = {
            "OPENAI_API_KEY": "local-test-key",
            "OPENAI_BASE_URL": endpoint,
        }
        try:
            with (
                patch.dict(os.environ, env, clear=False),
                patch.dict(
                    PROVIDER_API_BASE,
                    {"openai": endpoint, "openrouter": endpoint},
                ),
                TemporaryDirectory() as out_dir,
            ):
                adapters = [
                    get_adapter(
                        name,
                        model=(
                            "openrouter/gpt-4o-mini"
                            if name == "openclaw"
                            else "openai/gpt-4o-mini"
                        ),
                        timeout=90,
                        max_turns=3,
                        max_model_calls=3,
                        allow_final_message_recovery=True,
                        api_key="local-test-key",
                    )
                    for name in (
                        [os.environ["E2E_ADAPTER"]]
                        if os.environ.get("E2E_ADAPTER")
                        else ("openclaw", "hermes", "nanobot", "zeroclaw", "generic")
                    )
                ]
                for adapter in adapters:
                    with self.subTest(adapter=adapter.name):
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
                        metadata = json.loads((problem_dir / "metadata.json").read_text())
                        gateway = metadata["evidence"]["model_gateway_summary"]
                        self.assertGreater(gateway["model_calls"], 0)
                        self.assertLessEqual(
                            gateway["model_calls"], gateway["max_model_calls"],
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
                        self.assertIn(
                            "harness_runtime", metadata["evidence"]["provenance"]
                        )
                        tool_sets = FakeOpenAIHandler.seen_tool_sets[request_start:]
                        exposed = set().union(*tool_sets) if tool_sets else set()
                        self.assertTrue(exposed, f"{adapter.name} sent no tool schema")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
