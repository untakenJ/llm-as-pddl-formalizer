from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_formalizer.claws import get_adapter
from agent_formalizer.provider_reasoning import (
    ProviderReasoningRecorder,
    extract_reasoning_fragments,
    reasoning_capture_capability,
)


class ProviderReasoningExtractorTests(unittest.TestCase):
    def test_deepseek_chat_and_responses_formats_preserve_exact_text(self):
        payloads = [
            {
                "choices": [
                    {
                        "message": {
                            "reasoning_content": "chat reasoning",
                            "content": "final answer",
                        }
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "reasoning",
                        "content": [
                            {"type": "reasoning_text", "text": "response reasoning"}
                        ],
                    },
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "visible"}],
                    },
                ]
            },
            {"type": "response.reasoning_text.delta", "delta": "stream delta"},
        ]

        fragments = [
            fragment
            for payload in payloads
            for fragment in extract_reasoning_fragments("deepseek", payload)
        ]

        self.assertEqual(
            [fragment["text"] for fragment in fragments],
            ["chat reasoning", "response reasoning", "stream delta"],
        )
        self.assertNotIn("final answer", json.dumps(fragments))
        self.assertNotIn("visible", json.dumps(fragments))

    def test_gemini_native_compatibility_and_interactions_formats(self):
        payloads = [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "native thought"},
                                {"text": "final answer"},
                                {"thoughtSignature": "opaque-signature"},
                            ]
                        }
                    }
                ]
            },
            [
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"thought": True, "text": "native stream thought"}
                                ]
                            }
                        }
                    ]
                }
            ],
            {
                "choices": [
                    {"delta": {"reasoning_content": "compatibility thought"}}
                ]
            },
            {
                "steps": [
                    {
                        "type": "thought",
                        "summary": [{"type": "text", "text": "interaction summary"}],
                        "signature": "opaque-signature",
                    }
                ]
            },
            {
                "event_type": "step.start",
                "step": {
                    "type": "thought",
                    "summary": [
                        {"type": "text", "text": "stream initial summary"}
                    ],
                },
            },
            {
                "event_type": "step.delta",
                "delta": {
                    "type": "thought_summary",
                    "content": {"type": "text", "text": "summary delta"},
                },
            },
        ]

        fragments = [
            fragment
            for payload in payloads
            for fragment in extract_reasoning_fragments("google-vertex", payload)
        ]

        self.assertEqual(
            [fragment["text"] for fragment in fragments],
            [
                "native thought",
                "native stream thought",
                "compatibility thought",
                "interaction summary",
                "stream initial summary",
                "summary delta",
            ],
        )
        serialized = json.dumps(fragments)
        self.assertNotIn("final answer", serialized)
        self.assertNotIn("opaque-signature", serialized)

    def test_unknown_provider_is_explicitly_extensible_not_guessed(self):
        capability = reasoning_capture_capability("future-provider")
        self.assertEqual(capability["support"], "not_implemented")
        self.assertEqual(
            extract_reasoning_fragments(
                "future-provider", {"reasoning_content": "do not guess"}
            ),
            [],
        )

    def test_semantically_ambiguous_fields_are_not_guessed(self):
        for provider in ("deepseek", "gemini"):
            with self.subTest(provider=provider):
                self.assertEqual(
                    extract_reasoning_fragments(
                        provider,
                        {
                            "thinking": "configuration-like value",
                            "reasoning": "high",
                            "content": "ordinary answer",
                        },
                    ),
                    [],
                )


class ProviderReasoningRecorderTests(unittest.TestCase):
    def test_recorder_writes_restricted_exact_fragments_and_content_free_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "provider_reasoning.jsonl"
            status = root / "reasoning_capture_status.json"
            recorder = ProviderReasoningRecorder("deepseek", records, status)
            context = {
                "response_id": "logical-1-physical-1",
                "logical_call_index": 1,
                "physical_attempt": 1,
                "model": "deepseek-test",
                "api_path": "/v1/chat/completions",
                "streaming": False,
                "payload_sequence": 1,
            }
            report = recorder.capture_payload(
                {
                    "choices": [
                        {"message": {"reasoning_content": "exact\nreasoning"}}
                    ]
                },
                context=context,
            )
            recorder.record_boundary(
                context=context,
                response_complete=True,
                downstream_state="forwarded_complete",
            )
            rows = [json.loads(line) for line in records.read_text().splitlines()]
            status_value = json.loads(status.read_text())
            records_mode = stat.S_IMODE(records.stat().st_mode)
            status_mode = stat.S_IMODE(status.stat().st_mode)

        self.assertEqual(report["fragments"], 1)
        self.assertEqual(rows[0]["text"], "exact\nreasoning")
        self.assertEqual(rows[1]["record_type"], "response_boundary")
        self.assertEqual(records_mode, 0o600)
        self.assertEqual(status_mode, 0o600)
        self.assertEqual(status_value["fragments_captured"], 1)
        self.assertNotIn("exact", json.dumps(status_value))

    def test_extractor_failure_is_diagnostic_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = ProviderReasoningRecorder(
                "deepseek",
                root / "provider_reasoning.jsonl",
                root / "reasoning_capture_status.json",
            )
            with patch(
                "agent_formalizer.provider_reasoning.extract_reasoning_fragments",
                side_effect=RuntimeError("extractor failed"),
            ):
                report = recorder.capture_payload({}, context={})
            status_value = json.loads(
                (root / "reasoning_capture_status.json").read_text()
            )

        self.assertEqual(report["capture_errors"], 1)
        self.assertEqual(status_value["capture_errors"], 1)
        self.assertEqual(status_value["last_error_type"], "RuntimeError")


class FiveHarnessProviderRoutingTests(unittest.TestCase):
    def test_five_native_harnesses_use_shared_provider_capture_identity(self):
        for provider_model in ("deepseek/deepseek-test", "gemini/gemini-test"):
            expected = provider_model.split("/", 1)[0]
            for harness in ("openclaw", "hermes", "nanobot", "zeroclaw", "generic"):
                with self.subTest(provider=expected, harness=harness):
                    adapter = get_adapter(
                        harness,
                        model=provider_model,
                        api_key="test-key",
                    )
                    self.assertEqual(adapter.model_gateway()["provider"], expected)


if __name__ == "__main__":
    unittest.main()
