from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.external_calls import Action, Decision, ExternalCallInvalid, RetryController, RetryPolicy
from agent_formalizer.external_calls.solver import Response, classify_response, solve
from agent_formalizer.external_calls.control import ToolControl, ToolControlMonitor, read_json, write_json
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.tools.solver.remote_client import solver_failure
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile


def terminal(stdout="", stderr="", output=None, **extra):
    return Response(status=200, payload={"status": "ok", "result": {
        "stdout": stdout, "stderr": stderr, "output": output or {}, **extra,
    }})


SUBMIT = Response(status=200, payload={"result": "/check/task"})
PLAN = terminal("Plan found with cost: 1", output={"plan": "(move a b)\n"})
TIMEOUT = terminal("Request Time Out")
GENERIC = Response(status=200, payload={"error": "There was a server-side error trying to run a planutils package."})


class RetryTests(unittest.TestCase):
    def test_shared_budget_retry_after_and_replay_boundary(self):
        now = [0.0]
        policy = RetryPolicy(2, (1., 2.), recovery_timeout_seconds=10)
        controller = RetryController(policy, monotonic=lambda: now[0])
        error = Decision(Action.RETRY, "429")
        self.assertEqual(controller.decide(error, headers={"Retry-After": "3"}), (Action.RETRY, 3.))
        self.assertEqual(controller.decide(error), (Action.RETRY, 2.))
        self.assertEqual(controller.decide(error)[0], Action.INVALIDATE)
        self.assertEqual(RetryController(policy).decide(error, replay_safe=False)[0], Action.INVALIDATE)
        self.assertEqual(policy.delay(0, {"Retry-After": "500"}), 60.)
        self.assertEqual(policy.delay(0, {"Retry-After": "Wed, 01 Jan 2025 00:00:03 GMT"}, now=1735689600), 3.)

    def test_invalid_limits_rejected(self):
        for count in (-1, True, 0.5):
            with self.assertRaises(ValueError):
                RetryPolicy(count, (1.,))


class SolverRulesTests(unittest.TestCase):
    def test_request_rejections_are_agent_visible_not_guessed_configuration_failures(self):
        for status in (400, 415, 422):
            self.assertEqual(classify_response(Response(status=status), stage="submit").action, Action.RETURN)
        for error in ("predicate foo does not exist", "problem does not contain a goal",
                      "Adaptor Not Found", "input not configured correctly"):
            result = classify_response(Response(status=200, payload={"error": error}), stage="poll")
            self.assertEqual((result.action, result.exhausted), (Action.RETRY, Action.RETURN))

    def test_local_exception_name_alone_cannot_prove_configuration_error(self):
        for kind in ("ValueError", "KeyError"):
            for local in ({"error": {"type": kind}}, {"error_type": kind}):
                result = classify_response(Response(status=200, payload={"local_backend": local}), stage="poll")
                self.assertEqual((result.action, result.exhausted), (Action.RETRY, Action.RETURN))

    def test_routing_table(self):
        rows = [
            (PLAN, Action.RETURN, Action.INVALIDATE, "solver_plan"),
            (terminal("ff: goal can be simplified to FALSE. No plan will solve it"), Action.RETURN, Action.INVALIDATE, "solver_unsolvable"),
            (terminal("ff: goal can be simplified to TRUE. The empty plan solves it"), Action.RETURN, Action.INVALIDATE, "solver_empty_plan"),
            (terminal(stderr="domain.pddl: syntax error in line 7, 'foo':"), Action.RETURN, Action.INVALIDATE, "solver_input_error"),
            (terminal(stderr="undeclared predicate boo"), Action.RETURN, Action.INVALIDATE, "solver_input_error"),
            (terminal(stderr="increase MAX_TYPES"), Action.RETURN, Action.INVALIDATE, "solver_input_capability_limit"),
            (TIMEOUT, Action.RETRY, Action.RETURN, "solver_execution_timeout"),
            (GENERIC, Action.RETRY, Action.RETURN, "solver_server_side_error"),
            (terminal(stderr="Segmentation fault (core dumped)"), Action.RETRY, Action.RETURN, "solver_internal_failure"),
            (terminal("Plan found with cost: NOTFOUND\nFast-BFS search completed in 1"), Action.RETRY, Action.RETURN, "solver_missing_terminal_result"),
            (terminal("Plan found with cost: NOTFOUND\nBFS search completed in 1"), Action.RETURN, Action.INVALIDATE, "solver_search_exhausted"),
            (Response(status=429), Action.RETRY, Action.INVALIDATE, "solver_rate_limited"),
            (Response(status=504), Action.RETRY, Action.INVALIDATE, "solver_service_unavailable"),
            (Response(status=413), Action.RETURN, Action.INVALIDATE, "solver_request_size_limit"),
            (Response(status=403), Action.INVALIDATE, Action.INVALIDATE, "solver_authentication_error"),
            (Response(status=302), Action.INVALIDATE, Action.INVALIDATE, "solver_untrusted_redirect"),
            (Response(error="bad certificate", error_type="SSLCertVerificationError"), Action.INVALIDATE, Action.INVALIDATE, "solver_certificate_error"),
            (Response(error="Connection refused", error_type="ConnectionRefusedError"), Action.RETRY, Action.INVALIDATE, "solver_transport_error"),
            (Response(status=200, payload={"error": "Package x is not installed"}), Action.INVALIDATE, Action.INVALIDATE, "solver_protocol_configuration_error"),
            (terminal(local_backend={"timed_out": True}), Action.RETRY, Action.RETURN, "solver_execution_timeout"),
            (Response(status=200, payload={"error": "local solver worker failed", "local_backend": {"error": {"type": "worker_protocol_error"}}}), Action.RETRY, Action.INVALIDATE, "solver_worker_service_error"),
        ]
        for response, action, exhausted, reason in rows:
            with self.subTest(reason=reason):
                result = classify_response(response, stage="poll")
                self.assertEqual((result.action, result.exhausted, result.reason), (action, exhausted, reason))

    def test_warning_and_first_phase_notfound_do_not_hide_plan(self):
        response = terminal("Plan found with cost: NOTFOUND\nFast-BFS search completed in 1\nPlan found with cost: 1", "warning: empty type", {"plan": "(a)"})
        self.assertEqual(classify_response(response, stage="poll").reason, "solver_plan")

    def test_object_names_are_not_process_diagnostics(self):
        response = terminal("Parsing domain killed\nPlan found with cost: 1", output={"plan": "(killed a)"})
        self.assertEqual(classify_response(response, stage="poll").reason, "solver_plan")

    def test_existing_plan_not_discarded_for_zero_cost_or_later_timeout(self):
        for response in (
            terminal("Plan found with cost: 0", output={"plan": "(zero-cost-action)"}),
            terminal("Request Time Out", output={"plan": "(a)"}, local_backend={"timed_out": True}),
        ):
            self.assertEqual(classify_response(response, stage="poll").reason, "solver_plan")

    def scripted(self, rows, *, poll_interval=0.):
        now = [0.]
        records, requests = [], []
        sequence = iter(rows)

        def request(method, url, **kwargs):
            response, duration = next(sequence)
            now[0] += duration
            requests.append((method, url, kwargs))
            return response

        def sleep(seconds):
            now[0] += seconds

        result = solve("domain", "problem", solver="dual-bfws-ffparser", base_url="https://solver.test",
            format_failure=solver_failure, request=request, monotonic=lambda: now[0], sleep=sleep,
            policy=RetryPolicy(2, (5., 15.), recovery_timeout_seconds=300), event=records.append,
            poll_interval_seconds=poll_interval)
        return result, records, requests, now[0]

    def test_failed_solves_and_backoff_not_charged_only_last_timeout(self):
        result, records, requests, wall = self.scripted([(SUBMIT, 1.), (TIMEOUT, 30.)] * 3)
        self.assertFalse(result[0])
        self.assertIn("Request Time Out", result[1])
        self.assertAlmostEqual(result[2], 31.)
        self.assertAlmostEqual(wall, 113.)
        self.assertEqual(len([x for x in records if x.get("action") == "retry"]), 2)
        self.assertEqual([x[2]["body"] for x in requests[::2]], [{"domain": "domain", "problem": "problem"}] * 3)

    def test_retry_can_recover_and_return_different_actual_result(self):
        result, records, _, wall = self.scripted([(SUBMIT, 1.), (GENERIC, 2.), (SUBMIT, 1.), (PLAN, 2.)])
        self.assertEqual(result[:2], (True, {"plan": "(move a b)\n"}))
        self.assertAlmostEqual(result[2], 3.)
        self.assertAlmostEqual(wall, 11.)

    def test_transport_retries_keep_task_and_hide_failed_poll_time(self):
        failure = Response(error="No route to host", error_type="OSError")
        result, _, requests, wall = self.scripted([(SUBMIT, 1.), (failure, 10.), (PLAN, 2.)])
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[1][1], requests[2][1])
        self.assertAlmostEqual(result[2], 3.)
        self.assertAlmostEqual(wall, 18.)

    def test_repeated_429_invalidates(self):
        with self.assertRaises(ExternalCallInvalid) as caught:
            self.scripted([(Response(status=429), 1.)] * 3)
        self.assertEqual(caught.exception.reason, "solver_rate_limited")

    def test_mixed_errors_not_evidence_of_repeated_input_failure(self):
        with self.assertRaises(ExternalCallInvalid):
            self.scripted([(Response(status=429), 1.), (Response(status=429), 1.), (SUBMIT, 1.), (TIMEOUT, 30.)])

    def test_pending_not_resubmitted(self):
        result, _, requests, _ = self.scripted([(SUBMIT, 1.), (Response(payload={"status": "PENDING"}), 1.), (PLAN, 2.)], poll_interval=1.)
        self.assertAlmostEqual(result[2], 5.)
        self.assertEqual([r[1] for r in requests].count("https://solver.test/package/dual-bfws-ffparser/solve"), 1)

    def test_cross_origin_reference_invalidates_without_following(self):
        with self.assertRaises(ExternalCallInvalid) as caught:
            self.scripted([(Response(status=200, payload={"result": "https://elsewhere.test/check/x"}), 1.)])
        self.assertEqual(caught.exception.reason, "solver_untrusted_task_url")


class TimingControlTests(unittest.TestCase):
    def test_stuck_docker_pause_cancels_instead_of_leaving_clock_paused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solver.json"
            write_json(path, {"phase": "running", "pause_requested": True})
            workspace = AgentWorkspace("external-test", "mock-container", SimpleNamespace())
            workspace._solver_control_monitor = ToolControlMonitor(path)
            clock = AttemptClock(10)

            def run(command, **kwargs):
                self.assertEqual(kwargs["timeout"], 5)
                if command[:2] == ["docker", "pause"]:
                    raise subprocess.TimeoutExpired(command, 5)
                return SimpleNamespace(returncode=0)

            with patch("agent_formalizer.workspace.subprocess.run", side_effect=run), self.assertLogs("agent_formalizer.workspace", level="ERROR"):
                workspace.start_model_gateway_monitor(clock)
                workspace._gateway_monitor_thread.join(timeout=2)
                workspace.stop_model_gateway_monitor()
            self.assertEqual(workspace.gateway_monitor_error(), "external_call_control_failed")
            self.assertEqual(clock.cancellation_reason(), "external_call_control_failed")
            self.assertFalse(clock.snapshot()["paused"])

    def test_overlap_with_committed_stream_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solver.json"
            write_json(path, {"phase": "running", "pause_requested": True})
            result = ToolControlMonitor(path).merge({"active_committed_streams": 1}, AttemptClock(10))
            self.assertEqual(result["terminal_infra_error"]["reason"], "external_call_stream_overlap")

    def test_cancelled_call_does_not_wait_for_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            control = ToolControl(Path(directory) / "solver.json", cancelled=lambda: True)
            with self.assertRaises(ExternalCallInvalid) as caught:
                control.begin()
            self.assertEqual(caught.exception.reason, "external_call_cancelled")

    def test_escrow_charge_and_idempotent_settlement(self):
        now = [100.]
        with tempfile.TemporaryDirectory() as directory, patch("agent_formalizer.claws.base.time.monotonic", side_effect=lambda: now[0]):
            clock = AttemptClock(40)
            path = Path(directory) / "solver.json"
            monitor = ToolControlMonitor(path)
            now[0] += 2
            clock.pause()
            now[0] += 80
            write_json(path, {"phase": "settle", "pause_requested": True, "call_id": "x", "charged_seconds": 31})
            monitor.merge({}, clock)
            monitor.merge({}, clock)
            self.assertEqual(clock.remaining(), 7.)
            self.assertFalse(monitor.acknowledge(paused=True, clock=clock))
            self.assertEqual(read_json(monitor.ack_path)["status"], "charged")
            clock.resume()
            self.assertEqual(clock.snapshot()["active_duration_seconds"], 33.)
            self.assertEqual(clock.snapshot()["infra_pause_seconds"], 49.)

    def test_deadline_is_checked_before_result_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solver.json"
            monitor = ToolControlMonitor(path)
            clock = AttemptClock(1)
            clock.pause()
            write_json(path, {"phase": "settle", "pause_requested": True, "call_id": "x", "charged_seconds": 2})
            monitor.merge({}, clock)
            self.assertTrue(monitor.acknowledge(paused=True, clock=clock))
            self.assertEqual(read_json(monitor.ack_path)["status"], "deadline")
            self.assertIsNone(clock.cancellation_reason())

    def test_full_acknowledgement_handshake_with_workspace_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solver.json"
            control = ToolControl(path)
            workspace = AgentWorkspace("external-test", "mock-container", SimpleNamespace())
            workspace._solver_control_monitor = ToolControlMonitor(path)
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                return SimpleNamespace(returncode=0)

            with patch("agent_formalizer.workspace.subprocess.run", side_effect=run):
                clock = AttemptClock(5)
                workspace.start_model_gateway_monitor(clock)
                try:
                    control.begin()
                    time.sleep(0.05)
                    control.finish(0.02)
                    self.assertEqual(read_json(control.ack_path)["status"], "released")
                finally:
                    workspace.stop_model_gateway_monitor()
            self.assertIn(["docker", "pause", "mock-container"], commands)
            self.assertIn(["docker", "unpause", "mock-container"], commands)
            self.assertFalse(clock.snapshot()["paused"])
            self.assertIsNone(workspace.gateway_monitor_error())


class ProfileIdentityTests(unittest.TestCase):
    def test_new_policy_is_semantic_but_legacy_resolves_without_injection(self):
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool.json")
        resolved = profile.resolve("openclaw")
        self.assertEqual(resolved.raw["resolved"]["solver_error_routing"], "solver-transient-v1")
        self.assertIn("external_call_unrecoverable", resolved.raw["infra_retry"]["invalidators"])
        old = deepcopy(profile.raw)
        del old["condition_profile"]["overrides"]["solver_error_routing"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            path.write_text(json.dumps(old))
            legacy = load_benchmark_profile(path).resolve("openclaw")
            self.assertNotIn("solver_error_routing", legacy.raw["resolved"])
            self.assertNotIn("external_call_unrecoverable", legacy.raw["infra_retry"]["invalidators"])
            self.assertNotEqual(legacy.sha256, resolved.sha256)
            self.assertEqual(legacy.sha256, load_benchmark_profile(path).resolve("openclaw").sha256)

    def test_unknown_policy_rejected(self):
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool.json")
        raw = deepcopy(profile.raw)
        raw["condition_profile"]["overrides"]["solver_error_routing"] = "typo"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                load_benchmark_profile(path)


if __name__ == "__main__":
    unittest.main()
