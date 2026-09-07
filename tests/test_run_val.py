from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import run_val


class RunValExecutionValidityTests(unittest.TestCase):
    def test_stale_plan_is_ignored_and_validity_metadata_enters_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = "study"
            problem_dir = (
                root
                / "llm-as-formalizer-agent"
                / "logistics"
                / "Natural_Logistics-100"
                / model
                / "p01"
            )
            problem_dir.mkdir(parents=True)
            (problem_dir / f"p01_{model}_plan.txt").write_text("stale plan")
            (problem_dir / "completion.json").write_text(
                json.dumps(
                    {
                        "complete": True,
                        "attempt_valid": True,
                        "problem": "p01",
                        "model_label": model,
                        "attempt_index": 1,
                        "selected_execution_try": 1,
                        "generation_success": False,
                        "resolved_config_sha256": "config",
                        "runtime_identity_sha256": "runtime",
                    }
                )
            )

            with redirect_stdout(io.StringIO()):
                run_val.validate_plan_batch(
                    "logistics",
                    "Natural_Logistics-100",
                    model,
                    [1],
                    "llm-as-formalizer-agent",
                    True,
                    out_dir_root=str(root),
                    workers=1,
                )

            csv_path = (
                problem_dir.parent
                / "llm-as-formalizer-agent_logistics_Natural_Logistics-100_"
                "study_results.csv"
            )
            with csv_path.open(newline="") as stream:
                row = next(csv.DictReader(stream))

        self.assertEqual(row["plan_found"], "no")
        self.assertIn("no selected effective-valid execution", row["error, if not found"])
        self.assertEqual(row["execution_validity_revision"], "1")
        self.assertEqual(row["execution_validity_complete"], "True")
        self.assertEqual(len(row["execution_validity_state_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
