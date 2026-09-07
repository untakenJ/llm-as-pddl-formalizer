from __future__ import annotations

import json
import unittest

from agent_formalizer.claws import get_adapter
from agent_formalizer.logits_openai_bridge import (
    BridgeService,
    JsonlLedger,
    LogitsChatBackend,
    LogitsRestSampler,
    ModelConvention,
    UpstreamError,
    register_model_convention,
    resolve_model_convention,
    upstream_model_id,
)
from api_providers import (
    LOGITS_PROVIDER,
    default_tools_for_model,
    generate_logits_json,
    is_logits_model,
    validate_api_model,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeLogitsHttp:
    def __init__(self, *, expire_first_sample: bool = False):
        self.expire_first_sample = expire_first_sample
        self.session_index = 0
        self.sample_calls = 0
        self.closed = False

    def get(self, path, timeout=None):
        self.assert_path(path, "/api/v1/get_server_capabilities")
        return FakeResponse(
            200,
            {
                "supported_models": [
                    {"model_name": "Qwen/Qwen3.5-4B"},
                    {"model_name": "FutureOrg/FutureModel"},
                ]
            },
        )

    @staticmethod
    def assert_path(actual, expected):
        if actual != expected:
            raise AssertionError(f"expected {expected}, got {actual}")

    def post(self, path, json=None, timeout=None, headers=None):
        if path == "/api/v1/create_session":
            self.session_index += 1
            return FakeResponse(200, {"session_id": f"session-{self.session_index}"})
        if path == "/api/v1/create_sampling_session":
            return FakeResponse(
                200, {"sampling_session_id": f"sampling-{self.session_index}"}
            )
        if path == "/api/v1/asample":
            self.sample_calls += 1
            if self.expire_first_sample and self.sample_calls == 1:
                return FakeResponse(410, {"detail": "session expired"})
            return FakeResponse(200, {"request_id": f"request-{self.sample_calls}"})
        if path == "/api/v1/retrieve_future":
            return FakeResponse(
                200, {"sequences": [{"tokens": [7, 8], "stop_reason": "stop"}]}
            )
        if path == "/api/v1/session_heartbeat":
            return FakeResponse(200, {})
        raise AssertionError(f"unexpected path {path}")

    def close(self):
        self.closed = True


class FakeTokenizer:
    chat_template = "fixture"

    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        self.kwargs = kwargs
        return "rendered"

    def encode(self, value, add_special_tokens=False):
        return [1, 2, 3]

    def decode(self, value, skip_special_tokens=False):
        return (
            "<think>audit</think><tool_call><function=submit_json_response>"
            "<parameter=value>ok</parameter></function></tool_call>"
        )


class FakeSampler:
    def sample(self, prompt_tokens, sampling_params):
        return {"sequences": [{"tokens": [4, 5], "stop_reason": "stop"}]}, 0, 5

    def close(self):
        pass


class LogitsConventionTests(unittest.TestCase):
    def test_provider_route_is_dynamic_but_explicit(self):
        self.assertTrue(is_logits_model("logits/Qwen/Qwen3.5-4B"))
        self.assertEqual(
            validate_api_model("logits/AnyOrg/Model-Added-Later"),
            "logits/AnyOrg/Model-Added-Later",
        )
        self.assertEqual(
            upstream_model_id("logits/Qwen/Qwen3.5-4B"), "Qwen/Qwen3.5-4B"
        )
        self.assertEqual(default_tools_for_model("logits/AnyOrg/Model"), (None, None))

    def test_qwen35_uses_audited_convention_without_global_model_whitelist(self):
        convention = resolve_model_convention("Qwen/Qwen3.5-4B")
        self.assertEqual(convention.id, "qwen3.5-chat-tools-v1")
        with self.assertRaisesRegex(ValueError, "no audited chat/tool convention"):
            resolve_model_convention("FutureOrg/FutureModel")

    def test_registry_can_add_future_family_without_provider_changes(self):
        convention = ModelConvention(
            id="test-future-family",
            model_pattern=__import__("re").compile(r"FutureOrg/FutureModel"),
            tokenizer_revision="revision",
            chat_template_sha256="0" * 64,
            render_kwargs={},
            response_parser=lambda raw, tools: ("", raw, []),
        )
        register_model_convention(convention)
        self.assertIs(resolve_model_convention("FutureOrg/FutureModel"), convention)


class LogitsRestTests(unittest.TestCase):
    def test_capability_check_accepts_selected_model_among_dynamic_models(self):
        http = FakeLogitsHttp()
        sampler = LogitsRestSampler(
            model="Qwen/Qwen3.5-4B",
            api_key="secret",
            ledger=JsonlLedger(None),
            http_client=http,
        )
        try:
            self.assertEqual(sampler.session_generation, 1)
            self.assertEqual(sampler.sampling_session_id, "sampling-1")
        finally:
            sampler.close()

    def test_http_410_rotates_session_and_replays_same_logical_sample(self):
        http = FakeLogitsHttp(expire_first_sample=True)
        sampler = LogitsRestSampler(
            model="Qwen/Qwen3.5-4B",
            api_key="secret",
            ledger=JsonlLedger(None),
            http_client=http,
        )
        try:
            payload, seq_id, duration = sampler.sample([1, 2], {"max_tokens": 8})
            self.assertEqual(payload["sequences"][0]["tokens"], [7, 8])
            self.assertEqual(seq_id, 0)
            self.assertGreaterEqual(duration, 0)
            self.assertEqual(sampler.session_generation, 2)
            self.assertEqual(http.sample_calls, 2)
        finally:
            sampler.close()

    def test_upstream_error_exposes_http_status_to_shared_retry_classifier(self):
        error = UpstreamError(503, "temporary")
        self.assertEqual(error.status_code, 503)


class LogitsTranslationTests(unittest.TestCase):
    def backend(self):
        return LogitsChatBackend(
            model="Qwen/Qwen3.5-4B",
            api_key="secret",
            ledger=JsonlLedger(None),
            tokenizer=FakeTokenizer(),
            sampler=FakeSampler(),
        )

    def test_qwen35_structured_output_uses_official_tool_template(self):
        backend = self.backend()
        payload = backend.chat_completion(
            {
                "model": "Qwen/Qwen3.5-4B",
                "messages": [{"role": "user", "content": "answer"}],
                "logits_json_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            }
        )
        self.assertEqual(payload["choices"][0]["message"]["content"], '{"value":"ok"}')
        self.assertEqual(
            payload["choices"][0]["message"]["reasoning_content"], "audit"
        )
        self.assertIn("qwen3.5-chat-tools-v1", payload["system_fingerprint"])

    def test_bridge_auth_rejects_agent_placeholder_and_accepts_gateway_key(self):
        backend = self.backend()
        service = BridgeService(backend, "real-gateway-key", JsonlLedger(None))
        handler = object.__new__(service.handler_class())
        handler.headers = {
            "Authorization": "Bearer benchmark-gateway-placeholder"
        }
        self.assertFalse(handler._authorized())
        handler.headers = {"Authorization": "Bearer real-gateway-key"}
        self.assertTrue(handler._authorized())

    def test_direct_api_keeps_campaign_request_contract(self):
        class Client:
            def chat_completion(self, request):
                self.request = request
                return {
                    "choices": [
                        {"message": {"content": '{"value":"ok"}'}, "finish_reason": "stop"}
                    ]
                }

        client = Client()
        text = generate_logits_json(
            client,
            "logits/Qwen/Qwen3.5-4B",
            [{"role": "user", "content": "answer"}],
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        )
        self.assertEqual(text, '{"value":"ok"}')
        self.assertEqual(client.request["model"], "Qwen/Qwen3.5-4B")
        self.assertIn("logits_json_schema", client.request)


class LogitsHarnessRoutingTests(unittest.TestCase):
    def test_all_harnesses_route_explicit_logits_model_through_fixed_gateway(self):
        for name in ("openclaw", "hermes", "nanobot", "zeroclaw", "generic"):
            with self.subTest(name=name):
                adapter = get_adapter(
                    name,
                    model="logits/Qwen/Qwen3.5-4B",
                    api_key="gateway-only-secret",
                )
                try:
                    gateway = adapter.model_gateway()
                    self.assertEqual(gateway["transport"], "logits-rest-openai-v1")
                    self.assertEqual(gateway["upstream_model"], "Qwen/Qwen3.5-4B")
                    self.assertEqual(gateway["allowed_path_prefixes"], ["/v1"])
                    if name != "openclaw":
                        self.assertTrue(adapter.api_base.endswith("/v1"))
                    else:
                        self.assertTrue(
                            adapter._gateway_provider_config()["baseUrl"].endswith("/v1")
                        )
                    self.assertNotIn(
                        "gateway-only-secret", json.dumps(adapter.effective_config())
                    )
                finally:
                    if name == "openclaw":
                        adapter._cleanup_run_state()


if __name__ == "__main__":
    unittest.main()
