from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.configuration.benchmark_profile import (
    DEFAULT_BENCHMARK_PROFILE,
    load_benchmark_profile,
)
from agent_formalizer.claws import get_adapter
from agent_formalizer.claws.minimum.runtime import execute, parse_response
from agent_formalizer.claws.minimum.workspace import MinimumHostWorkspace
from agent_formalizer.orchestrator import (
    _freeze_execution_reference,
    run_one_problem,
)
from agent_formalizer.runtime.runtime_lock import validate_runtime_lock


MINIMUM_PROFILE_PATH = (
    HISTORICAL_PROFILES_DIR / "native_safety_minimum_agent.json"
)
DOMAIN = "(define (domain mock) (:requirements :strips) (:predicates (ready)))"
PROBLEM = "(define (problem p01) (:domain mock) (:init (ready)) (:goal (ready)))"


def structured_response(version: int) -> str:
    return json.dumps(
        {
            "reasoning": f"reasoning version {version}",
            "domain_file": DOMAIN + f" ; version {version}",
            "problem_file": PROBLEM + f" ; version {version}",
        }
    )


class MinimumProfileTests(unittest.TestCase):
    def test_profile_resolves_only_for_minimum_adapter(self):
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        resolved = profile.resolve("minimum")
        self.assertEqual(resolved.minimum_agent["execution_backend"], "host")
        self.assertEqual(resolved.minimum_agent["reflection_count"], 1)
        self.assertFalse(resolved.minimum_agent["solver_feedback"]["enabled"])
        self.assertEqual(resolved.agent_tools, [])
        self.assertEqual(resolved.skills_mode, "none")
        with self.assertRaisesRegex(ValueError, "only supported by the minimum"):
            profile.resolve("openclaw")
        with self.assertRaisesRegex(ValueError, "requires condition_profile"):
            DEFAULT_BENCHMARK_PROFILE.resolve("minimum")

    def test_adapter_has_no_model_tools_and_renders_profile_prompt(self):
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        adapter = get_adapter(
            "minimum",
            model="openai/test-model",
            api_key="secret",
            benchmark_profile=profile,
        )
        prompt = adapter.build_task_prompt("domain words", "problem words")
        self.assertIn("domain words", prompt)
        self.assertIn("problem words", prompt)
        self.assertIn("exactly 1 reflection", prompt)
        self.assertNotIn("/workspace", prompt)
        self.assertEqual(adapter.agent_tools(), [])
        self.assertEqual(adapter.runtime_tools(), [])
        self.assertEqual(adapter.tool_policy()["model_selectable_tools"], [])
        self.assertNotIn("secret", json.dumps(adapter.effective_config()))
        self.assertEqual(validate_runtime_lock(adapter)["status"], "pass")

    def test_solver_feedback_is_a_fixed_runtime_service_not_an_agent_tool(self):
        raw = json.loads(MINIMUM_PROFILE_PATH.read_text())
        raw["condition_profile"]["id"] = "minimum-agent-r1-solver"
        raw["condition_profile"]["overrides"]["minimum_agent"][
            "solver_feedback"
        ]["enabled"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(raw))
            profile = load_benchmark_profile(path)
            adapter = get_adapter(
                "minimum",
                model="openai/test-model",
                api_key="secret",
                benchmark_profile=profile,
            )
        self.assertEqual(adapter.agent_tools(), [])
        self.assertEqual(adapter.runtime_tools(), ["pddl_solver"])
        self.assertFalse(
            adapter.tool_policy()["fixed_solver_calls_count_as_tool_calls"]
        )

    def test_reflection_count_must_fit_model_budget(self):
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        with self.assertRaisesRegex(ValueError, r"reflection_count \+ 1 model calls"):
            profile.resolve("minimum", max_model_calls=1)

    def test_unknown_prompt_placeholder_is_rejected(self):
        raw = json.loads(MINIMUM_PROFILE_PATH.read_text())
        raw["condition_profile"]["overrides"]["minimum_agent"][
            "prompt_template"
        ]["reflection"] += " {unknown}"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError, "unsupported placeholder"):
                load_benchmark_profile(path)

    def test_minimum_does_not_resolve_or_freeze_a_docker_image(self):
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        adapter = get_adapter(
            "minimum",
            model="openai/test-model",
            api_key="secret",
            benchmark_profile=profile,
        )
        with patch(
            "agent_formalizer.orchestrator._freeze_image_reference",
            side_effect=AssertionError("minimum must not inspect Docker"),
        ):
            self.assertEqual(_freeze_execution_reference(adapter, None), (None, None))

    def test_native_adapter_still_uses_unchanged_docker_freeze_path(self):
        adapter = get_adapter(
            "hermes",
            model="deepseek/deepseek-v4-flash",
            api_key="secret",
            benchmark_profile=DEFAULT_BENCHMARK_PROFILE,
        )
        with patch(
            "agent_formalizer.orchestrator._freeze_image_reference",
            return_value=("pddl-agent-base:latest", "sha256:test"),
        ) as freeze:
            self.assertEqual(
                _freeze_execution_reference(adapter, None),
                ("pddl-agent-base:latest", "sha256:test"),
            )
        freeze.assert_called_once_with(None)

    def test_minimum_rejects_controlled_web_override(self):
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        with self.assertRaisesRegex(ValueError, "only model_only"):
            profile.resolve("minimum", network_mode="controlled_web")


class MinimumRuntimeTests(unittest.TestCase):
    def test_self_hosted_different_reflection_counts_and_solver_feedback(self):
        for n in (0, 1, 10):
            for enabled in (False, True):
                with self.subTest(n=n, solver=enabled), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    raw = json.loads(MINIMUM_PROFILE_PATH.read_text())
                    minimum = raw["condition_profile"]["overrides"]["minimum_agent"]
                    minimum["reflection_count"] = n
                    minimum["solver_feedback"]["enabled"] = enabled
                    path = root / "profile.json"; path.write_text(json.dumps(raw))
                    adapter = get_adapter("minimum", model="self-hosted/example/bf16", api_key="test-key",
                        benchmark_profile=load_benchmark_profile(path),
                        credential_provider_options={"self_hosted": {"base_url": "http://localhost:8000/v1"}})
                    self.assertEqual(adapter.upstream_api_base(), "http://localhost:8000/v1")
                    self.assertEqual(adapter.agent_tools(), [])
                    self.assertEqual(adapter.resolved_config.minimum_agent["reflection_count"], n)
                    config = {"api_base": "http://localhost:8000/v1", "model": "example/bf16",
                              "initial_prompt": adapter.build_task_prompt("domain", "problem"),
                              "reflection_count": n, "reflection_prompt": minimum["prompt_template"]["reflection"],
                              "solver_feedback": minimum["solver_feedback"], "solver_gateway": "http://localhost:8768",
                              "domain_output_path": str(root / "domain.pddl"),
                              "problem_output_path": str(root / "problem.pddl"),
                              "transcript_path": str(root / "transcript.json")}
                    calls = []
                    def chat(_config, messages):
                        calls.append(copy.deepcopy(messages))
                        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                        return structured_response(len(calls)), usage, {
                            "choices": [{"message": {"reasoning_content": "provider thinking"}}], "usage": usage}
                    with patch("agent_formalizer.claws.minimum.runtime._validate_output_path", side_effect=Path), \
                         patch("agent_formalizer.claws.minimum.runtime._chat_completion", side_effect=chat), \
                         patch("agent_formalizer.claws.minimum.runtime._solver_feedback",
                               return_value=("<solver_feedback>test plan</solver_feedback>", {"event": "fixed_solver_call"})) as solver:
                        transcript = execute(config)
                    self.assertEqual(len(calls), n + 1)
                    self.assertEqual(solver.call_count, n if enabled else 0)
                    self.assertEqual(transcript["model_calls_completed"], n + 1)
                    self.assertIn(f"version {n + 1}", (root / "domain.pddl").read_text())
                    self.assertIn("provider thinking", (root / "transcript.json").read_text())
                    if n and enabled:
                        self.assertIn("test plan", calls[-1][-1]["content"])

    def test_parser_enforces_exact_contract(self):
        parsed = parse_response("prefix\n" + structured_response(1) + "\nsuffix")
        self.assertIn("version 1", parsed["reasoning"])
        with self.assertRaisesRegex(ValueError, "expected"):
            parse_response(
                json.dumps(
                    {
                        "reasoning": "x",
                        "domain_file": DOMAIN,
                        "problem_file": PROBLEM,
                        "extra": "not allowed",
                    }
                )
            )
        with self.assertRaisesRegex(ValueError, "non-empty"):
            parse_response(
                json.dumps(
                    {
                        "reasoning": "",
                        "domain_file": DOMAIN,
                        "problem_file": PROBLEM,
                    }
                )
            )

    def test_fixed_sequence_keeps_reasoning_and_solver_feedback_in_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "api_base": "http://unused.invalid/v1",
                "model": "test-model",
                "initial_prompt": "initial task",
                "reflection_count": 2,
                "reflection_prompt": (
                    "Reflection {reflection_index} of {reflection_count}; "
                    "solver={solver_feedback_enabled}."
                ),
                "solver_feedback": {
                    "enabled": True,
                    "solver": "dual-bfws-ffparser",
                    "max_chars": 16000,
                },
                "solver_gateway": "http://unused.invalid:8768",
                "domain_output_path": str(root / "domain.pddl"),
                "problem_output_path": str(root / "problem.pddl"),
                "transcript_path": str(root / "transcript.json"),
            }
            requests: list[list[dict[str, str]]] = []

            def fake_chat(_config, messages):
                requests.append(copy.deepcopy(messages))
                version = len(requests)
                content = structured_response(version)
                usage = {
                    "prompt_tokens": 10 * version,
                    "completion_tokens": 5,
                    "total_tokens": 10 * version + 5,
                    "prompt_tokens_details": {"cached_tokens": version},
                    "completion_tokens_details": {"reasoning_tokens": 2},
                }
                return content, usage, {"choices": [], "usage": usage}

            def fake_solver(_config, parsed, reflection_index):
                feedback = f"<solver_feedback>plan for {reflection_index}</solver_feedback>"
                return feedback, {
                    "event": "fixed_solver_call",
                    "reflection_index": reflection_index,
                    "solver": "dual-bfws-ffparser",
                    "ok": True,
                    "input": copy.deepcopy(parsed),
                    "response": {"plan": f"plan {reflection_index}"},
                    "conversation_feedback": feedback,
                }

            with (
                patch(
                    "agent_formalizer.claws.minimum.runtime._validate_output_path",
                    side_effect=lambda value: Path(value),
                ),
                patch(
                    "agent_formalizer.claws.minimum.runtime._chat_completion",
                    side_effect=fake_chat,
                ),
                patch(
                    "agent_formalizer.claws.minimum.runtime._solver_feedback",
                    side_effect=fake_solver,
                ),
            ):
                transcript = execute(config)

            self.assertEqual(len(requests), 3)
            self.assertEqual(transcript["model_calls_completed"], 3)
            self.assertEqual(transcript["fixed_solver_calls_completed"], 2)
            self.assertIn("reasoning version 1", requests[1][1]["content"])
            self.assertIn("plan for 1", requests[1][-1]["content"])
            self.assertLess(
                requests[1][-1]["content"].index("plan for 1"),
                requests[1][-1]["content"].index("Reflection 1 of 2"),
            )
            self.assertIn("reasoning version 2", requests[2][-2]["content"])
            self.assertIn("plan for 2", requests[2][-1]["content"])
            self.assertTrue((root / "domain.pddl").read_text().endswith("version 3"))
            self.assertTrue((root / "problem.pddl").read_text().endswith("version 3"))
            self.assertEqual(
                transcript["official_delivery"]["source"],
                "last_parsed_model_response",
            )
            self.assertEqual(transcript["usage"]["input"], (10 - 1) + (20 - 2) + (30 - 3))
            self.assertEqual(transcript["usage"]["cacheRead"], 6)
            self.assertEqual(transcript["usage"]["output"], 15)
            self.assertEqual(transcript["usage"]["reasoningTokens"], 6)

    def test_final_parse_failure_writes_no_official_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "api_base": "http://unused.invalid/v1",
                "model": "test-model",
                "initial_prompt": "initial task",
                "reflection_count": 1,
                "reflection_prompt": "Reflection {reflection_index} of {reflection_count}",
                "solver_feedback": {
                    "enabled": False,
                    "solver": "dual-bfws-ffparser",
                    "max_chars": 16000,
                },
                "solver_gateway": "http://unused.invalid:8768",
                "domain_output_path": str(root / "domain.pddl"),
                "problem_output_path": str(root / "problem.pddl"),
                "transcript_path": str(root / "transcript.json"),
            }
            responses = iter(
                [
                    structured_response(1),
                    "the final reflection did not follow the contract",
                ]
            )

            def fake_chat(_config, _messages):
                content = next(responses)
                return content, {}, {"choices": []}

            with (
                patch(
                    "agent_formalizer.claws.minimum.runtime._validate_output_path",
                    side_effect=lambda value: Path(value),
                ),
                patch(
                    "agent_formalizer.claws.minimum.runtime._chat_completion",
                    side_effect=fake_chat,
                ),
                self.assertRaisesRegex(ValueError, "no JSON object"),
            ):
                execute(config)
            self.assertFalse((root / "domain.pddl").exists())
            self.assertFalse((root / "problem.pddl").exists())
            transcript = json.loads((root / "transcript.json").read_text())
            self.assertEqual(transcript["status"], "failed")
            calls = [row for row in transcript['events'] if row.get('event') == 'model_call']
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1]['response_text'], 'the final reflection did not follow the contract')


class _FakeCompletionHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.requests.append(payload)
        if getattr(self.server, "stall", False):
            self.server.release_stall.wait(10)
            return
        if getattr(self.server, "failures_remaining", 0):
            self.server.failures_remaining -= 1
            body = b'{"error":{"type":"rate_limit_error"}}'
            self.send_response(429)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        type(self).calls += 1
        version = type(self).calls
        body = json.dumps(
            {
                "id": f"fake-{version}",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": structured_response(version),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100 * version,
                    "completion_tokens": 20,
                    "total_tokens": 100 * version + 20,
                    "prompt_tokens_details": {"cached_tokens": 10 * version},
                    "completion_tokens_details": {"reasoning_tokens": 3},
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class MinimumHostWorkspaceTests(unittest.TestCase):
    def test_host_workspace_finalizes_gateway_after_runtime_exit(self):
        process = Mock()
        process.poll.return_value = None
        workspace = MinimumHostWorkspace.__new__(MinimumHostWorkspace)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace._gateway_process = process
            workspace._gateway_native_exit_path = root / "control/native-harness-exited"
            workspace._gateway_native_exit_path.parent.mkdir()
            workspace.model_gateway_origin = "http://127.0.0.1:12345"
            workspace.artifact_dir = root / "execution"
            acknowledgement = {
                "status": "native_harness_exited",
                "active_requests": 1,
            }
            with patch(
                "agent_formalizer.claws.minimum.workspace._post_empty_json",
                return_value=acknowledgement,
            ), patch.object(
                workspace,
                "_read_control",
                side_effect=[
                    {"in_flight_requests": 1},
                    {"in_flight_requests": 0},
                ],
            ), patch("agent_formalizer.claws.minimum.workspace.time.sleep"):
                report = workspace.finalize_model_gateway_after_native_exit(
                    wait_seconds=0.1
                )

            self.assertEqual(report["status"], "settled")
            self.assertTrue(workspace._gateway_native_exit_path.is_file())
            saved = json.loads(
                (workspace.artifact_dir / "gateway/native_exit_finalization.json")
                .read_text()
            )
            self.assertEqual(saved["final_control"]["in_flight_requests"], 0)

    def test_host_runtime_preserves_usage_transcript_and_reasoning_trace(self):
        self._assert_host_runtime("openai/test-model")

    def test_self_hosted_runtime_through_real_loopback_gateway(self):
        self._assert_host_runtime("self-hosted/test-model")

    def test_owned_loopback_client_survives_gateway_transparent_retry(self):
        self._assert_host_runtime("self-hosted/test-model", retry=True)

    def test_blocked_owned_request_is_still_bounded_by_active_watchdog(self):
        self._assert_host_runtime("self-hosted/test-model", stall=True)

    def _assert_host_runtime(self, model, retry=False, stall=False):
        _FakeCompletionHandler.calls = 0
        try:
            upstream = ThreadingHTTPServer(
                ("127.0.0.1", 0), _FakeCompletionHandler
            )
        except PermissionError:
            self.skipTest("sandbox does not allow loopback sockets")
        upstream.requests = []
        upstream.failures_remaining = int(retry)
        upstream.stall = stall
        upstream.release_stall = threading.Event()
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        adapter = get_adapter(
            "minimum",
            model=model,
            api_key="secret",
            benchmark_profile=profile,
            **({"timeout": 2} if stall else {}),
            credential_provider_options={"self_hosted": {"base_url": f"http://127.0.0.1:{upstream.server_port}/v1"}}
            if model.startswith("self-hosted/") else None,
        )
        direct_base = f"http://127.0.0.1:{upstream.server_port}/v1"
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(
                type(adapter), "direct_api_base", new_callable=PropertyMock
            ) as direct:
                direct.return_value = direct_base
                artifact_dir = Path(tmp) / "execution-001"
                workspace = MinimumHostWorkspace(
                    "test-instance",
                    "logical-runtime-name",
                    adapter,
                    artifact_dir=artifact_dir,
                )
                try:
                    workspace.start()
                    self.assertEqual(workspace.validate_network_policy()["status"], "pass")
                    self.assertEqual(
                        workspace.validate_environment_policy()["status"], "pass"
                    )
                    self.assertEqual(
                        workspace.validate_action_step_guard()["status"], "pass"
                    )
                    self.assertEqual(
                        workspace.validate_state_isolation()["status"], "pass"
                    )
                    clock = adapter.begin_attempt_clock()
                    workspace.start_model_gateway_monitor(clock)
                    result = adapter.send_task(
                        "host task",
                        agent_id="unused",
                        container_name="unused",
                        artifact_dir=artifact_dir,
                    )
                    workspace.stop_model_gateway_monitor()
                    adapter.end_attempt_clock()
                    if stall:
                        self.assertFalse(result.success)
                        self.assertTrue(result.timeout)
                        self.assertEqual(result.finish_reason, "timeout")
                        self.assertEqual(len(upstream.requests), 1)
                        self.assertLess(result.duration_seconds, 8)
                        return
                    self.assertTrue(result.success)
                    runtime_config = json.loads((artifact_dir / "minimum_agent_runtime_config.json").read_text())
                    self.assertIsNone(runtime_config["request_timeout_seconds"])
                    self.assertIsNone(runtime_config["solver_timeout_seconds"])
                    outputs = workspace.freeze_pddl_outputs()
                    self.assertTrue(outputs["domain"].endswith(b"version 2"))
                    self.assertTrue(outputs["problem"].endswith(b"version 2"))
                    usage = adapter.collect_usage(workspace, artifact_dir)
                    self.assertEqual(usage["input"], (100 - 10) + (200 - 20))
                    self.assertEqual(usage["cacheRead"], 30)
                    self.assertEqual(usage["output"], 40)
                    self.assertEqual(usage["reasoningTokens"], 6)
                    self.assertEqual(usage["minimumAgent"]["modelCallsCompleted"], 2)
                    usage_report = json.loads(
                        (
                            artifact_dir
                            / "minimum_agent_session"
                            / "usage.json"
                        ).read_text()
                    )
                    self.assertEqual(usage_report["measurement"], "provider")
                    self.assertEqual(len(usage_report["raw_usage_by_call"]), 2)
                    steps = list(adapter.iter_agent_steps("unused", artifact_dir))
                    model_steps = [row for row in steps if row["kind"] == "model_call"]
                    self.assertEqual(
                        [row["reasoning"] for row in model_steps],
                        ["reasoning version 1", "reasoning version 2"],
                    )
                    self.assertEqual(workspace.model_gateway_stats()["model_calls"], 2)
                    self.assertEqual(len(workspace.model_gateway_ledger()), 2)
                    self.assertEqual(len(upstream.requests), 3 if retry else 2)
                    if retry:
                        self.assertEqual(upstream.requests[0], upstream.requests[1])
                        self.assertEqual(workspace.model_gateway_ledger()[0]["transient_retry_count"], 1)
                    self.assertNotIn("tools", upstream.requests[0])
                finally:
                    workspace.cleanup()
        finally:
            upstream.release_stall.set()
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=5)

    def test_orchestrator_host_path_writes_standard_evidence_without_docker(self):
        _FakeCompletionHandler.calls = 0
        try:
            upstream = ThreadingHTTPServer(
                ("127.0.0.1", 0), _FakeCompletionHandler
            )
        except PermissionError:
            self.skipTest("sandbox does not allow loopback sockets")
        upstream.requests = []
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        profile = load_benchmark_profile(MINIMUM_PROFILE_PATH)
        adapter = get_adapter(
            "minimum",
            model="openai/test-model",
            api_key="secret",
            benchmark_profile=profile,
        )
        direct_base = f"http://127.0.0.1:{upstream.server_port}/v1"
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.object(
                type(adapter), "direct_api_base", new_callable=PropertyMock
            ) as direct, patch(
                "agent_formalizer.orchestrator._freeze_image_reference",
                side_effect=AssertionError("minimum must not inspect Docker"),
            ):
                direct.return_value = direct_base
                result = run_one_problem(
                    adapter,
                    "barman",
                    "Heavily_Templated_Barman-100",
                    "p01",
                    model_label="minimum-host-e2e",
                    out_dir_root=Path(tmp),
                )
                self.assertTrue(result.attempt_valid)
                self.assertTrue(result.generation_success)
                completion = json.loads(result.completion_path.read_text())
                self.assertEqual(completion["evidence"]["actions"]["model_calls"], 2)
                self.assertEqual(completion["agent"]["usage"]["output"], 40)
                self.assertFalse(
                    completion["evidence"]["provenance"]["container_image"][
                        "required"
                    ]
                )
                self.assertFalse(
                    completion["evidence"]["provenance"]["host_runtime"][
                        "docker_required"
                    ]
                )
                execution_dir = result.completion_path.parent / "executions" / "execution-001"
                steps_path = next(execution_dir.glob("*_agent_steps.jsonl"))
                steps = [json.loads(line) for line in steps_path.read_text().splitlines()]
                model_steps = [row for row in steps if row["kind"] == "model_call"]
                self.assertEqual(len(model_steps), 2)
                self.assertEqual(model_steps[1]["reasoning"], "reasoning version 2")
                usage_report = json.loads(
                    (
                        execution_dir
                        / "minimum_agent_session"
                        / "usage.json"
                    ).read_text()
                )
                self.assertEqual(usage_report["usage"]["total"], 340)
        finally:
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
