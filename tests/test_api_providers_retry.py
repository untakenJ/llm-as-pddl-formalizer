"""Unit tests for API-pipeline rate-limit retries."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from api_providers import (
    RATE_LIMIT_MAX_ATTEMPTS,
    call_with_rate_limit_retry,
    is_rate_limit_error,
)


class _ExcWithCode(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


class RateLimitHelpersTest(unittest.TestCase):
    def test_detects_resource_exhausted_text(self):
        self.assertTrue(
            is_rate_limit_error(
                RuntimeError(
                    "429 RESOURCE_EXHAUSTED. {'error': {'status': 'RESOURCE_EXHAUSTED'}}"
                )
            )
        )

    def test_detects_status_code_attr(self):
        self.assertTrue(is_rate_limit_error(_ExcWithCode("quota", 429)))
        self.assertFalse(is_rate_limit_error(_ExcWithCode("bad request", 400)))

    def test_retries_three_times_then_raises(self):
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        with patch("api_providers.time.sleep") as sleep:
            with self.assertRaises(RuntimeError):
                call_with_rate_limit_retry(
                    boom,
                    provider="google-vertex",
                    backoff_seconds=(0.01, 0.01, 0.01),
                )
        self.assertEqual(calls["n"], RATE_LIMIT_MAX_ATTEMPTS)
        self.assertEqual(sleep.call_count, RATE_LIMIT_MAX_ATTEMPTS - 1)

    def test_succeeds_on_second_attempt(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return "ok"

        with patch("api_providers.time.sleep"):
            self.assertEqual(call_with_rate_limit_retry(flaky, provider="test"), "ok")
        self.assertEqual(calls["n"], 2)

    def test_non_rate_limit_fails_immediately(self):
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise ValueError("parse error")

        with patch("api_providers.time.sleep") as sleep:
            with self.assertRaises(ValueError):
                call_with_rate_limit_retry(boom)
        self.assertEqual(calls["n"], 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
