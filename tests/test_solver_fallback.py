"""Public/local routing and logical accounting without external services."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_solver
from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.external_calls import ExternalCallInvalid
from agent_formalizer.external_calls.checkpoint import RequestCheckpoint
from agent_formalizer.external_calls.solver import Response
from agent_formalizer.external_calls.solver_fallback import POLICY_ID, solve, validate_local_health
from agent_formalizer.tools import resolve_agent_tools
from agent_formalizer.tools.solver.remote_client import solve_pddl, solver_failure
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.claws.minimum.workspace import MinimumHostWorkspace
from local_solver import base_urls_for_backend, fallback_url_for_backend

PUBLIC = "https://public.test"
LOCAL = "http://local.test:8769"
PACKAGE = "dual-bfws-ffparser"
SUBMIT = Response(status=200, payload={"result": "/check/task"})
HEALTH = Response(status=200, payload={"status": "ok", "backend": "local-planutils",
    "config": {"timeout_seconds": 90., "allowed_solvers": [PACKAGE, "lama-first"]}})


def terminal(stdout="", stderr="", output=None):
    return Response(status=200, payload={"status": "ok", "result": {
        "stdout": stdout, "stderr": stderr, "output": output or {}}})


PLAN = terminal("Plan found with cost: 1", output={"plan": "(move a b)\n"})
TIMEOUT = terminal("Request Time Out")
PLANUTILS = Response(status=200, payload={
    "error": "There was a server-side error trying to run a planutils package."})


class Script:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.now = 0.
        self.events = []
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response, elapsed = next(self.rows)
        self.now += elapsed
        return response

    def sleep(self, seconds):
        self.now += seconds

    def run(self, **overrides):
        options = dict(solver=PACKAGE, base_url=PUBLIC, fallback_base_url=LOCAL,
            format_failure=solver_failure, request=self.request,
            monotonic=lambda: self.now, sleep=self.sleep, event=self.events.append,
            poll_interval_seconds=0.)
        options.update(overrides)
        return solve("domain exact\n", "problem exact\n", **options)


class FallbackRulesTests(unittest.TestCase):
    def test_remote_meaningful_results_never_fall_back(self):
        for outcome in (PLAN, terminal(stderr="domain: syntax error in line 1, foo"),
                terminal("ff: goal can be simplified to FALSE. No plan will solve it"),
                terminal(stderr="increase MAX_TYPES"),
                terminal("ff: goal can be simplified to TRUE. The empty plan solves it")):
            with self.subTest(payload=outcome.payload):
                script = Script([(SUBMIT, 1.), (outcome, 2.)])
                result = script.run()
                self.assertEqual(result[2], 3.)
                self.assertEqual(len(script.requests), 2)
                self.assertFalse(any(e.get("action") == "fallback" for e in script.events))

    def test_three_remote_errors_fall_back_only_final_local_solve_charged(self):
        script = Script([(SUBMIT, 1.), (PLANUTILS, 30.)] * 3 +
                        [(HEALTH, 0.), (SUBMIT, 1.), (PLAN, 90.)])
        result = script.run()
        self.assertTrue(result[0])
        self.assertAlmostEqual(script.now, 204.)
        self.assertAlmostEqual(result[2], 91.)
        self.assertEqual([e["backend"] for e in script.events if e.get("action") == "return"], ["local"])
        self.assertEqual([e["planner_timeout_seconds"] for e in script.events
                          if e.get("action") == "backend_start"], [30., 90.])
        submissions = [r for r in script.requests if r[1].endswith("/solve")]
        self.assertEqual(len(submissions), 4)
        self.assertTrue(all(r[2]["body"] == {"domain": "domain exact\n", "problem": "problem exact\n"}
                            for r in submissions))
        # HTTP timeouts are not the planner's run limit.
        self.assertTrue(all(r[2]["timeout"] <= 30. for r in script.requests))

    def test_both_budgets_exhausted_only_last_local_timeout_visible_and_charged(self):
        script = Script([(SUBMIT, 1.), (TIMEOUT, 30.)] * 3 + [(HEALTH, 0.)] +
                        [(SUBMIT, 1.), (TIMEOUT, 90.)] * 3)
        result = script.run()
        self.assertFalse(result[0])
        self.assertIn("Request Time Out", result[1])
        self.assertAlmostEqual(script.now, 406.)
        self.assertAlmostEqual(result[2], 91.)
        self.assertEqual(len([e for e in script.events if e.get("action") == "retry"]), 4)
        self.assertEqual(len([r for r in script.requests if r[1].endswith("/solve")]), 6)

    def test_both_backends_transient_infra_exhaustion_invalidates(self):
        for failure in (Response(status=429), Response(error="Connection refused", error_type="OSError")):
            script = Script([(failure, 1.)] * 3 + [(HEALTH, 0.)] + [(failure, 1.)] * 3)
            with self.assertRaises(ExternalCallInvalid):
                script.run()
            self.assertFalse(any(e.get("action") == "return" for e in script.events))
            self.assertEqual(script.events[-1]["action"], "wrapper_invalid")
            self.assertEqual(script.events[-1]["backend"], "local")

    def test_remote_transport_exhaustion_can_recover_locally(self):
        script = Script([(Response(status=429), 1.)] * 3 +
                        [(HEALTH, 0.), (SUBMIT, 1.), (PLAN, 2.)])
        self.assertEqual(script.run()[2], 3.)
        self.assertAlmostEqual(script.now, 26.)

    def test_poll_retries_keep_local_task_and_exclude_failed_poll_time(self):
        script = Script([(SUBMIT, 1.), (PLANUTILS, 2.)] * 3 +
                        [(HEALTH, 0.), (SUBMIT, 1.),
                         (Response(error="No route to host", error_type="OSError"), 10.), (PLAN, 2.)])
        self.assertAlmostEqual(script.run()[2], 3.)
        local_submits = [r for r in script.requests if r[1] == LOCAL + "/package/" + PACKAGE + "/solve"]
        self.assertEqual(len(local_submits), 1)

    def test_fixed_security_configuration_errors_do_not_fall_back(self):
        for failure in (Response(status=401), Response(status=403), Response(status=404),
                Response(status=302), Response(error="bad certificate", error_type="SSLCertVerificationError"),
                Response(status=200, payload={"error": "Package x is not installed"}),
                Response(status=200, payload={"result": "https://untrusted.test/check/task"})):
            with self.subTest(failure=failure):
                script = Script([(failure, 1.)])
                with self.assertRaises(ExternalCallInvalid):
                    script.run()
                self.assertEqual(len(script.requests), 1)
                self.assertFalse(any(e.get("action") == "fallback" for e in script.events))

    def test_cancel_before_or_during_recovery_does_not_switch_backends(self):
        for cutoff in (0., 2.):
            script = Script([(Response(status=429), 1.)] * 3)
            with self.assertRaises(ExternalCallInvalid) as caught:
                script.run(cancelled=lambda: script.now >= cutoff)
            self.assertEqual(caught.exception.reason, "external_call_cancelled")
            self.assertTrue(all(r[1].startswith(PUBLIC) for r in script.requests))

    def test_control_failure_is_not_solver_recovery(self):
        script = Script([(Response(status=429), 1.)])

        def broken_control(value):
            if value.get("action") == "retry":
                raise ExternalCallInvalid("external_call_control_failed")

        with self.assertRaises(ExternalCallInvalid) as caught:
            script.run(event=broken_control)
        self.assertEqual(caught.exception.reason, "external_call_control_failed")
        self.assertEqual(len(script.requests), 1)

    def test_pending_task_cap_switches_without_duplicate_remote_job(self):
        pending = Response(status=200, payload={"status": "PENDING"})
        script = Script([(SUBMIT, 1.)] + [(pending, 30.)] * 6 +
                        [(HEALTH, 0.), (SUBMIT, 1.), (PLAN, 2.)])
        self.assertTrue(script.run()[0])
        self.assertEqual(len([r for r in script.requests if r[1] == PUBLIC + "/package/" + PACKAGE + "/solve"]), 1)
        fallback = next(e for e in script.events if e.get("action") == "fallback")
        self.assertEqual(fallback["reason"], "solver_task_wait_exhausted")

    def test_backend_guard_bounds_retry_after(self):
        busy = Response(status=429, headers={"Retry-After": "60"})
        script = Script([(busy, 30.)] * 2 + [(busy, 31.), (HEALTH, 0.), (SUBMIT, 1.), (PLAN, 2.)])
        self.assertTrue(script.run()[0])
        self.assertAlmostEqual(script.now, 214.)
        self.assertEqual(next(e for e in script.events if e.get("action") == "fallback")["reason"],
                         "solver_backend_deadline")

    def test_real_90_second_local_configuration_required(self):
        for payload in ([], None, {"status": "ok"},
                {**HEALTH.payload, "config": {"timeout_seconds": 60., "allowed_solvers": [PACKAGE]}},
                {**HEALTH.payload, "config": {"timeout_seconds": 90., "allowed_solvers": None}},
                {**HEALTH.payload, "config": {"timeout_seconds": 90., "allowed_solvers": []}}):
            script = Script([(Response(status=429), 1.)] * 3 + [(Response(status=200, payload=payload), 0.)])
            with self.assertRaises(ExternalCallInvalid) as caught:
                script.run()
            self.assertEqual(caught.exception.reason, "solver_fallback_configuration_error")
            self.assertEqual(script.requests[-1][:2], ("GET", LOCAL + "/__benchmark__/health"))
        validate_local_health(HEALTH.payload, solver=PACKAGE)

    def test_health_transport_failure_uses_same_local_retry_budget(self):
        script = Script([(Response(status=429), 1.)] * 3 +
                        [(Response(status=503), 10.), (HEALTH, 0.), (SUBMIT, 1.), (PLAN, 2.)])
        self.assertAlmostEqual(script.run()[2], 3.)
        self.assertEqual(len([e for e in script.events if e.get("backend") == "local"
                             and e.get("action") == "retry"]), 1)
        self.assertEqual(next(e for e in script.events if e.get("backend") == "local"
                              and "physical_attempt" in e)["request_source"], "local_health")

    def test_health_rejection_is_not_pddl_input_error(self):
        for status in (400, 413, 415, 422):
            script = Script([(Response(status=429), 1.)] * 3 + [(Response(status=status), 1.)])
            with self.assertRaises(ExternalCallInvalid) as caught:
                script.run()
            self.assertEqual(caught.exception.reason, "solver_fallback_configuration_error")

    def test_fallback_discards_last_remote_candidate_in_same_checkpoint(self):
        script = Script([(SUBMIT, 1.), (PLANUTILS, 2.)] * 3 +
                        [(HEALTH, 0.), (SUBMIT, 1.), (TIMEOUT, 90.), (SUBMIT, 1.), (PLAN, 2.)])
        checkpoint = RequestCheckpoint(b"one agent tool request", event=script.events.append)

        def event(value):
            script.events.append(value)
            if value.get("action") in {"retry", "fallback"}:
                checkpoint.discard(value["reason"])

        self.assertAlmostEqual(script.run(event=event)[2], 3.)
        self.assertEqual(checkpoint.discarded, 4)  # 2 remote + switch + 1 local
        checkpoint.commit()
        self.assertEqual(len([e for e in script.events if e.get("action") == "return"]), 1)

    def test_requested_package_preserved_and_origins_validated(self):
        script = Script([(Response(status=429), 1.)] * 3 +
                        [(HEALTH, 0.), (SUBMIT, 1.), (PLAN, 2.)])
        script.run(solver="lama-first")
        self.assertTrue(all("/package/lama-first/" in r[1] for r in script.requests if r[1].endswith("/solve")))
        for bad in (PUBLIC, "http://u:p@local.test", "http://local.test/unconfigured", "file:///tmp/x"):
            with self.assertRaises(ValueError):
                Script([]).run(fallback_base_url=bad)


class FallbackIntegrationTests(unittest.TestCase):
    def test_client_commits_only_wrapper_charge(self):
        with patch("agent_formalizer.external_calls.solver_fallback.solve",
                   return_value=(True, {"plan": "(a)"}, 91.)) as wrapper:
            charges = []
            self.assertEqual(solve_pddl("domain", "problem", base_url=PUBLIC,
                fallback_base_url=LOCAL, charge=charges.append), (True, {"plan": "(a)"}))
        self.assertEqual(charges, [91.])
        self.assertEqual(wrapper.call_args.kwargs["fallback_base_url"], LOCAL)

    def test_opt_in_identity_all_five_harnesses_and_defaults_unchanged(self):
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool_call_checkpoint.json")
        for harness in ("openclaw", "hermes", "generic", "nanobot", "zeroclaw"):
            wrapper = profile.resolve(harness, solver_backend="public_then_local")
            public = profile.resolve(harness, solver_backend="public")
            self.assertNotEqual(wrapper.sha256, public.sha256)
            self.assertEqual(wrapper.raw["resolved"]["solver_backend_policy"], POLICY_ID)
            self.assertNotIn("solver_backend_policy", public.raw["resolved"])
            self.assertEqual(profile.resolve(harness).solver_backend, "local")
        with self.assertRaises(ValueError):
            load_benchmark_profile(
                HISTORICAL_PROFILES_DIR / "native_safety_native_clean.json"
            ).resolve("openclaw", solver_backend="public_then_local")
        current = load_benchmark_profile().resolve("openclaw", solver_backend="public_then_local")
        self.assertEqual(current.raw["resolved"]["solver_backend_policy"], POLICY_ID)
        self.assertEqual(current.agent_tools, [])
        self.assertEqual(base_urls_for_backend("public_then_local"), base_urls_for_backend("public"))
        self.assertIsNone(fallback_url_for_backend("public"))

    def test_container_gateway_receives_both_origins_and_recovery(self):
        adapter = SimpleNamespace(
            resolved_config=SimpleNamespace(raw={"resolved": {"solver_error_routing": "solver-transient-v1"}}),
            solver_backend=lambda: "public_then_local", solver_upstream_base=lambda **kw: PUBLIC,
            solver_fallback_base=lambda **kw: LOCAL)
        workspace = AgentWorkspace("fallback-test", "mock-container", adapter)
        with tempfile.TemporaryDirectory() as tmp:
            workspace._gateway_control_dir = Path(tmp) / "control"
            workspace._gateway_evidence_dir = Path(tmp) / "evidence"
            workspace._gateway_control_dir.mkdir()
            (workspace._gateway_control_dir / "solver.json").write_text('{"phase": "idle"}')
            with patch("agent_formalizer.workspace.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                workspace._start_tool_gateway(resolve_agent_tools(["pddl_solver"])[0])
        command = run.call_args_list[0].args[0]
        for env in ("PDDL_SOLVER_BACKEND=public_then_local", "PDDL_SOLVER_FALLBACK_BASE=" + LOCAL,
                    "PDDL_SOLVER_UPSTREAM_BASE=" + PUBLIC, "PDDL_SOLVER_UPSTREAM_HEALTH_REQUIRED=1",
                    "PDDL_SOLVER_ERROR_ROUTING=solver-transient-v1"):
            self.assertIn(env, command)

    def test_evaluation_exhaustion_recorded_once_and_evidence_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "llm-as-formalizer-agent/logistics/data/model/p01"
            directory.mkdir(parents=True)
            for suffix in ("df", "pf"):
                (directory / f"p01_model_{suffix}.pddl").write_text("(pddl)")

            def failed(*args, **kwargs):
                self.assertEqual(kwargs["fallback_base_url"], fallback_url_for_backend("public_then_local"))
                self.assertEqual(kwargs["base_url"], base_urls_for_backend("public")[0])
                kwargs["event"]({"action": "wrapper_invalid", "reason": "solver_rate_limited", "backend": "local"})
                raise ExternalCallInvalid("solver_rate_limited", diagnostic="final actual diagnostic")

            with patch.object(run_solver, "solve_pddl", side_effect=failed) as client:
                self.assertFalse(run_solver._run_solver_one(1, "logistics", "data", "model", PACKAGE,
                    "llm-as-formalizer-agent", tmp, "model",
                    solver_backend="public_then_local"))
            self.assertEqual(client.call_count, 1)
            self.assertIn("final actual diagnostic", (directory / "p01_model_error.txt").read_text())
            events = directory / "p01_model_solver_events.jsonl"
            records = [json.loads(line) for line in events.read_text().splitlines()]
            self.assertEqual(next(r for r in records if r["action"] == "wrapper_invalid")["backend"], "local")
            self.assertEqual(records[-1]["action"], "evaluation_failed")
            self.assertEqual(events.stat().st_mode & 0o777, 0o600)

    def test_minimum_host_gateway_gets_local_host_fallback(self):
        adapter = SimpleNamespace(
            resolved_config=SimpleNamespace(raw={"resolved": {"solver_error_routing": "solver-transient-v1",
                                                               "environment": {"fixed": {}}}}),
            solver_backend=lambda: "public_then_local", solver_upstream_base=lambda **kw: PUBLIC,
            solver_fallback_base=lambda **kw: fallback_url_for_backend("public_then_local", **kw))
        with tempfile.TemporaryDirectory() as tmp, patch("agent_formalizer.claws.minimum.workspace._loopback_port", return_value=54321):
            root = Path(tmp)
            workspace = MinimumHostWorkspace("fallback", "mock-runtime", adapter, artifact_dir=root)
            workspace._control_dir = root
            workspace._cancel_path = root / "cancel"
            (root / "solver.json").write_text('{"phase": "idle"}')
            with patch.object(workspace, "_spawn") as spawn, patch.object(workspace, "_wait_healthy"):
                workspace._start_solver_gateway()
            env = spawn.call_args.kwargs["env"]
        self.assertEqual(env["PDDL_SOLVER_UPSTREAM_BASE"], PUBLIC)
        self.assertEqual(env["PDDL_SOLVER_FALLBACK_BASE"], fallback_url_for_backend("public_then_local"))
        self.assertEqual(env["PDDL_SOLVER_ERROR_ROUTING"], "solver-transient-v1")
        self.assertEqual(env["PDDL_SOLVER_UPSTREAM_HEALTH_REQUIRED"], "1")


if __name__ == "__main__":
    unittest.main()
