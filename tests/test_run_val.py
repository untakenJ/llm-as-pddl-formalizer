from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import run_val
from api_providers import sanitize_model_name


class RunValApiModelLabelTests(unittest.TestCase):
    def test_api_formalizer_and_planner_plans_share_generation_label(self):
        for model in ("gemini-3.1-flash-lite", "deepseek-chat", "alibaba/qwen3.8-27b",
                      "google-vertex/gemini-3.1-flash-lite"):
            for prediction in ("llm-as-formalizer-api", "llm-as-planner-api"):
                with self.subTest(model=model, prediction=prediction), tempfile.TemporaryDirectory() as tmp:
                    label = sanitize_model_name(model)
                    directory = Path(tmp) / prediction / "logistics" / "Natural_Logistics-100" / label
                    plan_dir = directory / "p01" if prediction == "llm-as-formalizer-api" else directory
                    plan_dir.mkdir(parents=True)
                    plan = "(load-truck package1 truck1 location1)\n"
                    (plan_dir / f"p01_{label}_plan.txt").write_text(plan)
                    with patch.object(run_val, "validate_plan", return_value="Plan valid") as validate, redirect_stdout(io.StringIO()):
                        run_val.validate_plan_batch(
                            "logistics", "Natural_Logistics-100", model, [1],
                            prediction, True, out_dir_root=tmp,
                        )
                    validate.assert_called_once()
                    self.assertEqual(Path(validate.call_args.args[2]).read_text(), plan.strip())
                    csv_path = directory / f"{prediction}_logistics_Natural_Logistics-100_{label}_results.csv"
                    with csv_path.open() as stream:
                        row = next(csv.DictReader(stream))
                    self.assertEqual(row["plan_found"], "yes")
                    self.assertEqual(row["is_plan_correct"], "yes")


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
