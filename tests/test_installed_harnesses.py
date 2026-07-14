from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HERMES_PROVIDER_MAP
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter
from agent_formalizer.config import (
    GENERIC_ENV_PATH,
    GENERIC_REPO_PATH,
    HERMES_ENV_PATH,
    NANOBOT_ENV_PATH,
    ZEROCLAW_BIN,
)


def require_path(path: Path):
    if not path.exists():
        raise unittest.SkipTest(f"optional harness runtime is not installed: {path}")


class InstalledHarnessTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.dict(
            os.environ, {"OPENAI_API_KEY": "integration-test-key"}, clear=False
        )
        self.key_patch.start()

    def tearDown(self):
        self.key_patch.stop()

    def test_hermes_provider_mapping_exists_in_installed_catalog(self):
        python = HERMES_ENV_PATH / "bin" / "python"
        require_path(python)
        code = (
            "from hermes_cli.models import CANONICAL_PROVIDERS; "
            "print('\\n'.join(p.slug for p in CANONICAL_PROVIDERS))"
        )
        result = subprocess.run(
            [str(python), "-c", code], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        available = set(result.stdout.splitlines())
        self.assertTrue(set(HERMES_PROVIDER_MAP.values()).issubset(available))

    def test_nanobot_accepts_generated_config(self):
        python = NANOBOT_ENV_PATH / "bin" / "python"
        require_path(python)
        config = NanoBotAdapter("openai/gpt-5.4-mini", 120, 17)._benchmark_config()
        code = (
            "import sys; from nanobot.config.schema import Config; "
            "c=Config.model_validate_json(sys.stdin.read()); "
            "print(c.agents.defaults.model, c.tools.restrict_to_workspace)"
        )
        result = subprocess.run(
            [str(python), "-c", code],
            input=json.dumps(config),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("gpt-5.4-mini True", result.stdout)

    def test_zeroclaw_accepts_generated_v3_config(self):
        require_path(ZEROCLAW_BIN)
        adapter = ZeroClawAdapter("openai/gpt-5.4-mini", 120, 17)
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "config.toml").write_text(adapter._benchmark_config_toml())
            env = {
                **os.environ,
                "HOME": tmp,
                "ZEROCLAW_providers__models__openai__benchmark__api_key": (
                    "integration-test-key"
                ),
            }
            result = subprocess.run(
                [str(ZEROCLAW_BIN), "--config-dir", tmp, "config", "list"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agents.benchmark.model_provider", result.stdout)

    def test_genericagent_resolves_generated_mykey(self):
        python = GENERIC_ENV_PATH / "bin" / "python"
        require_path(python)
        require_path(GENERIC_REPO_PATH / "llmcore.py")
        adapter = GenericAgentAdapter("openai/gpt-5.4-mini", 120)
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "mykey.py").write_text(adapter._mykey_source())
            env = {
                **os.environ,
                "PDDL_BENCHMARK_API_KEY": "integration-test-key",
                "PYTHONPATH": f"{config_dir}:{GENERIC_REPO_PATH}",
            }
            code = (
                "from llmcore import resolve_client; "
                "c=resolve_client('native_oai_config_benchmark'); "
                "print(c.backend.model)"
            )
            result = subprocess.run(
                [str(python), "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("gpt-5.4-mini", result.stdout)


if __name__ == "__main__":
    unittest.main()
