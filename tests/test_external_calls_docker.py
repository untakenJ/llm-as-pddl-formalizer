"""Opt-in real sidecar mounts/freeze/CLI, with a fake (never public) solver."""
import ipaddress
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent_formalizer.benchmark_profile import BENCHMARK_PROFILES_DIR, load_benchmark_profile
from agent_formalizer.claws import get_adapter
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.workspace import AgentWorkspace
from test_external_calls_gateway import Backend, SUBMIT, TIMEOUT, PLAN


@unittest.skipUnless(os.environ.get("RUN_EXTERNAL_CALLS_DOCKER_TESTS") == "1", "opt-in real Docker sidecar test")
class DockerSolverRecoveryTests(unittest.TestCase):
    def test_cli_sidecar_mounts_and_actual_container_pause(self):
        network = json.loads(subprocess.check_output(["docker", "network", "inspect", "bridge"], text=True))[0]
        bridge = network["IPAM"]["Config"][0]["Gateway"]
        self.assertTrue(ipaddress.ip_address(bridge).is_private)
        backend = ThreadingHTTPServer((bridge, 0), Backend)
        backend.responses = [SUBMIT, TIMEOUT, SUBMIT, PLAN]
        backend.requests = []
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        profile = load_benchmark_profile(BENCHMARK_PROFILES_DIR / "native_safety_streaming_solver_as_tool.json")
        adapter = get_adapter("openclaw", benchmark_profile=profile, model="openai/gpt-4o-mini", api_key="test-not-real")
        identity = "external-calls-smoke-" + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory(prefix="external-calls-docker-") as directory:
                workspace = AgentWorkspace(identity, identity, adapter, artifact_dir=Path(directory))
                with patch.object(adapter, "solver_upstream_base", return_value=f"http://{bridge}:{backend.server_port}"), \
                        patch.object(adapter, "solver_backend", return_value="public"):
                    try:
                        workspace.start()
                        self.assertTrue(workspace.write_text_file("/workspace/domain.pddl", "(domain bytes)"))
                        self.assertTrue(workspace.write_text_file("/workspace/problem.pddl", "(problem bytes)"))
                        clock = AttemptClock(30)
                        workspace.start_model_gateway_monitor(clock)
                        result = workspace.run_in_container("pddl-solver", timeout=30)
                        workspace.stop_model_gateway_monitor()
                        self.assertEqual(result.exit_code, 0, result.stderr)
                        self.assertIn("(move a b)", result.stdout)
                        self.assertIsNone(workspace.gateway_terminal_infra_error())
                        self.assertIsNone(workspace.gateway_monitor_error())
                        self.assertEqual(len(backend.requests), 4)
                        timing = clock.snapshot()
                        self.assertGreaterEqual(timing["infra_pause_seconds"], 5)
                        self.assertLess(timing["active_duration_seconds"], 5)
                        outcome = json.loads((Path(directory) / "gateway/solver_calls/call-0001/outcome.json").read_text())
                        self.assertEqual(outcome["action"], "return")
                        print("Docker external-call timing:", json.dumps(timing), flush=True)
                    finally:
                        workspace.cleanup()
        finally:
            backend.shutdown()
            backend.server_close()


if __name__ == "__main__":
    unittest.main()
