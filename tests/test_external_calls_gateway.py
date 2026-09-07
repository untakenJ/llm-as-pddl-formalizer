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
from agent_formalizer.external_calls import solver as policy
from agent_formalizer.external_calls import RetryPolicy
from agent_formalizer.external_calls.control import ToolControl, ToolControlMonitor, read_json
from agent_formalizer.tools.solver import gateway
from agent_formalizer.workspace import AgentWorkspace


class Backend(BaseHTTPRequestHandler):
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
    def run_case(self, responses, *, active_budget=10):
        try:
            backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
            proxy = ThreadingHTTPServer(("127.0.0.1", 0), gateway.SolverGatewayHandler)
        except PermissionError as exc:
            self.fail(f"Loopback sockets required; run this test outside the socket-restricted sandbox: {exc}")
        backend.responses = list(responses)
        backend.requests = []
        for server in (backend, proxy):
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
                        EVIDENCE_DIR=str(root / "evidence"), UPSTREAM_BASE=f"http://127.0.0.1:{backend.server_port}"), \
                        patch.object(policy, "solve", functools.partial(original_solve, policy=RetryPolicy(2, (0., 0.)))), \
                        patch("agent_formalizer.workspace.subprocess.run", side_effect=run):
                    with gateway.State.lock:
                        gateway.State.request_attempts = gateway.State.solved_ok = gateway.State.solved_fail = 0
                        gateway.State.ledger = []
                    clock = AttemptClock(active_budget)
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
                        workspace.stop_model_gateway_monitor()
                    evidence = root / "evidence" / "call-0001"
                    outcome = read_json(evidence / "outcome.json")
                    records = [json.loads(line) for line in (evidence / "events.jsonl").read_text().splitlines()]
                    self.assertEqual((evidence / "domain.pddl").read_text(), "(domain bytes)")
                    self.assertEqual(gateway.State.request_attempts, 1)
                    return result, outcome, records, backend.requests, workspace.gateway_terminal_infra_error(), clock.snapshot()
        finally:
            for server in (proxy, backend):
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


if __name__ == "__main__":
    unittest.main()
