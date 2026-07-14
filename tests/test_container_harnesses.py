from __future__ import annotations

import os
import shlex
import shutil
import unittest
from unittest.mock import patch

from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.zeroclaw import ZEROCLAW_CONFIG_DIR, ZeroClawAdapter
from agent_formalizer.workspace import AgentWorkspace


@unittest.skipUnless(
    os.environ.get("RUN_HARNESS_CONTAINER_TESTS") == "1",
    "set RUN_HARNESS_CONTAINER_TESTS=1 to exercise Docker mounts",
)
class ContainerHarnessTests(unittest.TestCase):
    def test_runtime_mounts_and_generated_configs(self):
        adapters = [
            HermesAdapter("openai/gpt-5.4-mini", 120, 17),
            NanoBotAdapter("openai/gpt-5.4-mini", 120, 17),
            ZeroClawAdapter("openai/gpt-5.4-mini", 120, 17),
            GenericAgentAdapter("openai/gpt-5.4-mini", 120),
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
                    "assert 'web_scan' not in names; print('generic-ok')"
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


if __name__ == "__main__":
    unittest.main()
