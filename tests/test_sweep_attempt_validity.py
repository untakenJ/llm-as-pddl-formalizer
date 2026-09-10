from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_formalizer.configuration.config import PREDICTION_TYPE
from sweep_agent_pipeline import _invalid_attempt_count, _valid_completion_indices


class SweepAttemptValidityTests(unittest.TestCase):
    def test_invalid_attempts_are_excluded_from_evaluation_indices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / PREDICTION_TYPE / "domain" / "dataset" / "model"
            for problem in ("p01", "p02", "p03"):
                (base / problem).mkdir(parents=True)
            (base / "p01" / "completion.json").write_text(
                json.dumps({"complete": True, "attempt_valid": True})
            )
            (base / "p02" / "invalid_attempt.json").write_text(
                json.dumps({"attempt_valid": False, "status": "infra_invalid"})
            )
            (base / "p03" / "completion.json").write_text(
                json.dumps({"complete": True, "attempt_valid": True})
            )

            valid = _valid_completion_indices(
                root, "domain", "dataset", "model", [1, 2, 3]
            )
            invalid = _invalid_attempt_count(
                root, "domain", "dataset", "model", [1, 2, 3]
            )

        self.assertEqual(valid, [1, 3])
        self.assertEqual(invalid, 1)

    def test_streaming_incomplete_attempt_is_counted_as_operationally_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / PREDICTION_TYPE / "domain" / "dataset" / "model" / "p01"
            base.mkdir(parents=True)
            (base / "invalid_attempt.json").write_text(
                json.dumps({"attempt_valid": False, "status": "incomplete"})
            )
            invalid = _invalid_attempt_count(
                root, "domain", "dataset", "model", [1]
            )

        self.assertEqual(invalid, 1)


if __name__ == "__main__":
    unittest.main()
