"""Exercise relocated resources and entrypoints from outside the checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent_formalizer.configuration.config import PACKAGE_DIR, SOURCE_DIR


class AgentPackageLayoutTests(unittest.TestCase):
    def run_fresh(self, args, *, package_imports=False):
        env = {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"}
        if package_imports:
            env["PYTHONPATH"] = str(SOURCE_DIR)
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [sys.executable, *map(str, args)],
                cwd=cwd, env=env, capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_default_resources_and_configuration_from_unrelated_directory(self):
        self.run_fresh(["-c", """
from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.configuration.config import ROOT_DIR
from agent_formalizer.configuration.credentials import (
    DEFAULT_CREDENTIAL_PROFILES_PATH, load_credential_registry,
)
from agent_formalizer.configuration.operational_config import (
    DEFAULT_OPERATIONAL_CONFIG_PATH, load_operational_config,
)
from agent_formalizer.configuration.skill_library import LIBRARY_ROOT, load_bundle
from agent_formalizer.prompts.prompt import build_prompt
from agent_formalizer.runtime.runtime_lock import load_runtime_lock

profile = load_benchmark_profile()
assert profile.resolve('hermes').raw['harness'] == 'hermes'
legacy = load_operational_config()
explicit = load_operational_config(DEFAULT_OPERATIONAL_CONFIG_PATH)
for operational in (legacy, explicit):
    assert operational.credential_registry_path == DEFAULT_CREDENTIAL_PROFILES_PATH
    assert operational.results_root == ROOT_DIR / 'output'
    load_credential_registry(operational.credential_registry_path)
assert legacy.raw['infra_diagnostics']['enabled'] is False
assert explicit.raw['infra_diagnostics']['enabled'] is True
bundle = load_bundle(LIBRARY_ROOT, ['simulate-and-check-plan'])
assert len(bundle.skills) == 1
prompt = build_prompt('LAYOUT_DOMAIN_DESCRIPTION', 'LAYOUT_PROBLEM_DESCRIPTION')
assert 'LAYOUT_DOMAIN_DESCRIPTION' in prompt and 'LAYOUT_PROBLEM_DESCRIPTION' in prompt
assert load_runtime_lock()['harnesses']['minimum']['runtime_entrypoint_sha256']
"""], package_imports=True)

    def test_cli_scripts_start_without_pythonpath_from_unrelated_directory(self):
        for script in (
            PACKAGE_DIR / "run_formalizer_agent.py",
            PACKAGE_DIR / "results/manage_execution_validity.py",
            PACKAGE_DIR / "results/streaming_report.py",
            SOURCE_DIR / "sweep_agent_pipeline.py",
            SOURCE_DIR / "run_solver.py",
            SOURCE_DIR / "run_val.py",
        ):
            with self.subTest(script=script.name):
                self.assertIn("usage:", self.run_fresh([script, "--help"]).lower())

    def test_result_cli_module_entrypoints(self):
        for module in (
            "agent_formalizer.results.manage_execution_validity",
            "agent_formalizer.results.streaming_report",
        ):
            with self.subTest(module=module):
                output = self.run_fresh(["-m", module, "--help"], package_imports=True)
                self.assertIn("usage:", output.lower())

    def test_shared_packages_do_not_initialize_platforms_or_gateways(self):
        self.run_fresh(["-c", """
import sys
import agent_formalizer.compute_platforms
import agent_formalizer.gateways
import agent_formalizer.results.execution_validity

assert 'agent_formalizer.gateways.model_gateway' not in sys.modules
assert 'agent_formalizer.compute_platforms.logits.logits_openai_bridge' not in sys.modules
assert 'agent_formalizer.claws' not in sys.modules
"""], package_imports=True)


if __name__ == "__main__":
    unittest.main()
