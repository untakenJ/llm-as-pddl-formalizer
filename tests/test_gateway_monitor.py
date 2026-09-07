from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.workspace import AgentWorkspace


class GatewayMonitorTests(unittest.TestCase):
    def test_action_step_limit_kills_agent_as_valid_budget_outcome(self):
        adapter = SimpleNamespace()
        workspace = AgentWorkspace("case", "agent-container", adapter)
        killed = threading.Event()
        commands: list[list[str]] = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if command[:2] == ["docker", "kill"]:
                killed.set()
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "pause_requested": False,
                        "action_step_limit_reached": True,
                        "terminal_infra_error": None,
                    }
                )
            )
            workspace._gateway_control_path = state_path
            clock = AttemptClock(10)
            with patch(
                "agent_formalizer.workspace.subprocess.run", side_effect=fake_run
            ):
                workspace.start_model_gateway_monitor(clock)
                self.assertTrue(killed.wait(2))
                workspace.stop_model_gateway_monitor()

        self.assertTrue(workspace.gateway_action_step_limit_reached())
        self.assertIsNone(workspace.gateway_terminal_infra_error())
        self.assertIn(["docker", "kill", "agent-container"], commands)
        self.assertNotIn(["docker", "pause", "agent-container"], commands)
        self.assertFalse(clock.snapshot()["paused"])

    def test_terminal_provider_state_pauses_and_kills_agent_container(self):
        adapter = SimpleNamespace()
        workspace = AgentWorkspace("case", "agent-container", adapter)
        killed = threading.Event()
        commands: list[list[str]] = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if command[:2] == ["docker", "kill"]:
                killed.set()
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "pause_requested": True,
                        "pause_started_unix": time.time(),
                        "terminal_infra_error": {
                            "reason": "provider_transient_exhausted"
                        },
                    }
                )
            )
            workspace._gateway_control_path = state_path
            clock = AttemptClock(10)
            with patch(
                "agent_formalizer.workspace.subprocess.run", side_effect=fake_run
            ):
                workspace.start_model_gateway_monitor(clock)
                self.assertTrue(killed.wait(2))
                workspace.stop_model_gateway_monitor()

        self.assertEqual(
            workspace.gateway_terminal_infra_error()["reason"],
            "provider_transient_exhausted",
        )
        self.assertIn(["docker", "pause", "agent-container"], commands)
        self.assertIn(["docker", "kill", "agent-container"], commands)
        self.assertFalse(clock.snapshot()["paused"])

    def test_streaming_gateway_exit_after_commit_invalidates_and_kills_agent(self):
        adapter = SimpleNamespace(
            resolved_config=SimpleNamespace(
                model_response_delivery={"mode": "native_streaming"}
            )
        )
        workspace = AgentWorkspace("case", "agent-container", adapter)
        killed = threading.Event()
        commands: list[list[str]] = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if command[:2] == ["docker", "inspect"]:
                return subprocess.CompletedProcess(command, 0, "false\n", "")
            if command[:2] == ["docker", "kill"]:
                killed.set()
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "pause_requested": False,
                        "active_committed_streams": 1,
                        "terminal_infra_error": None,
                    }
                )
            )
            workspace._gateway_control_path = state_path
            clock = AttemptClock(10)
            with patch(
                "agent_formalizer.workspace.subprocess.run", side_effect=fake_run
            ):
                workspace.start_model_gateway_monitor(clock)
                self.assertTrue(killed.wait(2))
                workspace.stop_model_gateway_monitor()

        terminal = workspace.gateway_terminal_infra_error()
        self.assertEqual(terminal["reason"], "post_commit_stream_failure")
        self.assertEqual(terminal["stream_error_type"], "GatewaySidecarExit")
        self.assertIn(["docker", "kill", "agent-container"], commands)


if __name__ == "__main__":
    unittest.main()
