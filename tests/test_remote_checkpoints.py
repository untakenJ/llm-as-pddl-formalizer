"""Execution sync/recovery fault injection. CPU/loopback only, no real services."""

from pathlib import Path
from copy import deepcopy
import os
import threading
import time
import unittest
from unittest.mock import patch

from test_remote_execution import TemporaryCase
from remote_execution import bundle, checkpoints
from remote_execution.client import Client
from remote_execution.protocol import CHUNK_SIZE, digest, file_hash, private_json, read_json
from remote_execution.store import Store, lock
from remote_execution.worker import Node, make_server


class CheckpointTests(TemporaryCase):
    def test_api_execution_sync_ack_and_restore_keep_valid_wrong_answer(self):
        from remote_execution.api import case_directory, selected_case
        spec = {"schema_version": 1, "job_id": "api-cell", "release_id": self.spec["release_id"], "kind": "api_cell",
                "parameters": {"model": "self-hosted/example", "domain": "barman", "dataset": "Heavily_Templated_Barman-100",
                               "indices": [1, 2, 3], "operational_config": "source/operational.json",
                               "services": [], "solver_backend": "local"}}
        self.node.submit(spec)
        self.node.store.transition("api-cell", "running")
        directory = self.node.store.directory("api-cell")
        for problem in ("p01", "p02", "p03"):
            execution = case_directory(directory / "output", spec["parameters"], problem) / "executions/execution-000001"
            execution.mkdir(parents=True)
            identity = {"request_sha256": digest(spec), "problem": problem}
            private_json(execution / "api_request.json", identity)
            if problem != "p03":
                valid = problem == "p01"
                private_json(execution / ("execution_result.json" if valid else "infra_invalid.json"), {
                    "complete": True, "attempt_valid": valid, "generation_success": False, "identity": identity,
                    "files": {"api_request.json": file_hash(execution / "api_request.json")}})
        index = checkpoints.publish_ready(directory, spec, self.config, 1)
        self.assertEqual(len(index["checkpoints"]), 2)
        progress = self.node.progress("api-cell")
        self.assertEqual(progress["cells"][0]["selected_valid_attempts"], 1)
        received = self.client.sync("api-cell", self.destination)
        self.assertEqual(received["durable_executions"], 2)
        self.assertEqual(received["status"], "running")
        self.assertEqual(self.node.progress("api-cell")["acknowledged_checkpoints"], 2)
        archive = self.root / "api-recovery.tar.gz"
        checkpoints.recovery_bundle(self.destination / "api-cell", archive)
        self.stop_server()
        os.rename(self.node.store.root, self.root / "retired-node")
        store = Store(Path(self.config["state_dir"]))
        bundle.install(self.archive, store.root / "releases", spec["release_id"])
        recovered = checkpoints.restore(archive, self.config, source_node_retired=True, reason="API test node retired")
        self.assertEqual(recovered["generation"], 2)
        case = case_directory(store.directory("api-cell") / "output", spec["parameters"], "p01")
        self.assertFalse(selected_case(case)[1]["generation_success"])
        self.assertFalse(case.with_name("p03").exists())

    def setUp(self):
        super().setUp()
        private_json(self.workspace / "source/profile.json", {})
        private_json(self.workspace / "source/operational.json", {})
        self.node = Node(self.config)
        self.archive, info = self.install_release(self.node)
        self.spec = {"schema_version": 1, "job_id": "cell", "release_id": info["release_id"], "kind": "agent_cell",
                     "parameters": {"harness": "openclaw", "domain": "barman", "dataset": "Heavily_Templated_Barman-100",
                         "indices": [1, 2, 3, 4], "benchmark_profile": "source/profile.json",
                         "operational_config": "source/operational.json", "resolved_config_sha256": "a" * 64, "services": []}}
        self.node.submit(self.spec)
        self.node.store.transition("cell", "running")
        self.directory = self.node.store.directory("cell")
        self.cell = self.directory / "output/llm-as-formalizer-agent/barman/Heavily_Templated_Barman-100/model"
        self.server = make_server(self.node)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}", self.token)
        self.destination = self.root / "collected"

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
            self.server = None
        for child in self.node.children.values():
            child.wait(timeout=15)

    def execution(self, problem="p01", *, kind="valid", model=None, number=1, payload=b"trace\n"):
        model_dir = self.cell if model is None else self.cell.parent / model
        root = model_dir / problem / "executions" / f"execution-{number:03d}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "trace.jsonl").write_bytes(payload)
        value = {"complete": True, "attempt_valid": True, "generation_success": False,
                 "problem": problem, "attempt_index": 1, "selected_execution_try": number,
                 "model_label": model_dir.name, "resolved_config_sha256": "a" * 64,
                 "runtime_identity_sha256": "b" * 64, "task_input_sha256": "c" * 64,
                 "completed_at": "2026-09-14T00:00:00+00:00", "artifacts": {}, "evidence": {}}
        if kind == "valid":
            private_json(root / "execution_result.json", value)
        elif kind == "invalid":
            private_json(root / "infra_invalid.json", {"attempt_valid": False, "execution_try": number,
                         "infra_invalidator": "provider_unavailable"})
        return root

    def publish(self):
        return checkpoints.publish_ready(self.directory, self.spec, self.config, 1)

    def test_incremental_before_batch_end_all_outcomes_and_diagnostics(self):
        valid = self.execution()
        self.execution("p02", kind="invalid")
        self.execution("p03", kind="live")
        (valid / "unsafe-link").symlink_to(self.token)
        diag = self.directory / "output/infra-diagnostics/run/barman/Heavily_Templated_Barman-100/model/p01/attempt-001/execution-001/runtime-abc/events.jsonl"
        private_json(diag, {"diagnostic": "kept"})
        index = self.publish()
        self.assertEqual(len(index["checkpoints"]), 2)
        row = self.client.sync("cell", self.destination)
        self.assertEqual(row["durable_executions"], 2)
        self.assertEqual(row["status"], "running")
        first = index["checkpoints"][0]["checkpoint_id"]
        mirror = self.destination / "cell/checkpoints" / first
        manifest = read_json(mirror / "transport-manifest.json")
        self.assertIn(diag.relative_to(self.directory).as_posix(), manifest["files"])
        self.assertIn(valid.relative_to(self.directory).as_posix() + "/unsafe-link", manifest["excluded_nonregular"])
        self.assertFalse(any("p03/" in name for name in manifest["files"]))
        self.assertEqual(self.publish(), index)
        with patch.object(self.client, "request", wraps=self.client.request) as request:
            self.assertEqual(self.client.sync("cell", self.destination)["durable_executions"], 2)
            self.assertFalse(any("checkpoint-file" in call.args[0] or "checkpoint-ack" in call.args[0]
                                 for call in request.call_args_list))

    def test_partial_download_and_lost_ack_never_repeat_agent(self):
        self.execution(payload=b"t" * (CHUNK_SIZE + 20))
        index = self.publish(); original = self.client.request; calls = 0
        def fail_download(path, **kwargs):
            nonlocal calls
            if "checkpoint-file" in path:
                calls += 1
                if calls == 2:
                    raise ConnectionError("test interruption")
            return original(path, **kwargs)
        with patch.object(self.client, "request", side_effect=fail_download), self.assertRaises(ConnectionError):
            self.client.sync("cell", self.destination)
        self.assertEqual(read_json(self.destination / "cell/sync-state.json")["checkpoints"], [])
        def lose_ack(path, **kwargs):
            result = original(path, **kwargs)
            if "checkpoint-ack" in path:
                raise ConnectionError("ACK lost after controller durable commit")
            return result
        with patch.object(self.client, "request", side_effect=lose_ack), self.assertRaises(ConnectionError):
            self.client.sync("cell", self.destination)
        self.assertEqual(len(read_json(self.destination / "cell/sync-state.json")["checkpoints"]), 1)
        self.client.sync("cell", self.destination)
        self.assertEqual(self.node.store.get("cell")["generation"], 1)
        self.assertEqual(self.publish(), index)

    def test_completed_snapshot_not_changed_by_later_source_write(self):
        root = self.execution(); self.publish()
        (root / "trace.jsonl").write_bytes(b"later mutation")
        self.client.sync("cell", self.destination)
        unit = checkpoints.catalog(self.directory)["checkpoints"][0]["checkpoint_id"]
        copied = self.destination / "cell/checkpoints" / unit / root.relative_to(self.directory) / "trace.jsonl"
        self.assertEqual(copied.read_bytes(), b"trace\n")
        copied.write_bytes(b"local corruption")
        with self.assertRaisesRegex(ValueError, "receipt"):
            checkpoints.recovery_bundle(self.destination / "cell", self.root / "corrupted.tar.gz")

    def test_restore_retains_valid_wrong_and_invalid_without_leases(self):
        root = self.execution(); self.execution("p02", kind="invalid")
        self.execution("p03", kind="live")
        private_json(root.parents[1] / ".attempt.lease", {"pid": os.getpid()})
        original = (root / "execution_result.json").read_bytes()
        self.publish(); self.client.sync("cell", self.destination)
        archive = self.root / "recovery.tar.gz"
        checkpoints.recovery_bundle(self.destination / "cell", archive)
        self.stop_server()
        # Simulate replacing the disk while retaining the same mount/absolute paths.
        os.rename(self.node.store.root, self.root / "retired-node")
        store = Store(Path(self.config["state_dir"]))
        bundle.install(self.archive, store.root / "releases", self.spec["release_id"])
        with self.assertRaisesRegex(ValueError, "retirement"):
            checkpoints.restore(archive, self.config, reason="test")
        row = checkpoints.restore(archive, self.config | {"node_id": "replacement"},
                                  reason="test VM explicitly terminated", source_node_retired=True)
        self.assertEqual(row["generation"], 2)
        self.assertEqual((root / "execution_result.json").read_bytes(), original)
        self.assertFalse((root.parents[1] / ".attempt.lease").exists())
        self.assertFalse((self.cell / "p03").exists())
        from agent_formalizer.results.execution_validity import refresh_cell_state, selected_execution_record
        state = refresh_cell_state(self.cell, expected_problems=["p01", "p02", "p03"], attempts_per_case=1)
        selected = selected_execution_record(state, "p01", 1)
        self.assertIsNotNone(selected)
        self.assertFalse(selected["generation_success"])
        self.assertIsNone(selected_execution_record(state, "p02", 1))
        self.assertIsNone(selected_execution_record(state, "p03", 1))
        with self.assertRaisesRegex(ValueError, "empty"):
            checkpoints.restore(archive, self.config, reason="duplicate", source_node_retired=True)

    def test_attempt_two_and_adjudication_revisions_preserved(self):
        self.execution(model="model__attempt_002")
        events = self.cell / "execution_validity_events.jsonl"
        private_json(events, {"test_event": 1})
        self.publish(); self.client.sync("cell", self.destination)
        with events.open("ab") as stream:
            stream.write(b'{"test_event":2}\n')
        self.publish(); self.client.sync("cell", self.destination)
        rows = read_json(self.destination / "cell/sync-state.json")["checkpoints"]
        self.assertEqual([r["kind"] for r in rows], ["execution", "adjudication", "adjudication"])
        recovery = self.root / "recovery.tar.gz"
        self.assertEqual(checkpoints.recovery_bundle(self.destination / "cell", recovery)["checkpoints"], 3)

    def test_no_terminal_no_checkpoint(self):
        self.execution(kind="live")
        self.assertEqual(self.publish()["checkpoints"], [])

    def test_zero_received_executions_can_restore_original_job(self):
        self.client.sync("cell", self.destination)
        archive = self.root / "empty-recovery.tar.gz"
        self.assertEqual(checkpoints.recovery_bundle(self.destination / "cell", archive)["checkpoints"], 0)
        self.stop_server()
        os.rename(self.node.store.root, self.root / "retired-node")
        store = Store(Path(self.config["state_dir"]))
        bundle.install(self.archive, store.root / "releases", self.spec["release_id"])
        row = checkpoints.restore(archive, self.config, source_node_retired=True, reason="terminated before first sync")
        self.assertEqual(row["spec"], self.spec)
        self.assertEqual(row["generation"], 2)

    def test_recovery_rename_before_queue_commit_is_retryable(self):
        self.execution(); self.publish(); self.client.sync("cell", self.destination)
        archive = self.root / "recovery.tar.gz"
        checkpoints.recovery_bundle(self.destination / "cell", archive)
        self.stop_server()
        os.rename(self.node.store.root, self.root / "retired-node")
        store = Store(Path(self.config["state_dir"]))
        bundle.install(self.archive, store.root / "releases", self.spec["release_id"])
        with patch("remote_execution.checkpoints.Store.event", side_effect=OSError("injected commit failure")), self.assertRaises(OSError):
            checkpoints.restore(archive, self.config, source_node_retired=True, reason="node retired")
        self.assertEqual(store.list(), [])
        row = checkpoints.restore(archive, self.config, source_node_retired=True, reason="node retired")
        self.assertEqual(row["generation"], 2)

    def test_checkpoint_validation_rejects_leases_and_wrong_identity(self):
        self.execution(); index = self.publish()
        manifest = checkpoints.checkpoint_manifest(self.directory, index["checkpoints"][0]["checkpoint_id"])
        for path in ("output/.attempt.lease", "output/llm-as-formalizer-agent/other/completion.json", "../private/key"):
            bad = deepcopy(manifest)
            bad["files"][path] = {"size": 0, "sha256": "a" * 64}
            with self.assertRaises(ValueError):
                checkpoints.validate_manifest(bad)
        with self.assertRaisesRegex(ValueError, "request"):
            checkpoints.validate_manifest(manifest | {"request_sha256": "b" * 64})

    def test_changing_replacement_configuration_is_refused(self):
        self.execution(); self.publish(); self.client.sync("cell", self.destination)
        archive = self.root / "recovery.tar.gz"
        checkpoints.recovery_bundle(self.destination / "cell", archive)
        self.stop_server()
        os.rename(self.node.store.root, self.root / "retired-node")
        store = Store(Path(self.config["state_dir"]))
        bundle.install(self.archive, store.root / "releases", self.spec["release_id"])
        with self.assertRaisesRegex(ValueError, "frozen"):
            checkpoints.restore(archive, self.config | {"max_formalizer_workers": 8},
                                source_node_retired=True, reason="not permission to change resources")
        self.assertEqual(store.list(), [])
        self.assertFalse(store.directory("cell").exists())

    def test_real_owner_publishes_while_second_case_still_running(self):
        self.node.store.transition("cell", "failed")
        entry = self.workspace / "source/remote_execution/benchmark.py"
        entry.parent.mkdir(parents=True)
        entry.write_text('''import argparse,json,pathlib,time
p=argparse.ArgumentParser()
for key in ("job","node","directory","generation"): p.add_argument("--"+key,required=True)
a=p.parse_args()
for number in (1,2):
 root=pathlib.Path(a.directory)/f"output/llm-as-formalizer-agent/barman/Heavily_Templated_Barman-100/model/p{number:02d}/executions/execution-001"
 root.mkdir(parents=True)
 (root/"trace.txt").write_text("synthetic; not a benchmark result")
 (root/"execution_result.json").write_text(json.dumps({"complete":True,"attempt_valid":True,"generation_success":False}))
 if number==1: time.sleep(5)
''')
        archive = self.root / "synthetic.tar.gz"
        info = bundle.build(self.workspace, ["source"], archive)
        self.client.upload(archive, info["release_id"])
        spec = self.spec | {"job_id": "synthetic", "release_id": info["release_id"]}
        self.client.submit(spec); self.node.tick()
        deadline = time.monotonic() + 15
        observed_midflight = False
        while time.monotonic() < deadline:
            result = self.client.sync("synthetic", self.destination)
            if result["durable_executions"] == 1 and result["status"] == "running":
                observed_midflight = True
            if result["status"] in {"completed", "failed", "needs_attention"}:
                break
            time.sleep(0.1)
        self.assertTrue(observed_midflight)
        self.assertEqual(result["durable_executions"], 2)
        self.assertEqual(result["status"], "completed")
        self.node.tick()


if __name__ == "__main__":
    unittest.main()
