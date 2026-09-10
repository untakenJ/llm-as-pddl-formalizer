from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agent_formalizer.configuration.operational_config import (
    DEFAULT_OPERATIONAL_CONFIG_PATH,
    load_operational_config,
    safe_operational_component,
)


class OperationalConfigTests(unittest.TestCase):
    def _write(self, root: Path, value: dict, name: str = "operational.json") -> Path:
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_standard_config_selects_provider_handlers_and_safe_paths(self):
        operational = load_operational_config(DEFAULT_OPERATIONAL_CONFIG_PATH)

        vertex = operational.execution_diagnostics_plan(
            provider="google-vertex",
            run_id="sweep/unsafe id",
            domain="blocksworld",
            data="dataset",
            problem="p01",
            model_label="google-vertex/gemini",
            attempt_index=2,
            execution_try=3,
            runtime_id="runtime-one",
        )
        deepseek = operational.execution_diagnostics_plan(
            provider="deepseek",
            run_id="run",
            domain="blocksworld",
            data="dataset",
            problem="p01",
            model_label="deepseek/model",
            attempt_index=1,
            execution_try=1,
            runtime_id="runtime-two",
        )

        self.assertIsNotNone(vertex)
        self.assertIsNotNone(deepseek)
        self.assertEqual(vertex.runtime_config["provider"], "google_vertex")
        self.assertEqual(
            vertex.runtime_config["handler"], "builtin:google_vertex@1"
        )
        self.assertEqual(
            deepseek.runtime_config["handler"], "builtin:deepseek@1"
        )
        self.assertNotIn("/", vertex.run_root.name)
        self.assertEqual(vertex.execution_dir.name, "runtime-runtime-one")
        self.assertEqual(vertex.execution_dir.parent.name, "execution-003")
        self.assertEqual(
            vertex.runtime_config["operational_config_sha256"], operational.sha256
        )

    def test_operational_path_components_are_safe_and_collision_resistant(self):
        transformed = safe_operational_component("../same/name")
        other = safe_operational_component(".._same_name")
        self.assertNotIn("/", transformed)
        self.assertNotIn("..", transformed)
        self.assertNotEqual(transformed, other)

    def test_absent_file_preserves_legacy_cli_defaults(self):
        operational = load_operational_config()
        self.assertFalse(operational.diagnostics_enabled)
        self.assertEqual(
            operational.raw["scheduling"]["formalizer_workers"], 1
        )
        self.assertTrue(operational.raw["evidence_collection"]["agent_trace"])
        self.assertIsNone(
            operational.execution_diagnostics_plan(
                provider="google-vertex",
                run_id="run",
                domain="domain",
                data="data",
                problem="p01",
                model_label="model",
                attempt_index=1,
                execution_try=1,
                runtime_id="runtime",
            )
        )

    def test_explicit_overrides_are_resolved_and_change_only_operational_sha(self):
        base = load_operational_config(DEFAULT_OPERATIONAL_CONFIG_PATH)
        changed = load_operational_config(
            DEFAULT_OPERATIONAL_CONFIG_PATH,
            formalizer_workers=4,
            credential_profile="google-vertex-fallback",
            agent_trace=False,
        )

        self.assertNotEqual(base.sha256, changed.sha256)
        self.assertEqual(changed.raw["scheduling"]["formalizer_workers"], 4)
        self.assertEqual(
            changed.raw["credential"]["profile"], "google-vertex-fallback"
        )
        self.assertFalse(changed.raw["evidence_collection"]["agent_trace"])
        self.assertEqual(changed.metadata()["experiment_identity"], "excluded")

    def test_unknown_fields_and_unknown_handlers_fail_fast(self):
        raw = json.loads(DEFAULT_OPERATIONAL_CONFIG_PATH.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unknown_field = deepcopy(raw)
            unknown_field["surprise"] = True
            with self.assertRaisesRegex(ValueError, "unknown field"):
                load_operational_config(self._write(root, unknown_field, "field.json"))

            unknown_handler = deepcopy(raw)
            unknown_handler["infra_diagnostics"]["provider_diagnostics"][
                "handlers"
            ] = {"google_vertex": "builtin:not_registered@1"}
            with self.assertRaisesRegex(ValueError, "unknown provider diagnostic"):
                load_operational_config(
                    self._write(root, unknown_handler, "handler.json")
                )

    def test_network_defaults_are_compatible_and_strictly_operational(self):
        raw = json.loads(DEFAULT_OPERATIONAL_CONFIG_PATH.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = load_operational_config(self._write(root, raw, "new.json"))
            raw.pop("network_resources")
            legacy = load_operational_config(self._write(root, raw, "legacy.json"))
            self.assertEqual(base.raw, legacy.raw)
            raw["network_resources"] = dict(base.raw["network_resources"], safety_margin=3)
            changed = load_operational_config(self._write(root, raw, "changed.json"))
            self.assertNotEqual(base.sha256, changed.sha256)
            self.assertEqual(changed.metadata()["experiment_identity"], "excluded")
            raw["network_resources"]["unknown"] = True
            with self.assertRaisesRegex(ValueError, "network_resources"):
                load_operational_config(self._write(root, raw, "bad.json"))

    def test_handler_provider_keys_are_canonicalized(self):
        raw = json.loads(DEFAULT_OPERATIONAL_CONFIG_PATH.read_text())
        raw["infra_diagnostics"]["provider_diagnostics"]["handlers"] = {
            "google-vertex": "builtin:google_vertex@1"
        }
        with tempfile.TemporaryDirectory() as tmp:
            operational = load_operational_config(
                self._write(Path(tmp), raw, "canonical.json")
            )

        self.assertEqual(
            operational.raw["infra_diagnostics"]["provider_diagnostics"][
                "handlers"
            ],
            {"google_vertex": "builtin:google_vertex@1"},
        )

    def test_metadata_contains_references_but_not_secret_file_contents(self):
        raw = json.loads(DEFAULT_OPERATIONAL_CONFIG_PATH.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets = root / ".env"
            secrets.write_text("GOOGLE_CLOUD_API_KEY=never-record-this\n")
            raw["credential"]["secrets_env_file"] = str(secrets)
            operational = load_operational_config(self._write(root, raw))

        serialized = json.dumps(operational.metadata())
        self.assertIn(str(secrets), serialized)
        self.assertNotIn("never-record-this", serialized)


if __name__ == "__main__":
    unittest.main()
