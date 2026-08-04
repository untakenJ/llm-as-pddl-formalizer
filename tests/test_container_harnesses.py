from __future__ import annotations

import os
import json
import shlex
import shutil
import unittest
import subprocess
import tempfile
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws import get_adapter
from agent_formalizer.benchmark_profile import DEFAULT_BENCHMARK_PROFILE, load_benchmark_profile
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.zeroclaw import ZEROCLAW_CONFIG_DIR, ZeroClawAdapter
from agent_formalizer.workspace import AgentWorkspace


@unittest.skipUnless(
    os.environ.get("RUN_HARNESS_CONTAINER_TESTS") == "1",
    "set RUN_HARNESS_CONTAINER_TESTS=1 to exercise Docker mounts",
)
class ContainerHarnessTests(unittest.TestCase):
    def test_deadline_cuts_model_route_and_stops_agent_tree(self):
        adapter = get_adapter(
            "hermes", model="openai/gpt-5.4-mini", timeout=120,
            max_action_steps=17, max_model_calls=10, api_key="container-test-key",
        )
        workspace = AgentWorkspace(
            "container-deadline-hermes", "pddl-harness-deadline-hermes", adapter
        )
        try:
            workspace.start()
            workspace.enforce_agent_deadline()
            agent_state = subprocess.run(
                [
                    "docker", "inspect", "--format", "{{.State.Running}}",
                    workspace.container_name,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(agent_state.returncode, 0, agent_state.stderr)
            self.assertEqual(agent_state.stdout.strip(), "false")
            network = subprocess.run(
                ["docker", "network", "inspect", workspace.network_name],
                capture_output=True,
                text=True,
                timeout=20,
            )
            attached = json.loads(network.stdout)[0].get("Containers") or {}
            attached_names = {row.get("Name") for row in attached.values()}
            self.assertNotIn(workspace.gateway_name, attached_names)
            # The sidecar remains inspectable through docker exec so timeout
            # evidence can still be collected after the agent loses access.
            self.assertEqual(
                workspace.model_gateway_stats().get("max_model_calls"), 10
            )
        finally:
            workspace.cleanup()

    def test_runtime_mounts_and_generated_configs(self):
        adapters = [
            get_adapter(
                name, model="openai/gpt-5.4-mini", timeout=120,
                max_action_steps=17, max_model_calls=10, api_key="container-test-key",
            )
            for name in ("hermes", "nanobot", "zeroclaw", "generic")
        ]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "container-test-key"}, clear=False):
            for adapter in adapters:
                with self.subTest(adapter=adapter.name):
                    self._check_adapter(adapter)

    def _check_adapter(self, adapter):
        instance_id = f"container-smoke-{adapter.name}"
        container_name = f"pddl-harness-smoke-{adapter.name}"
        workspace = AgentWorkspace(instance_id, container_name, adapter)
        state = None
        try:
            adapter.validate_runtime()
            workspace.start()
            network = subprocess.run(
                ["docker", "network", "inspect", workspace.network_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(network.returncode, 0, network.stderr)
            self.assertTrue(json.loads(network.stdout)[0]["Internal"])
            gateway = workspace.run_in_container(
                "python3 -c "
                + shlex.quote(
                    "import urllib.request; "
                    "urllib.request.urlopen("
                    "'http://model-gateway:8766/__benchmark__/health', "
                    "timeout=3).read()"
                ),
                timeout=10,
            )
            self.assertEqual(gateway.exit_code, 0, gateway.stderr)
            direct_egress = workspace.run_in_container(
                "python3 -c "
                + shlex.quote(
                    "import socket; socket.create_connection(('1.1.1.1', 80), 3)"
                ),
                timeout=10,
            )
            self.assertNotEqual(
                direct_egress.exit_code,
                0,
                "restricted agent container unexpectedly reached a public IP",
            )
            environment = workspace.run_in_container("env", timeout=10)
            self.assertNotIn("container-test-key", environment.stdout)
            self.assertEqual(
                workspace.validate_network_policy()["status"], "pass"
            )
            self.assertEqual(
                workspace.validate_environment_policy()["status"], "pass"
            )
            if isinstance(adapter, HermesAdapter):
                command = (
                    f"{shlex.quote(str(adapter.runtime_python))} -c "
                    + shlex.quote("import hermes_cli; print('hermes-ok')")
                )
            elif isinstance(adapter, NanoBotAdapter):
                command = (
                    f"{shlex.quote(str(adapter.runtime_python))} -c "
                    + shlex.quote("import nanobot; print('nanobot-ok')")
                )
            elif isinstance(adapter, ZeroClawAdapter):
                command = (
                    f"ZEROCLAW_CONFIG_DIR={ZEROCLAW_CONFIG_DIR} "
                    "/usr/local/bin/zeroclaw "
                    f"--config-dir {ZEROCLAW_CONFIG_DIR} config list >/dev/null"
                )
            else:
                state = adapter._instance_states[instance_id]
                config_dir = state / "config"
                code = (
                    "import json; "
                    f"p={str(adapter.runtime_repo / 'assets' / 'tools_schema.json')!r}; "
                    "names={x['function']['name'] for x in json.load(open(p))}; "
                    "assert 'web_scan' in names; print('generic-ok')"
                )
                command = (
                    f"PDDL_BENCHMARK_API_KEY=container-test-key "
                    f"PYTHONPATH={shlex.quote(str(config_dir))}:"
                    f"{shlex.quote(str(adapter.runtime_repo))} "
                    f"{shlex.quote(str(adapter.runtime_python))} -c {shlex.quote(code)}"
                )
            result = workspace.run_in_container(command, timeout=60)
            self.assertEqual(result.exit_code, 0, result.stderr)
        finally:
            workspace.cleanup()
            if state and state.exists():
                shutil.rmtree(state)

    def test_controlled_web_keeps_agent_internal(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        raw = deepcopy(DEFAULT_BENCHMARK_PROFILE.raw)
        raw["condition_profile"] = {
            "id": "controlled",
            "overrides": {
                "network_mode": "controlled_web",
                "controlled_web_allowlist": ["host.docker.internal"],
            },
        }
        profile_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        profile_file.write(json.dumps(raw).encode())
        profile_file.close()
        self.addCleanup(Path(profile_file.name).unlink, missing_ok=True)
        adapter = get_adapter(
            "hermes", model="openai/gpt-5.4-mini", timeout=120,
            max_action_steps=17, max_model_calls=10, api_key="container-test-key",
            benchmark_profile=load_benchmark_profile(profile_file.name),
        )
        workspace = AgentWorkspace(
            "container-network-hermes", "pddl-harness-network-hermes", adapter
        )
        try:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "container-test-key"}, clear=False):
                adapter.validate_runtime()
                workspace.start()
            result = subprocess.run(
                ["docker", "network", "inspect", workspace.network_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)[0]["Internal"])
            self.assertEqual(adapter.network_policy()["mode"], "controlled_web")
            self.assertEqual(
                workspace.validate_network_policy()["status"], "pass"
            )
            self.assertEqual(
                workspace.validate_environment_policy()["status"], "pass"
            )
            allowed = workspace.run_in_container(
                "python3 -c "
                + shlex.quote(
                    "import urllib.request; assert urllib.request.urlopen("
                    f"'http://host.docker.internal:{server.server_port}',timeout=5"
                    ").read()==b'ok'"
                ),
                timeout=15,
            )
            self.assertEqual(allowed.exit_code, 0, allowed.stderr)
            rejected = workspace.run_in_container(
                "python3 -c "
                + shlex.quote(
                    "import urllib.request; urllib.request.urlopen("
                    "'http://example.com',timeout=5).read()"
                ),
                timeout=15,
            )
            self.assertNotEqual(rejected.exit_code, 0)
        finally:
            workspace.cleanup()

    def test_generic_delivery_copy_survives_temp_memory_overlays(self):
        adapter = get_adapter(
            "generic", model="openai/gpt-5.4-mini", timeout=120,
            max_action_steps=17, max_model_calls=10, api_key="container-test-key",
        )
        instance_id = "container-generic-copy"
        workspace = AgentWorkspace(
            instance_id, "pddl-harness-generic-copy", adapter
        )
        state = None
        try:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "container-test-key"}, clear=False):
                adapter.validate_runtime()
                workspace.start()
            state = adapter._instance_states[instance_id]
            write = workspace.run_in_container(
                "printf 'domain' > /workspace/domain.pddl && "
                "printf 'problem' > /workspace/problem.pddl",
                timeout=15,
            )
            self.assertEqual(write.exit_code, 0, write.stderr)
            with tempfile.TemporaryDirectory() as tmp:
                host = Path(tmp) / "domain.pddl"
                self.assertTrue(
                    workspace.copy_from_container(
                        "/workspace/domain.pddl", str(host)
                    ),
                    "nested schema file mounts must not break docker cp",
                )
                self.assertEqual(host.read_text(), "domain")
            frozen = workspace.freeze_pddl_outputs()
            self.assertEqual(frozen.get("domain"), b"domain")
            self.assertEqual(frozen.get("problem"), b"problem")
        finally:
            workspace.cleanup()
            if state and state.exists():
                shutil.rmtree(state)


if __name__ == "__main__":
    unittest.main()
