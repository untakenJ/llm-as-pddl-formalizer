from __future__ import annotations

import json
import os
from copy import deepcopy
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from agent_formalizer.claws import CLAWS, get_adapter
from agent_formalizer.benchmark_profile import (
    BENCHMARK_PROFILES_DIR,
    DEFAULT_BENCHMARK_PROFILE,
    DEFAULT_PROFILE_PATH,
    load_benchmark_profile,
    with_google_vertex_project,
)
from agent_formalizer.claws.common import (
    google_vertex_openai_base,
    jsonl_steps,
    safe_component,
    split_model_id,
    tool_records,
)
from agent_formalizer.claws.generic import (
    GenericAgentAdapter,
    _parse_usage_text,
)
from agent_formalizer.claws.hermes import HermesAdapter, _read_hermes_usage
from agent_formalizer.claws.nanobot import (
    NANOBOT_USAGE_CAPTURE_SOURCE,
    NANOBOT_USAGE_PATH,
    NanoBotAdapter,
    _nanobot_usage_measurement,
    _normalize_nanobot_usage,
)
from agent_formalizer.claws.openclaw import (
    OpenClawAdapter,
    _normalize_openclaw_usage,
)
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter, _parse_costs
from agent_formalizer.config import CLAW_DEFAULTS, agent_model_label
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.util import read_named_secret, read_named_setting
from sweep_agent_pipeline import (
    _formalize_indices_for_resume,
    _freeze_study_profile,
    _qualify_model_label,
    _resolve_model_label,
)

NATIVE_HARNESSES = {"openclaw", "hermes", "nanobot", "zeroclaw", "generic"}


class AdapterRegistryTests(unittest.TestCase):
    def test_all_requested_harnesses_are_registered(self):
        self.assertEqual(
            set(CLAWS),
            {*NATIVE_HARNESSES, "minimum"},
        )

    def test_defaults_construct(self):
        for name in NATIVE_HARNESSES:
            with self.subTest(name=name):
                adapter = get_adapter(name)
                self.assertEqual(adapter.name, name)
                self.assertEqual(adapter.model, "google-vertex/gemini-3.1-flash-lite")
                self.assertEqual(adapter.timeout, 1800)
                self.assertEqual(adapter.max_model_calls, 50)
                self.assertEqual(adapter.max_action_steps, 200)
                self.assertFalse(adapter.allow_network)
                self.assertEqual(
                    adapter.resolved_config.model_error_routing,
                    DEFAULT_BENCHMARK_PROFILE.raw["benchmark_envelope"]
                    ["model_error_routing"],
                )

    def test_versioned_profile_drives_every_default(self):
        self.assertEqual(DEFAULT_BENCHMARK_PROFILE.schema_version, 3)
        self.assertEqual(DEFAULT_PROFILE_PATH.parent, BENCHMARK_PROFILES_DIR)
        self.assertEqual(DEFAULT_PROFILE_PATH.name, "native_safety_native_clean.json")
        envelope = DEFAULT_BENCHMARK_PROFILE.raw["benchmark_envelope"]
        self.assertEqual(envelope["id"], "native-safety-v4")
        self.assertEqual(
            set(envelope["safety_guards"]),
            {
                "harness_execution_timeout_seconds",
                "control_model_request_attempts",
                "action_steps",
            },
        )
        self.assertIn("actions", envelope["required_evidence"])
        self.assertIn(
            "state-isolation",
            {row["preset"] for row in envelope["validations"]},
        )
        self.assertEqual(
            load_benchmark_profile(
                BENCHMARK_PROFILES_DIR / "native_safety_solver_as_tool.json"
            ).raw["condition_profile"]["id"],
            "solver-as-tool",
        )
        temperature_profile = load_benchmark_profile(
            BENCHMARK_PROFILES_DIR / "native_safety_temperature_0_1.json"
        )
        solver_temperature_profile = load_benchmark_profile(
            BENCHMARK_PROFILES_DIR
            / "native_safety_solver_as_tool_temperature_0_1.json"
        )
        for name in NATIVE_HARNESSES:
            self.assertEqual(
                temperature_profile.resolve(name).generation_overrides,
                {"temperature": 0.1},
            )
            resolved = solver_temperature_profile.resolve(name)
            self.assertEqual(
                resolved.generation_overrides,
                {"temperature": 0.1},
            )
            self.assertEqual(resolved.agent_tools, ["pddl_solver"])
        self.assertEqual(
            {value["model"] for value in CLAW_DEFAULTS.values()},
            {DEFAULT_BENCHMARK_PROFILE.default_model},
        )

    def test_model_call_budget_cannot_exceed_action_step_budget(self):
        raw = deepcopy(DEFAULT_BENCHMARK_PROFILE.raw)
        raw["benchmark_envelope"]["safety_guards"]["action_steps"]["limit"] = 49
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid-budget.json"
            path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(
                ValueError, "cannot exceed action_steps.limit"
            ):
                load_benchmark_profile(path)

    def test_practical_unlimited_profile_uses_large_integer_budgets(self):
        profile = load_benchmark_profile(
            BENCHMARK_PROFILES_DIR / "native_clean_practical_unlimited.json"
        )
        for name in NATIVE_HARNESSES:
            with self.subTest(name=name):
                resolved = profile.resolve(name)
                self.assertEqual(resolved.timeout, 2_147_483_647)
                self.assertEqual(resolved.max_model_calls, 2_147_483_647)
                self.assertEqual(resolved.max_action_steps, 2_147_483_647)
                self.assertEqual(
                    resolved.raw["condition_profile"]["id"],
                    "practical-unlimited",
                )

    def test_unrestricted_legacy_network_flag_is_rejected(self):
        for name in NATIVE_HARNESSES:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    get_adapter(name, allow_network=True)

    def test_controlled_web_requires_and_records_allowlist(self):
        raw = deepcopy(DEFAULT_BENCHMARK_PROFILE.raw)
        raw["condition_profile"] = {
            "id": "controlled-docs",
            "overrides": {
                "network_mode": "controlled_web",
                "controlled_web_allowlist": ["docs.example.org"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(raw))
            from agent_formalizer.benchmark_profile import load_benchmark_profile
            profile = load_benchmark_profile(path)
            for name in NATIVE_HARNESSES:
                adapter = get_adapter(name, benchmark_profile=profile)
                self.assertEqual(adapter.network_policy()["mode"], "controlled_web")
                self.assertEqual(
                    adapter.network_policy()["controlled_web_allowlist"],
                    ["docs.example.org"],
                )
                if name == "openclaw":
                    adapter._cleanup_run_state()


class ProviderTests(unittest.TestCase):
    def test_runner_dotenv_reads_only_named_values_without_exporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "IGNORED=personal-setting\n"
                "GOOGLE_CLOUD_PROJECT='study-project'\n"
                "GOOGLE_CLOUD_API_KEY=runner-secret # comment\n"
            )
            with patch.dict(os.environ, {"GOOGLE_CLOUD_API_KEY": "ambient"}):
                self.assertEqual(
                    read_named_secret("GOOGLE_CLOUD_API_KEY", path),
                    "runner-secret",
                )
            self.assertEqual(
                read_named_setting("GOOGLE_CLOUD_PROJECT", path), "study-project"
            )
            self.assertNotIn("IGNORED", os.environ)

    def test_legacy_benchmark_vertex_project_participates_in_hash(self):
        materialized = with_google_vertex_project(
            DEFAULT_BENCHMARK_PROFILE, "study-project"
        )
        self.assertNotEqual(materialized.sha256, DEFAULT_BENCHMARK_PROFILE.sha256)
        self.assertEqual(
            materialized.raw["providers"]["google_vertex"]["project"],
            "study-project",
        )

    def test_real_secret_is_gateway_only_for_all_harnesses(self):
        secret = "must-not-reach-agent"
        for name in NATIVE_HARNESSES:
            with self.subTest(name=name):
                adapter = get_adapter(
                    name,
                    model="openai/test-model",
                    api_key=secret,
                    api_key_name="BENCHMARK_KEY",
                )
                self.assertEqual(adapter.model_gateway_secret(), secret)
                self.assertNotIn(secret, json.dumps(adapter.effective_config()))
                if name == "openclaw":
                    self.assertNotIn(secret, json.dumps(adapter.container_run_args("x")))
                    adapter._cleanup_run_state()
                else:
                    self.assertNotIn(
                        secret, json.dumps(adapter.docker_exec_env_args())
                    )

    def test_default_label_separates_harnesses(self):
        self.assertEqual(
            agent_model_label("hermes", "openrouter/anthropic/claude"),
            "hermes__openrouter__anthropic__claude",
        )

    def test_sweep_label_separates_claw_model_jobs(self):
        self.assertEqual(
            _resolve_model_label("nanobot", "openai/gpt", None, 2),
            "nanobot__openai__gpt",
        )
        with self.assertRaises(ValueError):
            _resolve_model_label("nanobot", "openai/gpt", "custom", 2)

    def test_output_label_always_contains_config_identity(self):
        self.assertEqual(
            _qualify_model_label("custom", "native--default--abc123"),
            "custom__native--default--abc123",
        )
        self.assertEqual(
            _qualify_model_label(
                "custom__native--default--abc123",
                "native--default--abc123",
            ),
            "custom__native--default--abc123",
        )

    def test_sweep_freezes_profile_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frozen = _freeze_study_profile(DEFAULT_BENCHMARK_PROFILE, root)
            self.assertEqual(frozen.raw, DEFAULT_BENCHMARK_PROFILE.raw)
            changed = deepcopy(DEFAULT_BENCHMARK_PROFILE.raw)
            changed["condition_profile"]["id"] = "changed"
            profile_path = root / "changed.json"
            profile_path.write_text(json.dumps(changed))
            from agent_formalizer.benchmark_profile import load_benchmark_profile
            with self.assertRaises(ValueError):
                _freeze_study_profile(load_benchmark_profile(profile_path), root)

    def test_nested_gateway_model_is_preserved(self):
        self.assertEqual(
            split_model_id("openrouter/anthropic/claude-sonnet"),
            ("openrouter", "anthropic/claude-sonnet"),
        )

    def test_model_requires_provider_prefix(self):
        with self.assertRaises(ValueError):
            split_model_id("gpt-5.4-mini")

    def test_api_key_override_is_reported_without_value(self):
        adapter = HermesAdapter(
            "openai/gpt-5.4-mini",
            10,
            model_api_keys={"openai/gpt-5.4-mini": "BENCH_KEY"},
        )
        with patch.dict(os.environ, {"BENCH_KEY": "do-not-record"}, clear=False):
            auth = adapter.model_auth()
        self.assertEqual(auth["api_key_env"], "BENCH_KEY")
        self.assertTrue(auth["api_key_present"])
        self.assertNotIn("do-not-record", json.dumps(auth))

    def test_openclaw_host_commands_ignore_operator_openclaw_environment(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENCLAW_CONFIG_PATH": "/home/operator/personal.json",
                "OPENCLAW_PROFILE": "personal",
                "OPENCLAW_BUNDLED_SKILLS_DIR": "/home/operator/skills",
                "CLAWDBOT_GATEWAY_PASSWORD": "personal-password",
            },
            clear=False,
        ):
            adapter = OpenClawAdapter(
                "openai/gpt-5.4-mini", 120, max_action_steps=200
            )
            env = adapter._openclaw_env()
            self.assertEqual(env["OPENCLAW_CONFIG_PATH"], str(adapter._config_path()))
            self.assertEqual(env["OPENCLAW_STATE_DIR"], str(adapter._state_dir))
            self.assertEqual(env["OPENCLAW_NO_AUTO_UPDATE"], "1")
            self.assertNotIn("OPENCLAW_PROFILE", env)
            self.assertNotIn("OPENCLAW_BUNDLED_SKILLS_DIR", env)
            self.assertNotIn("CLAWDBOT_GATEWAY_PASSWORD", env)
            self.assertNotIn("test-key", json.dumps(env))
            adapter._cleanup_run_state()

    def test_safe_component_retains_full_identity_in_hash(self):
        shared = "case-" + ("x" * 240)
        first = safe_component(shared + "-runtime-one")
        second = safe_component(shared + "-runtime-two")
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), 160)
        self.assertLessEqual(len(second), 160)

    def test_openclaw_attempt_mounts_and_trash_are_not_shared(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.claws.openclaw.OPENCLAW_BENCHMARK_STATE_DIR",
            Path(tmp),
        ):
            adapter = OpenClawAdapter(
                "openai/gpt-5.4-mini", 120, api_key="test-key"
            )
            try:
                first_args = adapter.container_run_args("case-one")
                first = adapter._attempt_for_instance("case-one")
                (first.state_dir / ".Trash" / "prior-case").mkdir(parents=True)
                (first.state_dir / ".Trash" / "prior-case" / "domain.pddl").write_text(
                    "private"
                )

                second_args = adapter.container_run_args("case-two")
                second = adapter._attempt_for_instance("case-two")
                self.assertNotEqual(first.root, second.root)
                self.assertNotIn(str(first.root), " ".join(second_args))
                self.assertNotIn(str(second.root), " ".join(first_args))
                self.assertNotIn(
                    str(adapter._attempts_root) + ":/root/.openclaw",
                    " ".join(second_args),
                )
                self.assertFalse((second.state_dir / ".Trash").exists())
                self.assertEqual(
                    set(adapter.state_isolation_spec("case-two")["writable_bind_sources"]),
                    {str(second.state_dir), str(second.workspace_dir)},
                )

                first_root = first.root
                second_root = second.root
                adapter.delete_agent("unused", instance_id="case-one")
                self.assertFalse(first_root.exists())
                self.assertTrue(second_root.exists())
            finally:
                adapter._cleanup_run_state()

    def test_sweep_resume_uses_valid_completion_not_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_label = "openclaw__google-vertex__gemini"
            base = root / "llm-as-formalizer-agent" / "blocksworld" / "dataset" / model_label

            ok = base / "p01"
            ok.mkdir(parents=True)
            (ok / "completion.json").write_text(
                json.dumps({"complete": True, "attempt_valid": True})
            )
            (ok / f"p01_{model_label}_df.pddl").write_text("domain")
            (ok / f"p01_{model_label}_pf.pddl").write_text("problem")
            (ok / "agent_stderr.log").write_text(
                "recovered after Google Vertex AI API error (429)"
            )

            agent_failure = base / "p02"
            agent_failure.mkdir()
            (agent_failure / "completion.json").write_text(
                json.dumps({"complete": True, "attempt_valid": True,
                            "generation_success": False})
            )

            rate_limited = base / "p03"
            rate_limited.mkdir()
            (rate_limited / "completion.json").write_text(
                json.dumps({"complete": True, "attempt_valid": True,
                            "generation_success": False, "error": "429"})
            )
            (rate_limited / "agent_stderr.log").write_text(
                "Google Vertex AI API error (429): Resource exhausted"
            )

            incomplete_ok = base / "p05"
            incomplete_ok.mkdir()
            (incomplete_ok / "completion.json").write_text(
                json.dumps({"complete": False, "attempt_valid": True})
            )

            pending = _formalize_indices_for_resume(
                root, "blocksworld", "dataset", model_label, [1, 2, 3, 4, 5]
            )

        self.assertEqual(pending, [4, 5])


class GeneratedConfigTests(unittest.TestCase):
    def test_state_validation_rejects_undeclared_writable_bind(self):
        adapter = SimpleNamespace(
            runtime_tools=lambda: [],
            state_isolation_spec=lambda instance_id: {
                "mode": "isolated",
                "scope": "per_attempt",
                "personal_harness_state": "excluded",
                "cross_attempt_reuse": False,
                "attempt_root": None,
                "writable_bind_sources": [],
                "tests": {},
            }
        )
        workspace = AgentWorkspace("case", "container", adapter)
        inspected = subprocess.CompletedProcess(
            ["docker", "inspect", "container"],
            0,
            stdout=json.dumps(
                [
                    {
                        "Mounts": [
                            {
                                "Type": "bind",
                                "Source": "/shared/cross-case-state",
                                "Destination": "/state",
                                "RW": True,
                            },
                            {
                                "Type": "bind",
                                "Source": "/shared/read-only-history",
                                "Destination": "/history",
                                "RW": False,
                            }
                        ]
                    }
                ]
            ),
            stderr="",
        )
        with patch(
            "agent_formalizer.workspace.subprocess.run", return_value=inspected
        ):
            report = workspace.validate_state_isolation()
        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["tests"]["writable_bind_mounts_exact"])
        self.assertFalse(report["tests"]["readonly_bind_mounts_exact"])

    def setUp(self):
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_hermes_config_is_clean(self):
        adapter = HermesAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        config = adapter._benchmark_config()
        self.assertEqual(config["model"]["provider"], "openai-api")
        self.assertNotIn("max_turns", config["agent"])
        self.assertEqual(config["plugins"]["enabled"], [])
        self.assertNotIn("test-secret", json.dumps(config))

    def test_nanobot_config_preserves_clean_native_tools(self):
        adapter = NanoBotAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        config = adapter._benchmark_config()
        self.assertEqual(
            config["providers"]["openai"]["apiKey"],
            "${PDDL_BENCHMARK_API_KEY}",
        )
        self.assertNotIn("test-secret", json.dumps(config))
        self.assertTrue(config["tools"]["web"]["enable"])
        self.assertFalse(config["tools"]["restrictToWorkspace"])
        self.assertTrue(config["tools"]["cliApps"]["enable"])
        self.assertTrue(config["tools"]["my"]["enable"])
        self.assertEqual(config["agents"]["defaults"]["fallbackModels"], [])
        self.assertNotIn("maxToolIterations", config["agents"]["defaults"])
        self.assertEqual(config["tools"]["mcpServers"], {})

    def test_nanobot_usage_wrapper_is_valid_python(self):
        compile(
            NANOBOT_USAGE_CAPTURE_SOURCE,
            "nanobot-benchmark-usage-wrapper.py",
            "exec",
        )

    def test_nanobot_usage_wrapper_captures_aggregate_run_usage(self):
        class FakeAgentHook:
            def __init__(self):
                pass

        class FakeAgentLoop:
            async def process_direct(self, *args, **kwargs):
                context = SimpleNamespace(
                    usage={
                        "prompt_tokens": 36,
                        "completion_tokens": 14,
                        "total_tokens": 50,
                        "provider_tokens": 45,
                        "estimated_tokens": 5,
                    },
                    stop_reason="completed",
                    error=None,
                )
                for hook in kwargs["hooks"]:
                    await hook.after_run(context)

        def fake_app():
            import asyncio

            asyncio.run(FakeAgentLoop().process_direct("task"))

        modules = {
            name: ModuleType(name)
            for name in (
                "nanobot",
                "nanobot.agent",
                "nanobot.agent.hook",
                "nanobot.agent.loop",
                "nanobot.cli",
                "nanobot.cli.commands",
            )
        }
        modules["nanobot.agent.hook"].AgentHook = FakeAgentHook
        modules["nanobot.agent.loop"].AgentLoop = FakeAgentLoop
        modules["nanobot.cli.commands"].app = fake_app

        with tempfile.TemporaryDirectory() as tmp:
            usage_path = Path(tmp) / "usage.json"
            source = NANOBOT_USAGE_CAPTURE_SOURCE.replace(
                repr(NANOBOT_USAGE_PATH),
                repr(str(usage_path)),
                1,
            )
            with patch.dict(sys.modules, modules):
                exec(compile(source, "nanobot-usage-test.py", "exec"), {})
            report = json.loads(usage_path.read_text())

        self.assertEqual(report["capture_status"], "complete")
        self.assertEqual(report["raw_usage"]["total_tokens"], 50)
        self.assertEqual(report["raw_usage"]["provider_tokens"], 45)
        self.assertEqual(report["raw_usage"]["estimated_tokens"], 5)

    def test_nanobot_session_path_matches_pinned_session_manager(self):
        self.assertEqual(
            NanoBotAdapter._session_path("pddl-blocksworld-p01-model"),
            (
                "/workspace/sessions/"
                "benchmark_pddl-blocksworld-p01-model.jsonl"
            ),
        )

    def test_zeroclaw_v3_config_has_no_persisted_key(self):
        adapter = ZeroClawAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        config = adapter._benchmark_config_toml()
        self.assertIn("schema_version = 3", config)
        self.assertNotIn("max_tool_iterations", config)
        self.assertIn('auto_approve = ["shell", "file_read"', config)
        self.assertIn("allowed_tools = []", config)
        self.assertNotIn("native_tools = true", config)
        self.assertNotIn("test-secret", config)
        self.assertNotIn("api_key =", config)

    def test_zeroclaw_vertex_custom_provider_enables_native_tools(self):
        options = {
            "google_vertex": {
                "project": "benchmark-project",
                "location": "global",
                "origin": "https://aiplatform.googleapis.com",
            }
        }
        adapter = ZeroClawAdapter(
            "google-vertex/gemini-3.1-flash-lite",
            120,
            max_action_steps=200,
            provider_options=options,
        )
        config = adapter._benchmark_config_toml()
        self.assertIn("[providers.models.custom.benchmark]", config)
        self.assertIn("native_tools = true", config)
        self.assertIn('wire_api = "chat_completions"', config)

    def test_generic_mykey_reads_secret_from_environment(self):
        adapter = GenericAgentAdapter("openai/gpt-5.4-mini", 120)
        source = adapter._mykey_source()
        self.assertIn("PDDL_BENCHMARK_API_KEY", source)
        self.assertNotIn("test-secret", source)

    def test_generic_tool_schema_preserves_official_bundle(self):
        adapter = GenericAgentAdapter("openai/gpt-5.4-mini", 120)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            config = root / "config"
            assets.mkdir()
            config.mkdir()
            source = [
                {"function": {"name": name}}
                for name in ("code_run", "file_read", "web_scan", "ask_user")
            ]
            for filename in ("tools_schema.json", "tools_schema_cn.json"):
                (assets / filename).write_text(json.dumps(source))
            adapter.runtime_repo = root
            adapter._write_filtered_schemas(config)
            copied = json.loads((config / "tools_schema.json").read_text())
        names = {entry["function"]["name"] for entry in copied}
        self.assertEqual(names, {"code_run", "file_read", "web_scan", "ask_user"})

    def test_vertex_configs_use_cloud_endpoint_without_persisting_key(self):
        options = {"google_vertex": {
            "project": "benchmark-project",
            "location": "global",
            "origin": "https://aiplatform.googleapis.com",
        }}
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "ignored-host"}, clear=False):
            model = "google-vertex/gemini-3.1-flash-lite"
            expected_base = (
                "https://aiplatform.googleapis.com/v1/projects/benchmark-project/"
                "locations/global/endpoints/openapi"
            )
            self.assertEqual(google_vertex_openai_base(options), expected_base)

            hermes = HermesAdapter(model, 120, provider_options=options)._benchmark_config()
            self.assertEqual(hermes["model"]["provider"], "custom")
            self.assertEqual(
                hermes["model"]["default"], "google/gemini-3.1-flash-lite"
            )
            gateway_base = (
                "http://model-gateway:8766/v1/projects/benchmark-project/"
                "locations/global/endpoints/openapi"
            )
            self.assertEqual(hermes["model"]["base_url"], gateway_base)
            self.assertEqual(hermes["model"]["default_headers"]["Authorization"], "")

            nanobot = NanoBotAdapter(model, 120, provider_options=options)._benchmark_config()
            self.assertEqual(
                nanobot["agents"]["defaults"]["model"],
                "google/gemini-3.1-flash-lite",
            )
            self.assertEqual(nanobot["providers"]["openai"]["apiBase"], gateway_base)
            self.assertEqual(nanobot["agents"]["defaults"]["disabledSkills"], [])
            self.assertEqual(
                nanobot["providers"]["openai"]["extraHeaders"]["Authorization"],
                "",
            )

            zeroclaw = ZeroClawAdapter(
                model, 120, provider_options=options
            )._benchmark_config_toml()
            self.assertIn('model = "google/gemini-3.1-flash-lite"', zeroclaw)
            self.assertIn("http://model-gateway:8766/v1/projects/benchmark-project", zeroclaw)
            self.assertIn("native_tools = true", zeroclaw)

            generic = GenericAgentAdapter(model, 120, provider_options=options)
            generic_key = generic._mykey_source()
            self.assertIn("google/gemini-3.1-flash-lite", generic_key)

        serialized = json.dumps(
            {"hermes": hermes, "nanobot": nanobot, "zeroclaw": zeroclaw}
        ) + generic_key
        self.assertNotIn("ignored-host", serialized)

    def test_generic_uses_unmodified_native_entrypoint(self):
        adapter = GenericAgentAdapter("openai/gpt-5.4-mini", 120, 200)
        self.assertFalse(hasattr(adapter, "_agentmain_wrapper_source"))
        self.assertNotIn(
            "max_turns_patch",
            adapter.effective_config()["harness_config"],
        )

    def test_generic_container_args_avoid_nested_schema_file_mounts(self):
        adapter = GenericAgentAdapter("openai/gpt-5.4-mini", 120, api_key="test-key")
        try:
            args = adapter.container_run_args("generic-mount-regression")
            joined = " ".join(args)
            self.assertIn(f"{adapter.runtime_repo}:{adapter.runtime_repo}:ro", joined)
            self.assertIn(f"{adapter.runtime_repo / 'temp'}:rw", joined)
            self.assertIn(f"{adapter.runtime_repo / 'memory'}:rw", joined)
            self.assertNotIn("tools_schema.json:", joined)
            self.assertNotIn("tools_schema_cn.json:", joined)
        finally:
            state = adapter._instance_states.pop("generic-mount-regression", None)
            if state and state.exists():
                shutil.rmtree(state)

    def test_generic_long_instance_ids_get_distinct_private_state(self):
        adapter = GenericAgentAdapter(
            "openai/gpt-5.4-mini", 120, api_key="test-key"
        )
        shared = "logistics-dataset-" + ("same-prefix-" * 30)
        first_id = shared + "runtime-one"
        second_id = shared + "runtime-two"
        first = None
        second = None
        try:
            adapter.container_run_args(first_id)
            adapter.container_run_args(second_id)
            first = adapter._instance_states[first_id]
            second = adapter._instance_states[second_id]
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, second.parent)
            self.assertNotEqual(
                set(adapter.state_isolation_spec(first_id)["writable_bind_sources"]),
                set(adapter.state_isolation_spec(second_id)["writable_bind_sources"]),
            )
        finally:
            adapter.delete_agent("unused-first", instance_id=first_id)
            adapter.delete_agent("unused-second", instance_id=second_id)


class ArtifactParsingTests(unittest.TestCase):
    @staticmethod
    def _write_hermes_db(path: Path) -> None:
        with sqlite3.connect(path) as connection:
            connection.execute(
                """CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    message_count INTEGER,
                    tool_call_count INTEGER,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cache_read_tokens INTEGER,
                    cache_write_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    api_call_count INTEGER,
                    estimated_cost_usd REAL,
                    actual_cost_usd REAL
                )"""
            )
            connection.executemany(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("s1", 7, 2, 100, 20, 30, 4, 5, 2, 0.01, None),
                    ("s2", 3, 1, 40, 10, 6, 0, 2, 1, 0.02, 0.025),
                ],
            )

    def test_hermes_usage_is_aggregated_from_one_problem_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            self._write_hermes_db(db_path)
            usage = _read_hermes_usage(db_path)

        self.assertEqual(
            usage,
            {
                "input": 140,
                "output": 30,
                "cacheRead": 36,
                "cacheWrite": 4,
                "reasoning": 7,
                "apiCalls": 3,
                "sessions": 2,
                "messages": 10,
                "toolCalls": 3,
                "estimatedCostUsd": 0.03,
                "actualCostUsd": 0.025,
                "total": 210,
            },
        )

    def test_hermes_collect_usage_writes_problem_owned_artifacts(self):
        adapter = HermesAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        instance_id = "blocksworld-dataset-p01"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_db = root / "fixture.db"
            artifact_dir = root / "p01"
            self._write_hermes_db(fixture_db)

            class FakeWorkspace:
                def __init__(self):
                    self.instance_id = instance_id
                    self.commands = []
                    self.sources = []

                def run_in_container(self, command, timeout=300):
                    self.commands.append((command, timeout))
                    return SimpleNamespace(exit_code=0, stdout="", stderr="")

                def copy_from_container(self, source, destination):
                    self.sources.append(source)
                    target = Path(destination)
                    if source.endswith("/state.snapshot.db"):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(fixture_db, target)
                        return True
                    if source.endswith("/sessions"):
                        target.mkdir(parents=True, exist_ok=True)
                        (target / "transcript.jsonl").write_text("{}\n")
                        return True
                    return False

            workspace = FakeWorkspace()
            usage = adapter.collect_usage(workspace, artifact_dir)
            report = json.loads((artifact_dir / "sessions" / "usage.json").read_text())

        task_home = adapter._task_home(instance_id)
        self.assertIn(task_home, workspace.commands[0][0])
        self.assertIn(f"{task_home}/state.snapshot.db", workspace.sources)
        self.assertIn(f"{task_home}/sessions", workspace.sources)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["instance_id"], instance_id)
        self.assertEqual(report["hermes_home"], task_home)
        self.assertEqual(report["usage"], usage)
        self.assertEqual(usage["total"], 210)

    def test_hermes_snapshot_command_includes_committed_wal_rows(self):
        adapter = HermesAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "live.db"
            snapshot = Path(tmp) / "snapshot.db"
            connection = sqlite3.connect(source)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA wal_autocheckpoint=0")
                connection.execute("CREATE TABLE records (value TEXT)")
                connection.execute("INSERT INTO records VALUES ('committed-in-wal')")
                connection.commit()
                self.assertTrue(Path(f"{source}-wal").is_file())

                result = subprocess.run(
                    adapter._snapshot_command(str(source), str(snapshot)),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                with sqlite3.connect(snapshot) as copied:
                    rows = copied.execute("SELECT value FROM records").fetchall()
                self.assertEqual(rows, [("committed-in-wal",)])
                self.assertFalse(Path(f"{snapshot}-wal").exists())
            finally:
                connection.close()

    def test_hermes_collection_error_is_diagnostic_not_an_exception(self):
        adapter = HermesAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )

        class MissingStateWorkspace:
            instance_id = "domain-dataset-p03"

            @staticmethod
            def run_in_container(command, timeout=300):
                return SimpleNamespace(
                    exit_code=1,
                    stdout="",
                    stderr="state.db does not exist",
                )

            @staticmethod
            def copy_from_container(source, destination):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "p03"
            old_sessions = artifact_dir / "sessions"
            old_sessions.mkdir(parents=True)
            (old_sessions / "state.db").write_text("stale previous attempt")
            (old_sessions / "state.db-wal").write_text("stale wal")

            usage = adapter.collect_usage(MissingStateWorkspace(), artifact_dir)
            report = json.loads((old_sessions / "usage.json").read_text())

            self.assertEqual(usage, {})
            self.assertEqual(report["status"], "error")
            self.assertIn("state.db does not exist", report["error"])
            self.assertFalse((old_sessions / "state.db").exists())
            self.assertFalse((old_sessions / "state.db-wal").exists())

    def test_hermes_problem_homes_are_distinct(self):
        first = HermesAdapter._task_home("domain-dataset-p01")
        second = HermesAdapter._task_home("domain-dataset-p02")
        self.assertNotEqual(first, second)

    def test_nanobot_jsonl_steps_and_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            rows = [
                {"_type": "metadata", "key": "benchmark:x"},
                {"role": "user", "content": "task"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "write_file", "arguments": '{"path":"x"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
                {"role": "assistant", "content": "done"},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows))
            steps = list(jsonl_steps([path]))
            tools = list(tool_records(steps))
        self.assertEqual([step["event"] for step in steps], [
            "message", "message", "tool_call", "tool_result", "message"
        ])
        self.assertEqual(tools[0]["name"], "write_file")
        self.assertEqual(tools[0]["arguments"], {"path": "x"})

    def test_openclaw_uses_aggregate_usage_and_recomputes_total(self):
        usage = _normalize_openclaw_usage(
            {
                "usage": {
                    "input": 57_678,
                    "output": 2_237,
                    "cacheRead": 127_945,
                    # OpenClaw currently exposes the last-call total here.
                    "total": 17_879,
                },
                "lastCallUsage": {
                    "input": 305,
                    "output": 48,
                    "cacheRead": 17_526,
                    "total": 17_879,
                },
            }
        )
        self.assertEqual(
            usage,
            {
                "input": 57_678,
                "output": 2_237,
                "cacheRead": 127_945,
                "cacheWrite": 0,
                "total": 187_860,
            },
        )

    def test_nanobot_usage_normalizes_cached_prompt_tokens(self):
        raw = {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "cached_tokens": 30,
            "provider_tokens": 120,
        }
        self.assertEqual(
            _normalize_nanobot_usage(raw),
            {
                "input": 70,
                "output": 20,
                "cacheRead": 30,
                "cacheWrite": 0,
                "total": 120,
                "providerTokens": 120,
                "estimatedTokens": 0,
            },
        )
        self.assertEqual(
            _nanobot_usage_measurement(raw),
            "provider-reported",
        )

    def test_nanobot_usage_marks_estimated_and_mixed_measurements(self):
        estimated = {
            "prompt_tokens": 11,
            "completion_tokens": 4,
            "total_tokens": 15,
            "estimated_tokens": 15,
        }
        mixed = {
            **estimated,
            "provider_tokens": 8,
        }
        self.assertEqual(
            _nanobot_usage_measurement(estimated),
            "nanobot-estimated",
        )
        self.assertEqual(_nanobot_usage_measurement(mixed), "mixed")

    def test_nanobot_collect_usage_preserves_raw_report(self):
        raw = {
            "prompt_tokens": 50,
            "completion_tokens": 7,
            "total_tokens": 57,
            "provider_tokens": 57,
        }

        class FakeWorkspace:
            def __init__(self):
                self.sources = []

            def copy_from_container(self, source, destination):
                self.sources.append(source)
                Path(destination).write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "source": "nanobot-agent-run-result",
                            "capture_status": "complete",
                            "raw_usage": raw,
                        }
                    )
                )
                return True

        adapter = NanoBotAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "p01"
            workspace = FakeWorkspace()
            usage = adapter.collect_usage(workspace, artifact_dir)
            report = json.loads(
                (artifact_dir / "sessions" / "usage.json").read_text()
            )

        self.assertEqual(workspace.sources, [NANOBOT_USAGE_PATH])
        self.assertEqual(report["raw_usage"], raw)
        self.assertEqual(report["measurement"], "provider-reported")
        self.assertEqual(report["usage"], usage)
        self.assertEqual(usage["input"], 50)
        self.assertEqual(usage["output"], 7)
        self.assertEqual(usage["total"], 57)

    def test_nanobot_missing_usage_is_diagnostic(self):
        class MissingWorkspace:
            @staticmethod
            def copy_from_container(source, destination):
                return False

        adapter = NanoBotAdapter(
            "openai/gpt-5.4-mini", 120, max_action_steps=200
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "p02"
            usage = adapter.collect_usage(MissingWorkspace(), artifact_dir)
            report = json.loads(
                (artifact_dir / "sessions" / "usage.json").read_text()
            )

        self.assertEqual(usage, {})
        self.assertEqual(report["capture_status"], "missing")

    def test_generic_usage(self):
        usage = _parse_usage_text(
            "[Cache] input=10 cached=3\n[Output] tokens=4\n"
            "[Cache] input=20 creation=5 read=6\n[Output] tokens=7\n"
        )
        self.assertEqual(
            usage,
            {
                "input": 27,
                "output": 11,
                "cacheRead": 9,
                "cacheWrite": 5,
                "total": 52,
            },
        )

    def test_zeroclaw_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "costs.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 2,
                            "cached_input_tokens": 4,
                        }
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "usage": {
                            "prompt_tokens": 3,
                            "completion_tokens": 4,
                            "cached_tokens": 1,
                        }
                    }
                )
                + "\n"
            )
            usage = _parse_costs(path)
        self.assertEqual(
            usage,
            {
                "input": 8,
                "output": 6,
                "cacheRead": 5,
                "cacheWrite": 0,
                "reasoning": 0,
                "total": 19,
            },
        )
        self.assertNotIn("turns", usage)


if __name__ == "__main__":
    unittest.main()
