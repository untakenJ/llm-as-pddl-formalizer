"""Deployment tests use temporary nodes and mock uv/probes; no external calls."""
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from remote_execution import bundle, deploy
from remote_execution.protocol import digest, file_hash, private_json, read_json
from remote_execution.store import Store, lock


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="remote-deploy-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "checkout"
        self.source.mkdir()
        for name, body in {
            "source/remote_execution/deploy.py": "# frozen worker\n",
            "source/agent_formalizer/timing/example.py": "# timing\n",
            "source/local_solver/worker.py": "# solver\n",
            "pyproject.toml": "[project]\nname='test'\nversion='0.1'\n",
            "uv.lock": "version = 1\n", "README.md": "fixture\n",
        }.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        self.store = Store(self.root / "state")
        self.config = {"schema_version": 1, "node_id": "test", "state_dir": str(self.store.root),
                       "python": str(self.root / "old-env/bin/python"),
                       "token_file": str(self.root / "private/token")}
        self.config_path = self.root / "node.json"
        private_json(self.config_path, self.config)
        self.dest = self.root / "deployments"
        self.matches = patch.object(deploy, "environment_matches", return_value=True).start()
        patch.object(deploy, "verify_unit", return_value={"status": "pass"}).start()
        self.addCleanup(patch.stopall)

    def plan(self, **kwargs):
        return deploy.plan(self.source, self.config_path, self.dest, **kwargs)

    def apply(self):
        p = self.plan()
        return deploy.apply(p, p["plan_sha256"])

    def job(self, status):
        spec = {"schema_version": 1, "job_id": "old", "release_id": "a" * 64,
                "kind": "probe", "parameters": {}}
        self.store.submit(spec)
        self.store.directory("old").mkdir(exist_ok=True)
        self.store.transition("old", status)
        return self.store.directory("old")

    def test_inventory_matches_build_and_writes_nothing(self):
        before = sorted(str(p) for p in self.source.rglob("*"))
        manifest = bundle.inventory(self.source, deploy.INCLUDES)
        self.assertEqual(before, sorted(str(p) for p in self.source.rglob("*")))
        info = bundle.build(self.source, deploy.INCLUDES, self.root / "bundle.tar.gz")
        self.assertEqual(digest(manifest), info["release_id"])

    def test_plan_is_read_only_and_components_are_not_whole_repo_commit(self):
        before = {str(p): file_hash(p) for p in self.source.rglob("*") if p.is_file()}
        result = self.plan(installed_source=self.source)
        self.assertFalse(self.dest.exists())
        self.assertTrue(result["request"]["reuse_node_python"])
        self.assertTrue(all(r["source_changed"] is False for r in result["components"].values()))
        self.assertEqual(before, {str(p): file_hash(p) for p in self.source.rglob("*") if p.is_file()})

    def test_plan_requires_initialized_queue(self):
        self.config["state_dir"] = str(self.root / "missing-state")
        private_json(self.config_path, self.config)
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.plan()
        self.assertFalse((self.root / "missing-state").exists())

    def test_rejects_unknown_harness_and_service(self):
        for kwargs in ({"harnesses": ["unknown"]}, {"services": ["unknown"]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.plan(**kwargs)

    def test_rejects_source_state_and_link_destinations(self):
        (self.root / "linked").symlink_to(self.root, target_is_directory=True)
        for dest in (self.source, self.source / "source/new", self.store.root / "deploy", self.root / "linked/new"):
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                deploy.plan(self.source, self.config_path, dest)

    def test_apply_is_create_only_idempotent_and_reuses_python_without_sync(self):
        original = self.config_path.read_bytes()
        with patch.object(deploy.subprocess, "run") as command:
            first = self.apply()
            second = self.apply()
            command.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(original, self.config_path.read_bytes())
        candidate = Path(first["prepared"])
        self.assertEqual(read_json(candidate / "node.json"), self.config)
        self.assertEqual(first["status"], "prepared_not_activated")
        self.assertIn("KillMode=process", (candidate / "worker.service").read_text())
        self.assertIn("ExecStart=:", (candidate / "worker.service").read_text())
        self.assertFalse((self.source / ".venv").exists())

    def test_active_worker_lock_blocks_before_install(self):
        with lock(self.store.root / "worker.lock"), self.assertRaisesRegex(ValueError, "Control worker"):
            self.apply()
        self.assertFalse(self.dest.exists())

    def test_queued_running_uncertain_jobs_block(self):
        self.job("queued")
        for status in ("queued", "launching", "running", "needs_attention"):
            self.store.transition("old", status)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "Unsettled"):
                self.apply()
        self.assertFalse(self.dest.exists())

    def test_detached_owner_blocks_even_with_terminal_status(self):
        directory = self.job("failed")
        with lock(directory / "owner.lock"), self.assertRaisesRegex(ValueError, "Detached owner"):
            self.apply()
        self.assertFalse(self.dest.exists())

    def test_surviving_process_group_blocks_with_unlocked_owner(self):
        self.job("completed")
        with patch.object(deploy, "group_alive", return_value=True), self.assertRaisesRegex(ValueError, "process group"):
            self.apply()
        self.assertFalse(self.dest.exists())

    def test_worker_cannot_start_during_idle_guard(self):
        with deploy.idle_node(self.config):
            with self.assertRaises(BlockingIOError), lock(self.store.root / "worker.lock"):
                pass

    def test_source_or_config_drift_or_unreviewed_plan_rejected(self):
        p = self.plan()
        with self.assertRaisesRegex(ValueError, "Plan changed"):
            deploy.apply(p, "a" * 64)
        (self.source / "source/new.py").write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            deploy.apply(p, p["plan_sha256"])
        p = self.plan()
        private_json(self.config_path, self.config | {"max_jobs": 2})
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            deploy.apply(p, p["plan_sha256"])
        self.assertFalse(self.dest.exists())

    def test_existing_unowned_directory_is_never_adopted(self):
        self.dest.mkdir()
        with self.assertRaisesRegex(ValueError, "ownership marker"):
            self.apply()
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_new_dependencies_use_isolated_env_no_old_node_mutation(self):
        self.matches.side_effect = lambda source, python: "deployments/environments/" in str(python)
        with patch.object(deploy, "uv_command", return_value=["uv", "sync", "--locked"]), \
                patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as command:
            first = self.apply()
            second = self.apply()
        self.assertEqual(command.call_count, 1)
        self.assertEqual(first, second)
        env_path = command.call_args.kwargs["env"]["UV_PROJECT_ENVIRONMENT"]
        self.assertTrue(env_path.startswith(str(self.dest / "environments")))
        self.assertFalse(first["old_job_config_compatible"])
        self.assertEqual(read_json(self.config_path), self.config)

    def test_used_managed_environment_drift_is_not_repaired(self):
        self.matches.side_effect = lambda source, python: "deployments/environments/" in str(python)
        with patch.object(deploy, "uv_command", return_value=["uv", "sync"]), \
                patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.apply()
        self.matches.side_effect = None
        self.matches.return_value = False
        with patch.object(deploy.subprocess, "run") as command, self.assertRaisesRegex(ValueError, "never repaired"):
            self.apply()
        command.assert_not_called()

    def test_env_failure_never_publishes_candidate(self):
        self.matches.return_value = False
        with patch.object(deploy, "uv_command", return_value=["uv", "sync"]), \
                patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                self.assertRaisesRegex(ValueError, "uv sync failed"):
            self.apply()
        self.assertFalse((self.dest / "prepared").exists())
        self.assertEqual(read_json(self.config_path), self.config)

    def test_environment_change_after_plan_rejected_without_sync(self):
        p = self.plan()
        self.matches.return_value = False
        with patch.object(deploy.subprocess, "run") as command, self.assertRaisesRegex(ValueError, "in-place sync"):
            deploy.apply(p, p["plan_sha256"])
        command.assert_not_called()

    def test_check_uses_staged_python_source_and_retains_all_reports(self):
        result = self.apply()
        prepared = Path(result["prepared"])
        process = subprocess.CompletedProcess([], 0, json.dumps({"status": "pass", "checks": {}}), "")
        with patch.object(deploy, "run_probe", return_value=process) as command:
            one, two = deploy.check(prepared), deploy.check(prepared)
        self.assertNotEqual(one["report"], two["report"])
        self.assertEqual(command.call_args.args[0][0], self.config["python"])
        self.assertEqual(str(command.call_args.kwargs["cwd"]), result["workspace"])
        self.assertEqual(command.call_args.kwargs["env"]["PYTHONPATH"], str(Path(result["workspace"]) / "source"))
        self.assertTrue(one["not_a_real_model_canary"])

    def test_check_rejects_staged_source_or_node_drift(self):
        result = self.apply()
        prepared = Path(result["prepared"])
        private_json(prepared / "node.json", self.config | {"max_jobs": 2})
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            deploy.check(prepared)
        private_json(prepared / "node.json", self.config)
        (Path(result["workspace"]) / "source/new.py").write_text("# drift\n")
        with self.assertRaises(ValueError):
            deploy.check(prepared)

    def test_check_rejects_unit_drift_and_records_unverified_stages(self):
        prepared = Path(self.apply()["prepared"])
        process = subprocess.CompletedProcess([], 0, json.dumps({"status": "pass", "checks": {}}), "")
        with patch.object(deploy, "run_probe", return_value=process), \
                patch.object(deploy, "verify_unit", return_value={"status": "not_verified"}):
            result = deploy.check(prepared)
        self.assertEqual(result["status"], "not_verified")
        for stage in ("native_startup_acceptance", "real_model_canary", "service_activation", "unit_parsing"):
            self.assertEqual(result["stages"][stage]["status"], "not_verified")
        (prepared / "worker.service").write_text("[Service]\nExecStart=/bin/true\n")
        with self.assertRaisesRegex(ValueError, "service unit changed"):
            deploy.check(prepared)

    def test_check_records_failure_without_subprocess_error_text(self):
        result = self.apply()
        process = subprocess.CompletedProcess([], 1, "provider secret", "provider secret")
        with patch.object(deploy, "run_probe", return_value=process):
            report = deploy.check(Path(result["prepared"]))
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("provider secret", json.dumps(report))

    def test_check_uses_frozen_original_config_not_later_operator_edits(self):
        result = self.apply()
        private_json(self.config_path, self.config | {"max_jobs": 3})
        process = subprocess.CompletedProcess([], 0, json.dumps({"status": "pass", "checks": {}}), "")
        with patch.object(deploy, "run_probe", return_value=process):
            self.assertEqual(deploy.check(Path(result["prepared"]))["status"], "pass")

    def test_uv_check_is_offline_locked_and_never_uses_ambient_env(self):
        with patch.object(deploy.shutil, "which", return_value="/bin/uv"):
            cmd = deploy.uv_command(self.source, check=True)
        for flag in ("--check", "--locked", "--offline", "--no-cache"):
            self.assertIn(flag, cmd)
        with patch.dict(deploy.os.environ, {"DEEPSEEK_API_KEY": "secret", "UV_PROJECT_ENVIRONMENT": "/bad", "HTTP_PROXY": "bad"}):
            env = deploy.environment(self.source, self.root / "new-env")
        self.assertNotIn("DEEPSEEK_API_KEY", env)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(self.root / "new-env"))

    def test_probe_timeout_allows_container_cleanup_before_hard_kill(self):
        with patch.object(deploy.subprocess, "Popen") as popen:
            process = popen.return_value.__enter__.return_value
            process.communicate.side_effect = [subprocess.TimeoutExpired("probe", 900), ("", "")]
            with self.assertRaises(subprocess.TimeoutExpired):
                deploy.run_probe(["python", "probe"], cwd=self.source, env={})
            process.terminate.assert_called_once()
            process.kill.assert_not_called()
            self.assertEqual(process.communicate.call_args.kwargs["timeout"], 45)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="remote-deploy-probe-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        val = self.root / "build/linux64/Release/bin/Validate"
        val.parent.mkdir(parents=True)
        val.write_text("fixture")
        val.chmod(0o700)
        self.config = {"bindings": {"val": str(self.root)}, "services": {"solver": {}, "model": {}}}

    def test_native_runtime_probe_and_overlay_with_mock_docker(self):
        image = "sha256:" + "1" * 64
        binary = self.root / "zeroclaw"; binary.write_text("fixture")
        with patch("agent_formalizer.runtime.runtime_lock.validate_runtime_lock", return_value={"status": "pass"}) as validate, \
                patch.object(deploy, "timing_probe", return_value={"status": "pass"}) as timing, \
                patch("agent_formalizer.timing.zeroclaw_deadlines.prepared", return_value=(binary, {})), \
                patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, image, "")):
            result = deploy.probe(self.config, deploy.NATIVE, [])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(validate.call_count, 5)
        self.assertEqual(timing.call_count, 5)
        for call in validate.call_args_list:
            self.assertEqual(call.kwargs["container_image_id"], image)
            self.assertEqual(call.kwargs["lock_path"].name, "runtime_lock_text_v1.json")

    def test_compiler_missing_is_not_verified_not_pass(self):
        with patch.object(deploy.shutil, "which", return_value=None):
            self.assertEqual(deploy.timing_probe("hermes")["status"], "not_verified")

    def test_build_error_is_not_hidden_by_runtime_lock_pass(self):
        with patch.object(deploy, "timing_probe", return_value={"status": "fail", "build_diagnostic": "unused-result"}), \
                patch("agent_formalizer.runtime.runtime_lock.validate_runtime_lock", return_value={"status": "pass"}), \
                patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "image", "")):
            result = deploy.probe(self.config, ["hermes"], [])
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"]["hermes"]["status"], "pass")
        self.assertEqual(result["checks"]["timing:hermes"]["build_diagnostic"], "unused-result")

    @unittest.skipUnless(shutil.which("gcc"), "requires actual GCC")
    def test_timing_probe_reports_real_uncached_compiler_failure(self):
        from agent_formalizer.timing import deadline_integration
        gcc = shutil.which("gcc")
        source = (deadline_integration.RUNTIME / "timeout_deadline.c").read_text()
        old = source.replace("ssize_t ignored_read_result = read(fd, reply, sizeof reply);\n"
                             "                    (void)ignored_read_result;", "(void)read(fd, reply, sizeof reply);")
        self.assertNotEqual(source, old)
        runtime = self.root / "old-runtime"; runtime.mkdir()
        (runtime / "timeout_deadline.c").write_text(old)
        compiler = self.root / "gcc"
        compiler.write_text('#!/bin/sh\nexec ' + shlex.quote(gcc) + ' -D_FORTIFY_SOURCE=2 "$@"\n')
        compiler.chmod(0o700)
        with patch.object(deadline_integration, "RUNTIME", runtime), \
                patch.dict(os.environ, {"PATH": str(self.root) + os.pathsep + os.environ.get("PATH", "")}):
            row = deploy.timing_probe("hermes")
        self.assertEqual(row["status"], "fail", row)
        self.assertEqual(row["error_type"], "CalledProcessError")
        self.assertIn("unused-result", row["build_diagnostic"])

    def test_individual_service_failure_is_reported_and_other_checks_continue(self):
        def health(services, names, evidence, **kwargs):
            if names == ["solver"]:
                raise ValueError("secret upstream body")
            return {"model": {"status": "ok"}}
        with patch("remote_execution.benchmark.service_preflight", side_effect=health) as service:
            result = deploy.probe(self.config, ["api", "minimum"], ["solver", "model"])
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"]["service:solver"]["status"], "fail")
        self.assertEqual(result["checks"]["service:model"]["status"], "pass")
        self.assertEqual(service.call_count, 2)
        self.assertNotIn("secret upstream body", json.dumps(result))

    def test_missing_val_never_passes(self):
        result = deploy.probe({}, ["api", "minimum"], [])
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"]["val"]["status"], "fail")

    def test_cpu_only_real_host_import_probe_subprocess(self):
        import sys
        source = Path(__file__).resolve().parents[1]
        config = {"schema_version": 1, "node_id": "fixture", "state_dir": str(self.root / "state"),
                  "python": sys.executable, "token_file": str(self.root / "unused-token"),
                  "bindings": {"val": str(self.root)}}
        path = self.root / "node.json"; private_json(path, config)
        result = subprocess.run([sys.executable, "-B", "-m", "remote_execution.deploy", "_probe",
                                 "--config", str(path), "--harnesses", "api,minimum", "--services", ""],
                                env=deploy.environment(source), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")

    def test_real_cli_plan_apply_check_with_reused_environment(self):
        import sys
        source = Path(__file__).resolve().parents[1]
        if not deploy.shutil.which("uv") or not deploy.environment_matches(source, sys.executable):
            self.skipTest("requires an existing compatible uv environment; never install dependencies in this test")
        state = Store(self.root / "state")
        config = {"schema_version": 1, "node_id": "fixture", "state_dir": str(state.root),
                  "python": sys.executable, "token_file": str(self.root / "unused-token"),
                  "bindings": {"val": str(self.root)}}
        path = self.root / "node.json"; private_json(path, config)
        args = ["--source", str(source), "--config", str(path), "--destination", str(self.root / "deployments"),
                "--harness", "api", "--harness", "minimum"]
        def call(command, options):
            result = subprocess.run([sys.executable, "-B", "-m", "remote_execution.deploy", command, *options],
                                    env=deploy.environment(source), capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        preview = call("plan", args)
        self.assertFalse((self.root / "deployments").exists())
        prepared = call("apply", [*args, "--expect-plan", preview["plan_sha256"]])
        self.assertEqual(prepared["status"], "prepared_not_activated")
        checked = call("check", ["--prepared", prepared["prepared"]])
        self.assertEqual(checked["status"], "pass")
        self.assertTrue(checked["no_service_activated"])
        self.assertEqual(read_json(path), config)


class SystemdUnitTests(unittest.TestCase):
    def test_path_validation_and_field_specific_quoting(self):
        text = deploy.unit_text(Path("/tmp/work space/中文%dir"), "/usr/bin/true", Path("/tmp/config space%.json"))
        self.assertIn("WorkingDirectory=/tmp/work space/中文%%dir\n", text)
        self.assertIn('Environment="PYTHONPATH=/tmp/work space/中文%%dir/source"', text)
        self.assertIn('ExecStart=:"/usr/bin/true"', text)
        self.assertIn('"/tmp/config space%%.json"', text)
        for invalid in ('relative', '/tmp/a\nb', '/tmp/a\x00b', '/tmp/a\x7fb', '/tmp/a"b', '/tmp/a\\b', '/tmp/end '):
            with self.subTest(path=invalid), self.assertRaises(ValueError):
                deploy.unit_text(Path(invalid), "/usr/bin/true", Path("/tmp/config"))

    def test_missing_systemd_is_not_verified(self):
        with patch.object(deploy.shutil, "which", return_value=None):
            self.assertEqual(deploy.verify_unit(Path("/unused"))["status"], "not_verified")

    @unittest.skipUnless(shutil.which("systemd-analyze"), "requires real systemd parser")
    def test_real_systemd_parser_accepts_paths_and_rejects_old_quoted_directory(self):
        with tempfile.TemporaryDirectory(prefix="rd-unit-") as directory:
            root = Path(directory)
            for suffix in ("ordinary", "space 中文%value"):
                workspace = root / suffix
                workspace.mkdir()
                path = root / "worker.service"
                python = workspace / "python 中文%bin"
                python.symlink_to("/usr/bin/true")
                text = deploy.unit_text(workspace, python, workspace / "node config%.json")
                path.write_text(text)
                result = deploy.verify_unit(path)
                self.assertEqual(result["status"], "pass", result)
                bad = text.replace("WorkingDirectory=" + str(workspace).replace("%", "%%"),
                                   'WorkingDirectory="' + str(workspace).replace("%", "%%") + '"')
                path.write_text(bad)
                result = deploy.verify_unit(path)
                self.assertEqual(result["status"], "fail", result)
                self.assertIn("not absolute", result["diagnostic"])


if __name__ == "__main__":
    unittest.main()
