"""Remote comparability checks; no models, solver, Docker or installed runtimes."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_formalizer.runtime import runtime_lock as r


class TextPayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def package(self, name):
        env = self.root / name
        site = env / "lib/python3.12/site-packages"
        info = site / "example-1.0.dist-info"
        info.mkdir(parents=True)
        (site / "example").mkdir()
        (site / "example/main.py").write_text("print('hello')\n")
        (site / "example/prompt.md").write_text("Write the requested file.\n")
        (info / "METADATA").write_text("Name: example\nVersion: 1.0\n")
        (info / "entry_points.txt").write_text("[console_scripts]\nexample=example.main:main\n")
        (env / "bin").mkdir()
        (env / "bin/example").write_text(f"#!{env}/bin/python\nprint('launcher')\n")
        (env / "locales").mkdir()
        (env / "locales/en.yaml").write_text("hello: Hello\n")
        rows = ["../../../bin/example", "../../../locales/en.yaml", "example/main.py", "example/prompt.md",
                "example-1.0.dist-info/METADATA", "example-1.0.dist-info/entry_points.txt",
                "example-1.0.dist-info/RECORD"]
        with (info / "RECORD").open("w", newline="") as stream:
            csv.writer(stream).writerows([[value, "", ""] for value in rows])
        return env, site, info

    def test_install_paths_record_order_and_bytecode_do_not_change_text_identity(self):
        left, _, _ = self.package("one")
        right, site, info = self.package("another-install-root")
        (site / "example/__pycache__").mkdir()
        (site / "example/__pycache__/main.cpython-312.pyc").write_bytes(b"generated")
        record = info / "RECORD"
        record.write_text("\n".join(reversed(record.read_text().splitlines())) + "\n")
        (info / "INSTALLER").write_text("different-installer")
        self.assertEqual(r._python_text_payload(left, "example"), r._python_text_payload(right, "example"))

    def test_code_prompt_and_added_source_changes_are_detected(self):
        for relative in ("main.py", "prompt.md", "new_hook.py"):
            with self.subTest(relative=relative):
                env, site, _ = self.package(relative)
                before = r._python_text_payload(env, "example")
                (site / "example" / relative).write_text("different runtime text\n")
                self.assertNotEqual(before, r._python_text_payload(env, "example"))

    def test_installed_locale_outside_site_packages_is_checked(self):
        env, _, _ = self.package("locale")
        before = r._python_text_payload(env, "example")
        (env / "locales/en.yaml").write_text("hello: changed\n")
        self.assertNotEqual(before, r._python_text_payload(env, "example"))

    def test_missing_declared_source_fails(self):
        env, site, _ = self.package("missing")
        (site / "example/main.py").unlink()
        with self.assertRaisesRegex(r.RuntimeLockMismatch, "missing installed"):
            r._python_text_payload(env, "example")

    def test_record_cannot_escape_environment(self):
        env, _, info = self.package("escape")
        with (info / "RECORD").open("a") as stream:
            stream.write("../../../../outside.py,,\n")
        with self.assertRaisesRegex(r.RuntimeLockMismatch, "escapes"):
            r._python_text_payload(env, "example")

    def test_external_source_symlink_is_rejected(self):
        env, site, _ = self.package("symlink")
        outside = self.root / "outside.py"
        outside.write_text("print('outside')\n")
        (site / "example/extra.py").symlink_to(outside)
        with self.assertRaisesRegex(r.RuntimeLockMismatch, "escapes"):
            r._python_text_payload(env, "example")

    def test_nonexecuted_binary_assets_are_not_a_text_check(self):
        env, site, _ = self.package("binary")
        before = r._python_text_payload(env, "example")
        (site / "example/icon.png").write_bytes(b"\x89PNG")
        self.assertEqual(before, r._python_text_payload(env, "example"))


class TextPolicyTests(unittest.TestCase):
    def setUp(self):
        self.lock = r.load_runtime_lock(r.TEXT_LOCK_PATH)
        self.adapter = SimpleNamespace(name="hermes", raw_provider="openai")
        self.image = "sha256:" + "a" * 64
        self.observed = dict(self.lock["harnesses"]["hermes"], python_executable_sha256="different-build",
                             python_version="Python 3.12.99", harness_payload_manifest_sha256="different-install")

    def check(self, *, observed=None, lock=None, image=None, capabilities=None):
        with patch.object(r, "load_runtime_lock", return_value=lock or self.lock), \
             patch.object(r, "observe_text_runtime", return_value=observed or self.observed), \
             patch.object(r, "observe_container_capabilities", return_value=(
                 capabilities or self.lock["container"]["runtime_capabilities"])):
            return r.validate_runtime_lock(self.adapter, container_image_id=image or self.image,
                                           lock_path=r.TEXT_LOCK_PATH)

    def test_new_binary_image_and_python_patch_are_audit_only(self):
        first = self.check()
        second = self.check(image="sha256:" + "b" * 64,
                            observed=self.observed | {"python_executable_sha256": "another-build"})
        self.assertNotEqual(first["observed"], second["observed"])
        self.assertEqual(r.execution_runtime_identity(first, self.image, "code"),
                         r.execution_runtime_identity(second, "another-image", "code"))
        self.assertEqual(first["status"], "pass")

    def test_code_version_dependencies_resources_and_language_family_still_block(self):
        for field in ("version", "harness_text_manifest_sha256", "python_distribution_manifest_sha256",
                      "native_assets_manifest_sha256", "python_runtime"):
            with self.subTest(field=field), self.assertRaisesRegex(r.RuntimeLockMismatch, field):
                self.check(observed=self.observed | {field: "different"})

    def test_commit_and_dirty_worktree_still_block(self):
        for name in ("generic", "zeroclaw"):
            self.adapter.name = name
            for field, value in (("source_commit", "wrong"), ("source_worktree_clean", False)):
                with self.subTest(name=name, field=field), self.assertRaises(r.RuntimeLockMismatch):
                    self.check(observed=self.lock["harnesses"][name] | {field: value})

    def test_missing_capability_still_blocks(self):
        cap = deepcopy(self.lock["container"]["runtime_capabilities"])
        cap["commands"].remove("timeout")
        with self.assertRaisesRegex(r.RuntimeLockMismatch, "runtime_capabilities"):
            self.check(capabilities=cap)

    def test_missing_check_or_null_expected_value_is_not_a_bypass(self):
        for change in ("missing", "null", "unknown"):
            lock = deepcopy(self.lock)
            checks = lock["harnesses"]["hermes"]
            if change == "missing":
                checks.pop("version")
            elif change == "null":
                checks["version"] = None
            else:
                checks["surprise"] = "ignored?"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check(lock=lock)

    def test_text_policy_cannot_skip_container_probe(self):
        with patch.object(r, "observe_text_runtime", return_value=self.observed):
            with self.assertRaisesRegex(r.RuntimeLockMismatch, "frozen container"):
                r.validate_runtime_lock(self.adapter, lock_path=r.TEXT_LOCK_PATH)

    def test_local_default_lock_and_byte_identity_remain_unchanged(self):
        legacy = r.load_runtime_lock()
        self.assertEqual(legacy["schema_version"], 1)
        self.assertEqual(r._file_sha256(r.LOCK_PATH),
                         "208dbca4efb889fef10b29764420fba82c449b208047a57f96b547b01eb9ea08")
        observed = dict(legacy["harnesses"]["hermes"])
        with patch.object(r, "observe_runtime", return_value=observed):
            evidence = r.validate_runtime_lock(self.adapter, container_image_id=legacy["container"]["image_id"])
            expected = {"runtime_lock": evidence, "container_image_id": self.image, "adapter_code_sha256": "code"}
            self.assertEqual(r.execution_runtime_identity(evidence, self.image, "code"), expected)
            observed["python_executable_sha256"] = "different"
            with self.assertRaisesRegex(r.RuntimeLockMismatch, "python_executable_sha256"):
                r.validate_runtime_lock(self.adapter)
        with patch.object(r, "observe_runtime", return_value=legacy["harnesses"]["hermes"]):
            with self.assertRaisesRegex(r.RuntimeLockMismatch, "image_id"):
                r.validate_runtime_lock(self.adapter, container_image_id=self.image)

    def test_changed_semantic_check_changes_comparison_identity(self):
        before = self.check()
        lock = deepcopy(self.lock)
        lock["harnesses"]["hermes"]["version"] = "new-version"
        after = self.check(lock=lock, observed=self.observed | {"version": "new-version"})
        self.assertNotEqual(before["comparison_identity"], after["comparison_identity"])

    def test_minimum_remains_host_only(self):
        self.adapter.name = "minimum"
        with patch.object(r, "observe_text_runtime", return_value=self.lock["harnesses"]["minimum"]), \
             patch.object(r, "observe_container_capabilities") as probe:
            result = r.validate_runtime_lock(self.adapter, lock_path=r.TEXT_LOCK_PATH)
        probe.assert_not_called()
        self.assertFalse(result["container"]["required"])


class CapabilityProbeTests(unittest.TestCase):
    def test_probe_is_bounded_isolated_and_always_cleaned(self):
        expected = r.load_runtime_lock(r.TEXT_LOCK_PATH)["container"]["runtime_capabilities"]
        with patch.object(r.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, json.dumps(expected), ""),
            subprocess.CompletedProcess([], 1, "", "Error: No such container"),
        ]) as run:
            self.assertEqual(r.observe_container_capabilities("sha256:" + "a" * 64), expected)
        call = run.call_args_list[0]
        command = call.args[0]
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--pids-limit", command)
        self.assertEqual(call.kwargs["timeout"], 30)
        self.assertEqual(run.call_args_list[1].args[0][-1], command[command.index("--name") + 1])

    def test_probe_timeout_still_removes_only_owned_container(self):
        with patch.object(r.subprocess, "run", side_effect=[
            subprocess.TimeoutExpired("docker", 30), subprocess.CompletedProcess([], 0, "", ""),
        ]) as run, self.assertRaises(r.RuntimeLockMismatch):
            r.observe_container_capabilities("sha256:" + "a" * 64)
        self.assertEqual(run.call_count, 2)
        self.assertTrue(run.call_args.args[0][-1].startswith("pddl-runtime-preflight-"))


class PipelineSelectionTests(unittest.TestCase):
    def test_pipeline_forwards_explicit_lock_but_does_not_change_local_default(self):
        import inspect
        import sweep_agent_pipeline as pipeline
        for selected in (None, str(r.TEXT_LOCK_PATH)):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as tmp:
                # All unspecified condition overrides retain their existing None
                # semantics. No real formalizer/evaluator subprocess is started.
                kwargs = {name: None for name, param in inspect.signature(pipeline.run_agent_pipeline).parameters.items()
                          if param.default is inspect.Parameter.empty}
                kwargs.update(claw="hermes", model="openai/test-model", model_label="test",
                              domain="logistics", dataset="Natural_Logistics-100", indices=[1],
                              out_dir=Path(tmp) / "output", log_dir=Path(tmp) / "logs", stages={"formalize"},
                              formalizer_workers=1, solver_workers=1, val_workers=1,
                              trace=True, resume=True, secrets_env_file="_private/.env",
                              vertex_project_env="GOOGLE_CLOUD_PROJECT", runtime_lock_path=selected)
                with patch.object(pipeline, "_run", return_value=(0, "", "", 0.0, {"stderr": "test.log"})) as run:
                    pipeline.run_agent_pipeline(**kwargs)
                command = run.call_args.args[0]
                if selected is None:
                    self.assertNotIn("--runtime-lock", command)
                else:
                    self.assertEqual(command[command.index("--runtime-lock") + 1], selected)
        from agent_formalizer.run_formalizer_agent import build_parser
        args = build_parser().parse_args(["--domain", "logistics", "--data", "Natural_Logistics-100", "--indices", "1"])
        self.assertIsNone(args.runtime_lock)


if __name__ == "__main__":
    unittest.main()
