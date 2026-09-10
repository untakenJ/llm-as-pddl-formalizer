"""Full evaluator -> shared client -> real recovery engines, virtual upstream."""
import functools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_solver
from agent_formalizer.external_calls import solver, solver_fallback
from test_solver_fallback import Script, SUBMIT, PLAN, PLANUTILS, TIMEOUT, HEALTH, terminal


class EvaluationRecoveryTests(unittest.TestCase):
    def evaluate(self, rows, backend="public", problems=(1,)):
        script = Script(rows)
        engine = solver_fallback if backend == "public_then_local" else solver
        real_solve = engine.solve
        snapshots = {}
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / "llm-as-formalizer-api/logistics/data/model"
            for number in problems:
                directory = model_dir / f"p{number:02}"
                directory.mkdir(parents=True)
                for suffix in ("df", "pf"):
                    (directory / f"p{number:02}_model_{suffix}.pddl").write_text(f"exact-{suffix}\n")
            controlled = functools.partial(real_solve, request=script.request,
                monotonic=lambda: script.now, sleep=script.sleep, poll_interval_seconds=0.)
            with patch.object(engine, "solve", side_effect=controlled):
                run_solver.run_solver_batch("logistics", "model", "data", problems,
                    "dual-bfws-ffparser", "llm-as-formalizer-api", out_dir_root=tmp,
                    solver_backend=backend)
            for file in model_dir.rglob("*"):
                if file.is_file():
                    snapshots[str(file.relative_to(model_dir))] = file.read_text()
                    if file.suffix == ".jsonl":
                        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertTrue(all(r[2]["body"] == {"domain": "exact-df\n", "problem": "exact-pf\n"}
                for r in script.requests if r[1].endswith("/solve")))
        return script, snapshots

    def test_all_backends_hide_transient_planutils_then_return_plan(self):
        for backend in ("public", "local", "public_then_local"):
            with self.subTest(backend=backend):
                script, files = self.evaluate([(SUBMIT, 1.), (PLANUTILS, 2.),
                                              (SUBMIT, 1.), (PLAN, 2.)], backend)
                self.assertAlmostEqual(script.now, 11.)
                self.assertIn("p01/p01_model_plan.txt", files)
                self.assertNotIn("p01/p01_model_error.txt", files)
                events = [json.loads(x) for x in files["p01/p01_model_solver_events.jsonl"].splitlines()]
                self.assertEqual(len([e for e in events if e.get("action") == "retry"]), 1)
                self.assertEqual(events[-1]["action"], "evaluation_return")
                self.assertTrue(events[-1]["plan_found"])
                self.assertEqual(len({e["evaluation_request_id"] for e in events}), 1)

    def test_transport_poll_retry_preserves_task_and_continues_batch_on_exhaustion(self):
        refused = solver.Response(error="Connection refused", error_type="ConnectionRefusedError")
        script, files = self.evaluate([(SUBMIT, 1.), (refused, 1.)] + [(refused, 1.)] * 2 +
                                     [(SUBMIT, 1.), (PLAN, 1.)], problems=(1, 2))
        self.assertEqual(len(script.requests), 6)  # No outer 3x multiplication.
        self.assertEqual(len({request[1] for request in script.requests[1:4]}), 1)
        self.assertIn("solver infrastructure failure: solver_transport_error", files["p01/p01_model_error.txt"])
        self.assertIn("Connection refused", files["p01/p01_model_error.txt"])
        self.assertIn("p02/p02_model_plan.txt", files)

    def test_repeated_terminal_timeout_returns_last_diagnostic_after_three_solves(self):
        script, files = self.evaluate([(SUBMIT, 1.), (TIMEOUT, 30.)] * 3)
        self.assertEqual(len(script.requests), 6)
        self.assertAlmostEqual(script.now, 113.)
        self.assertIn("Request Time Out", files["p01/p01_model_error.txt"])
        events = [json.loads(x) for x in files["p01/p01_model_solver_events.jsonl"].splitlines()]
        self.assertEqual(next(e for e in events if e.get("action") == "return")["charged_seconds"], 31.)

    def test_pending_is_bounded_and_retains_task_evidence(self):
        pending = solver.Response(status=200, payload={"status": "PENDING"})
        script, files = self.evaluate([(SUBMIT, 1.), (pending, 90.), (pending, 90.)])
        self.assertEqual(len(script.requests), 3)
        error = files["p01/p01_model_error.txt"]
        self.assertIn("solver_task_wait_exhausted", error)
        self.assertIn("PENDING", error)
        self.assertIn("/check/task", error)

    def test_pending_public_switches_to_local_without_replaying_agent(self):
        pending = solver.Response(status=200, payload={"status": "PENDING"})
        script, files = self.evaluate([(SUBMIT, 1.), (pending, 90.), (pending, 90.),
                                      (HEALTH, 0.), (SUBMIT, 1.), (PLAN, 2.)], "public_then_local")
        events = [json.loads(x) for x in files["p01/p01_model_solver_events.jsonl"].splitlines()]
        self.assertEqual(len([e for e in events if e.get("action") == "fallback"]), 1)
        self.assertEqual(next(e for e in events if e.get("action") == "return")["charged_seconds"], 3.)
        self.assertIn("p01/p01_model_plan.txt", files)

    def test_no_retry_for_definitive_input_error_or_no_plan(self):
        for result in (terminal(stderr="syntax error in line 1"),
                       terminal("ff: goal can be simplified to FALSE. No plan will solve it")):
            script, files = self.evaluate([(SUBMIT, 1.), (result, 1.)], "public_then_local")
            self.assertEqual(len(script.requests), 2)
            self.assertIn("p01/p01_model_error.txt", files)


if __name__ == "__main__":
    unittest.main()
