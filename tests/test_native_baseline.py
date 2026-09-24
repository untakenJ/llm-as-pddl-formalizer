"""The user-approved campaign baseline and explicit derivation contract."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.claws import get_adapter
from agent_formalizer.configuration.benchmark_profile import (
    BENCHMARK_PROFILES_DIR,
    DEFAULT_PROFILE_PATH,
    load_benchmark_profile,
)
from agent_formalizer.run_formalizer_agent import build_parser
from sweep_agent_pipeline import _freeze_study_profile


HARNESSES = ("openclaw", "hermes", "nanobot", "generic", "zeroclaw")


class NativeBaselineTests(unittest.TestCase):
    def test_only_one_production_preset_and_cli_default(self):
        self.assertEqual(
            sorted(p.name for p in BENCHMARK_PROFILES_DIR.glob("*.json")),
            ["native_baseline_v1.json"],
        )
        self.assertEqual(load_benchmark_profile().path, DEFAULT_PROFILE_PATH)
        self.assertIn("native_baseline_v1.json", build_parser().format_help())

    def test_baseline_is_authorized_parent_without_solver_tool(self):
        parent = load_benchmark_profile(
            HISTORICAL_PROFILES_DIR
            / "native_safety_streaming_solver_as_tool_call_checkpoint.json"
        )
        expected = deepcopy(parent.raw)
        expected["profile_id"] = "pddl-native-baseline-v1"
        expected["condition_profile"]["id"] = "native-clean--call-checkpoint-v1"
        expected["condition_profile"]["overrides"]["agent_tools"] = []
        expected["condition_profile"]["overrides"]["generation"] = {"max_output_tokens": "model_max"}
        expected["infra_retry"]["invalidators"].remove("solver_gateway_start_failed")
        self.assertEqual(load_benchmark_profile().raw, expected)

    def test_native_defaults_have_no_solver_tool_or_experimental_skills(self):
        prompts = []
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                adapter = get_adapter(harness)
                resolved = adapter.resolved_config
                self.assertEqual(adapter.model, "google-vertex/gemini-3.1-flash-lite")
                self.assertEqual(resolved.solver_backend, "local")
                self.assertEqual(resolved.model_response_delivery["mode"], "native_streaming")
                self.assertEqual(resolved.raw["resolved"]["external_call_timing"], "call-checkpoint-v1")
                self.assertEqual(resolved.raw["resolved"]["solver_error_routing"], "solver-transient-v1")
                self.assertEqual((resolved.timeout, resolved.max_model_calls, resolved.max_action_steps), (1800, 50, 200))
                self.assertEqual(resolved.attempts_per_case, 1)
                self.assertEqual(resolved.max_execution_tries, 5)
                self.assertEqual(resolved.agent_tools, [])
                self.assertEqual(adapter.runtime_tools(), [])
                self.assertFalse(adapter.pddl_solver_tool_enabled())
                self.assertEqual(adapter.skills_mode, "official")
                self.assertNotIn("experiment_skills", resolved.raw["resolved"])
                self.assertEqual(resolved.generation_overrides, {"output_token_policy": resolved.output_token_policy})
                self.assertEqual(resolved.output_token_policy["max_output_tokens"], 65536)
                prompt = adapter.build_task_prompt("DOMAIN", "PROBLEM")
                self.assertNotIn("pddl-solver", prompt)
                self.assertNotIn(".benchmark-skills", prompt)
                prompts.append(prompt)
        self.assertEqual(len(set(prompts)), 1)

    def test_derived_solver_condition_and_freeze_do_not_mutate_baseline(self):
        baseline = load_benchmark_profile()
        original_bytes = DEFAULT_PROFILE_PATH.read_bytes()
        raw = deepcopy(baseline.raw)
        raw["profile_id"] = "pddl-native-baseline-v1-solver-as-tool"
        raw["condition_profile"]["id"] = "solver-as-tool--call-checkpoint-v1"
        raw["condition_profile"]["overrides"]["agent_tools"] = ["pddl_solver"]
        raw["infra_retry"]["invalidators"].append("solver_gateway_start_failed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "derived.json"
            path.write_text(json.dumps(raw))
            derived = load_benchmark_profile(path)
            frozen = _freeze_study_profile(derived, root)
            self.assertEqual(frozen.raw, derived.frozen_raw())
            self.assertEqual(derived.raw["benchmark_envelope"], baseline.raw["benchmark_envelope"])
            for harness in HARNESSES:
                adapter = get_adapter(harness, benchmark_profile=frozen)
                self.assertEqual(adapter.agent_tools(), ["pddl_solver"])
                self.assertIn("pddl-solver", adapter.build_task_prompt("DOMAIN", "PROBLEM"))
                self.assertNotEqual(adapter.resolved_config.sha256, baseline.resolve(harness).sha256)
        self.assertEqual(DEFAULT_PROFILE_PATH.read_bytes(), original_bytes)

    def test_legacy_explicit_inputs_load_but_removed_paths_do_not_alias(self):
        for path in HISTORICAL_PROFILES_DIR.glob("*.json"):
            with self.subTest(profile=path.name):
                profile = load_benchmark_profile(path)
                harness = "minimum" if "minimum_agent" in profile.raw["condition_profile"]["overrides"] else "hermes"
                profile.resolve(harness)
                with self.assertRaisesRegex(ValueError, "Cannot load benchmark profile"):
                    load_benchmark_profile(BENCHMARK_PROFILES_DIR / path.name)


if __name__ == "__main__":
    unittest.main()
