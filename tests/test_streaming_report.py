from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_formalizer.results.streaming_report import summarize_streaming_outputs


def _metadata(harness: str, overshoot: int, *, streaming: bool = True) -> dict:
    return {
        "attempt_valid": True,
        "evidence": {
            "actions": {"action_step_overshoot": overshoot},
            "provenance": {
                "resolved_config": {
                    "raw": {
                        "harness": harness,
                        "resolved": {
                            "model_response_delivery": {
                                "mode": (
                                    "native_streaming"
                                    if streaming
                                    else "buffered_atomic"
                                )
                            }
                        },
                    }
                }
            },
        },
    }


class StreamingReportTests(unittest.TestCase):
    def test_selected_metrics_and_discarded_operations_stay_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, row in enumerate(
                [
                    _metadata("hermes", 0),
                    _metadata("hermes", 2),
                    _metadata("openclaw", 4),
                    _metadata("openclaw", 99, streaming=False),
                ]
            ):
                path = root / f"case-{index}" / "metadata.json"
                path.parent.mkdir()
                path.write_text(json.dumps(row))
            invalid = root / "case-invalid" / "provider_infra_invalid.json"
            invalid.parent.mkdir()
            invalid.write_text(
                json.dumps(
                    {
                        "infra_invalidator": "post_commit_stream_failure",
                        "model_gateway_summary": {"upstream_attempts": 3},
                        "actions": {"action_step_overshoot": 1000},
                    }
                )
            )

            report = summarize_streaming_outputs([root])

        official = report["official_selected_valid_executions"]
        self.assertEqual(official["valid_executions"], 3)
        self.assertEqual(official["affected_valid_executions"], 2)
        self.assertEqual(official["overshoot_mean"], 3.0)
        self.assertEqual(official["overshoot_p95"], 4)
        self.assertEqual(official["overshoot_max"], 4)
        self.assertEqual(
            official["harness_breakdown"]["hermes"]["affected_valid_executions"],
            1,
        )
        operational = report["operational_discarded_executions"]
        self.assertEqual(operational["count"], 1)
        self.assertEqual(operational["physical_upstream_attempts"], 3)


if __name__ == "__main__":
    unittest.main()
