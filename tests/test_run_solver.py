from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import run_solver as solver_module
from api_providers import sanitize_model_name
from agent_formalizer.results.execution_validity import append_manual_event


class RunSolverModelLabelTests(unittest.TestCase):
    def test_api_batch_reads_generated_files_and_writes_outcome_for_each_provider(self):
        models = [
            "gemini-3.1-flash-lite",
            "deepseek-chat",
            "alibaba/qwen3.8-27b",
            "google-vertex/gemini-3.1-flash-lite",
        ]
        for model in models:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as root:
                label = sanitize_model_name(model)
                directory = (Path(root) / "llm-as-formalizer-api" / "barman"
                             / "Heavily_Templated_Barman-100" / label / "p01")
                directory.mkdir(parents=True)
                domain = "(define (domain fixture))"
                problem = "(define (problem fixture) (:domain fixture))"
                (directory / f"p01_{label}_df.pddl").write_text(domain)
                (directory / f"p01_{label}_pf.pddl").write_text(problem)
                with patch.object(solver_module, "solve_pddl", return_value=(False, "fixture input error")) as solve:
                    solver_module.run_solver_batch(
                        "barman", model, "Heavily_Templated_Barman-100", [1],
                        "dual-bfws-ffparser", "llm-as-formalizer-api",
                        out_dir_root=root, solver_backend="public",
                    )
                self.assertEqual(solve.call_args.args, (domain, problem))
                self.assertIn("fixture input error", (directory / f"p01_{label}_error.txt").read_text())

    def test_non_api_legacy_model_label_is_preserved(self):
        self.assertEqual(solver_module._model_output_name("google/legacy-model", "llm-as-formalizer"), "legacy-model")

    def test_logits_model_id_uses_direct_api_filesystem_label(self):
        self.assertEqual(
            solver_module._model_output_name("logits/Qwen/Qwen3.5-4B"),
            "logits__Qwen__Qwen3.5-4B",
        )


class RunSolverFailureHandlingTests(unittest.TestCase):
    prediction_type = "llm-as-formalizer-agent"
    domain = "logistics"
    dataset = "Heavily_Templated_Logistics-100"
    model = "test-model"
    solver = "dual-bfws-ffparser"

    def _problem_dir(self, root: str, problem: str) -> Path:
        return (
            Path(root)
            / self.prediction_type
            / self.domain
            / self.dataset
            / self.model
            / problem
        )

    def _write_pddl(self, root: str, problem: str = "p01") -> Path:
        problem_dir = self._problem_dir(root, problem)
        problem_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{problem}_{self.model}"
        (problem_dir / f"{stem}_df.pddl").write_text("(define (domain mock))")
        (problem_dir / f"{stem}_pf.pddl").write_text(
            "(define (problem mock-problem) (:domain mock))"
        )
        return problem_dir

    def test_terminal_error_without_result_is_recorded_per_problem(self):
        with tempfile.TemporaryDirectory() as root:
            problem_dir = self._write_pddl(root)
            diagnostic = (
                "solver request failed\n"
                "stage: terminal\n"
                "terminal response missing top-level 'result'\n"
                'response_json:\n{"error": "server-side error"}'
            )
            with patch.object(
                solver_module, "solve_pddl", return_value=(False, diagnostic)
            ):
                passed = solver_module._run_solver_one(
                    1,
                    self.domain,
                    self.dataset,
                    self.model,
                    self.solver,
                    self.prediction_type,
                    root,
                    self.model,
                )

            self.assertFalse(passed)
            error_file = problem_dir / f"p01_{self.model}_error.txt"
            diagnostic = error_file.read_text()
            self.assertIn("solver_status: failed", diagnostic)
            self.assertIn("stage: terminal", diagnostic)
            self.assertIn("terminal response missing top-level 'result'", diagnostic)
            self.assertIn("server-side error", diagnostic)
            self.assertIn('"error"', diagnostic)

    def test_invalid_json_becomes_a_single_solver_failure(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_pddl(root)
            diagnostic = (
                "solver request failed\n"
                "stage: submit\n"
                "response was not valid JSON\n"
                "response_body:\nupstream proxy error"
            )
            with patch.object(
                solver_module, "solve_pddl", return_value=(False, diagnostic)
            ):
                passed, diagnostic = solver_module.run_solver(
                    self.domain,
                    self.dataset,
                    "p01",
                    self.model,
                    self.solver,
                    self.prediction_type,
                    out_dir_root=root,
                )

            self.assertFalse(passed)
            self.assertIn("stage: submit", diagnostic)
            self.assertIn("response was not valid JSON", diagnostic)
            self.assertIn("upstream proxy error", diagnostic)

    def test_empty_plan_with_killed_stdout_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_pddl(root)
            diagnostic = (
                "solver request failed\n"
                "stage: solver-result\n"
                "dual-bfws-ffparser returned no plan; stdout: Killed"
            )
            with patch.object(
                solver_module, "solve_pddl", return_value=(False, diagnostic)
            ):
                passed, diagnostic = solver_module.run_solver(
                    self.domain,
                    self.dataset,
                    "p01",
                    self.model,
                    self.solver,
                    self.prediction_type,
                    out_dir_root=root,
                )

            self.assertFalse(passed)
            self.assertIn("stage: solver-result", diagnostic)
            self.assertIn("Killed", diagnostic)

    def test_exhausted_exceptions_do_not_abort_the_remaining_batch(self):
        calls = []

        def fake_run_solver(
            domain,
            data,
            problem,
            model,
            solver,
            prediction_type,
            out_dir_root,
            solver_base_url,
        ):
            calls.append(problem)
            if problem == "p01":
                raise RuntimeError("simulated transport failure")
            return True, {"plan": "(noop)"}

        with tempfile.TemporaryDirectory() as root:
            with patch.object(solver_module, "run_solver", side_effect=fake_run_solver):
                solver_module.run_solver_batch(
                    self.domain,
                    self.model,
                    self.dataset,
                    [1, 2],
                    self.solver,
                    self.prediction_type,
                    out_dir_root=root,
                    workers=1,
                )

            p01_error = self._problem_dir(root, "p01") / f"p01_{self.model}_error.txt"
            p02_plan = self._problem_dir(root, "p02") / f"p02_{self.model}_plan.txt"
            diagnostic = p01_error.read_text()
            self.assertEqual(calls, ["p01", "p01", "p01", "p02"])
            self.assertIn("all 3 attempt(s)", diagnostic)
            self.assertIn("RuntimeError: simulated transport failure", diagnostic)
            self.assertEqual(p02_plan.read_text(), "(noop)")

    def test_agent_evaluation_reads_selected_frozen_execution_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            problem_dir = self._write_pddl(root)
            (problem_dir / f"p01_{self.model}_df.pddl").write_text("stale-domain")
            execution = problem_dir / "executions" / "execution-001"
            frozen = execution / "frozen_workspace"
            frozen.mkdir(parents=True)
            (frozen / "domain.pddl").write_text("selected-domain")
            (frozen / "problem.pddl").write_text("selected-problem")
            completion = {
                "complete": True,
                "attempt_valid": True,
                "problem": "p01",
                "model_label": self.model,
                "attempt_index": 1,
                "selected_execution_try": 1,
                "generation_success": True,
                "resolved_config_sha256": "config",
                "runtime_identity_sha256": "runtime",
                "evidence": {"frozen_workspace_artifacts": {}},
            }
            completion_path = problem_dir / "completion.json"
            completion_path.write_text(json.dumps(completion))

            with patch.object(
                solver_module,
                "solve_pddl",
                return_value=(False, "expected diagnostic"),
            ) as solve:
                passed, diagnostic = solver_module.run_solver(
                    self.domain,
                    self.dataset,
                    "p01",
                    self.model,
                    self.solver,
                    self.prediction_type,
                    out_dir_root=root,
                )

            self.assertFalse(passed)
            self.assertEqual(diagnostic, "expected diagnostic")
            self.assertEqual(solve.call_args.args[:2], ("selected-domain", "selected-problem"))

            cell = problem_dir.parent
            append_manual_event(
                cell,
                action="invalidate",
                problem="p01",
                attempt_index=1,
                execution_try=1,
                operator="benchmark-owner",
                reason_code="tool_infra.solver_transport",
                reason="agent-visible solver transport error",
                evidence_paths=[completion_path],
                result_visibility="blind",
                timestamp="2026-09-01T00:00:00Z",
            )
            with patch.object(solver_module, "solve_pddl") as solve:
                passed, diagnostic = solver_module.run_solver(
                    self.domain,
                    self.dataset,
                    "p01",
                    self.model,
                    self.solver,
                    self.prediction_type,
                    out_dir_root=root,
                )
            self.assertFalse(passed)
            self.assertIn("selected effective-valid execution", diagnostic)
            solve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
