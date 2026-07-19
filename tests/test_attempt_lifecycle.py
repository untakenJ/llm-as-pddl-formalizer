from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.benchmark_profile import DEFAULT_BENCHMARK_PROFILE
from agent_formalizer.orchestrator import InfraInvalid, _run_attempt
from agent_formalizer.result_types import AgentResult, FormalizerResult


def adapter(max_tries: int = 3):
    resolved = DEFAULT_BENCHMARK_PROFILE.resolve(
        "hermes",
        model="openai/test-model",
        max_execution_tries=max_tries,
    )
    return SimpleNamespace(resolved_config=resolved)


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


class AttemptLifecycleTests(unittest.TestCase):
    def invoke(self, root: Path, fake, *, config=None):
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
            task_identity={"sha256": "task-hash", "raw": {}},
            runtime_lock={"status": "pass"},
            runtime_identity_sha256="runtime-hash",
        )

    def test_only_infra_invalid_execution_is_retried(self):
        calls = []

        def fake(*args, **kwargs):
            calls.append(kwargs["execution_try"])
            if len(calls) == 1:
                raise InfraInvalid("container_start_failed", "docker unavailable")
            return valid_result(generated=False), {"evidence": "minimal"}

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
            return_value=(valid_result(generated=False), {"evidence": "minimal"}),
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
                {"evidence": "minimal"},
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
                return_value=(valid_result(generated=False), {"evidence": "minimal"}),
            ):
                first = self.invoke(root, None)
            with patch(
                "agent_formalizer.orchestrator._run_execution_try",
                side_effect=AssertionError("must not execute"),
            ):
                resumed = self.invoke(root, None)

        self.assertEqual(resumed.completion_path, first.completion_path)
        self.assertTrue(resumed.attempt_valid)

    def test_exhausted_infra_tries_do_not_create_valid_attempt(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "agent_formalizer.orchestrator._run_execution_try",
            side_effect=InfraInvalid("gateway_start_failed", "gateway failed"),
        ) as run:
            result = self.invoke(Path(tmp), run, config=adapter(max_tries=2))

        self.assertEqual(run.call_count, 2)
        self.assertFalse(result.attempt_valid)
        self.assertEqual(result.status, "infra_invalid")
        self.assertIsNone(result.completion_path)


if __name__ == "__main__":
    unittest.main()
