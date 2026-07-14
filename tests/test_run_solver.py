from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import run_solver as solver_module


class FakeResponse:
    def __init__(self, payload, *, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


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
            responses = [
                FakeResponse({"result": "/check/task-1"}),
                FakeResponse(
                    {
                        "error": (
                            "There was a server-side error trying to run "
                            "a planutils package."
                        )
                    }
                ),
            ]
            with patch.object(solver_module.requests, "post", side_effect=responses):
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
            response = FakeResponse(ValueError("bad json"), text="upstream proxy error")
            with patch.object(solver_module.requests, "post", return_value=response):
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
            responses = [
                FakeResponse({"result": "/check/task-oom"}),
                FakeResponse(
                    {
                        "status": "ok",
                        "result": {
                            "stdout": "Killed\n",
                            "stderr": "",
                            "call": "timeout 20 planutils run dual-bfws-ffparser",
                            "output": {"plan": ""},
                            "output_type": "generic",
                        },
                    }
                ),
            ]
            with patch.object(solver_module.requests, "post", side_effect=responses):
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

        def fake_run_solver(domain, data, problem, model, solver, prediction_type, out_dir_root):
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


if __name__ == "__main__":
    unittest.main()
