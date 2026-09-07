from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent_formalizer.execution_validity import (
    EVENTS_NAME,
    STATE_NAME,
    ExecutionValidityError,
    append_manual_event,
    refresh_cell_state,
    selected_artifact_paths_for_model_dir,
    selected_attempt,
    write_execution_result,
)


class ExecutionValidityTests(unittest.TestCase):
    def _completion(
        self,
        execution_try: int,
        *,
        generated: bool = True,
        task_hash: str = "task-hash",
    ) -> dict:
        return {
            "schema_version": 2,
            "complete": True,
            "resolved_config_sha256": "config-hash",
            "task_input_sha256": task_hash,
            "runtime_identity_sha256": "runtime-hash",
            "problem": "p01",
            "model_label": "study",
            "attempt_index": 1,
            "attempt_valid": True,
            "generation_success": generated,
            "selected_execution_try": execution_try,
            "extraction_source": "file" if generated else None,
            "error": None if generated else "delivery missing",
            "evidence": {"frozen_workspace_artifacts": {}},
        }

    def _execution(
        self,
        cell: Path,
        execution_try: int,
        *,
        generated: bool = True,
        task_hash: str = "task-hash",
    ) -> tuple[Path, dict]:
        execution = cell / "p01" / "executions" / f"execution-{execution_try:03d}"
        frozen = execution / "frozen_workspace"
        frozen.mkdir(parents=True)
        completion = self._completion(
            execution_try, generated=generated, task_hash=task_hash
        )
        if generated:
            (frozen / "domain.pddl").write_text(f"domain-{execution_try}")
            (frozen / "problem.pddl").write_text(f"problem-{execution_try}")
        write_execution_result(execution, completion)
        return execution, completion

    def _event(self, cell: Path, action: str, execution_try: int, evidence: Path):
        return append_manual_event(
            cell,
            action=action,
            problem="p01",
            attempt_index=1,
            execution_try=execution_try,
            operator="benchmark-owner",
            reason_code="tool_infra.solver_transport",
            reason="agent-visible solver transport failed independently of the model",
            evidence_paths=[evidence],
            result_visibility="blind",
            timestamp=f"2026-09-01T00:00:0{execution_try}Z",
        )

    def test_invalidate_repair_and_reinstate_use_first_effective_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            cell = Path(tmp) / "study"
            first_execution, first_completion = self._execution(cell, 1)
            root_completion = cell / "p01" / "completion.json"
            root_completion.write_text(json.dumps(first_completion))
            original_completion_hash = hashlib.sha256(
                root_completion.read_bytes()
            ).hexdigest()

            initial = refresh_cell_state(
                cell,
                expected_problems=["p01"],
                attempts_per_case=1,
                resolved_config_sha256="config-hash",
                runtime_identity_sha256="runtime-hash",
            )
            self.assertEqual(
                selected_attempt(initial, "p01", 1)["selected_execution"], 1
            )

            _, invalidated = self._event(
                cell, "invalidate", 1, first_execution / "execution_result.json"
            )
            self.assertIsNone(selected_attempt(invalidated, "p01", 1))
            self.assertTrue(
                invalidated["problems"]["p01"]["attempts"]["1"][
                    "repair_required"
                ]
            )

            second_execution, _ = self._execution(cell, 2)
            repaired = refresh_cell_state(cell)
            self.assertEqual(
                selected_attempt(repaired, "p01", 1)["selected_execution"], 2
            )
            selected_paths = selected_artifact_paths_for_model_dir(cell, "p01")
            self.assertEqual(selected_paths[0].read_text(), "domain-2")
            self.assertEqual(selected_paths[1].read_text(), "problem-2")

            _, reinstated = self._event(
                cell, "reinstate", 1, second_execution / "execution_result.json"
            )
            self.assertEqual(
                selected_attempt(reinstated, "p01", 1)["selected_execution"], 1
            )
            self.assertEqual(
                hashlib.sha256(root_completion.read_bytes()).hexdigest(),
                original_completion_hash,
            )
            self.assertEqual(reinstated["events"]["count"], 2)
            self.assertTrue((cell / EVENTS_NAME).is_file())

    def test_direct_state_edit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cell = Path(tmp) / "study"
            self._execution(cell, 1)
            state = refresh_cell_state(
                cell, expected_problems=["p01"], attempts_per_case=1
            )
            state["complete"] = False
            (cell / STATE_NAME).write_text(json.dumps(state))
            with self.assertRaisesRegex(ExecutionValidityError, "hash mismatch"):
                refresh_cell_state(cell)

    def test_event_ledger_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cell = Path(tmp) / "study"
            execution, _ = self._execution(cell, 1)
            refresh_cell_state(
                cell, expected_problems=["p01"], attempts_per_case=1
            )
            self._event(cell, "invalidate", 1, execution / "execution_result.json")
            events_path = cell / EVENTS_NAME
            event = json.loads(events_path.read_text())
            event["reason"] = "silently changed"
            events_path.write_text(json.dumps(event) + "\n")
            with self.assertRaisesRegex(ExecutionValidityError, "event hash mismatch"):
                refresh_cell_state(cell)

    def test_multiple_attempt_labels_share_one_cell_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_dir = Path(tmp)
            cell = dataset_dir / "study"
            for attempt_index in (1, 2):
                attempt_model_dir = dataset_dir / f"study__attempt_{attempt_index:03d}"
                execution = (
                    attempt_model_dir
                    / "p01"
                    / "executions"
                    / "execution-001"
                )
                frozen = execution / "frozen_workspace"
                frozen.mkdir(parents=True)
                (frozen / "domain.pddl").write_text(f"domain-a{attempt_index}")
                (frozen / "problem.pddl").write_text(f"problem-a{attempt_index}")
                completion = self._completion(1)
                completion["attempt_index"] = attempt_index
                completion["model_label"] = attempt_model_dir.name
                (attempt_model_dir / "p01" / "completion.json").write_text(
                    json.dumps(completion)
                )

            state = refresh_cell_state(
                cell,
                expected_problems=["p01"],
                attempts_per_case=2,
                resolved_config_sha256="config-hash",
                runtime_identity_sha256="runtime-hash",
            )

            self.assertTrue(state["complete"])
            self.assertEqual(state["selected_problem_attempt_pairs"], 2)
            self.assertEqual(
                selected_attempt(state, "p01", 1)["selected_execution"], 1
            )
            self.assertEqual(
                selected_attempt(state, "p01", 2)["selected_execution"], 1
            )
            selected = selected_artifact_paths_for_model_dir(
                dataset_dir / "study__attempt_002", "p01"
            )
            self.assertEqual(selected[0].read_text(), "domain-a2")

    def test_dataset_update_requires_exact_replacement_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            cell = Path(tmp) / "study"
            execution, _ = self._execution(cell, 1)
            refresh_cell_state(
                cell, expected_problems=["p01"], attempts_per_case=1
            )
            with self.assertRaisesRegex(
                ExecutionValidityError, "requires exact replacement"
            ):
                append_manual_event(
                    cell,
                    action="invalidate",
                    problem="p01",
                    attempt_index=1,
                    execution_try=1,
                    operator="benchmark-owner",
                    reason_code="dataset_update.input_revision",
                    reason="input correction",
                    evidence_paths=[execution / "execution_result.json"],
                    result_visibility="score_visible",
                    timestamp="2026-09-02T00:00:00Z",
                )

    def test_tool_infra_runtime_migration_requires_same_exact_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            cell = Path(tmp) / "study"
            exact_task = "a" * 64
            execution, _ = self._execution(cell, 1, task_hash=exact_task)
            refresh_cell_state(
                cell, expected_problems=["p01"], attempts_per_case=1
            )
            with self.assertRaisesRegex(
                ExecutionValidityError, "preserve the exact task identity"
            ):
                append_manual_event(
                    cell,
                    action="invalidate",
                    problem="p01",
                    attempt_index=1,
                    execution_try=1,
                    operator="benchmark-owner",
                    reason_code="tool_infra.solver_transport",
                    reason="reviewed infra-transparent runtime repair",
                    evidence_paths=[execution / "execution_result.json"],
                    result_visibility="score_visible",
                    timestamp="2026-09-02T00:00:00Z",
                    replacement_task_input_sha256="1" * 64,
                    replacement_runtime_identity_sha256="2" * 64,
                )

            event, state = append_manual_event(
                cell,
                action="invalidate",
                problem="p01",
                attempt_index=1,
                execution_try=1,
                operator="benchmark-owner",
                reason_code="tool_infra.solver_transport",
                reason="reviewed infra-transparent runtime repair",
                evidence_paths=[execution / "execution_result.json"],
                result_visibility="score_visible",
                timestamp="2026-09-02T00:00:01Z",
                replacement_task_input_sha256=exact_task,
                replacement_runtime_identity_sha256="2" * 64,
            )
            self.assertEqual(
                event["replacement_runtime_identity_sha256"], "2" * 64
            )
            self.assertIn(
                "2" * 64,
                state["cell"]["authorized_repair_runtime_identity_sha256s"],
            )


if __name__ == "__main__":
    unittest.main()
