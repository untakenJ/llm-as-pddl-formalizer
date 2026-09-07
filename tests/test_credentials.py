from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agent_formalizer.benchmark_profile import DEFAULT_BENCHMARK_PROFILE
from agent_formalizer.claws import get_adapter
from agent_formalizer.credentials import load_credential_registry
from sweep_agent_pipeline import _freeze_credential_registry


VERTEX_MODEL = "google-vertex/gemini-3.1-flash-lite"


class CredentialProfileTests(unittest.TestCase):
    def test_logits_provider_default_accepts_dynamic_explicit_model_ids(self):
        registry = load_credential_registry()
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("LOGITS_API_KEY=logits-secret\n")
            credential = registry.resolve(
                "logits/FutureOrg/Model-Added-By-Provider", env_file=env_file
            )
        self.assertEqual(credential.profile_name, "logits-default")
        self.assertEqual(credential.api_key, "logits-secret")
        self.assertNotIn("logits-secret", json.dumps(credential.metadata()))

    def test_default_and_fallback_resolve_as_bound_key_project_pairs(self):
        registry = load_credential_registry()
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "GOOGLE_CLOUD_API_KEY=primary-secret\n"
                "GOOGLE_CLOUD_PROJECT=primary-project\n"
                "FALLBACK_GOOGLE_CLOUD_API_KEY=fallback-secret\n"
                "FALLBACK_GOOGLE_CLOUD_PROJECT=fallback-project\n"
            )
            primary = registry.resolve(VERTEX_MODEL, env_file=env_file)
            fallback = registry.resolve(
                VERTEX_MODEL,
                name="google-vertex-fallback",
                env_file=env_file,
            )

        self.assertEqual(primary.profile_name, "google-vertex-default")
        self.assertEqual(primary.api_key, "primary-secret")
        self.assertEqual(
            primary.provider_options["google_vertex"]["project"],
            "primary-project",
        )
        self.assertEqual(fallback.api_key, "fallback-secret")
        self.assertEqual(
            fallback.provider_options["google_vertex"]["project"],
            "fallback-project",
        )
        serialized = json.dumps(fallback.metadata())
        self.assertIn("FALLBACK_GOOGLE_CLOUD_API_KEY", serialized)
        self.assertIn("FALLBACK_GOOGLE_CLOUD_PROJECT", serialized)
        self.assertNotIn("fallback-secret", serialized)
        self.assertNotIn("fallback-project", serialized)
        self.assertNotIn("fallback-secret", repr(fallback))

    def test_profile_must_belong_to_model_pool(self):
        registry = load_credential_registry()
        with self.assertRaisesRegex(ValueError, "belongs to provider"):
            registry.profile("openai/gpt-5.4-mini", "google-vertex-fallback")

    def test_credential_route_does_not_change_experiment_identity(self):
        primary = get_adapter(
            "hermes",
            model=VERTEX_MODEL,
            api_key="primary-secret",
            credential_provider_options={
                "google_vertex": {"project": "primary-project"}
            },
            credential_metadata={"profile": "google-vertex-default"},
        )
        fallback = get_adapter(
            "hermes",
            model=VERTEX_MODEL,
            api_key="fallback-secret",
            credential_provider_options={
                "google_vertex": {"project": "fallback-project"}
            },
            credential_metadata={"profile": "google-vertex-fallback"},
        )

        self.assertEqual(
            primary.resolved_config.sha256, fallback.resolved_config.sha256
        )
        self.assertEqual(
            primary.resolved_config.sha256,
            DEFAULT_BENCHMARK_PROFILE.resolve("hermes", model=VERTEX_MODEL).sha256,
        )
        self.assertNotEqual(primary.direct_api_base, fallback.direct_api_base)
        self.assertEqual(
            primary.model_auth()["credential"]["profile"],
            "google-vertex-default",
        )
        self.assertEqual(
            fallback.model_auth()["credential"]["profile"],
            "google-vertex-fallback",
        )

    def test_sweep_freezes_registry_without_making_it_experiment_config(self):
        registry = load_credential_registry()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frozen = _freeze_credential_registry(registry, root)
            self.assertEqual(frozen.raw, registry.raw)
            self.assertEqual(
                frozen.path.name,
                "study_credential_profiles.json",
            )

            changed = deepcopy(registry.raw)
            changed["profiles"]["openai-default"]["api_key_env"] = (
                "OPENAI_API_KEY_ROTATED"
            )
            changed_path = root / "changed-credentials.json"
            changed_path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "different frozen credential"):
                _freeze_credential_registry(
                    load_credential_registry(changed_path), root
                )


if __name__ == "__main__":
    unittest.main()
