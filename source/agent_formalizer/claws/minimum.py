"""Benchmark-owned fixed-reflection baseline adapter."""

from __future__ import annotations

import json
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from agent_formalizer.claws.common import EnvConfiguredAdapter, run_captured_agent
from agent_formalizer.result_types import AgentResult
from agent_formalizer.tools.solver import TOOL_ID as SOLVER_TOOL_ID


RUNTIME_HOST_PATH = Path(__file__).resolve().parents[1] / "minimum_agent_runtime.py"
SESSION_DIR_NAME = "minimum_agent_session"


class MinimumAgentAdapter(EnvConfiguredAdapter):
    """Run a deterministic orchestration loop with no model-selected tools.

    The adapter makes one initial chat-completion request followed by exactly
    ``reflection_count`` requests. Before each reflection it may make one
    harness-controlled solver call and append that observation as a user
    message. Every assistant reply contains reasoning plus complete domain and
    problem strings; only the final parsed reply becomes the official files.
    """

    name = "minimum"

    def __init__(
        self,
        model: str,
        timeout: int,
        max_action_steps: int = 200,
        *,
        model_api_keys: dict[str, str] | None = None,
        api_key: str | None = None,
        api_key_name: str | None = None,
        credential_metadata: dict | None = None,
        provider_options: dict | None = None,
        max_model_calls: int = 50,
        allow_network: bool = False,
        network_mode: str | None = None,
        skills_mode: str = "none",
        benchmark_profile=None,
        resolved_config=None,
    ):
        super().__init__(
            model,
            timeout,
            max_action_steps,
            model_api_keys=model_api_keys,
            api_key=api_key,
            api_key_name=api_key_name,
            credential_metadata=credential_metadata,
            provider_options=provider_options,
            max_model_calls=max_model_calls,
            allow_network=allow_network,
            network_mode=network_mode,
            skills_mode=skills_mode,
            benchmark_profile=benchmark_profile,
            resolved_config=resolved_config,
        )
        if resolved_config is None or resolved_config.minimum_agent is None:
            raise ValueError(
                "minimum adapter requires a resolved minimum_agent condition; "
                "use benchmark_profiles/native_safety_minimum_agent.json"
            )
        self.minimum_config = resolved_config.minimum_agent
        if self.minimum_config["execution_backend"] != "host":
            raise ValueError("minimum adapter requires execution_backend=host")
        # One adapter is shared by batch worker threads.  Service endpoints and
        # output roots are therefore bound per execution thread, never globally.
        self._host_execution = threading.local()

    def validate_runtime(self) -> None:
        super().validate_runtime()
        if not RUNTIME_HOST_PATH.is_file():
            raise RuntimeError(f"minimum-agent runtime missing: {RUNTIME_HOST_PATH}")
        if self.raw_provider == "anthropic":
            raise RuntimeError(
                "minimum adapter currently uses the OpenAI chat-completions wire "
                "protocol; direct Anthropic Messages transport is not implemented"
            )

    def runtime_tools(self) -> list[str]:
        if self.minimum_config["solver_feedback"]["enabled"]:
            return [SOLVER_TOOL_ID]
        return []

    def build_task_prompt(
        self, domain_description: str, problem_description: str
    ) -> str:
        prompt = self.minimum_config["prompt_template"]
        values = {
            "reflection_count": self.minimum_config["reflection_count"],
            "solver_feedback_enabled": str(
                bool(self.minimum_config["solver_feedback"]["enabled"])
            ).lower(),
        }
        before = prompt["before_task"].format(**values)
        after = prompt["after_task"].format(**values)
        return (
            before
            + "\n<domain_description>\n"
            + domain_description
            + "\n</domain_description>\n\n<problem_description>\n"
            + problem_description
            + "\n</problem_description>"
            + after
        )

    def configure_host_execution(
        self,
        *,
        api_base: str,
        solver_gateway: str | None,
        workspace_dir: Path,
    ) -> None:
        """Bind one host execution's private services to its worker thread."""
        self._host_execution.value = {
            "api_base": api_base,
            "solver_gateway": solver_gateway,
            "workspace_dir": Path(workspace_dir),
        }

    def clear_host_execution(self) -> None:
        self._host_execution.value = None

    def _runtime_config(self, prompt: str, artifact_dir: Path) -> dict:
        host = getattr(self._host_execution, "value", None)
        if not isinstance(host, dict):
            raise RuntimeError("minimum host execution services are not configured")
        contract = self.resolved_config.raw["resolved"]["artifact_contract"]
        workspace_dir = Path(host["workspace_dir"])
        session_dir = artifact_dir / SESSION_DIR_NAME
        return {
            "schema_version": 1,
            "api_base": host["api_base"],
            "model": self.openai_compatible_model,
            "initial_prompt": prompt,
            "reflection_count": self.minimum_config["reflection_count"],
            "reflection_prompt": self.minimum_config["prompt_template"]["reflection"],
            "solver_feedback": deepcopy(self.minimum_config["solver_feedback"]),
            "solver_gateway": host["solver_gateway"],
            "request_timeout_seconds": 600,
            "solver_timeout_seconds": 600,
            "output_root": str(workspace_dir),
            "domain_output_path": str(
                workspace_dir / contract["workspace_domain_file"]
            ),
            "problem_output_path": str(
                workspace_dir / contract["workspace_problem_file"]
            ),
            "transcript_path": str(session_dir / "transcript.json"),
        }

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        if artifact_dir is None:
            raise ValueError("minimum adapter requires an artifact directory")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / SESSION_DIR_NAME).mkdir(parents=True, exist_ok=True)
        config_path = artifact_dir / "minimum_agent_runtime_config.json"
        config_path.write_text(
            json.dumps(
                self._runtime_config(prompt, artifact_dir),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        fixed = self.resolved_config.raw["resolved"]["environment"]["fixed"]
        runtime_env = {name: value for name, value in fixed.items()}
        result = run_captured_agent(
            [
                sys.executable,
                str(RUNTIME_HOST_PATH),
                "--config",
                str(config_path),
            ],
            timeout=self.remaining_timeout(),
            stdout_path=artifact_dir / "minimum_agent.stdout.log",
            stderr_path=artifact_dir / "minimum_agent.stderr.log",
            attempt_clock=self.current_attempt_clock(),
            env=runtime_env,
        )

        transcript_path = artifact_dir / SESSION_DIR_NAME / "transcript.json"
        if transcript_path.is_file():
            try:
                transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                transcript = {}
            responses = [
                event.get("response_text")
                for event in transcript.get("events", [])
                if event.get("event") == "model_call"
                and isinstance(event.get("response_text"), str)
            ]
            if responses:
                result.final_text = responses[-1]
            result.session_file = str(transcript_path)
        elif result.success:
            result.success = False
            result.finish_reason = "error"
            result.exit_code = -1
            result.usage["session_collection_error"] = "minimum transcript unavailable"
        return result

    @staticmethod
    def _transcript(artifact_dir: Path) -> dict:
        path = artifact_dir / SESSION_DIR_NAME / "transcript.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def collect_usage(self, workspace, artifact_dir: Path) -> dict:
        transcript = self._transcript(artifact_dir)
        usage = transcript.get("usage")
        result = dict(usage) if isinstance(usage, dict) else {}
        normalized_usage = dict(result)
        result["minimumAgent"] = {
            "reflectionCountRequested": transcript.get(
                "reflection_count_requested", self.minimum_config["reflection_count"]
            ),
            "modelCallsCompleted": transcript.get("model_calls_completed", 0),
            "fixedSolverCalls": transcript.get("fixed_solver_calls_completed", 0),
            "finalSource": (
                transcript.get("official_delivery", {}).get("source")
                if isinstance(transcript.get("official_delivery"), dict)
                else None
            ),
        }
        # Keep the same self-contained usage artifact shape used by other
        # adapters.  Pricing remains a reporting concern; these disjoint token
        # buckets plus raw provider usage are sufficient for cost calculation.
        raw_calls = [
            event.get("usage")
            for event in transcript.get("events", [])
            if isinstance(event, dict)
            and event.get("event") == "model_call"
            and isinstance(event.get("usage"), dict)
        ]
        usage_report = {
            "schema_version": 1,
            "measurement": "provider",
            "source": "minimum-agent chat-completion response usage",
            "model": self.model,
            "raw_usage_by_call": raw_calls,
            "usage": normalized_usage,
        }
        usage_path = artifact_dir / SESSION_DIR_NAME / "usage.json"
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        usage_path.write_text(
            json.dumps(usage_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result

    def additional_action_metrics(self, artifact_dir: Path | None = None) -> dict:
        if artifact_dir is None:
            return {}
        transcript = self._transcript(artifact_dir)
        model_calls_completed = int(transcript.get("model_calls_completed", 0) or 0)
        return {
            "fixed_solver_calls": int(
                transcript.get("fixed_solver_calls_completed", 0) or 0
            ),
            "reflections_completed": max(0, model_calls_completed - 1),
            "fixed_solver_calls_are_tool_calls": False,
        }

    def iter_agent_steps(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        transcript = self._transcript(artifact_dir)
        index = 0
        for event in transcript.get("events", []):
            if not isinstance(event, dict):
                continue
            index += 1
            if event.get("event") == "model_call":
                parsed = event.get("parsed") if isinstance(event.get("parsed"), dict) else {}
                yield {
                    "index": index,
                    "kind": "model_call",
                    "phase": event.get("phase"),
                    "reflection_index": event.get("reflection_index"),
                    "logical_call_index": event.get("logical_call_index"),
                    "input": event.get("request_messages"),
                    "output": event.get("response_text"),
                    "parsed": event.get("parsed"),
                    "reasoning": parsed.get("reasoning"),
                    "usage": event.get("usage"),
                }
            elif event.get("event") == "fixed_solver_call":
                yield {
                    "index": index,
                    "kind": "fixed_solver_call",
                    "reflection_index": event.get("reflection_index"),
                    "solver": event.get("solver"),
                    "input": event.get("input"),
                    "output": event.get("response") or event.get("error"),
                    "ok": event.get("ok"),
                    "conversation_feedback": event.get("conversation_feedback"),
                }

    def iter_tool_calls(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        # The model has no tool schema and makes no structured tool calls.
        return []

    def tool_policy(self) -> dict:
        return {
            "model_selectable_tools": [],
            "workspace_visible_to_model": False,
            "fixed_solver_feedback": deepcopy(self.minimum_config["solver_feedback"]),
            "fixed_solver_calls_count_as_tool_calls": False,
        }

    def translation_ledger(self) -> dict:
        value = super().translation_ledger()
        value["native_clean_baseline"].update(
            {
                "policy": (
                    "benchmark-owned fixed-loop baseline; no external native "
                    "harness defaults, tools, skills, memory, or workspace access"
                ),
                "tool_and_skill_evidence": "empty manifests by construction",
            }
        )
        rules = value["benchmark_envelope_rules"]
        rules["interaction"]["implementation"] = (
            "benchmark-owned noninteractive fixed chat-completion loop"
        )
        rules["state_isolation"]["implementation"] = (
            "benchmark-owned host process with per-attempt output directory, loopback-only "
            "fixed-route gateway, and immutable conversation transcript"
        )
        rules["network"]["implementation"] = (
            "benchmark-owned runtime has no tool or arbitrary-I/O surface and sends model "
            "requests only to a per-attempt loopback fixed-route gateway"
        )
        rules["canonical_prompt"]["implementation"] = (
            "condition-owned minimum-agent before/task/after template; exact rendered "
            "message is hashed and recorded"
        )
        rules["artifact_contract"]["implementation"] = (
            "runtime parses the last assistant JSON response and writes its two PDDL "
            "strings to the configured official workspace files; no orchestrator "
            "final-message recovery"
        )
        rules["agent_tools"] = {
            "resolved_value": [],
            "implementation": (
                "no model-selectable tools; optional solver feedback is one fixed "
                "harness call before each reflection"
            ),
            "evidence": (
                "request payloads contain no tool schemas; transcript records "
                "fixed_solver_call events separately"
            ),
        }
        value["minimum_agent"] = {
            "resolved_value": deepcopy(self.minimum_config),
            "implementation": (
                "initial generation followed by exactly n reflection requests; every "
                "assistant response remains in subsequent context; only the last parsed "
                "response is delivered"
            ),
            "evidence": "minimum_agent_session/transcript.json",
        }
        return value

    def runtime_info(self) -> dict:
        return {
            **super().runtime_info(),
            "runtime_entrypoint": str(RUNTIME_HOST_PATH),
            "execution_backend": "host",
            "python_executable": sys.executable,
            "wire_protocol": "openai_chat_completions",
            "external_harness_distribution": None,
        }

    def skills_info(self) -> dict:
        return {"mode": "none", "manifest": []}
