from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from agent_formalizer.configuration.benchmark_profile import (
    DEFAULT_BENCHMARK_PROFILE, ResolvedBenchmarkConfig,
    load_benchmark_profile,
)
from agent_formalizer.claws import get_adapter
from agent_formalizer.orchestrator import _adapter_code_sha256
from agent_formalizer.configuration.skill_library import (
    CONTAINER_ROOT, bundle_for_profile, load_bundle, validate_selection,
)
from agent_formalizer.workspace import AgentWorkspace
from sweep_agent_pipeline import _freeze_study_profile

HARNESSES = ("openclaw", "hermes", "nanobot", "generic", "zeroclaw")


class ExperimentSkillsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.add_skill("skill-a")
        self.add_skill("skill-b")

    def add_skill(self, name):
        directory = self.library / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: >\n  Optional fixture\n  for tests.\n---\n"
            "PRIVATE BODY MARKER. Read references/note.txt when relevant.\n"
        )
        (directory / "references").mkdir()
        (directory / "references/note.txt").write_text("REFERENCE MARKER")
        (directory / "scripts").mkdir()
        script = directory / "scripts/check.sh"
        script.write_text("#!/bin/sh\nprintf 'fixture\\n'\n")
        script.chmod(0o755)

    def profile(self, selection=None, **overrides):
        raw = deepcopy(DEFAULT_BENCHMARK_PROFILE.raw)
        raw["condition_profile"]["overrides"].update(overrides)
        if selection is not None:
            raw["condition_profile"]["overrides"]["experiment_skills"] = selection
        raw["experiment_skill_library"] = {"path": "library"}
        path = self.root / "profile.json"
        path.write_text(json.dumps(raw))
        return load_benchmark_profile(path)

    def test_empty_selection_is_exact_baseline_for_all_five_harnesses(self):
        profile = self.profile([])
        with patch("agent_formalizer.configuration.skill_library.load_bundle", side_effect=AssertionError("scanned")):
            for name in HARNESSES:
                with self.subTest(harness=name):
                    baseline = get_adapter(name)
                    disabled = get_adapter(name, benchmark_profile=profile)
                    self.assertEqual(baseline.resolved_config.raw, disabled.resolved_config.raw)
                    self.assertEqual(baseline.build_task_prompt("d", "p"),
                                     disabled.build_task_prompt("d", "p"))
                    self.assertEqual(baseline.skills_info(), disabled.skills_info())
                    self.assertEqual(AgentWorkspace("x", "y", disabled)._prepare_experiment_skills(), [])

    def test_equal_catalog_and_selected_files_for_five_harnesses(self):
        profile = self.profile(["skill-a"])
        prompts = []
        for name in HARNESSES:
            adapter = get_adapter(name, benchmark_profile=profile)
            prompts.append(adapter.build_task_prompt("DOMAIN", "PROBLEM"))
            artifacts = self.root / name
            workspace = AgentWorkspace("case", "container", adapter, artifact_dir=artifacts)
            args = workspace._prepare_experiment_skills()
            self.assertEqual(args, ["-v", f"{artifacts}/experiment_skills:{CONTAINER_ROOT}:ro"])
            self.assertEqual({p.name for p in (artifacts / "experiment_skills").iterdir()}, {"skill-a"})
            manifest = json.loads((artifacts / "experiment_skills_manifest.json").read_text())
            self.assertEqual(manifest, adapter.resolved_config.raw["resolved"]["experiment_skills"])
            self.assertEqual(adapter.skills_mode, "official")
        self.assertEqual(len(set(prompts)), 1)
        self.assertIn(f"{CONTAINER_ROOT}/skill-a/SKILL.md", prompts[0])
        self.assertNotIn("skill-b", prompts[0])
        self.assertNotIn("PRIVATE BODY MARKER", prompts[0])
        self.assertNotIn("REFERENCE MARKER", prompts[0])

    def test_official_skills_ablation_is_independent(self):
        adapter = get_adapter("hermes", benchmark_profile=self.profile(["skill-a"], skills_mode="none"))
        self.assertEqual(adapter.skills_mode, "none")
        self.assertIn("skill-a", adapter.build_task_prompt("d", "p"))

    def test_selection_is_sorted_and_changes_identity(self):
        a = self.profile(["skill-a"]).resolve("hermes")
        b = self.profile(["skill-b"]).resolve("hermes")
        ab = self.profile(["skill-a", "skill-b"]).resolve("hermes")
        ba = self.profile(["skill-b", "skill-a"]).resolve("hermes")
        self.assertEqual(ab.sha256, ba.sha256)
        self.assertEqual(len({a.sha256, b.sha256, ab.sha256,
                              self.profile([]).resolve("hermes").sha256}), 4)

    def test_all_selected_files_and_executable_bits_are_hashed(self):
        profile = self.profile(["skill-a"])
        before = profile.resolve("hermes")
        script = self.library / "skill-a/scripts/check.sh"
        script.chmod(0o644)
        after_mode = profile.resolve("hermes")
        self.assertNotEqual(before.sha256, after_mode.sha256)
        script.write_text("changed bytes")
        self.assertNotEqual(after_mode.sha256, profile.resolve("hermes").sha256)
        (self.library / "skill-a/references/note.txt").write_text("changed reference")
        self.assertNotEqual(after_mode.sha256, profile.resolve("hermes").sha256)

    def test_resolved_bundle_keeps_bytes_when_live_library_changes(self):
        resolved = self.profile(["skill-a"]).resolve("hermes")
        (self.library / "skill-a/references/note.txt").write_text("changed")
        destination = self.root / "snapshot"
        resolved.skill_bundle.materialize(destination)
        self.assertEqual((destination / "skill-a/references/note.txt").read_text(), "REFERENCE MARKER")

    def test_unselected_contents_do_not_affect_semantic_hash(self):
        profile = self.profile(["skill-a"])
        before = profile.resolve("hermes").sha256
        (self.library / "skill-b/SKILL.md").write_text("even invalid unselected content is not opened")
        self.assertEqual(before, profile.resolve("hermes").sha256)

    def test_payload_library_does_not_affect_adapter_code_hash(self):
        package = self.root / "package"
        package.mkdir()
        (package / "orchestrator.py").write_text("implementation")
        (package / "skills").mkdir()
        with patch("agent_formalizer.orchestrator.__file__", str(package / "orchestrator.py")):
            before = _adapter_code_sha256()
            (package / "skills/unselected.py").write_text("arbitrary skill script")
            self.assertEqual(before, _adapter_code_sha256())
            (package / "skill_library.py").write_text("loader change")
            self.assertNotEqual(before, _adapter_code_sha256())

    def test_freeze_and_resume_with_original_or_frozen_profile(self):
        profile = self.profile(["skill-a"])
        out = self.root / "output"
        out.mkdir()
        frozen = _freeze_study_profile(profile, out)
        self.assertEqual(frozen.resolve("hermes").sha256, profile.resolve("hermes").sha256)
        self.assertEqual(_freeze_study_profile(profile, out).raw, frozen.raw)
        self.assertEqual(_freeze_study_profile(frozen, out).raw, frozen.raw)
        before = frozen.resolve("hermes").sha256
        (self.library / "skill-a/SKILL.md").write_text("changed upstream library")
        self.assertEqual(frozen.resolve("hermes").sha256, before)
        self.assertEqual([p.name for p in (out / frozen.raw["experiment_skill_library"]["path"]).iterdir()], ["skill-a"])

    def test_frozen_file_tampering_is_rejected(self):
        out = self.root / "out"
        out.mkdir()
        frozen = _freeze_study_profile(self.profile(["skill-a"]), out)
        snapshot = out / frozen.raw["experiment_skill_library"]["path"]
        (snapshot / "skill-a/references/note.txt").write_text("tamper")
        with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
            frozen.resolve("hermes")

    def test_changed_selection_cannot_replace_frozen_profile(self):
        out = self.root / "out"
        out.mkdir()
        frozen = _freeze_study_profile(self.profile(["skill-a"]), out)
        with self.assertRaisesRegex(ValueError, "different frozen"):
            _freeze_study_profile(self.profile(["skill-b"]), out)
        self.assertEqual(load_benchmark_profile(frozen.path).raw, frozen.raw)

    def test_parallel_execution_snapshots_are_independent(self):
        bundle = bundle_for_profile(self.profile(["skill-a"]).raw, self.root / "profile.json")
        targets = [self.root / f"execution-{i}" for i in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(bundle.materialize, targets))
        (targets[0] / "skill-a/references/note.txt").write_text("changed")
        self.assertEqual((targets[1] / "skill-a/references/note.txt").read_text(), "REFERENCE MARKER")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            bundle.materialize(targets[0])

    def test_snapshot_is_readable_regardless_of_operator_umask(self):
        bundle = load_bundle(self.library, ["skill-a"])
        destination = self.root / "private-umask-snapshot"
        previous = os.umask(0o077)
        try:
            bundle.materialize(destination)
        finally:
            os.umask(previous)
        for path in [destination, *destination.rglob("*")]:
            self.assertTrue(path.stat().st_mode & 0o004, str(path))
            if path.is_dir():
                self.assertTrue(path.stat().st_mode & 0o001, str(path))

    def test_no_artifact_directory_fails_before_resources_start(self):
        adapter = get_adapter(
            "hermes", benchmark_profile=self.profile(["skill-a"]),
            model="deepseek/deepseek-v4-flash", api_key="not-real",
        )
        workspace = AgentWorkspace("x", "y", adapter)
        with patch.object(workspace, "_create_network") as create, self.assertRaisesRegex(ValueError, "artifact"):
            workspace.start()
        create.assert_not_called()

    def test_minimum_rejects_skills_before_native_execution(self):
        with self.assertRaisesRegex(ValueError, "minimum.*file tools"):
            self.profile(["skill-a"]).resolve("minimum")

    def test_serialized_manifest_cannot_silently_lose_files(self):
        resolved = self.profile(["skill-a"]).resolve("hermes")
        with self.assertRaisesRegex(ValueError, "frozen bytes"):
            ResolvedBenchmarkConfig(resolved.raw)

    def test_invalid_selection(self):
        for value in ("skill-a", ["../secret"], ["/tmp/x"], ["A"], ["a_b"], [1], ["a", "a"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_selection(value)
        with self.assertRaisesRegex(ValueError, "Unknown skill"):
            self.profile(["missing"]).resolve("hermes")

    def test_invalid_frontmatter(self):
        path = self.library / "skill-a/SKILL.md"
        for content in (
            "no frontmatter", "---\n[]\n---\nbody",
            "---\nname: wrong\ndescription: text\n---\nbody",
            "---\nname: skill-a\ndescription: 12\n---\nbody",
            "---\nname: skill-a\nname: skill-a\ndescription: text\n---\nbody",
            "---\nname: skill-a\ndescription: text\n---\n",
        ):
            path.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                load_bundle(self.library, ["skill-a"])

    def test_symlinks_and_special_files_rejected(self):
        (self.library / "linked").symlink_to(self.library / "skill-a", target_is_directory=True)
        with self.assertRaises(ValueError):
            load_bundle(self.library, ["linked"])
        (self.library / "skill-a/leak").symlink_to(self.root / "outside")
        with self.assertRaisesRegex(ValueError, "symlink"):
            load_bundle(self.library, ["skill-a"])
        os.mkfifo(self.library / "skill-b/pipe")
        with self.assertRaisesRegex(ValueError, "special file"):
            load_bundle(self.library, ["skill-b"])

    def test_snapshot_extra_files_and_symlink_destination_rejected(self):
        bundle = load_bundle(self.library, ["skill-a"])
        dest = self.root / "snapshot"
        bundle.materialize(dest)
        bundle.materialize(dest)
        (dest / "unexpected.txt").write_text("not selected")
        with self.assertRaises(ValueError):
            bundle.materialize(dest)
        link = self.root / "linked-snapshot"
        link.symlink_to(dest, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            bundle.materialize(link)

    def test_state_isolation_requires_exact_readonly_target_and_content(self):
        adapter = get_adapter("hermes", benchmark_profile=self.profile(["skill-a"]))
        workspace = AgentWorkspace("case", "container", adapter, artifact_dir=self.root / "artifacts")
        workspace._prepare_experiment_skills()
        spec = {"mode": "isolated", "scope": "per_attempt", "personal_harness_state": "excluded",
                "cross_attempt_reuse": False, "tests": {}}
        mounts = [{"Type": "bind", "RW": False, "Source": str(workspace._experiment_skills_directory),
                   "Destination": CONTAINER_ROOT}]

        def inspect(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, json.dumps([{"Mounts": mounts}]), "")

        with patch.object(adapter, "state_isolation_spec", return_value=spec), patch(
            "agent_formalizer.workspace.subprocess.run", side_effect=inspect,
        ):
            self.assertEqual(workspace.validate_state_isolation()["status"], "pass")
            mounts[0]["RW"] = True
            self.assertEqual(workspace.validate_state_isolation()["status"], "fail")
            mounts[0]["RW"] = False
            mounts[0]["Destination"] = "/wrong"
            self.assertEqual(workspace.validate_state_isolation()["status"], "fail")
            mounts[0]["Destination"] = CONTAINER_ROOT
            (workspace._experiment_skills_directory / "skill-a/references/note.txt").write_text("tamper")
            self.assertFalse(workspace.validate_state_isolation()["tests"]["experimental_skill_snapshot_exact"])


if __name__ == "__main__":
    unittest.main()
