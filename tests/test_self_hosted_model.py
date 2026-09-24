"""Provider wiring and a real loopback gateway against a synthetic GPU API."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import urlopen

from agent_formalizer.claws import get_adapter
from agent_formalizer.configuration.benchmark_profile import BenchmarkProfile, DEFAULT_BENCHMARK_PROFILE, load_benchmark_profile
from agent_formalizer.configuration.credentials import load_credential_registry
from agent_formalizer.compute_platforms.self_hosted import api_base
from agent_formalizer.results.provider_reasoning import extract_reasoning_fragments, token_accounting
from test_streaming_model_gateway import running_gateway, _request, _ledger


class SelfHostedTests(unittest.TestCase):
    def native_output_profile(self):
        # These provider-wiring tests use synthetic/unknown model IDs, not a
        # claim about their real capabilities. Test the explicit native path.
        raw = deepcopy(DEFAULT_BENCHMARK_PROFILE.raw)
        raw['condition_profile']['overrides']['generation']['max_output_tokens'] = 'native'
        return BenchmarkProfile(DEFAULT_BENCHMARK_PROFILE.path, raw)

    def test_native_and_minimum_adapters_keep_external_provider_routes(self):
        from profile_fixtures import HISTORICAL_PROFILES_DIR
        from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
        minimum = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_minimum_agent.json")
        for harness in ("openclaw", "hermes", "nanobot", "generic", "zeroclaw", "minimum"):
            for model in ("deepseek/deepseek-v4-flash", "google-vertex/gemini-3.1-flash-lite", "openai/gpt-4o-mini"):
                with self.subTest(harness=harness, model=model):
                    adapter = get_adapter(harness, model=model, api_key="test-external-key",
                        benchmark_profile=minimum if harness == "minimum" else self.native_output_profile(),
                        credential_provider_options={"google_vertex": {"project": "test-project"}}
                        if model.startswith("google-vertex/") else None)
                    self.assertEqual(adapter.resolved_config.model, model)
                    gateway = adapter.model_gateway()
                    self.assertTrue(gateway)
                    self.assertNotIn("test-external-key", json.dumps(adapter.effective_config()))
                    self.assertNotIn("localhost:8000", adapter.upstream_api_base())

    def test_all_harness_routes_share_gateway_not_direct_model_access(self):
        for harness in ("openclaw", "hermes", "nanobot", "generic", "zeroclaw"):
            with self.subTest(harness=harness):
                model = "self-hosted/example/model-revision"
                adapter = get_adapter(harness, model=model, api_key="node-private-model-key",
                    benchmark_profile=self.native_output_profile(),
                    credential_provider_options={"self_hosted": {"base_url": "http://host.docker.internal:8000/v1"}})
                self.assertEqual(adapter.upstream_api_base(), "http://host.docker.internal:8000/v1")
                gateway = adapter.model_gateway()
                self.assertEqual(gateway["auth_mode"], "bearer")
                self.assertIn("example/model-revision", gateway["allowed_models"])
                self.assertEqual(adapter.resolved_config.sha256, self.native_output_profile().resolve(harness, model=model).sha256)
                self.assertNotIn("node-private-model-key", json.dumps(adapter.model_auth()))
                if harness != "openclaw":
                    self.assertNotIn("host.docker.internal", adapter.api_base)
                if harness in {"hermes", "nanobot"}:
                    native = adapter._benchmark_config()
                    self.assertNotIn("host.docker.internal", json.dumps(native))
                if harness == "zeroclaw":
                    self.assertTrue(adapter.zeroclaw_provider)

    def test_origin_is_required_and_never_inferred_from_environment(self):
        for options in ({}, {"self_hosted": {}}, {"self_hosted": {"base_url": "https://user:secret@host/v1"}},
                        {"self_hosted": {"base_url": "http://host/v2"}},
                        {"self_hosted": {"base_url": "http://host/v1?key=secret"}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                api_base(options)

    def test_registry_resolves_key_and_origin_together(self):
        raw = deepcopy(load_credential_registry().raw)
        raw["defaults"]["providers"]["self-hosted"] = "node-model"
        raw["profiles"]["node-model"] = {"provider": "self-hosted", "api_key_env": "SELF_HOSTED_API_KEY",
            "provider_options": {"self_hosted": {"base_url": {"env": "SELF_HOSTED_BASE_URL"}}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry.json").write_text(json.dumps(raw))
            (root / "node.env").write_text("SELF_HOSTED_API_KEY=private-node-key\nSELF_HOSTED_BASE_URL=http://host.docker.internal:8000/v1\n")
            credential = load_credential_registry(root / "registry.json").resolve("self-hosted/served-id", env_file=root / "node.env")
            self.assertEqual(credential.api_key, "private-node-key")
            self.assertEqual(api_base(credential.provider_options), "http://host.docker.internal:8000/v1")
            self.assertNotIn("private-node-key", json.dumps(credential.metadata()))

    def test_current_and_legacy_vllm_reasoning_without_payload_mutation(self):
        payload = {"choices": [{"message": {"reasoning": "modern text", "content": "answer"}},
                               {"delta": {"reasoning_content": "legacy text"}}],
                   "unrelated": {"reasoning": "not a documented message field"}}
        before = deepcopy(payload)
        fragments = extract_reasoning_fragments("self-hosted", payload)
        self.assertEqual({f["text"] for f in fragments}, {"modern text", "legacy text"})
        self.assertEqual(payload, before)
        usage = token_accounting({"usage": {"prompt_tokens": 5, "completion_tokens": 10}}, "self-hosted/example")
        self.assertEqual(usage["input_tokens"], 5)
        self.assertIsNone(usage["estimated_cost_usd"])

    def test_gateway_retries_429_preserves_stream_tool_and_reasoning(self):
        payloads = [
            {"choices": [{"index": 0, "delta": {"reasoning": "check the preconditions"}}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "test-call", "type": "function",
                "function": {"name": "write_file", "arguments": "{\"path\":\"domain.pddl\",\"content\":\"(define (domain x))\"}"}}]}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
             "usage": {"prompt_tokens": 8, "completion_tokens": 16}},
        ]
        wire = b"".join(b"data: " + json.dumps(p).encode() + b"\n\n" for p in payloads) + b"data: [DONE]\n\n"
        class FakeGPU(BaseHTTPRequestHandler):
            calls = []
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                self.calls.append((raw, self.headers.get("Authorization")))
                if len(self.calls) == 1:
                    payload = b'{"error":{"message":"temporary capacity","type":"rate_limit"}}'
                    self.send_response(429); self.send_header("Content-Type", "application/json")
                else:
                    payload = wire
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload))); self.end_headers()
                self.wfile.write(payload); self.wfile.flush()
            def log_message(self, *_):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with running_gateway(FakeGPU, provider="self-hosted", reasoning_dir=root) as (base, *_):
                with urlopen(_request(base), timeout=10) as response:
                    self.assertEqual(response.read(), wire)
                ledger = _ledger(base)
            self.assertEqual(len(FakeGPU.calls), 2)
            self.assertEqual(FakeGPU.calls[0], FakeGPU.calls[1])
            self.assertEqual(ledger["model_calls"], 1)
            self.assertEqual(ledger["tool_calls"], 1)
            captured = (root / "provider_reasoning.jsonl").read_text()
            self.assertIn("check the preconditions", captured)
            self.assertNotIn("stream-test-key", captured)


if __name__ == "__main__":
    unittest.main()
