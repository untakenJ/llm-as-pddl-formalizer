"""Loopback integration: real HTTP, fake backend, real timing control protocol."""
from __future__ import annotations

import functools
import http.client
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.timing.call_checkpoint import CheckpointBroker
from agent_formalizer.timing.checkpoint_monitor import monitor as checkpoint_monitor
from agent_formalizer.external_calls import solver as policy
from agent_formalizer.external_calls import RetryPolicy
from agent_formalizer.external_calls.control import ToolControl, ToolControlMonitor, read_json
from agent_formalizer.tools.solver import gateway
from agent_formalizer.workspace import AgentWorkspace


class Backend(BaseHTTPRequestHandler):
    def do_GET(self):
        raw = json.dumps({"status": "ok", "backend": "local-planutils", "config": {
            "timeout_seconds": 90., "allowed_solvers": ["dual-bfws-ffparser"]}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append((self.path, body))
        status, data = self.server.responses.pop(0)
        # Public Flask polling tries to parse JSON if Content-Type says JSON.
        # An empty POST must not claim to contain a JSON document.
        if not body and self.headers.get("Content-Type") == "application/json":
            status, data = 400, {"error": "empty JSON body"}
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


SUBMIT = (200, {"result": "/check/one"})
TIMEOUT = (200, {"status": "ok", "result": {"stdout": "Request Time Out", "stderr": "", "output": {}}})
PLAN = (200, {"status": "ok", "result": {"stdout": "Plan found with cost: 1", "stderr": "", "output": {"plan": "(move a b)\n"}}})


class SolverGatewayIntegrationTests(unittest.TestCase):
    def run_case(self, responses, *, active_budget=10, fallback_responses=None, checkpoint=False):
        try:
            backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
            proxy = ThreadingHTTPServer(("127.0.0.1", 0), gateway.SolverGatewayHandler)
            local = ThreadingHTTPServer(("127.0.0.1", 0), Backend) if fallback_responses is not None else None
        except PermissionError as exc:
            self.fail(f"Loopback sockets required; run this test outside the socket-restricted sandbox: {exc}")
        backend.responses = list(responses)
        backend.requests = []
        if local is not None:
            local.responses = list(fallback_responses)
            local.requests = []
        servers = (backend, proxy) + ((local,) if local is not None else ())
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                control = ToolControl(root / "solver.json")
                workspace = AgentWorkspace("solver-test", "fake-agent", SimpleNamespace())
                workspace._solver_control_monitor = ToolControlMonitor(control.path)
                commands = []

                def run(command, **kwargs):
                    commands.append(command)
                    return SimpleNamespace(returncode=0)

                original_solve = policy.solve
                with patch.multiple(gateway, CONTROL=control, RECOVERY_POLICY=policy.POLICY_ID,
                        CONTROL_FILE=str(control.path),
                        BACKEND="public_then_local" if local else "single",
                        FALLBACK_BASE=f"http://127.0.0.1:{local.server_port}" if local else None,
                        EVIDENCE_DIR=str(root / "evidence"), UPSTREAM_BASE=f"http://127.0.0.1:{backend.server_port}"), \
                        patch.dict("os.environ", {"PDDL_SOLVER_EXTERNAL_CALL_TIMING": "call-checkpoint-v1" if checkpoint else ""}), \
                        patch.object(policy, "solve", functools.partial(original_solve, policy=RetryPolicy(2, (0., 0.)))), \
                        patch("agent_formalizer.workspace.subprocess.run", side_effect=run):
                    with gateway.State.lock:
                        gateway.State.request_attempts = gateway.State.solved_ok = gateway.State.solved_fail = 0
                        gateway.State.ledger = []
                    clock = AttemptClock(active_budget)
                    if checkpoint:
                        workspace._deadline_broker = CheckpointBroker(root / "deadlines")
                        workspace._gateway_control_dir = root
                        workspace._read_gateway_control = lambda: {}
                        stop = threading.Event()
                        monitor_thread = threading.Thread(target=checkpoint_monitor, args=(workspace, clock, stop))
                        monitor_thread.start()
                    else:
                        workspace.start_model_gateway_monitor(clock)
                    request = urllib.request.Request(f"http://127.0.0.1:{proxy.server_port}/solve",
                        data=json.dumps({"domain": "(domain bytes)", "problem": "(problem bytes)"}).encode(),
                        headers={"Content-Type": "application/json"})
                    try:
                        try:
                            response = urllib.request.urlopen(request, timeout=5)
                        except urllib.error.HTTPError as exc:
                            response = exc
                        with response:
                            result = (response.status, json.load(response))
                    except http.client.RemoteDisconnected:
                        result = None
                    finally:
                        # Terminal state is also read synchronously after a fast
                        # process exit, not only on the monitor polling interval.
                        workspace.gateway_terminal_infra_error()
                        if checkpoint:
                            stop.set()
                            monitor_thread.join(5)
                            workspace._deadline_broker.close()
                            self.assertFalse(monitor_thread.is_alive())
                        else:
                            workspace.stop_model_gateway_monitor()
                    evidence = root / "evidence" / "call-0001"
                    outcome = read_json(evidence / "outcome.json")
                    records = [json.loads(line) for line in (evidence / "events.jsonl").read_text().splitlines()]
                    self.assertEqual((evidence / "domain.pddl").read_text(), "(domain bytes)")
                    self.assertEqual(gateway.State.request_attempts, 1)
                    requests = backend.requests + (local.requests if local else [])
                    return result, outcome, records, requests, workspace.gateway_terminal_infra_error(), clock.snapshot()
        finally:
            for server in reversed(servers):
                server.shutdown()
                server.server_close()

    def test_timeout_then_success_hidden_and_one_logical_call(self):
        result, outcome, records, requests, terminal, clock = self.run_case([SUBMIT, TIMEOUT, SUBMIT, PLAN])
        self.assertEqual(result[0], 200)
        self.assertEqual(result[1]["plan"], "(move a b)\n")
        self.assertEqual(outcome["action"], "return")
        self.assertEqual(len(requests), 4)
        self.assertEqual(requests[0][1], requests[2][1])
        self.assertEqual(len([r for r in records if r.get("action") == "retry"]), 1)
        self.assertIsNone(terminal)
        self.assertGreater(clock["infra_pause_seconds"], 0)

    def test_repeated_timeout_last_actual_diagnostic_returned(self):
        result, outcome, _, requests, terminal, _ = self.run_case([SUBMIT, TIMEOUT] * 3)
        self.assertEqual(result[0], 422)
        self.assertIn("Request Time Out", result[1]["error"])
        self.assertNotIn("retry", result[1]["error"])
        self.assertEqual(len(requests), 6)
        self.assertIsNone(terminal)

    def test_429_exhaustion_invalidates_without_agent_observation(self):
        result, outcome, _, requests, terminal, _ = self.run_case([(429, {"error": "busy"})] * 3)
        self.assertIsNone(result)
        self.assertEqual(outcome["action"], "invalidate")
        self.assertEqual(terminal["reason"], "external_call_unrecoverable")
        self.assertEqual(terminal["classification"], "solver_rate_limited")
        self.assertEqual(len(requests), 3)

    def test_input_syntax_error_returned_without_retry(self):
        syntax = (200, {"status": "ok", "result": {"stdout": "", "stderr": "domain: syntax error in line 3, foo", "output": {}}})
        result, outcome, _, requests, terminal, _ = self.run_case([SUBMIT, syntax])
        self.assertEqual(result[0], 422)
        self.assertIn("syntax error", result[1]["error"])
        self.assertEqual(len(requests), 2)
        self.assertIsNone(terminal)

    def test_fallback_only_final_local_success_delivered_as_one_tool_call(self):
        result, outcome, records, requests, terminal, clock = self.run_case(
            [SUBMIT, TIMEOUT] * 3, fallback_responses=[SUBMIT, PLAN])
        self.assertEqual(result[0], 200)
        self.assertEqual(result[1]["plan"], "(move a b)\n")
        self.assertEqual(outcome["action"], "return")
        self.assertEqual(len(requests), 8)
        self.assertEqual([r["backend"] for r in records if r.get("action") == "return"], ["local"])
        self.assertEqual(len([r for r in records if r.get("action") == "fallback"]), 1)
        self.assertIsNone(terminal)
        self.assertGreater(clock["infra_pause_seconds"], 0)

    def test_fallback_terminal_timeout_delivered_but_persistent_infra_not_delivered(self):
        result, outcome, records, requests, terminal, _ = self.run_case(
            [SUBMIT, TIMEOUT] * 3, fallback_responses=[SUBMIT, TIMEOUT] * 3)
        self.assertEqual(result[0], 422)
        self.assertIn("Request Time Out", result[1]["error"])
        self.assertEqual(len(requests), 12)
        self.assertIsNone(terminal)
        self.assertEqual(len([r for r in records if r.get("action") == "retry"]), 4)
        result, outcome, _, requests, terminal, _ = self.run_case(
            [(429, {"error": "busy"})] * 3, fallback_responses=[(429, {"error": "busy"})] * 3)
        self.assertIsNone(result)
        self.assertEqual(outcome["action"], "invalidate")
        self.assertEqual(terminal["classification"], "solver_rate_limited")
        self.assertEqual(len(requests), 6)

    def test_fallback_checkpoint_discards_both_phases_and_commits_once(self):
        result, outcome, records, requests, terminal, _ = self.run_case(
            [SUBMIT, TIMEOUT] * 3, fallback_responses=[SUBMIT, TIMEOUT, SUBMIT, PLAN], checkpoint=True)
        self.assertEqual(result[0], 200)
        self.assertEqual(outcome["timing_mode"], "isolated_escrow")
        self.assertEqual(next(r for r in records if r.get("action") == "checkpoint")["policy"], "call-checkpoint-v1")
        self.assertEqual(len([r for r in records if r.get("action") == "rollback"]), 4)
        self.assertEqual(len([r for r in records if r.get("action") == "checkpoint"]), 1)
        self.assertEqual(len([r for r in records if r.get("action") == "commit"]), 1)
        self.assertEqual(len(requests), 10)
        self.assertIsNone(terminal)


if __name__ == "__main__":
    unittest.main()
