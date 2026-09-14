from __future__ import annotations

import sys
import json
import os
import subprocess
import tempfile
import time
import unittest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
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
        self.assertIn("--init", command)
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

    def test_worker_startup_rejects_a_legacy_runner_without_cleanup(self):
        pool = DockerWorkerPool(ServerConfig())
        pool._run = Mock(return_value=subprocess.CompletedProcess([], 0,
            '{"installed_solver_packages": ["dual-bfws-ffparser"]}', ""))
        with self.assertRaisesRegex(RuntimeError, "subreaper cleanup"):
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


class ProcessCleanupTests(unittest.TestCase):
    # Real double-fork/setsid/ignored-SIGTERM children, but no model or planner.
    # Run the reaper in its own process, never in the unittest process.
    CHILD_SCRIPT = '''
import os, signal, time
from pathlib import Path
pid = os.fork()
if pid == 0:
    os.setsid()
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if os.fork() != 0:
        os._exit(0)
    Path("descendant.pid").write_text(str(os.getpid()))
    time.sleep(60)
    os._exit(0)
while not Path("descendant.pid").exists():
    time.sleep(0.001)
print("planner output", flush=True)
Path("plan").write_text("(move a b)\\n")
MODE
'''

    def _exercise(self, ending, timeout=5):
        script = self.CHILD_SCRIPT.replace("MODE", ending)
        with tempfile.TemporaryDirectory() as directory:
            helper = (
                "import json,sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(SOURCE_DIR)!r}); "
                "from local_solver import planutils_runner as r; "
                "r._enable_subreaper(); "
                f"result=r._run_command([sys.executable,'-c',{script!r}],Path({directory!r}),{timeout}); "
                "assert not r._children(); print(json.dumps(result))"
            )
            result = subprocess.run([sys.executable, "-c", helper], capture_output=True,
                                    text=True, timeout=12, check=True)
            value = json.loads(result.stdout)
            pid = int((Path(directory) / "descendant.pid").read_text())
            self.assertFalse(Path(f"/proc/{pid}").exists(), "live or zombie descendant survived")
            self.assertEqual((Path(directory) / "plan").read_text(), "(move a b)\n")
            self.assertEqual(value[0], "planner output\n")
            self.assertTrue(value[4]["complete"])
            self.assertGreaterEqual(value[4]["reaped_descendants"], 1)
            return value

    def test_normal_exit_reaps_detached_child_without_pipe_eof_wait(self):
        value = self._exercise("os._exit(0)")
        self.assertEqual(value[2], 0)
        self.assertFalse(value[3])

    def test_error_exit_reaps_detached_child_and_preserves_returncode(self):
        self.assertEqual(self._exercise("os._exit(7)")[2], 7)

    def test_timeout_kills_and_reaps_even_when_group_leader_exits_first(self):
        self.assertTrue(self._exercise("time.sleep(60)", timeout=0.25)[3])

    def test_repeated_tasks_do_not_accumulate_zombies(self):
        for _ in range(3):
            self._exercise("os._exit(0)")

    def test_cleanup_deadline_fails_closed(self):
        with patch.object(planutils_runner, "_children", return_value=[123456]), \
             patch.object(planutils_runner.time, "monotonic", side_effect=[0, 6]):
            with self.assertRaises(planutils_runner.ProcessCleanupError):
                planutils_runner._reap_process_tree(Mock(pid=123456))


class WorkerRecoveryTests(unittest.TestCase):
    def _pool(self):
        pool = DockerWorkerPool(ServerConfig())
        pool._names = ["test-worker"]
        pool._available.put("test-worker")
        pool._inspect = Mock(return_value={"running": True, "init_enabled": True})
        pool._replace_worker = Mock()
        return pool

    def test_missing_cleanup_evidence_does_not_release_a_plan(self):
        pool = self._pool()
        reply = subprocess.CompletedProcess([], 0, json.dumps(FakePool().response), "")
        with patch("local_solver.server.subprocess.run", return_value=reply):
            response = pool.execute({})
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "ProcessCleanupError")
        pool._replace_worker.assert_called_once()

    def test_crashed_runner_replaces_worker_before_next_task(self):
        pool = self._pool()
        with patch("local_solver.server.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 137, "", "killed")):
            self.assertFalse(pool.execute({})["ok"])
        pool._replace_worker.assert_called_once()

    def test_control_timeout_replaces_worker_before_reuse(self):
        pool = self._pool()
        with patch("local_solver.server.subprocess.run", side_effect=
                   subprocess.TimeoutExpired(["docker", "exec"], 105)):
            response = pool.execute({})
        self.assertEqual(response["error"]["type"], "worker_control_timeout")
        pool._replace_worker.assert_called_once()

    def test_replacement_removal_failure_does_not_start_another_container(self):
        pool = DockerWorkerPool(ServerConfig())
        pool._run = Mock(return_value=subprocess.CompletedProcess([], 1, "", "busy"))
        pool._start_worker = Mock()
        with self.assertRaisesRegex(RuntimeError, "cannot remove failed worker"):
            pool._replace_worker("test-worker")
        pool._start_worker.assert_not_called()

    def test_failed_replacement_is_quarantined_not_reused_or_deadlocked(self):
        pool = self._pool()
        pool._replace_worker.side_effect = RuntimeError("replacement failed")
        with patch("local_solver.server.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 137, "", "killed")) as run:
            pool.execute({})
            second = pool.execute({})
        self.assertEqual(run.call_count, 1)
        self.assertEqual(second["error"]["type"], "worker_unavailable")
        self.assertFalse(pool.snapshot()["worker_status"]["test-worker"]["running"])
        self.assertEqual(pool.snapshot()["idle_workers"], 0)

    def test_verified_normal_result_is_reused_unchanged(self):
        pool = self._pool()
        response = FakePool().response
        response["result"]["local_backend"] = {"process_cleanup": {
            "complete": True, "version": "subreaper-v1"}}
        with patch("local_solver.server.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, json.dumps(response), "")):
            actual = pool.execute({})
        self.assertEqual(actual["result"], response["result"])
        pool._replace_worker.assert_not_called()


@unittest.skipUnless(os.environ.get("RUN_LOCAL_SOLVER_DOCKER_TESTS") == "1",
                     "explicit isolated Docker integration opt-in required")
class DockerProcessCleanupTests(unittest.TestCase):
    """Use private offline workers; never submit to the shared solver service."""

    def setUp(self):
        image = os.environ.get("LOCAL_SOLVER_TEST_IMAGE", "pddl-local-solver:planutils-v1")
        pool = DockerWorkerPool(ServerConfig(image=image, workers=2, timeout_seconds=2))
        run = pool._run

        def mounted_runner(command, **kwargs):
            if command[:2] == ["docker", "run"]:
                # Test the current runner over the installed, pinned planner
                # image without replacing a production tag or rebuilding SIFs.
                index = command.index(image)
                command = command[:index] + ["-v", str(SOURCE_DIR / "local_solver" /
                    "planutils_runner.py") + ":/opt/pddl-local-solver/planutils_runner.py:ro"] + command[index:]
            return run(command, **kwargs)

        pool._run = mounted_runner
        self.pool = pool
        self.addCleanup(pool.close)
        pool.start()

    def _idle(self, name):
        # docker top omits zombies. Inspect procfs from a dedicated diagnostic
        # exec, excluding only the two permanent processes and the probe itself.
        script = (
            "import json,os; from pathlib import Path; rows=[]; "
            "\nfor p in Path('/proc').iterdir():"
            "\n if not p.name.isdigit() or int(p.name)==os.getpid(): continue"
            "\n try:"
            "\n  s=(p/'status').read_text(); d=dict(x.split(':',1) for x in s.splitlines() if ':' in x);"
            " rows.append([int(p.name),d['Name'].strip(),d['State'].strip()])"
            "\n except FileNotFoundError: pass"
            "\nprint(json.dumps(rows))"
        )
        result = subprocess.run(["docker", "exec", name, "python3", "-c", script],
                                capture_output=True, text=True, timeout=10, check=True)
        rows = json.loads(result.stdout)
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual({r[1] for r in rows}, {"docker-init", "tail"})
        self.assertTrue(all(not r[2].startswith("Z") for r in rows), rows)

    def test_real_planner_and_concurrent_workers_leave_no_children(self):
        request = {"solver": "dual-bfws-ffparser",
                   "domain": "(define (domain d) (:requirements :strips) (:predicates (p) (q)) "
                             "(:action a :parameters () :precondition (p) :effect (and (q))))",
                   "problem": "(define (problem p1) (:domain d) (:init (p)) (:goal (q)))"}
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.pool.execute, [request] * 8))
        for result in results:
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["result"]["output"], result)
            self.assertTrue(result["result"]["local_backend"]["process_cleanup"]["complete"])
        for name in self.pool._names:
            self._idle(name)

    def test_detached_timeout_and_error_descendants_are_reaped_in_container(self):
        for ending, limit in (("os._exit(0)", 5), ("os._exit(7)", 5), ("time.sleep(60)", .25)):
            script = ProcessCleanupTests.CHILD_SCRIPT.replace("MODE", ending)
            helper = (
                "import json,sys,tempfile; from pathlib import Path; "
                "sys.path.insert(0,'/opt/pddl-local-solver'); import planutils_runner as r; "
                "r._enable_subreaper(); "
                "\nwith tempfile.TemporaryDirectory() as d:"
                f"\n print(json.dumps(r._run_command([sys.executable,'-c',{script!r}],Path(d),{limit})))"
            )
            name = self.pool._names[0]
            result = subprocess.run(["docker", "exec", name, "python3", "-c", helper],
                                    capture_output=True, text=True, timeout=12, check=True)
            self.assertTrue(json.loads(result.stdout)[4]["complete"])
            self._idle(name)


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
