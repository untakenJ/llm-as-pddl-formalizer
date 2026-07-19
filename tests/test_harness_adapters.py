from __future__ import annotations

import json
import os
from copy import deepcopy
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.claws import CLAWS, get_adapter
from agent_formalizer.benchmark_profile import (
    DEFAULT_BENCHMARK_PROFILE,
    with_google_vertex_project,
)
from agent_formalizer.claws.common import (
    google_vertex_openai_base,
    jsonl_steps,
    split_model_id,
    tool_records,
)
from agent_formalizer.claws.generic import (
    GenericAgentAdapter,
    _parse_usage_text,
)
from agent_formalizer.claws.hermes import HermesAdapter, _read_hermes_usage
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.openclaw import OpenClawAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter, _parse_costs
from agent_formalizer.config import CLAW_DEFAULTS, agent_model_label
from agent_formalizer.util import read_named_secret, read_named_setting
from sweep_agent_pipeline import (
    _formalize_indices_for_resume,
    _freeze_study_profile,
    _qualify_model_label,
    _resolve_model_label,
)


class AdapterRegistryTests(unittest.TestCase):
    def test_all_requested_harnesses_are_registered(self):
        self.assertEqual(
            set(CLAWS),
            {"openclaw", "hermes", "nanobot", "zeroclaw", "generic"},
        )

    def test_defaults_construct(self):
        for name in CLAWS:
            with self.subTest(name=name):
                adapter = get_adapter(name)
                self.assertEqual(adapter.name, name)
                self.assertEqual(adapter.model, "google-vertex/gemini-3.1-flash-lite")
                self.assertEqual(adapter.timeout, 1800)
                self.assertEqual(adapter.max_turns, 200)
                self.assertEqual(adapter.max_model_calls, 50)
                self.assertFalse(adapter.allow_network)

    def test_versioned_profile_drives_every_default(self):
        self.assertEqual(DEFAULT_BENCHMARK_PROFILE.schema_version, 2)
        self.assertEqual(
            {value["model"] for value in CLAW_DEFAULTS.values()},
            {DEFAULT_BENCHMARK_PROFILE.default_model},
        )

    def test_unrestricted_legacy_network_flag_is_rejected(self):
        for name in CLAWS:
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
            for name in CLAWS:
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

    def test_materialized_vertex_project_participates_in_hash(self):
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
        for name in CLAWS:
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
            adapter = OpenClawAdapter("openai/gpt-5.4-mini", 120, 17)
            env = adapter._openclaw_env()
            self.assertEqual(env["OPENCLAW_CONFIG_PATH"], str(adapter._config_path()))
            self.assertEqual(env["OPENCLAW_STATE_DIR"], str(adapter._state_dir))
            self.assertEqual(env["OPENCLAW_NO_AUTO_UPDATE"], "1")
            self.assertNotIn("OPENCLAW_PROFILE", env)
            self.assertNotIn("OPENCLAW_BUNDLED_SKILLS_DIR", env)
            self.assertNotIn("CLAWDBOT_GATEWAY_PASSWORD", env)
            self.assertNotIn("test-key", json.dumps(env))
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
    def setUp(self):
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_hermes_config_is_clean(self):
        adapter = HermesAdapter("openai/gpt-5.4-mini", 120, 17)
        config = adapter._benchmark_config()
        self.assertEqual(config["model"]["provider"], "openai-api")
        self.assertEqual(config["agent"]["max_turns"], 17)
        self.assertEqual(config["plugins"]["enabled"], [])
        self.assertNotIn("test-secret", json.dumps(config))

    def test_nanobot_config_preserves_clean_native_tools(self):
        adapter = NanoBotAdapter("openai/gpt-5.4-mini", 120, 17)
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
        self.assertEqual(config["tools"]["mcpServers"], {})

    def test_zeroclaw_v3_config_has_no_persisted_key(self):
        adapter = ZeroClawAdapter("openai/gpt-5.4-mini", 120, 17)
        config = adapter._benchmark_config_toml()
        self.assertIn("schema_version = 3", config)
        self.assertIn("max_tool_iterations = 17", config)
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
            17,
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

    def test_generic_max_turns_is_patched_without_editing_runtime(self):
        adapter = GenericAgentAdapter("openai/gpt-5.4-mini", 120, 200)
        wrapper = adapter._agentmain_wrapper_source()
        self.assertIn("max_turns=200", wrapper)
        self.assertIn("max_turns=180", wrapper)

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
        adapter = HermesAdapter("openai/gpt-5.4-mini", 120, 17)
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
        adapter = HermesAdapter("openai/gpt-5.4-mini", 120, 17)
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
        adapter = HermesAdapter("openai/gpt-5.4-mini", 120, 17)

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

    def test_generic_usage(self):
        usage = _parse_usage_text(
            "[Cache] input=10 cached=3\n[Output] tokens=4\n"
            "[Cache] input=20 creation=5 read=6\n[Output] tokens=7\n"
        )
        self.assertEqual(
            usage,
            {"input": 30, "output": 11, "cacheRead": 9, "cacheWrite": 5},
        )

    def test_zeroclaw_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "costs.jsonl"
            path.write_text(
                json.dumps({"usage": {"input_tokens": 10, "output_tokens": 2}})
                + "\n"
                + json.dumps({"usage": {"prompt_tokens": 3, "completion_tokens": 4}})
                + "\n"
            )
            usage = _parse_costs(path)
        self.assertEqual(usage["turns"], 2)
        self.assertEqual(usage["input_tokens"], 13)
        self.assertEqual(usage["output_tokens"], 6)
        self.assertEqual(usage["total_tokens"], 19)


if __name__ == "__main__":
    unittest.main()
