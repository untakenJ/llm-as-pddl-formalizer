from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_formalizer.infra_diagnostics.recorder import InfraDiagnosticsRecorder
from agent_formalizer.infra_diagnostics.registry import (
    create_handler,
    resolve_handler_id,
)
from agent_formalizer.infra_diagnostics.types import ProviderResponseSnapshot


def _snapshot(*, provider: str, body: dict, headers: dict[str, str]):
    payload = json.dumps(body).encode()
    return ProviderResponseSnapshot(
        event_type="provider_response",
        provider=provider,
        model="provider/model",
        status_code=429,
        headers=headers,
        body=payload,
        body_sha256="body-sha",
        body_original_bytes=len(payload),
        body_truncated=False,
        error_type=None,
        error_message=None,
        routing_class="provider_transient",
        routing_reason="upstream_rate_limit",
        retryable=True,
        retry_after_ms=1000,
        duration_ms=12.5,
        observed_at="2026-08-31T00:00:00Z",
        correlation={"run_id": "run"},
    )


class ProviderDiagnosticHandlerTests(unittest.TestCase):
    def test_google_vertex_projects_structured_429_details(self):
        snapshot = _snapshot(
            provider="google_vertex",
            headers={"x-goog-request-id": "vertex-request"},
            body={
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "shared capacity unavailable",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"subject": "project/test"}],
                        }
                    ],
                }
            },
        )
        projected = create_handler("builtin:google_vertex@1").project(snapshot)

        self.assertEqual(projected.normalized["request_id"], "vertex-request")
        self.assertEqual(
            projected.normalized["provider_error_status"], "RESOURCE_EXHAUSTED"
        )
        self.assertEqual(projected.provider_payload["error_code"], 429)
        self.assertEqual(
            projected.provider_payload["detail_types"],
            ["type.googleapis.com/google.rpc.QuotaFailure"],
        )

    def test_deepseek_projects_openai_compatible_error(self):
        snapshot = _snapshot(
            provider="deepseek",
            headers={"x-request-id": "deepseek-request"},
            body={
                "error": {
                    "type": "insufficient_balance",
                    "code": "insufficient_balance",
                    "message": "account balance is insufficient",
                    "param": None,
                }
            },
        )
        projected = create_handler("builtin:deepseek@1").project(snapshot)

        self.assertEqual(projected.normalized["request_id"], "deepseek-request")
        self.assertEqual(
            projected.normalized["provider_error_type"], "insufficient_balance"
        )
        self.assertEqual(
            projected.provider_payload["error_code"], "insufficient_balance"
        )

    def test_unknown_provider_uses_generic_handler(self):
        self.assertEqual(
            resolve_handler_id("future-provider"), "builtin:generic_http@1"
        )


class InfraDiagnosticsRecorderTests(unittest.TestCase):
    def _config(self, root: Path, **overrides):
        value = {
            "enabled": True,
            "provider": "google_vertex",
            "mode": "structured",
            "capture_success_metadata": False,
            "capture_transport_errors": True,
            "capture_gateway_internal_errors": True,
            "handler": "builtin:google_vertex@1",
            "max_event_bytes": 65536,
            "max_run_bytes": 1048576,
            "event_path": str(root / "events.jsonl"),
            "manifest_path": str(root / "manifest.json"),
            "run_budget_path": str(root / ".run-bytes"),
            "operational_config_sha256": "op-sha",
            "correlation": {
                "run_id": "run",
                "attempt_index": 1,
                "execution_try": 2,
            },
        }
        value.update(overrides)
        return value

    def test_structured_event_is_correlated_redacted_and_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = InfraDiagnosticsRecorder(self._config(root))
            recorder.observe_provider_response(
                model="google-vertex/gemini-test",
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Request-Id": "request-123",
                    "Authorization": "Bearer header-secret",
                    "Retry-After": "2",
                },
                body=json.dumps(
                    {
                        "error": {
                            "code": 429,
                            "status": "RESOURCE_EXHAUSTED",
                            "message": "retry Bearer message-secret",
                            "details": [{"api_key": "body-secret"}],
                        }
                    }
                ).encode(),
                routing_class="provider_transient",
                routing_reason="upstream_rate_limit",
                retryable=True,
                duration_ms=25.0,
                correlation={"logical_request_id": 7, "physical_attempt": 3},
            )
            recorder.close(timeout=5.0)

            lines = (root / "events.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            manifest = json.loads((root / "manifest.json").read_text())

        self.assertEqual(event["normalized"]["http_status"], 429)
        self.assertEqual(event["normalized"]["retry_after_ms"], 2000)
        self.assertEqual(event["normalized"]["request_id"], "request-123")
        self.assertEqual(event["correlation"]["execution_try"], 2)
        self.assertEqual(event["correlation"]["physical_attempt"], 3)
        self.assertEqual(
            event["provider"]["google_vertex"]["details"][0]["api_key"],
            "[REDACTED]",
        )
        serialized = json.dumps(event)
        self.assertNotIn("header-secret", serialized)
        self.assertNotIn("message-secret", serialized)
        self.assertNotIn("body-secret", serialized)
        self.assertEqual(event["diagnostics"]["handler"], "builtin:google_vertex@1")
        self.assertTrue(manifest["closed"])
        self.assertEqual(manifest["events_written"], 1)

    def test_storage_unavailability_is_fail_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocker = root / "not-a-directory"
            blocker.write_text("block")
            config = self._config(root)
            config.update(
                {
                    "event_path": str(blocker / "events.jsonl"),
                    "manifest_path": str(blocker / "manifest.json"),
                    "run_budget_path": str(blocker / ".run-bytes"),
                }
            )
            recorder = InfraDiagnosticsRecorder(config)
            recorder.observe_transport_error(
                model="google-vertex/gemini-test",
                error=OSError("transport failed"),
                routing_class="provider_transient",
                routing_reason="upstream_transport_error",
                retryable=True,
                duration_ms=1.0,
                correlation={},
            )
            recorder.close(timeout=5.0)
            status = recorder.status()

        self.assertGreaterEqual(status["storage_failures"], 1)
        self.assertGreaterEqual(status["events_dropped"], 1)

    def test_provider_mode_off_still_allows_selected_transport_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = InfraDiagnosticsRecorder(self._config(root, mode="off"))
            recorder.observe_provider_response(
                model="google-vertex/gemini-test",
                status_code=429,
                headers={"Content-Type": "application/json"},
                body=b'{"error":{"code":429}}',
                routing_class="provider_transient",
                routing_reason="upstream_rate_limit",
                retryable=True,
                duration_ms=1.0,
                correlation={},
            )
            recorder.observe_transport_error(
                model="google-vertex/gemini-test",
                error=TimeoutError("upstream timeout"),
                routing_class="provider_transient",
                routing_reason="upstream_transport_error",
                retryable=True,
                duration_ms=2.0,
                correlation={},
            )
            recorder.close(timeout=5.0)
            events = [
                json.loads(line)
                for line in (root / "events.jsonl").read_text().splitlines()
            ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "upstream_transport_error")
        self.assertEqual(events[0]["normalized"]["error_type"], "TimeoutError")

    def test_raw_json_is_bounded_structured_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = InfraDiagnosticsRecorder(self._config(root, mode="raw"))
            recorder.observe_provider_response(
                model="google-vertex/gemini-test",
                status_code=429,
                headers={"Content-Type": "application/json"},
                body=json.dumps(
                    {
                        "error": {"code": 429},
                        "api_key": "raw-body-secret",
                    }
                ).encode(),
                routing_class="provider_transient",
                routing_reason="upstream_rate_limit",
                retryable=True,
                duration_ms=1.0,
                correlation={},
            )
            recorder.close(timeout=5.0)
            event = json.loads((root / "events.jsonl").read_text().splitlines()[0])

        self.assertEqual(event["raw"]["body_json"]["api_key"], "[REDACTED]")
        self.assertNotIn("raw-body-secret", json.dumps(event))

    def test_raw_binary_body_is_hashed_but_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = InfraDiagnosticsRecorder(self._config(root, mode="raw"))
            recorder.observe_provider_response(
                model="google-vertex/gemini-test",
                status_code=500,
                headers={"Content-Type": "application/octet-stream"},
                body=b"binary-secret-payload",
                routing_class="provider_transient",
                routing_reason="upstream_http_500",
                retryable=False,
                duration_ms=1.0,
                correlation={},
            )
            recorder.close(timeout=5.0)
            event = json.loads((root / "events.jsonl").read_text().splitlines()[0])

        self.assertTrue(event["raw"]["binary_body_omitted"])
        self.assertNotIn("binary-secret-payload", json.dumps(event))
        self.assertIsNotNone(event["raw"]["body_sha256"])

    def test_handler_failure_records_health_event_and_uses_generic_fallback(self):
        class BrokenHandler:
            def project(self, _snapshot):
                raise RuntimeError("handler broke")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = InfraDiagnosticsRecorder(self._config(root))
            recorder._handler = BrokenHandler()
            recorder.observe_provider_response(
                model="google-vertex/gemini-test",
                status_code=429,
                headers={"Content-Type": "application/json"},
                body=b'{"error":{"code":429}}',
                routing_class="provider_transient",
                routing_reason="upstream_rate_limit",
                retryable=True,
                duration_ms=1.0,
                correlation={},
            )
            recorder.close(timeout=5.0)
            events = [
                json.loads(line)
                for line in (root / "events.jsonl").read_text().splitlines()
            ]
            status = recorder.status()

        self.assertEqual(
            [event["event_type"] for event in events],
            ["diagnostic_handler_failure", "provider_response"],
        )
        self.assertEqual(status["handler_failures"], 1)
        self.assertEqual(
            events[1]["provider"]["google_vertex"]["response_json"]["error"][
                "code"
            ],
            429,
        )

    def test_invalid_declared_handler_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown provider diagnostic"):
                InfraDiagnosticsRecorder(
                    self._config(Path(tmp), handler="builtin:missing@1")
                )


if __name__ == "__main__":
    unittest.main()
