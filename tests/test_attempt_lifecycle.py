from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.configuration.benchmark_profile import (
    DEFAULT_BENCHMARK_PROFILE,
    load_benchmark_profile,
)
from agent_formalizer.orchestrator import InfraInvalid, _run_attempt
from agent_formalizer.result_types import AgentResult, FormalizerResult
from agent_formalizer.results.execution_validity import (
    append_manual_event,
    refresh_cell_state,
    selected_attempt,
)


def adapter(max_tries: int = 3):
    resolved = DEFAULT_BENCHMARK_PROFILE.resolve(
        "hermes",
        model="deepseek/deepseek-v4-flash",
        max_execution_tries=max_tries,
    )
    return SimpleNamespace(resolved_config=resolved)


def streaming_adapter():
    profile = load_benchmark_profile(
        HISTORICAL_PROFILES_DIR / "native_safety_streaming_native_clean.json"
    )
    return SimpleNamespace(
        resolved_config=profile.resolve("hermes", model="openai/test-model")
    )


def valid_result(*, generated: bool, payload: bytes = b""):
    return FormalizerResult(
        problem="p01",
        status="ok" if generated else "failed",
        attempt_index=1,
        execution_try=1,
        attempt_valid=True,
        generation_success=generated,
        model_label="study",
        domain_file=payload.decode(errors="replace") if generated else None,
        problem_file="" if generated else None,
        domain_bytes=payload if generated else None,
        problem_bytes=b"" if generated else None,
        extraction_source="file" if generated else None,
        error=None if generated else "delivery files missing",
        agent_result=AgentResult(
            success=False,
            timeout=True,
            exit_code=-1,
            finish_reason="timeout",
        ),
    )


def minimal_evidence() -> dict:
    return {
        "evidence": "minimal",
        "actions": {
            "model_calls": 0,
            "tool_calls": 0,
            "action_steps": 0,
            "max_model_calls": 50,
            "max_action_steps": 200,
            "action_step_limit_reached": False,
        },
    }


class AttemptLifecycleTests(unittest.TestCase):
    def invoke(
        self,
        root: Path,
        fake,
        *,
        config=None,
        task_hash="task-hash",
        runtime_hash="runtime-hash",
    ):
        return _run_attempt(
            config or adapter(),
            "blocksworld",
            "dataset",
            "p01",
            attempt_index=1,
            model_label="study",
            record_trace=False,
            out_dir_root=root,
            image=None,
            domain_description="domain input",
            problem_description="problem input",
            prompt="canonical prompt",
            task_identity={"sha256": task_hash, "raw": {}},
            runtime_lock={"status": "pass"},
            runtime_identity_sha256=runtime_hash,
        )

    def test_only_infra_invalid_execution_is_retried(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs["execution_try"])
            if len(calls) == 1:
                raise InfraInvalid("container_start_failed", "docker unavailable")
            return valid_result(generated=False), minimal_evidence()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try", side_effect=fake
        ):
            result = self.invoke(Path(tmp), fake)
            completion = json.loads(result.completion_path.read_text())

        self.assertEqual(calls, [1, 2])
        self.assertTrue(result.attempt_valid)
        self.assertFalse(result.generation_success)
        self.assertEqual(completion["selected_execution_try"], 2)
        self.assertEqual(
            completion["invalid_executions"][0]["infra_invalidator"],
            "container_start_failed",
        )

    def test_timeout_without_files_is_valid_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            return_value=(valid_result(generated=False), minimal_evidence()),
        ) as run:
            result = self.invoke(Path(tmp), run)

        self.assertEqual(run.call_count, 1)
        self.assertTrue(result.attempt_valid)
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.agent_result.timeout)

    def test_delivery_bytes_are_not_rewritten_and_empty_file_counts(self):
        payload = b"\xff\x00native-bytes\r\n"
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            return_value=(
                valid_result(generated=True, payload=payload),
                minimal_evidence(),
            ),
        ):
            root = Path(tmp)
            result = self.invoke(root, None)
            directory = result.completion_path.parent
            domain = directory / "p01_study_df.pddl"
            problem = directory / "p01_study_pf.pddl"
            domain_bytes = domain.read_bytes()
            problem_bytes = problem.read_bytes()

        self.assertEqual(domain_bytes, payload)
        self.assertEqual(problem_bytes, b"")
        self.assertTrue(result.generation_success)

    def test_hash_matching_completion_resumes_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "agent_formalizer.orchestrator._run_execution_try",
                return_value=(valid_result(generated=False), minimal_evidence()),
            ):
                first = self.invoke(root, None)
            with patch(
                "agent_formalizer.orchestrator._run_execution_try",
                side_effect=AssertionError("must not execute"),
            ):
                resumed = self.invoke(root, None)

        self.assertEqual(resumed.completion_path, first.completion_path)
        self.assertTrue(resumed.attempt_valid)

    def test_manual_invalidation_repairs_without_rewriting_completion(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs["execution_try"])
            return valid_result(generated=False), minimal_evidence()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try", side_effect=fake
        ):
            root = Path(tmp)
            first = self.invoke(root, fake)
            completion_path = first.completion_path
            original_completion = completion_path.read_bytes()
            cell = completion_path.parent.parent
            append_manual_event(
                cell,
                action="invalidate",
                problem="p01",
                attempt_index=1,
                execution_try=1,
                operator="benchmark-owner",
                reason_code="tool_infra.solver_transport",
                reason="solver tool returned an independently verified transport error",
                evidence_paths=[completion_path],
                result_visibility="blind",
                timestamp="2026-09-01T00:00:00Z",
            )
            second = self.invoke(root, fake)
            state = refresh_cell_state(cell)
            completion_unchanged = completion_path.read_bytes() == original_completion

        self.assertEqual(calls, [1, 2])
        self.assertTrue(completion_unchanged)
        self.assertEqual(second.completion_path.name, "execution_result.json")
        self.assertEqual(
            selected_attempt(state, "p01", 1)["selected_execution"], 2
        )

    def test_dataset_update_binds_task_and_runtime_identity_migration(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs["execution_try"])
            return valid_result(generated=False), minimal_evidence()

        old_task = "1" * 64
        new_task = "2" * 64
        old_runtime = "3" * 64
        new_runtime = "4" * 64
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try", side_effect=fake
        ):
            root = Path(tmp)
            first = self.invoke(
                root, fake, task_hash=old_task, runtime_hash=old_runtime
            )
            completion_path = first.completion_path
            original_completion = completion_path.read_bytes()
            cell = completion_path.parent.parent
            append_manual_event(
                cell,
                action="invalidate",
                problem="p01",
                attempt_index=1,
                execution_try=1,
                operator="benchmark-owner",
                reason_code="dataset_update.input_revision",
                reason="owner-approved correction to an ambiguous input sentence",
                evidence_paths=[completion_path],
                result_visibility="score_visible",
                timestamp="2026-09-02T00:00:00Z",
                replacement_task_input_sha256=new_task,
                replacement_runtime_identity_sha256=new_runtime,
            )
            second = self.invoke(
                root, fake, task_hash=new_task, runtime_hash=new_runtime
            )
            state = refresh_cell_state(cell)
            completion_unchanged = completion_path.read_bytes() == original_completion

        self.assertEqual(calls, [1, 2])
        self.assertTrue(completion_unchanged)
        self.assertEqual(second.completion_path.name, "execution_result.json")
        self.assertEqual(
            selected_attempt(state, "p01", 1)["selected_execution"], 2
        )
        self.assertEqual(
            state["cell"]["observed_runtime_identity_sha256s"],
            [old_runtime, new_runtime],
        )

    def test_dataset_update_rejects_unbound_replacement_identity(self):
        old_task = "1" * 64
        new_task = "2" * 64
        old_runtime = "3" * 64
        authorized_runtime = "4" * 64
        other_runtime = "5" * 64
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            return_value=(valid_result(generated=False), minimal_evidence()),
        ):
            root = Path(tmp)
            first = self.invoke(
                root, None, task_hash=old_task, runtime_hash=old_runtime
            )
            cell = first.completion_path.parent.parent
            append_manual_event(
                cell,
                action="invalidate",
                problem="p01",
                attempt_index=1,
                execution_try=1,
                operator="benchmark-owner",
                reason_code="dataset_update.input_revision",
                reason="owner-approved correction",
                evidence_paths=[first.completion_path],
                result_visibility="score_visible",
                timestamp="2026-09-02T00:00:00Z",
                replacement_task_input_sha256=new_task,
                replacement_runtime_identity_sha256=authorized_runtime,
            )
            with self.assertRaisesRegex(
                Exception, "without an exact authorized repair runtime"
            ):
                self.invoke(
                    root,
                    None,
                    task_hash=new_task,
                    runtime_hash=other_runtime,
                )

    def test_tool_infra_binds_same_task_to_reviewed_runtime_revision(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs["execution_try"])
            return valid_result(generated=False), minimal_evidence()

        task = "1" * 64
        old_runtime = "3" * 64
        new_runtime = "4" * 64
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try", side_effect=fake
        ):
            root = Path(tmp)
            first = self.invoke(
                root, fake, task_hash=task, runtime_hash=old_runtime
            )
            cell = first.completion_path.parent.parent
            append_manual_event(
                cell,
                action="invalidate",
                problem="p01",
                attempt_index=1,
                execution_try=1,
                operator="benchmark-owner",
                reason_code="tool_infra.solver_transport",
                reason="reviewed infra-transparent runtime repair",
                evidence_paths=[first.completion_path],
                result_visibility="score_visible",
                timestamp="2026-09-02T00:00:00Z",
                replacement_task_input_sha256=task,
                replacement_runtime_identity_sha256=new_runtime,
            )
            second = self.invoke(
                root, fake, task_hash=task, runtime_hash=new_runtime
            )
            state = refresh_cell_state(cell)

        self.assertEqual(calls, [1, 2])
        self.assertEqual(second.completion_path.name, "execution_result.json")
        self.assertEqual(
            selected_attempt(state, "p01", 1)["selected_execution"], 2
        )

    def test_exhausted_infra_tries_do_not_create_valid_attempt(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            side_effect=InfraInvalid("gateway_start_failed", "gateway failed"),
        ) as run:
            result = self.invoke(Path(tmp), run, config=adapter(max_tries=2))

        self.assertEqual(run.call_count, 2)
        self.assertFalse(result.attempt_valid)
        self.assertEqual(result.status, "incomplete")  # Current v5 envelope.
        self.assertIsNone(result.completion_path)

    def test_automatic_invalid_runtime_repair_needs_authorization_and_resumes(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs['execution_try'])
            if len(calls) == 1:
                raise InfraInvalid('provider_transient_exhausted', 'unavailable', retry_execution=False)
            return valid_result(generated=False), minimal_evidence()

        with tempfile.TemporaryDirectory() as tmp, patch(
            'agent_formalizer.orchestrator._run_execution_try', side_effect=fake
        ):
            root = Path(tmp)
            self.invoke(root, fake, task_hash='a' * 64, runtime_hash='b' * 64)
            cell = next(root.glob('**/invalid_attempt.json')).parent.parent
            evidence = cell / 'p01/executions/execution-001/infra_invalid.json'
            original = evidence.read_bytes()
            with self.assertRaisesRegex(Exception, 'without an exact authorized repair runtime'):
                self.invoke(root, fake, task_hash='a' * 64, runtime_hash='c' * 64)
            append_manual_event(cell, action='authorize_repair', problem='p01', attempt_index=1,
                execution_try=1, operator='owner', reason_code='tool_infra.checkpoint_lifecycle',
                reason='Authorized lifecycle fix', evidence_paths=[evidence], result_visibility='score_visible',
                timestamp='2026-09-09T00:00:00Z', replacement_task_input_sha256='a' * 64,
                replacement_runtime_identity_sha256='c' * 64)
            second = self.invoke(root, fake, task_hash='a' * 64, runtime_hash='c' * 64)
            resumed = self.invoke(root, fake, task_hash='a' * 64, runtime_hash='c' * 64)
            self.assertTrue(second.attempt_valid)
            self.assertEqual(resumed.execution_try, 2)
            self.assertEqual(calls, [1, 2])
            self.assertEqual(evidence.read_bytes(), original)
            self.assertEqual(selected_attempt(refresh_cell_state(cell), 'p01')['selected_execution'], 2)

    def test_provider_transient_exhaustion_is_invalid_without_auto_rerun(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            side_effect=InfraInvalid(
                "provider_transient_exhausted",
                "provider unavailable",
                retry_execution=False,
            ),
        ) as run:
            root = Path(tmp)
            result = self.invoke(root, run, config=adapter(max_tries=3))
            invalid_path = result.completion_path
            records = list(root.glob("**/invalid_attempt.json"))

        self.assertEqual(run.call_count, 1)
        self.assertFalse(result.attempt_valid)
        self.assertEqual(result.status, "infra_invalid")
        self.assertIsNone(invalid_path)
        self.assertEqual(len(records), 1)

    def test_manual_rerun_preserves_invalid_execution_and_uses_next_number(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs["execution_try"])
            if len(calls) == 1:
                raise InfraInvalid(
                    "provider_transient_exhausted",
                    "provider unavailable",
                    retry_execution=False,
                )
            return valid_result(generated=False), minimal_evidence()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try", side_effect=fake
        ):
            root = Path(tmp)
            first = self.invoke(root, fake)
            second = self.invoke(root, fake)
            completion = json.loads(second.completion_path.read_text())

        self.assertFalse(first.attempt_valid)
        self.assertTrue(second.attempt_valid)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(completion["selected_execution_try"], 2)
        self.assertEqual(
            completion["invalid_executions"][0]["infra_invalidator"],
            "provider_transient_exhausted",
        )

    def test_streaming_postcommit_failure_retries_five_clean_executions(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            side_effect=InfraInvalid(
                "post_commit_stream_failure", "upstream reset"
            ),
        ) as run:
            root = Path(tmp)
            result = self.invoke(root, run, config=streaming_adapter())
            incomplete = list(root.glob("**/invalid_attempt.json"))
            incomplete_status = (
                json.loads(incomplete[0].read_text())["status"]
                if incomplete
                else None
            )

        self.assertEqual(run.call_count, 5)
        self.assertFalse(result.attempt_valid)
        self.assertEqual(result.status, "incomplete")
        self.assertIsNone(result.completion_path)
        self.assertEqual(len(incomplete), 1)
        self.assertEqual(incomplete_status, "incomplete")

    def test_invalid_streaming_artifact_and_metrics_are_not_selected(self):
        invalid_payload = b"invalid execution artifact"
        selected_payload = b"selected clean execution"

        def fake(*args, **kwargs):
            execution_dir = (
                kwargs["attempt_dir"]
                / "executions"
                / f"execution-{kwargs['execution_try']:03d}"
            )
            execution_dir.mkdir(parents=True, exist_ok=True)
            if kwargs["execution_try"] == 1:
                (execution_dir / "domain.pddl").write_bytes(invalid_payload)
                raise InfraInvalid(
                    "post_commit_stream_failure", "reset after delivery"
                )
            evidence = minimal_evidence()
            evidence["actions"]["model_calls"] = 2
            return valid_result(generated=True, payload=selected_payload), evidence

        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try", side_effect=fake
        ):
            result = self.invoke(
                Path(tmp), fake, config=streaming_adapter()
            )
            completion = json.loads(result.completion_path.read_text())
            selected_domain = result.completion_path.parent / "p01_study_df.pddl"
            selected_bytes = selected_domain.read_bytes()

        self.assertEqual(completion["selected_execution_try"], 2)
        self.assertEqual(selected_bytes, selected_payload)
        self.assertEqual(completion["evidence"]["actions"]["model_calls"], 2)
        self.assertNotIn(invalid_payload.decode(), json.dumps(completion))


if __name__ == "__main__":
    unittest.main()
