"""Unit tests for standalone API-pipeline transient retries."""

from __future__ import annotations

import os
import ssl
import unittest
from unittest.mock import patch

from api_providers import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_PROVIDER,
    DIRECT_API_MAX_TRANSIENT_RETRIES,
    DIRECT_API_RETRYABLE_HTTP_STATUSES,
    DIRECT_API_TRANSIENT_POLICY_ID,
    build_gemini_client,
    build_deepseek_client,
    build_provider_client,
    call_with_transient_retry,
    classify_direct_api_error,
    direct_api_transient_policy,
    generate_gemini_json,
    generate_deepseek_json,
    default_tools_for_model,
    is_rate_limit_error,
)


class _Response:
    def __init__(self, status_code: int | None = None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _ApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status: str | None = None,
        details=None,
        response=None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details
        self.response = response


class _CollectingTracer:
    def __init__(self):
        self.events = []

    def emit(self, event: str, **fields):
        self.events.append({"event": event, **fields})


class DirectApiTransientHelpersTest(unittest.TestCase):
    def test_policy_matches_external_transient_v2(self):
        policy = direct_api_transient_policy()
        self.assertEqual(policy["id"], DIRECT_API_TRANSIENT_POLICY_ID)
        self.assertEqual(
            policy["max_retries"], DIRECT_API_MAX_TRANSIENT_RETRIES
        )
        self.assertEqual(
            policy["retryable_http_statuses"],
            sorted(DIRECT_API_RETRYABLE_HTTP_STATUSES),
        )

    def test_classifies_structured_google_503(self):
        exc = _ApiError(
            "503 UNAVAILABLE",
            code=503,
            status="UNAVAILABLE",
            details={"error": {"code": 503, "status": "UNAVAILABLE"}},
        )
        classification = classify_direct_api_error(exc)
        self.assertTrue(classification["retryable"])
        self.assertEqual(classification["reason"], "upstream_http_503")
        self.assertEqual(classification["http_status"], 503)

    def test_classifies_the_real_google_server_error_shape(self):
        from google.genai.errors import ServerError

        exc = ServerError(
            503,
            {
                "error": {
                    "code": 503,
                    "message": "The service is currently unavailable.",
                    "status": "UNAVAILABLE",
                }
            },
        )
        classification = classify_direct_api_error(exc)
        self.assertTrue(classification["retryable"])
        self.assertEqual(classification["reason"], "upstream_http_503")
        self.assertEqual(classification["provider_status"], "UNAVAILABLE")

    def test_all_allowlisted_http_statuses_are_retryable(self):
        for status in DIRECT_API_RETRYABLE_HTTP_STATUSES:
            with self.subTest(status=status):
                classification = classify_direct_api_error(
                    _ApiError(f"{status} provider error", code=status)
                )
                self.assertTrue(classification["retryable"])
                self.assertEqual(classification["http_status"], status)

    def test_500_requires_structured_internal_reason(self):
        transient = classify_direct_api_error(
            _ApiError(
                "server error",
                code=500,
                details={"error": {"status": "INTERNAL"}},
            )
        )
        deterministic = classify_direct_api_error(
            _ApiError("500 INTERNAL appears only in unstructured text", code=500)
        )
        self.assertTrue(transient["retryable"])
        self.assertEqual(
            transient["reason"], "upstream_structured_internal_error"
        )
        self.assertFalse(deterministic["retryable"])

    def test_text_fallback_is_anchored_to_leading_http_status(self):
        self.assertTrue(
            classify_direct_api_error(RuntimeError("503 UNAVAILABLE"))["retryable"]
        )
        self.assertFalse(
            classify_direct_api_error(
                RuntimeError("invalid input mentions example status 503")
            )["retryable"]
        )

    def test_transport_timeout_is_retryable_but_certificate_error_is_not(self):
        self.assertTrue(
            classify_direct_api_error(TimeoutError("connect timed out"))["retryable"]
        )
        self.assertFalse(
            classify_direct_api_error(
                ssl.SSLCertVerificationError("certificate verify failed")
            )["retryable"]
        )

    def test_rate_limit_predicate_remains_backwards_compatible(self):
        self.assertTrue(
            is_rate_limit_error(
                RuntimeError(
                    "429 RESOURCE_EXHAUSTED. "
                    "{'error': {'status': 'RESOURCE_EXHAUSTED'}}"
                )
            )
        )
        self.assertTrue(is_rate_limit_error(_ApiError("quota", code=429)))
        self.assertFalse(is_rate_limit_error(_ApiError("unavailable", code=503)))


class DirectApiTransientRetryTest(unittest.TestCase):
    def test_recovers_from_503_on_second_attempt(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise _ApiError("503 UNAVAILABLE", code=503, status="UNAVAILABLE")
            return "ok"

        with patch("api_providers.time.sleep") as sleep:
            result = call_with_transient_retry(flaky, provider="google-vertex")
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 2)
        sleep.assert_called_once_with(1.0)

    def test_exhaustion_raises_after_five_retries(self):
        calls = {"n": 0}

        def unavailable():
            calls["n"] += 1
            raise _ApiError("503 UNAVAILABLE", code=503, status="UNAVAILABLE")

        with patch("api_providers.time.sleep") as sleep:
            with self.assertRaises(_ApiError):
                call_with_transient_retry(unavailable, provider="google-vertex")
        self.assertEqual(calls["n"], DIRECT_API_MAX_TRANSIENT_RETRIES + 1)
        self.assertEqual(sleep.call_count, DIRECT_API_MAX_TRANSIENT_RETRIES)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [1.0, 2.0, 4.0, 8.0, 16.0],
        )

    def test_retry_after_header_is_honored_and_capped(self):
        calls = {"n": 0}

        def overloaded():
            calls["n"] += 1
            if calls["n"] == 1:
                raise _ApiError(
                    "429 RESOURCE_EXHAUSTED",
                    code=429,
                    response=_Response(429, {"Retry-After": "120"}),
                )
            return "ok"

        with patch("api_providers.time.sleep") as sleep:
            self.assertEqual(call_with_transient_retry(overloaded), "ok")
        sleep.assert_called_once_with(60.0)

    def test_non_transient_error_fails_immediately(self):
        calls = {"n": 0}

        def bad_request():
            calls["n"] += 1
            raise _ApiError("400 INVALID_ARGUMENT", code=400)

        with patch("api_providers.time.sleep") as sleep:
            with self.assertRaises(_ApiError):
                call_with_transient_retry(bad_request)
        self.assertEqual(calls["n"], 1)
        sleep.assert_not_called()

    def test_trace_records_each_attempt_without_error_message(self):
        calls = {"n": 0}
        tracer = _CollectingTracer()

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise _ApiError("503 sensitive provider detail", code=503)
            return "ok"

        with patch("api_providers.time.sleep"):
            self.assertEqual(
                call_with_transient_retry(flaky, tracer=tracer),
                "ok",
            )
        self.assertEqual(len(tracer.events), 2)
        first, second = tracer.events
        self.assertEqual(first["event"], "api_attempt")
        self.assertEqual(first["routing_class"], "transparent_transient")
        self.assertTrue(first["will_retry"])
        self.assertNotIn("error_message", first)
        self.assertEqual(second["outcome"], "success")

    def test_gemini_generation_recovers_inside_one_logical_call(self):
        from google.genai.errors import ServerError

        class Models:
            def __init__(self):
                self.calls = 0

            def generate_content(self, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise ServerError(
                        503,
                        {"error": {"code": 503, "status": "UNAVAILABLE"}},
                    )
                return type("Response", (), {"text": '{"ok": true}'})()

        models = Models()
        client = type("Client", (), {"models": models})()
        tracer = _CollectingTracer()
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }
        with patch("api_providers.time.sleep"):
            result = generate_gemini_json(
                client,
                "gemini-test",
                "prompt",
                schema,
                tracer=tracer,
            )
        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(models.calls, 2)
        attempts = [row for row in tracer.events if row["event"] == "api_attempt"]
        self.assertEqual([row["outcome"] for row in attempts], ["error", "success"])

    def test_deepseek_json_preserves_reasoning_in_trace(self):
        class Message:
            content = '{"ok": true}'
            reasoning_content = "reasoning retained by model_dump"

        class Response:
            choices = [type("Choice", (), {"message": Message(), "finish_reason": "stop"})()]

            def model_dump(self, **_kwargs):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": self.choices[0].message.content,
                                "reasoning_content": self.choices[0].message.reasoning_content,
                            }
                        }
                    ]
                }

        class Completions:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs
                return Response()

        completions = Completions()
        client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": completions})()},
        )()
        tracer = _CollectingTracer()
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }
        result = generate_deepseek_json(
            client,
            "deepseek-v4-flash",
            [{"role": "user", "content": "Return JSON."}],
            schema,
            tracer=tracer,
        )
        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(
            completions.kwargs["response_format"], {"type": "json_object"}
        )
        self.assertIn("JSON Schema", completions.kwargs["messages"][0]["content"])
        response_event = next(row for row in tracer.events if row["event"] == "response")
        self.assertEqual(
            response_event["response"]["choices"][0]["message"]["reasoning_content"],
            "reasoning retained by model_dump",
        )


class DirectApiClientRetryOwnershipTest(unittest.TestCase):
    def test_openai_sdk_retries_are_disabled(self):
        with (
            patch("api_providers._read_key_file", return_value="test-key"),
            patch("api_providers.OpenAI") as client_class,
        ):
            provider, _ = build_provider_client("gpt-4o-mini")
        self.assertEqual(provider, "openai")
        client_class.assert_called_once_with(api_key="test-key", max_retries=0)

    def test_gemini_sdk_retries_are_disabled(self):
        env = {
            "GOOGLE_CLOUD_API_KEY": "test-key",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "global",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("google.genai.Client") as client_class:
                build_gemini_client()
        options = client_class.call_args.kwargs["http_options"]
        self.assertEqual(options.api_version, "v1")
        self.assertEqual(options.retry_options.attempts, 1)

    def test_deepseek_sdk_retries_are_disabled_and_named_key_is_used(self):
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-deepseek-key"}),
            patch("api_providers.OpenAI") as client_class,
        ):
            build_deepseek_client()
        client_class.assert_called_once_with(
            api_key="test-deepseek-key",
            base_url=DEEPSEEK_BASE_URL,
            max_retries=0,
        )

    def test_deepseek_provider_routing_and_tools(self):
        with patch("api_providers.build_deepseek_client", return_value=object()):
            provider, _ = build_provider_client("deepseek-v4-flash")
        self.assertEqual(provider, DEEPSEEK_PROVIDER)
        self.assertEqual(default_tools_for_model("deepseek-v4-flash"), (None, None))


if __name__ == "__main__":
    unittest.main()
