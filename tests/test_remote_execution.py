"""CPU-only tests: no Docker, real provider, solver, installed service or GPU."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from remote_execution import bundle
from remote_execution.benchmark import prepare, run, service_preflight
from remote_execution.client import Client, resolve_evidence_path
from remote_execution.protocol import (CHUNK_SIZE, canonical, digest, endpoint, file_hash,
    private_json, read_json, relative, safe_path, validate_job, validate_node)
from remote_execution.store import Store, lock, seal_artifacts
from remote_execution.worker import Node, make_server

ROOT = Path(__file__).resolve().parents[1]


class TemporaryCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="remote-execution-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"; self.workspace.mkdir()
        (self.workspace / "source").mkdir()
        (self.workspace / "source" / "hello.txt").write_text("frozen input\n")
        self.token = self.root / "token"
        self.token.write_text("a" * 64); self.token.chmod(0o600)
        self.config = {"schema_version": 1, "node_id": "test-node", "state_dir": str(self.root / "node"),
                       "python": sys.executable, "token_file": str(self.token), "allow_probe": True,
                       "max_jobs": 1, "max_formalizer_workers": 4}

    def install_release(self, node=None):
        archive = self.root / "release.tar.gz"
        info = bundle.build(self.workspace, ["source"], archive)
        if node is not None:
            bundle.install(archive, node.store.root / "releases", info["release_id"])
        return archive, info

    def probe(self, release_id, job_id="probe-1", delay=0):
        return {"schema_version": 1, "job_id": job_id, "release_id": release_id,
                "kind": "probe", "parameters": {"delay_seconds": delay}}


class ContractTests(TemporaryCase):
    def test_path_rejections(self):
        for value in ("../x", "/tmp/x", "a/../b", "a//b", "a/./b", "", "a\\b", "a\x00b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                relative(value)

    def test_symlink_parent_rejected(self):
        (self.workspace / "link").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            safe_path(self.workspace, "link/token")

    def test_strict_job(self):
        spec = self.probe("a" * 64)
        validate_job(spec)
        for replacement in ({"command": "echo bad"}, {"kind": "shell"}, {"job_id": "../escape"},
                            {"schema_version": True}, {"parameters": {"delay_seconds": -1}}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                validate_job(spec | replacement)

    def test_node_limits_are_not_silently_coerced(self):
        for key, value in (("max_jobs", 0), ("max_jobs", True), ("allow_probe", 1), ("state_dir", "relative")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_node(self.config | {key: value})

    def test_control_channel_is_loopback_only(self):
        for url in ("http://remote:8876", "http://user:secret@localhost", "file:///tmp/x", "http://localhost/?key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                endpoint(url, loopback=True)

    def test_insecure_token_and_state_refused(self):
        self.token.chmod(0o644)
        with self.assertRaises(ValueError):
            Node(self.config)
        self.token.chmod(0o600)
        Path(self.config["state_dir"]).chmod(0o755)
        with self.assertRaises(ValueError):
            Node(self.config)


class BundleTests(TemporaryCase):
    def test_roundtrip_deterministic_create_only(self):
        archive, info = self.install_release()
        archive2 = self.root / "second.tar.gz"
        self.assertEqual(info, bundle.build(self.workspace, ["source"], archive2))
        releases = self.root / "releases"
        release = bundle.install(archive, releases, info["release_id"])
        self.assertEqual(bundle.verify(release)["files"]["source/hello.txt"]["sha256"], file_hash(self.workspace / "source/hello.txt"))
        self.assertEqual(bundle.install(archive, releases, info["release_id"]), release)
        with self.assertRaises(FileExistsError):
            bundle.build(self.workspace, ["source"], archive)

    def test_excludes_secrets_caches_outputs_and_weights(self):
        for name in ("source/.env", "source/output/old", "source/_private/key", "source/__pycache__/x.pyc",
                     "source/model.safetensors", "source/model.gguf"):
            path = self.workspace / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("DO NOT SEND")
        archive, info = self.install_release()
        release = bundle.install(archive, self.root / "releases", info["release_id"])
        self.assertEqual(list(bundle.verify(release)["files"]), ["source/hello.txt"])

    def test_local_campaign_inputs_require_explicit_include_and_roundtrip(self):
        inputs = ".local/campaign-inputs/study"
        registry = inputs + "/credentials.json"
        private_json(self.workspace / registry, {"schema_version": 1})
        private_json(self.workspace / inputs / "operational.json",
                     {"credential": {"registry_file": registry}})
        archive, info = self.install_release()
        release = bundle.install(archive, self.root / "releases", info["release_id"])
        self.assertNotIn(registry, bundle.verify(release)["files"])

        archive = self.root / "with-inputs.tar.gz"
        info = bundle.build(self.workspace, ["source", inputs], archive)
        release = bundle.install(archive, self.root / "releases", info["release_id"])
        workspace = release / "workspace"
        self.assertEqual(set(bundle.verify(release)["files"]),
                         {"source/hello.txt", registry, inputs + "/operational.json"})
        operational = read_json(workspace / inputs / "operational.json")
        self.assertEqual(read_json(safe_path(workspace, operational["credential"]["registry_file"])),
                         {"schema_version": 1})

    def test_symlink_input_refused(self):
        (self.workspace / "source" / "secret").symlink_to(self.token)
        with self.assertRaises(ValueError):
            bundle.build(self.workspace, ["source"], self.root / "bad.tar.gz")

    def test_release_drift_fails_closed(self):
        archive, info = self.install_release()
        release = bundle.install(archive, self.root / "releases", info["release_id"])
        (release / "workspace/source/hello.txt").write_text("changed")
        with self.assertRaises(ValueError):
            bundle.install(archive, self.root / "releases", info["release_id"])

    def test_unlisted_source_file_is_drift(self):
        archive, info = self.install_release()
        release = bundle.install(archive, self.root / "releases", info["release_id"])
        (release / "workspace/source/extra.py").write_text("unexpected import code")
        with self.assertRaisesRegex(ValueError, "inventory"):
            bundle.verify(release)

    def test_malicious_archives_rejected_without_external_write(self):
        for index, (name, kind) in enumerate((("../escaped", tarfile.REGTYPE),
                ("workspace/../../escaped", tarfile.REGTYPE), ("workspace/link", tarfile.SYMTYPE),
                ("workspace/link", tarfile.LNKTYPE), ("workspace/device", tarfile.CHRTYPE))):
            archive = self.root / f"bad-{index}.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                info = tarfile.TarInfo(name); info.type = kind
                stream.addfile(info, io.BytesIO())
            with self.assertRaises(ValueError):
                bundle.install(archive, self.root / "releases", "a" * 64)
        self.assertFalse((self.root / "escaped").exists())

    def test_expansion_limit(self):
        archive, info = self.install_release()
        with self.assertRaises(ValueError):
            bundle.install(archive, self.root / "releases", info["release_id"], max_bytes=10)

    def test_bindings_never_hot_change(self):
        archive, info = self.install_release()
        release = bundle.install(archive, self.root / "releases", info["release_id"])
        runtimes = self.root / "runtimes"; runtimes.mkdir()
        bundle.bind_runtime(release, {"harness_runtimes": str(runtimes)})
        bundle.bind_runtime(release, {"harness_runtimes": str(runtimes)})
        with self.assertRaises(ValueError):
            bundle.bind_runtime(release, {"harness_runtimes": str(self.root)})


class QueueTests(TemporaryCase):
    def test_concurrent_submission_is_idempotent(self):
        store = Store(Path(self.config["state_dir"]))
        spec = self.probe("a" * 64)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: store.submit(spec), range(8)))
        self.assertEqual({r["identity"] for r in results}, {digest(spec)})
        self.assertEqual(len(store.list()), 1)
        self.assertEqual(len(store.events(spec["job_id"])), 1)
        with self.assertRaises(ValueError):
            store.submit(spec | {"parameters": {"delay_seconds": 1}})

    def test_queue_survives_reopen(self):
        store = Store(Path(self.config["state_dir"]))
        spec = self.probe("a" * 64)
        store.submit(spec)
        self.assertEqual(Store(store.root).get(spec["job_id"])["status"], "queued")

    def test_explicit_resume_requires_reason_and_stopped_owner(self):
        store = Store(Path(self.config["state_dir"])); spec = self.probe("a" * 64)
        store.submit(spec)
        store.transition(spec["job_id"], "needs_attention")
        with self.assertRaises(ValueError):
            store.resume(spec["job_id"], "", 1)
        with lock(store.directory(spec["job_id"]) / "owner.lock"):
            with self.assertRaises(BlockingIOError):
                store.resume(spec["job_id"], "connection recovery", 1)
        row = store.resume(spec["job_id"], "owner stopped; native recovery checks required", 1)
        self.assertEqual(row["generation"], 2)
        self.assertEqual(store.resume(spec["job_id"], "same request retry", 1)["generation"], 2)

    def test_live_orphan_process_group_blocks_resume(self):
        store = Store(Path(self.config["state_dir"])); spec = self.probe("a" * 64)
        store.submit(spec); store.transition(spec["job_id"], "needs_attention")
        with patch("remote_execution.store.group_alive", return_value=True), self.assertRaisesRegex(ValueError, "process group"):
            store.resume(spec["job_id"], "do not duplicate", 1)

    def test_completed_agent_result_cannot_be_job_retried(self):
        store = Store(Path(self.config["state_dir"])); spec = self.probe("a" * 64)
        store.submit(spec); store.transition(spec["job_id"], "completed")
        with self.assertRaises(ValueError):
            store.resume(spec["job_id"], "try for a better result", 1)

    def test_missing_owner_is_not_automatically_retried(self):
        node = Node(self.config); _, info = self.install_release(node)
        spec = self.probe(info["release_id"]); node.submit(spec)
        node.store.transition(spec["job_id"], "running")
        with node.store.connect() as db:
            db.execute("UPDATE jobs SET updated=?", (time.time() - 60,))
        node.tick()
        row = node.store.get(spec["job_id"])
        self.assertEqual(row["status"], "needs_attention")
        self.assertEqual(row["generation"], 1)

    def test_probe_disabled_by_default(self):
        node = Node(self.config | {"allow_probe": False}); _, info = self.install_release(node)
        with self.assertRaises(ValueError):
            node.submit(self.probe(info["release_id"]))

    def test_orphaned_live_work_blocks_new_admission(self):
        node = Node(self.config); _, info = self.install_release(node)
        first = self.probe(info["release_id"]); second = self.probe(info["release_id"], "probe-2")
        node.submit(first); node.submit(second)
        node.store.transition(first["job_id"], "needs_attention")
        with patch("remote_execution.worker.group_alive", return_value=True):
            node.tick()
        self.assertEqual(node.store.get(second["job_id"])["status"], "queued")
        self.assertFalse(node.children)


class TransportTests(TemporaryCase):
    def setUp(self):
        super().setUp()
        self.node = Node(self.config)
        self.server = make_server(self.node)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop_server)
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}", self.token)

    def stop_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
        for child in self.node.children.values():
            child.wait(timeout=15)

    def test_authentication(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.client.base_url + "/health", timeout=2)
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(self.client.request("/health")["node_id"], "test-node")

    def test_upload_resume_after_lost_ack(self):
        archive, info = self.install_release()
        route = "/uploads/" + file_hash(archive)
        payload = archive.read_bytes()
        self.client.request(route + "?offset=0", method="PUT", data=payload[:50])
        self.assertEqual(self.client.upload(archive, info["release_id"])["release_id"], info["release_id"])
        self.assertEqual(self.client.upload(archive, info["release_id"])["release_id"], info["release_id"])

    def test_real_detached_owner_survives_client_and_control_restart(self):
        archive, info = self.install_release()
        self.client.upload(archive, info["release_id"])
        spec = self.probe(info["release_id"], delay=1.5)
        self.client.submit(spec); self.node.tick()
        deadline = time.monotonic() + 10
        while self.client.status(spec["job_id"])["status"] != "running":
            if time.monotonic() > deadline:
                self.fail("Owner did not start")
            time.sleep(0.02)
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
        restarted = Node(self.config)
        self.server = make_server(restarted)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}", self.token)
        restarted.tick()
        self.assertEqual(self.client.submit(spec)["generation"], 1)
        while self.client.status(spec["job_id"])["status"] not in {"completed", "failed", "needs_attention"}:
            if time.monotonic() > deadline:
                self.fail("Detached owner did not finish")
            time.sleep(0.02)
        self.node.tick()  # Reap the original child.
        row = self.client.status(spec["job_id"])
        self.assertEqual(row["status"], "completed", row)
        receipt = self.client.collect(spec["job_id"], self.root / "received")
        self.assertGreater(receipt["files"], 0)
        self.assertEqual(receipt, self.client.collect(spec["job_id"], self.root / "received"))
        probe = self.root / "received/probe-1/generation-1/output/probe.json"
        self.assertTrue(read_json(probe)["not_a_benchmark_result"])

    def sealed_job(self, payload):
        _, info = self.install_release(self.node)
        spec = self.probe(info["release_id"]); self.node.submit(spec)
        directory = self.node.store.directory(spec["job_id"])
        output = directory / "output"; output.mkdir(parents=True)
        (output / "completion.json").write_bytes(payload)
        (output / "link").symlink_to(self.token)
        manifest = seal_artifacts(directory, 1)
        self.node.store.transition(spec["job_id"], "completed", {"artifacts_sha256": digest(manifest)})
        return spec, manifest, directory

    def test_collect_disconnect_resumes_and_never_rewrites_original(self):
        payload = b"x" * (CHUNK_SIZE + 117)
        spec, manifest, directory = self.sealed_job(payload)
        destination = self.root / "received"
        original = self.client.request; calls = 0
        def disconnect(path, **kwargs):
            nonlocal calls
            if "/file?" in path:
                calls += 1
                if calls == 2:
                    raise ConnectionError("simulated control outage")
            return original(path, **kwargs)
        with patch.object(self.client, "request", side_effect=disconnect), self.assertRaises(ConnectionError):
            self.client.collect(spec["job_id"], destination)
        receipt = self.client.collect(spec["job_id"], destination)
        target = destination / "probe-1/generation-1/output/completion.json"
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual((directory / "output/completion.json").read_bytes(), payload)
        self.assertEqual(receipt["manifest_sha256"], digest(manifest))
        self.assertIn("output/link", manifest["excluded_nonregular"])
        self.assertFalse((target.parent / "link").exists())
        target.write_text("user file")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.client.collect(spec["job_id"], destination)
        self.assertEqual(target.read_text(), "user file")

    def test_snapshot_stays_immutable_when_resume_updates_summary(self):
        spec, _, directory = self.sealed_job(b"original")
        (directory / "output/completion.json").write_bytes(b"later data")
        self.client.collect(spec["job_id"], self.root / "received")
        mirror = self.root / "received/probe-1/generation-1"
        self.assertEqual((mirror / "output/completion.json").read_bytes(), b"original")
        self.assertEqual(resolve_evidence_path(mirror, str(directory / "output/completion.json")).read_bytes(), b"original")
        with self.assertRaises(ValueError):
            resolve_evidence_path(mirror, "/etc/passwd")

    def test_progress_reads_validity_without_rewriting_it(self):
        _, info = self.install_release(self.node)
        spec = self.probe(info["release_id"]); self.node.submit(spec)
        path = self.node.store.directory(spec["job_id"]) / "output/cell/execution_validity.json"
        private_json(path, {"problems": {"p01": {"attempts": {"1": {"selected_execution": "execution-001"}}},
                                        "p02": {"attempts": {"1": {"selected_execution": None}}}}})
        before = path.read_bytes()
        progress = self.client.request("/jobs/probe-1/progress")
        self.assertEqual(progress["cells"][0]["selected_valid_attempts"], 1)
        self.assertEqual(progress["cells"][0]["known_unfilled_attempts"], 1)
        self.assertEqual(path.read_bytes(), before)

    def test_sealed_evidence_remains_collectible_after_terminal_commit_crash(self):
        spec, _, _ = self.sealed_job(b"already durably sealed")
        self.node.store.transition(spec["job_id"], "needs_attention", {"reason": "owner_missing"})
        receipt = self.client.collect(spec["job_id"], self.root / "received")
        self.assertEqual(receipt["files"], 1)
        self.assertEqual(self.client.status(spec["job_id"])["status"], "needs_attention")

    def test_bad_upload_offset_rejected(self):
        with self.assertRaises(HTTPError):
            self.client.request("/uploads/" + "a" * 64 + "?offset=1", method="PUT", data=b"x")

    def test_real_release_entrypoint_runs_in_its_workspace(self):
        # Synthetic entrypoint exercises process/CWD/env/argument wiring; it
        # deliberately does NOT execute a harness, Docker or a real evaluator.
        entry = self.workspace / "source/remote_execution/benchmark.py"
        entry.parent.mkdir(parents=True)
        entry.write_text('''import argparse,json,os,pathlib
p=argparse.ArgumentParser()
for name in ("job","node","directory","generation"): p.add_argument("--"+name,required=True)
a=p.parse_args(); out=pathlib.Path(a.directory)/"output"; out.mkdir(exist_ok=True)
(out/"synthetic-entry.json").write_text(json.dumps({"cwd":os.getcwd(),"generation":a.generation,
    "not_a_benchmark_result":True,"ambient_key_present":"UNRELATED_SECRET" in os.environ}))
''')
        (self.workspace / "profile.json").write_text("{}")
        (self.workspace / "operational.json").write_text("{}")
        archive = self.root / "entry.tar.gz"
        info = bundle.build(self.workspace, ["source", "profile.json", "operational.json"], archive)
        self.client.upload(archive, info["release_id"])
        spec = {"schema_version":1,"job_id":"synthetic-cell","release_id":info["release_id"],"kind":"agent_cell",
                "parameters":{"harness":"openclaw","domain":"barman","dataset":"Heavily_Templated_Barman-100",
                    "indices":[1],"benchmark_profile":"profile.json","operational_config":"operational.json",
                    "resolved_config_sha256":"a"*64,"services":[]}}
        self.client.submit(spec)
        with patch.dict(os.environ, {"UNRELATED_SECRET":"must-not-leak"}):
            self.node.tick()
        deadline = time.monotonic()+10
        while self.client.status(spec["job_id"])["status"] not in {"completed","failed","needs_attention"}:
            if time.monotonic()>deadline: self.fail("Synthetic release entrypoint timed out")
            time.sleep(0.02)
        self.node.tick()
        row=self.client.status(spec["job_id"])
        self.assertEqual(row["status"],"completed",row)
        self.client.collect(spec["job_id"],self.root/"received")
        evidence=read_json(self.root/"received/synthetic-cell/generation-1/output/synthetic-entry.json")
        self.assertFalse(evidence["ambient_key_present"])
        self.assertEqual(evidence["cwd"],str(self.node.store.root/"releases"/info["release_id"]/"workspace"))


class BenchmarkBridgeTests(TemporaryCase):
    def fixture(self):
        from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
        baseline_name = "source/agent_formalizer/configs/benchmark_profiles/native_baseline_v1.json"
        baseline = read_json(ROOT / baseline_name)
        private_json(self.workspace / baseline_name, baseline)
        from remote_execution.benchmark import RUNTIME_LOCK_RELATIVE
        private_json(self.workspace / RUNTIME_LOCK_RELATIVE, read_json(ROOT / RUNTIME_LOCK_RELATIVE))
        private_json(self.workspace / "profile.json", baseline)
        private_json(self.workspace / "credentials.json", read_json(ROOT / "source/agent_formalizer/configs/credential_profiles.json"))
        op = read_json(ROOT / "source/agent_formalizer/configs/operational_configs/standard.json")
        op["credential"]["registry_file"] = "credentials.json"
        private_json(self.workspace / "operational.json", op)
        self.config["bindings"] = {"secrets_env_file": str(self.root / "runner.env")}
        resolved = load_benchmark_profile(self.workspace / "profile.json").resolve("openclaw")
        spec = {"schema_version": 1, "job_id": "case", "release_id": "a" * 64, "kind": "agent_cell",
                "parameters": {"harness": "openclaw", "domain": "barman", "dataset": "Heavily_Templated_Barman-100",
                  "indices": [1, 2], "benchmark_profile": "profile.json", "operational_config": "operational.json",
                  "resolved_config_sha256": resolved.sha256, "services": ["solver"]}}
        self.config["services"] = {"solver": {"systemd_unit": "fake-solver.service",
            "health_url": "http://127.0.0.1:8769/__benchmark__/health", "expected": {
                "status": "ok", "backend": "local-planutils", "pool": {"image_id": "sha256:abc"},
                "config": {"workers": 1, "memory": "4096m", "memory_swap": "4096m", "cpus": 1.0,
                           "pids_limit": 256, "timeout_seconds": 90, "worker_security": "privileged",
                           "allowed_solvers": ["dual-bfws-ffparser"]}}}}
        directory = self.root / "job"; directory.mkdir()
        return spec, directory, baseline, op

    def test_materialization_changes_paths_only(self):
        spec, directory, baseline, original = self.fixture()
        _, resolved, raw, path = prepare(spec, self.config, self.workspace, directory, 1)
        self.assertEqual(resolved.sha256, spec["parameters"]["resolved_config_sha256"])
        self.assertEqual(read_json(self.workspace / "profile.json"), baseline)
        self.assertEqual(read_json(self.workspace / "operational.json"), original)
        self.assertEqual(raw["scheduling"], original["scheduling"])
        self.assertEqual(raw["network_resources"], original["network_resources"])
        self.assertEqual(raw["infra_diagnostics"]["storage"]["root"], str(directory / "output/infra-diagnostics"))
        self.assertEqual(read_json(directory / "evidence/configuration-1.json")["profile_differences"], [])
        validation = read_json(directory / "evidence/configuration-1.json")["runtime_validation"]
        self.assertEqual(validation["policy"], "remote-text-v1")
        self.assertEqual(validation["sha256"], file_hash(self.workspace / validation["path"]))

    def test_identity_mismatch_before_launch(self):
        spec, directory, _, _ = self.fixture()
        spec["parameters"]["resolved_config_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            prepare(spec, self.config, self.workspace, directory, 1)

    def test_over_capacity_is_refused_not_reduced(self):
        spec, directory, _, op = self.fixture()
        op["scheduling"]["formalizer_workers"] = 5
        private_json(self.workspace / "operational.json", op)
        with self.assertRaisesRegex(ValueError, "capacity"):
            prepare(spec, self.config, self.workspace, directory, 1)

    def test_existing_pipeline_all_stages_and_valid_wrong_answers(self):
        from sweep_agent_pipeline import AgentBatchResult
        spec, directory, _, _ = self.fixture()
        result = AgentBatchResult("openclaw", "model", "label", "barman", "dataset",
                                  valid_attempts=2, pddl_completed=0, correctness="0", total=2,
                                  stages={"formalize": "ok", "solve": "ok", "val": "ok"})
        with patch("remote_execution.benchmark.service_preflight", return_value={}), \
             patch("sweep_agent_pipeline.run_agent_pipeline", return_value=result) as pipeline:
            self.assertEqual(run(spec, self.config, self.workspace, directory, 1), 0)
        kwargs = pipeline.call_args.kwargs
        self.assertEqual(kwargs["stages"], {"formalize", "solve", "val"})
        self.assertEqual(kwargs["indices"], [1, 2])
        self.assertTrue(kwargs["resume"])
        self.assertIsNone(kwargs["solver_backend"])
        self.assertIsNone(kwargs["timeout"])
        self.assertEqual(kwargs["formalizer_workers"], 1)
        from remote_execution.benchmark import RUNTIME_LOCK_RELATIVE
        self.assertEqual(kwargs["runtime_lock_path"], str(self.workspace / RUNTIME_LOCK_RELATIVE))

    def test_local_solver_cannot_be_silently_skipped(self):
        spec, directory, _, _ = self.fixture()
        spec["parameters"]["services"] = []
        with patch("sweep_agent_pipeline.run_agent_pipeline") as pipeline, self.assertRaisesRegex(ValueError, "shared solver"):
            run(spec, self.config, self.workspace, directory, 1)
        pipeline.assert_not_called()

    def test_supervisor_and_health_are_both_required(self):
        _, directory, _, _ = self.fixture()
        stdout = "ActiveState=active\nSubState=running\nRestart=on-failure\n"
        health = self.config["services"]["solver"]["expected"]
        response = io.BytesIO(canonical(health))
        with patch("remote_execution.benchmark.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout)), \
             patch("remote_execution.benchmark.build_opener") as opener:
            opener.return_value.open.return_value = response
            seen = service_preflight(self.config["services"], ["solver"], directory / "health.json")
        self.assertEqual(seen["solver"]["health"], health)
        with patch("remote_execution.benchmark.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ActiveState=inactive\n")), \
             self.assertRaisesRegex(ValueError, "supervised"):
            service_preflight(self.config["services"], ["solver"], directory / "bad.json")


if __name__ == "__main__":
    unittest.main()
