from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_formalizer.configuration.benchmark_profile import canonical_sha256
from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.minimum import MinimumAgentAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.openclaw import OpenClawAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter
from agent_formalizer.results.optional_evidence import (
    build_analysis_evidence_manifest,
    inspect_json_analysis_fields,
    inventory_raw_evidence,
)
from agent_formalizer.orchestrator import (
    _ensure_uncollected_analysis_manifest,
    _record_optional_evidence,
)
from agent_formalizer.results.provider_reasoning import ProviderReasoningRecorder
from agent_formalizer.util import Tracer


class FakeAdapter:
    name = "fake"
    model = "provider/test-model"

    def __init__(
        self,
        *,
        raw_persistence="implemented",
        observation=None,
        absence_is_model_attributable=False,
    ):
        self.raw_persistence = raw_persistence
        self.observation = observation
        self.absence_is_model_attributable = absence_is_model_attributable

    def raw_evidence_roots(self, artifact_dir):
        return [artifact_dir / "sessions", artifact_dir / "gateway"]

    def analysis_evidence_spec(self):
        return {
            "schema_version": 1,
            "analysis_source": {
                "kind": "native_message_field",
                "native_harness_exposure": "structured",
                "absence_is_model_attributable": self.absence_is_model_attributable,
                "text_fields": ["reasoning_content"],
                "opaque_fields": [],
            },
            "raw_session": {
                "adapter_persistence": self.raw_persistence,
                "collector": "fake-copy",
            },
            "normalized_analysis": {
                "status": "not_implemented",
                "known_loss_modes": [],
            },
        }

    def inspect_analysis_evidence(self, artifact_dir):
        if self.observation is not None:
            return self.observation
        return inspect_json_analysis_fields(
            sorted((artifact_dir / "sessions").glob("*.jsonl")),
            artifact_dir=artifact_dir,
            text_fields={"reasoning_content"},
        )

    def backup_session(self, agent_id, artifact_dir, **kwargs):
        sessions = artifact_dir / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "native.jsonl").write_text(
            json.dumps(
                {
                    "role": "assistant",
                    "reasoning_content": "TOP-SECRET-ANALYSIS",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "status": "persisted",
            "collector": "fake-copy",
            "files_copied": 1,
        }

    def iter_agent_steps(self, *args, **kwargs):
        return iter([{"event": "message", "role": "assistant"}])

    def iter_tool_calls(self, *args, **kwargs):
        return iter([{"kind": "call", "name": "write", "arguments": {}}])


class RawEvidenceInventoryTests(unittest.TestCase):
    def test_inventory_hashes_and_counts_supported_formats_without_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            jsonl = sessions / "native.jsonl"
            jsonl.write_text(
                '{"event":"one","secret":"DO-NOT-LEAK"}\n'
                "not-json\n"
                '{"event":"two"}\n',
                encoding="utf-8",
            )
            expected_jsonl_sha256 = hashlib.sha256(jsonl.read_bytes()).hexdigest()
            (sessions / "transcript.json").write_text(
                json.dumps({"events": [{"event": "one"}, {"event": "two"}]}),
                encoding="utf-8",
            )
            database = sessions / "state.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE messages (id INTEGER, content TEXT)")
                connection.executemany(
                    "INSERT INTO messages VALUES (?, ?)",
                    [(1, "a"), (2, "b")],
                )
            inventory = inventory_raw_evidence(root, [sessions])

        rows = {row["path"]: row for row in inventory["files"]}
        self.assertEqual(inventory["file_count"], 3)
        self.assertEqual(rows["sessions/native.jsonl"]["record_count"], 3)
        self.assertEqual(rows["sessions/native.jsonl"]["parseable_json_records"], 2)
        self.assertEqual(rows["sessions/native.jsonl"]["malformed_records"], 1)
        self.assertEqual(rows["sessions/transcript.json"]["record_count"], 2)
        self.assertEqual(rows["sessions/state.db"]["table_rows"]["messages"], 2)
        self.assertEqual(
            rows["sessions/native.jsonl"]["sha256"],
            expected_jsonl_sha256,
        )
        self.assertNotIn("DO-NOT-LEAK", json.dumps(inventory))

    def test_inventory_rejects_symlink_root_without_reading_target(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            tempfile.TemporaryDirectory() as other,
        ):
            root = Path(tmp)
            target = Path(other)
            (target / "secret.jsonl").write_text(
                '{"reasoning_content":"DO-NOT-LEAK"}\n', encoding="utf-8"
            )
            linked = root / "sessions"
            linked.symlink_to(target, target_is_directory=True)
            inventory = inventory_raw_evidence(root, [linked])

        self.assertEqual(inventory["file_count"], 0)
        self.assertEqual(inventory["roots"][0]["status"], "rejected_symlink_root")
        self.assertNotIn("DO-NOT-LEAK", json.dumps(inventory))


class AnalysisAttributionTests(unittest.TestCase):
    def build(self, adapter, *, collection):
        with tempfile.TemporaryDirectory() as tmp:
            return build_analysis_evidence_manifest(
                adapter,
                Path(tmp),
                session_collection=collection,
                usage_collection={"status": "completed"},
                steps_collection={"status": "empty"},
                tool_trace_collection={"status": "empty"},
            )

    def test_observed_text_is_attributed_to_emission(self):
        manifest = self.build(
            FakeAdapter(observation={"status": "text_observed"}),
            collection={"status": "persisted"},
        )
        self.assertEqual(
            manifest["analysis_attribution"]["status"],
            "analysis_text_observed",
        )
        self.assertEqual(
            manifest["analysis_attribution"]["model_behavior_conclusion"],
            "analysis_emission_observed",
        )

    def test_collection_failure_is_not_misattributed_to_model(self):
        manifest = self.build(
            FakeAdapter(observation={"status": "not_persisted"}),
            collection={"status": "failed", "error_type": "OSError"},
        )
        self.assertEqual(
            manifest["analysis_attribution"]["status"],
            "adapter_collection_failed",
        )
        self.assertEqual(
            manifest["analysis_attribution"]["model_behavior_conclusion"],
            "not_determined",
        )

    def test_missing_adapter_capture_is_explicit(self):
        manifest = self.build(
            FakeAdapter(
                raw_persistence="not_implemented",
                observation={"status": "not_persisted"},
            ),
            collection={"status": "not_exposed"},
        )
        self.assertEqual(
            manifest["analysis_attribution"]["status"],
            "adapter_did_not_persist_native_evidence",
        )

    def test_model_omission_requires_authoritative_explicit_absence(self):
        manifest = self.build(
            FakeAdapter(
                observation={"status": "explicit_absence"},
                absence_is_model_attributable=True,
            ),
            collection={"status": "persisted"},
        )
        self.assertEqual(
            manifest["analysis_attribution"]["status"],
            "model_omitted_analysis",
        )
        self.assertEqual(
            manifest["analysis_attribution"]["model_behavior_conclusion"],
            "model_omission_supported_by_direct_record",
        )


class OptionalEvidenceOrchestrationTests(unittest.TestCase):
    def test_orchestrator_writes_manifest_and_legacy_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracer = Tracer(str(root / "trace.jsonl"))
            optional = _record_optional_evidence(
                FakeAdapter(),
                "agent",
                root,
                "p01",
                "fake-model",
                tracer,
                None,
                "container",
                {"status": "completed", "values_present": False},
            )
            tracer.close()
            manifest_path = root / "analysis_evidence_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(optional["traced_tool_call_count"], 1)
        self.assertEqual(optional["agent_trace_record_count"], 1)
        self.assertEqual(optional["analysis_evidence_manifest"]["status"], "complete")
        self.assertEqual(manifest["raw_evidence"]["file_count"], 1)
        self.assertEqual(
            manifest["analysis_attribution"]["status"],
            "analysis_text_observed",
        )
        manifest_identity = dict(manifest)
        stored_identity_hash = manifest_identity.pop("content_free_manifest_sha256")
        manifest_identity.pop("content_free_manifest_sha256_scope")
        self.assertEqual(stored_identity_hash, canonical_sha256(manifest_identity))
        self.assertNotIn("TOP-SECRET-ANALYSIS", json.dumps(manifest))

    def test_nanobot_copy_failure_is_reported(self):
        adapter = NanoBotAdapter.__new__(NanoBotAdapter)
        failed = subprocess.CompletedProcess(["docker", "cp"], 1, b"", b"denied")
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.claws.nanobot.subprocess.run", return_value=failed
        ):
            report = adapter.backup_session(
                "agent", Path(tmp), container_name="container"
            )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["copy_exit_code"], 1)
        self.assertNotIn("denied", json.dumps(report))

    def test_precollection_failure_writes_explicit_boundary_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _ensure_uncollected_analysis_manifest(
                FakeAdapter(), root, reason="container_start_failed"
            )
            manifest = json.loads(
                (root / "analysis_evidence_manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(record["status"], "collection_not_reached")
        self.assertEqual(manifest["manifest_status"], "collection_not_reached")
        self.assertEqual(
            manifest["collection_boundary_reason"], "container_start_failed"
        )
        self.assertEqual(
            manifest["collection"]["raw_session"]["status"], "not_attempted"
        )

    def test_provider_reasoning_is_hashed_and_counted_but_not_copied_to_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway = root / "gateway"
            recorder = ProviderReasoningRecorder(
                "deepseek",
                gateway / "provider_reasoning.jsonl",
                gateway / "reasoning_capture_status.json",
            )
            context = {
                "response_id": "logical-1-physical-1",
                "logical_call_index": 1,
                "physical_attempt": 1,
                "model": "deepseek-test",
                "api_path": "/v1/chat/completions",
                "streaming": False,
            }
            recorder.capture_payload(
                {
                    "choices": [
                        {
                            "message": {
                                "reasoning_content": "PROVIDER-PRIVATE-REASONING"
                            }
                        }
                    ]
                },
                context=context,
            )
            recorder.record_boundary(
                context=context,
                response_complete=True,
                downstream_state="forwarded_complete",
            )
            adapter = FakeAdapter(observation={"status": "not_observed"})
            adapter.model = "deepseek/deepseek-test"
            manifest = build_analysis_evidence_manifest(
                adapter,
                root,
                session_collection={"status": "persisted"},
                usage_collection={"status": "completed"},
                steps_collection={"status": "empty"},
                tool_trace_collection={"status": "empty"},
            )

        self.assertEqual(
            manifest["analysis_attribution"]["status"],
            "api_readable_analysis_captured",
        )
        self.assertEqual(
            manifest["provider_analysis_observation"]["fragments_examined"], 1
        )
        provider_files = [
            row
            for row in manifest["raw_evidence"]["files"]
            if row["role"] == "provider_readable_reasoning_transcript"
        ]
        self.assertEqual(len(provider_files), 1)
        self.assertEqual(len(provider_files[0]["sha256"]), 64)
        self.assertNotIn("PROVIDER-PRIVATE-REASONING", json.dumps(manifest))


class AdapterEvidenceDeclarationTests(unittest.TestCase):
    def test_every_harness_declares_analysis_provenance(self):
        for cls in (
            OpenClawAdapter,
            HermesAdapter,
            NanoBotAdapter,
            ZeroClawAdapter,
            GenericAgentAdapter,
            MinimumAgentAdapter,
        ):
            with self.subTest(adapter=cls.name):
                adapter = cls.__new__(cls)
                spec = adapter.analysis_evidence_spec()
                self.assertEqual(spec["schema_version"], 1)
                self.assertIn(
                    spec["analysis_source"]["native_harness_exposure"],
                    {"conditional", "structured", "explicit_response_field"},
                )
                self.assertIn(
                    spec["raw_session"]["adapter_persistence"],
                    {"implemented", "not_implemented", "runtime_direct"},
                )
                self.assertIn("status", spec["normalized_analysis"])


if __name__ == "__main__":
    unittest.main()
