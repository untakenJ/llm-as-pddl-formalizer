from __future__ import annotations

import sys
import subprocess
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch


SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from agent_formalizer.configuration.benchmark_profile import (
    BENCHMARK_PROFILES_DIR,
    BenchmarkProfile,
    load_benchmark_profile,
)
from agent_formalizer.tools import resolve_agent_tools
from agent_formalizer.workspace import AgentWorkspace
from local_solver import planutils_runner
from local_solver.server import (
    DEFAULT_ALLOWED_SOLVERS,
    DockerWorkerPool,
    LocalSolverState,
    ServerConfig,
    build_parser,
)
from sweep_agent_pipeline import run_agent_pipeline
from sweep_pipeline import run_formalizer_pipeline


class FakePool:
    def __init__(self, response=None):
        self.response = response or {
            "ok": True,
            "result": {
                "stdout": "Plan found with cost: 1\n",
                "stderr": "",
                "call": "planutils run dual-bfws-ffparser",
                "output": {"plan": "(move a b)\n"},
                "output_type": "generic",
            },
            "worker": {"name": "fake-worker", "running": True},
        }

    def execute(self, _request):
        return self.response

    def snapshot(self):
        return {
            "workers": 1,
            "idle_workers": 1,
            "worker_status": {"fake-worker": {"running": True}},
        }


class LocalSolverDefaultsTests(unittest.TestCase):
    def test_defaults_are_lightweight_and_resource_bounded(self):
        config = ServerConfig()
        self.assertEqual(config.workers, 1)
        self.assertEqual(config.memory, "4096m")
        self.assertEqual(config.memory_swap, "4096m")
        self.assertEqual(config.timeout_seconds, 90.0)
        self.assertEqual(build_parser().parse_args([]).timeout_seconds, 90.0)
        self.assertEqual(build_parser().parse_args(['--timeout', '60']).timeout_seconds, 60.0)
        self.assertEqual(config.worker_security, "privileged")
        self.assertEqual(DEFAULT_ALLOWED_SOLVERS, ("dual-bfws-ffparser",))

    def test_worker_command_keeps_limits_and_offline_network_in_compat_mode(self):
        pool = DockerWorkerPool(ServerConfig())
        pool._run = Mock(return_value=type("Result", (), {"returncode": 0})())
        pool._start_worker("test-worker")
        command = pool._run.call_args.args[0]
        self.assertIn("--privileged", command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[command.index("--memory") + 1], "4096m")
        self.assertEqual(command[command.index("--memory-swap") + 1], "4096m")
        self.assertEqual(command[command.index("--cpus") + 1], "1.0")

    def test_worker_startup_rejects_an_image_missing_an_allowed_package(self):
        pool = DockerWorkerPool(
            ServerConfig(allowed_solvers=("dual-bfws-ffparser", "lama-first"))
        )
        result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"installed_solver_packages": ["dual-bfws-ffparser"]}',
                "stderr": "",
            },
        )()
        pool._run = Mock(return_value=result)
        with self.assertRaisesRegex(RuntimeError, "lacks allowed package.*lama-first"):
            pool._verify_worker("test-worker")

    def test_container_gateway_receives_local_upstream_without_agent_change(self):
        class Adapter:
            def solver_backend(self):
                return "local"

            def solver_upstream_base(self, *, containerized):
                self.containerized = containerized
                return "http://host.docker.internal:8769"

        adapter = Adapter()
        workspace = AgentWorkspace(
            "local-solver-test", "pddl-local-solver-gateway-test", adapter
        )
        spec = resolve_agent_tools(["pddl_solver"])[0]
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch(
            "agent_formalizer.workspace.subprocess.run", return_value=completed
        ) as run:
            workspace._start_tool_gateway(spec)
        start_command = run.call_args_list[0].args[0]
        self.assertIn(
            "PDDL_SOLVER_UPSTREAM_BASE=http://host.docker.internal:8769",
            start_command,
        )
        self.assertIn("PDDL_SOLVER_UPSTREAM_HEALTH_REQUIRED=1", start_command)
        self.assertIn("host.docker.internal:host-gateway", start_command)
        self.assertTrue(adapter.containerized)

    def test_backend_mode_changes_resolved_experiment_identity(self):
        profile = load_benchmark_profile()
        local = profile.resolve("openclaw")
        public = profile.resolve("openclaw", solver_backend="public")
        self.assertEqual(local.solver_backend, "local")
        self.assertEqual(local.raw["resolved"]["solver_backend"], "local")
        self.assertEqual(public.solver_backend, "public")
        self.assertNotEqual(public.sha256, local.sha256)

    def test_every_bundled_profile_defaults_to_local(self):
        for path in BENCHMARK_PROFILES_DIR.glob("*.json"):
            with self.subTest(profile=path.name):
                profile = load_benchmark_profile(path)
                harness = (
                    "minimum"
                    if "minimum_agent"
                    in profile.raw["condition_profile"]["overrides"]
                    else "openclaw"
                )
                self.assertEqual(profile.resolve(harness).solver_backend, "local")

    def test_legacy_frozen_profile_without_backend_stays_public(self):
        profile = load_benchmark_profile()
        raw = deepcopy(profile.raw)
        raw["condition_profile"]["overrides"].pop("solver_backend")
        legacy = BenchmarkProfile(profile.path, raw).resolve("openclaw")
        self.assertEqual(legacy.solver_backend, "public")
        self.assertNotIn("solver_backend", legacy.raw["resolved"])


class PlanutilsManifestTests(unittest.TestCase):
    def test_manifest_arguments_are_materialized_without_shell_execution(self):
        manifest = {
            "call": "fake-planner {domain} {problem}",
            "args": [
                {"name": "domain", "type": "file"},
                {"name": "problem", "type": "file"},
            ],
            "return": {"files": "*.plan", "type": "generic"},
        }
        packages = {"fake": {"endpoint": {"services": {"solve": manifest}}}}
        request = {"domain": "(domain)", "problem": "(problem)"}
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            with patch.object(planutils_runner, "_packages", return_value=packages):
                service = planutils_runner._service_manifest("fake")
                call, materialized = planutils_runner._write_argument_files(
                    request, service, directory
                )
        self.assertEqual(call, "fake-planner domain problem")
        self.assertEqual(materialized["domain"]["bytes"], len("(domain)"))
        self.assertEqual(materialized["problem"]["bytes"], len("(problem)"))


class LocalSolverProtocolTests(unittest.TestCase):
    def test_task_state_emits_planning_domains_compatible_terminal_payload(self):
        state = LocalSolverState(ServerConfig(), FakePool())
        try:
            task_id = state.submit(
                "dual-bfws-ffparser",
                "(define (domain mock))",
                "(define (problem mock-problem) (:domain mock))",
            )
            self.assertIsNotNone(task_id)
            deadline = time.monotonic() + 2
            while True:
                status, payload = state.terminal_payload(task_id)
                if payload.get("status") != "PENDING":
                    break
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
        finally:
            state.close()
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["result"]["output"], {"plan": "(move a b)\n"})
        self.assertEqual(state.status()["succeeded"], 1)

    def test_sweep_routes_agent_and_evaluator_to_the_same_local_backend(self):
        profile = load_benchmark_profile()
        resolved = profile.resolve(
            "openclaw", model="openai/test-model", solver_backend="local"
        )
        label = f"test-label__{resolved.label}"
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            problem_dir = (
                root
                / "llm-as-formalizer-agent"
                / "logistics"
                / "Natural_Logistics-100"
                / label
                / "p01"
            )
            problem_dir.mkdir(parents=True)
            (problem_dir / "completion.json").write_text(
                '{"complete": true, "attempt_valid": true}'
            )
            completed = (0, "", "", 0.01, {"stdout": "out", "stderr": "err"})
            with patch("sweep_agent_pipeline._run", return_value=completed) as run:
                run_agent_pipeline(
                    claw="openclaw",
                    model="openai/test-model",
                    model_label="test-label",
                    domain="logistics",
                    dataset="Natural_Logistics-100",
                    indices=[1],
                    out_dir=root,
                    log_dir=root / "logs",
                    stages={"formalize", "solve"},
                    formalizer_workers=1,
                    solver_workers=1,
                    val_workers=1,
                    timeout=None,
                    max_action_steps=None,
                    max_model_calls=None,
                    network_mode=None,
                    attempts_per_case=None,
                    max_execution_tries=None,
                    allow_final_message_recovery=None,
                    benchmark_config=str(profile.path),
                    solver_backend=None,
                    solver_base_url=None,
                    solver_container_base_url=None,
                    api_key_env=None,
                    secrets_env_file="/unused/.env",
                    vertex_project_env="GOOGLE_CLOUD_PROJECT",
                    image=None,
                    trace=True,
                    tools_profile=None,
                    tools_allow=None,
                    tools_deny=None,
                    resume=False,
                )
        formalizer_command = run.call_args_list[0].args[0]
        evaluator_command = run.call_args_list[1].args[0]
        self.assertIn("--solver-backend", formalizer_command)
        self.assertIn("local", formalizer_command)
        self.assertIn("--solver-backend", evaluator_command)
        self.assertIn("local", evaluator_command)
        self.assertIn("http://127.0.0.1:8769", evaluator_command)

    def test_direct_api_sweep_can_select_the_local_evaluator(self):
        completed = (0, "", "")
        with patch("sweep_pipeline._run", return_value=completed) as run:
            run_formalizer_pipeline(
                "test-model",
                "logistics",
                "Natural_Logistics-100",
                [1],
                "/tmp/local-solver-direct-api-test",
                1,
            )
        solver_command = run.call_args_list[1].args[0]
        self.assertIn("--solver-backend", solver_command)
        self.assertIn("local", solver_command)


if __name__ == "__main__":
    unittest.main()
