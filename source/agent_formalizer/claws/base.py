"""Base interface every claw (agent harness) adapter implements.

Ported from ``claw-swe-bench`` (``claw_swebench/claws/base.py``). The
orchestrator and workspace are claw-agnostic; everything specific to a claw
(how its runtime gets into the container, how a task is launched, how
sessions/usage/tool-traces are collected) lives behind this interface.

Hook call order for one problem (see orchestrator.run_one_problem):

    create_agent(agent_id)                  # optional isolation setup
    container_run_args(instance_id)         # extra `docker run` args (mounts, env)
    post_container_start(workspace)         # provision config inside container
    send_task(prompt, ...)                  # run the agent, return AgentResult
    collect_usage(workspace, artifact_dir)  # claw-specific usage, container alive
    iter_tool_calls(agent_id, artifact_dir) # yield normalized tool-call records
    iter_agent_steps(agent_id, artifact_dir) # yield per-step agent loop records
    backup_session(agent_id, artifact_dir)  # save raw session logs
    workspace.cleanup()                     # unmount runtime/state paths
    delete_agent(agent_id)                  # teardown (always called)
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable

from agent_formalizer.result_types import AgentResult

logger = logging.getLogger(__name__)


class AttemptClock:
    """Thread-safe active-time clock that can exclude infrastructure pauses."""

    def __init__(self, limit_seconds: float):
        self.limit_seconds = float(limit_seconds)
        self.started_monotonic = time.monotonic()
        self._deadline = self.started_monotonic + self.limit_seconds
        self._lock = threading.RLock()
        self._pause_depth = 0
        self._pause_started: float | None = None
        self._paused_seconds = 0.0

    def pause(self, *, retroactive_seconds: float = 0.0) -> None:
        """Freeze active time, optionally crediting monitor-observation delay."""
        with self._lock:
            if self._pause_depth == 0:
                credit = max(0.0, float(retroactive_seconds))
                self._deadline += credit
                self._paused_seconds += credit
                self._pause_started = time.monotonic()
            self._pause_depth += 1

    def resume(self) -> None:
        with self._lock:
            if self._pause_depth <= 0:
                return
            self._pause_depth -= 1
            if self._pause_depth == 0 and self._pause_started is not None:
                duration = time.monotonic() - self._pause_started
                self._deadline += duration
                self._paused_seconds += duration
                self._pause_started = None

    def remaining(self) -> float:
        with self._lock:
            reference = (
                self._pause_started
                if self._pause_depth > 0 and self._pause_started is not None
                else time.monotonic()
            )
            return max(0.0, self._deadline - reference)

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            live_pause = (
                now - self._pause_started
                if self._pause_depth > 0 and self._pause_started is not None
                else 0.0
            )
            paused = self._paused_seconds + live_pause
            wall = now - self.started_monotonic
            return {
                "limit_seconds": self.limit_seconds,
                "wall_duration_seconds": round(wall, 6),
                "infra_pause_seconds": round(paused, 6),
                "active_duration_seconds": round(max(0.0, wall - paused), 6),
                "paused": self._pause_depth > 0,
                "deadline_exceeded": self.remaining() <= 0.0,
            }


def run_process_with_attempt_clock(
    cmd: list[str],
    *,
    clock: AttemptClock,
    capture_output: bool = True,
    text: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a process against active time rather than a fixed wall timeout."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        env=env,
    )
    while True:
        remaining = clock.remaining()
        if remaining <= 0:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(
                cmd,
                clock.limit_seconds,
                output=stdout,
                stderr=stderr,
            )
        try:
            stdout, stderr = proc.communicate(timeout=min(0.25, remaining))
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


class BaseClawAdapter:
    """Common no-op implementations; adapters override what they need."""

    #: Short claw identifier; used for container naming and logs.
    name = "base"

    def __init__(
        self,
        model: str,
        timeout: int,
        max_action_steps: int = 200,
        *,
        max_model_calls: int = 50,
        allow_network: bool = False,
        network_mode: str | None = None,
        skills_mode: str = "official",
        benchmark_profile=None,
        resolved_config=None,
    ):
        self.model = model
        self.timeout = timeout
        self.max_action_steps = max_action_steps
        self.max_model_calls = max_model_calls
        if timeout <= 0 or max_model_calls <= 0 or max_action_steps <= 0:
            raise ValueError(
                "timeout, max_model_calls, and max_action_steps must be positive"
            )
        if max_model_calls > max_action_steps:
            raise ValueError("max_model_calls cannot exceed max_action_steps")
        self.network_mode = network_mode or (
            "controlled_web" if allow_network else "model_only"
        )
        if self.network_mode not in {"model_only", "controlled_web"}:
            raise ValueError(f"Unsupported network mode: {self.network_mode}")
        self.allow_network = self.network_mode == "controlled_web"
        self.skills_mode = skills_mode
        self.benchmark_profile = benchmark_profile
        self.resolved_config = resolved_config
        self._attempt_clock = threading.local()

    def agent_tools(self) -> list[str]:
        if self.resolved_config is None:
            return []
        return list(self.resolved_config.agent_tools)

    def runtime_tools(self) -> list[str]:
        """Benchmark sidecars/CLIs needed by the harness execution.

        Ordinary harnesses expose exactly the configured model-selectable
        agent tools. A fixed-loop adapter may override this to use a
        benchmark-controlled service without presenting it as a model tool.
        """
        return self.agent_tools()

    def pddl_solver_tool_enabled(self) -> bool:
        from agent_formalizer.tools.solver import TOOL_ID

        return TOOL_ID in self.agent_tools()

    def begin_attempt_clock(self) -> AttemptClock:
        """Start the envelope deadline after infrastructure setup."""
        clock = AttemptClock(self.timeout)
        self._attempt_clock.clock = clock
        return clock

    def current_attempt_clock(self) -> AttemptClock | None:
        return getattr(self._attempt_clock, "clock", None)

    def remaining_timeout(self) -> float:
        clock = self.current_attempt_clock()
        if clock is None:
            return self.timeout
        return max(0.001, clock.remaining())

    def deadline_exceeded(self) -> bool:
        clock = self.current_attempt_clock()
        return clock is not None and clock.expired()

    def end_attempt_clock(self) -> None:
        self._attempt_clock.clock = None

    # ------------------------------------------------------------------
    # Container integration
    # ------------------------------------------------------------------

    def validate_runtime(self) -> None:
        """Fail early when the harness runtime or credentials are unavailable."""
        return None

    def container_run_args(self, instance_id: str) -> list[str]:
        """Extra arguments for ``docker run`` (bind mounts, env vars)."""
        return []

    def post_container_start(self, workspace) -> None:
        """Provision the running container (e.g. copy a config file in)."""
        pass

    # ------------------------------------------------------------------
    # Agent lifecycle (no-ops for stateless claws)
    # ------------------------------------------------------------------

    def create_agent(self, agent_id: str) -> None:
        pass

    def delete_agent(self, agent_id: str) -> None:
        pass

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> None:
        pass

    def switch_model(self, model_name: str) -> None:
        self.model = model_name
        logger.info("Model set to %s", model_name)

    # ------------------------------------------------------------------
    # Task execution & accounting
    # ------------------------------------------------------------------

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        """Run the agent on ``prompt`` inside ``container_name``."""
        raise NotImplementedError

    def collect_usage(self, workspace, artifact_dir: Path) -> dict:
        """Collect claw-specific usage/artifacts while the container is alive.

        The returned dict is stored as metadata.json's top-level "usage" key.
        """
        return {}

    def iter_tool_calls(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        """Yield normalized tool-call records for trace recording.

        Each record is a plain dict; recommended keys: ``name``,
        ``arguments``, ``result``, ``ok``, ``index``. Default is no records
        (claws that do not expose tool transcripts simply override nothing).
        """
        return []

    def iter_agent_steps(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        """Yield per-step agent loop records (user/assistant/tool I/O)."""
        return []

    def additional_action_metrics(self, artifact_dir: Path | None = None) -> dict:
        """Adapter-specific counters that do not redefine public action steps."""
        return {}

    def build_task_prompt(
        self, domain_description: str, problem_description: str
    ) -> str:
        """Render the exact task message transported to this harness."""
        from agent_formalizer.prompt import build_prompt

        contract = self.resolved_config.raw["resolved"]["artifact_contract"]
        return build_prompt(
            domain_description,
            problem_description,
            template_path=None,
            domain_output_name=contract["workspace_domain_file"],
            problem_output_name=contract["workspace_problem_file"],
            agent_tools=self.resolved_config.agent_tools,
        )

    def prompt_template(self) -> Path | None:
        """Prompt template override; None means prompts/default.txt."""
        return None

    def task_transport_payload(self, prompt: str) -> bytes:
        """Exact task payload handed to the native harness transport."""
        return prompt.encode("utf-8")

    def tool_policy(self) -> dict:
        """Harness-specific tool policy for trace/metadata (override in adapters)."""
        return {}

    def model_auth(self) -> dict:
        """Model/API-key resolution summary for trace/metadata (no secret values).

        Adapters should report which environment variable supplies the active
        model's API key and whether it is present, so runs are reproducible and
        debuggable without leaking the key itself.
        """
        return {"model": self.model}

    def upstream_api_base(self) -> str:
        """Actual provider URL used by the model-gateway sidecar."""
        raise NotImplementedError

    def model_gateway(self) -> dict:
        """Non-secret gateway configuration used by AgentWorkspace."""
        from urllib.parse import urlsplit

        origin = urlsplit(self.upstream_api_base())
        value = {
            "upstream_origin": f"{origin.scheme}://{origin.netloc}",
            "max_model_calls": self.max_model_calls,
            "max_action_steps": self.max_action_steps,
            "auth_mode": "bearer",
            "allowed_models": [self.model.split("/", 1)[-1]],
            "allowed_path_prefixes": [origin.path.rstrip("/") or "/v1"],
        }
        if self.resolved_config is not None:
            value["transient_error_policy"] = (
                self.resolved_config.model_error_routing
            )
            value["request_overrides"] = (
                self.resolved_config.generation_overrides
            )
        else:
            value["transient_error_policy"] = {
                "id": "external-transient-v2",
                "max_retries": 5,
                "backoff_seconds": [1, 2, 4, 8, 16],
                "max_retry_after_seconds": 60,
                "retryable_http_statuses": [
                    408, 429, 502, 503, 504, 520, 521, 522, 523, 524, 525, 529
                ],
            }
            value["request_overrides"] = {}
        return value

    def model_gateway_secret(self) -> str | None:
        """Optional gateway-only credential; never written to metadata."""
        return None

    def network_policy(self) -> dict:
        return {
            "mode": self.network_mode,
            "controlled_web_allowlist": (
                self.resolved_config.controlled_web_allowlist
                if self.resolved_config is not None
                else []
            ),
            "model_gateway": True,
        }

    def translation_ledger(self) -> dict:
        """Map benchmark-owned rules without treating native differences as errors."""
        interaction_surfaces = {
            "openclaw": "local CLI agent run has no interactive approval channel",
            "hermes": "hermes chat --yolo --quiet",
            "nanobot": "one-shot CLI agent with channels={} and no user-input channel",
            "zeroclaw": "benchmark risk profile disables approval prompts and auto-approves native tools",
            "generic": "official --no-user-tools flag removes ask_user and long-term-update tools",
        }
        state_surfaces = {
            "openclaw": "per-run state plus per-attempt agent workspace/session/memory",
            "hermes": "per-attempt HERMES_HOME and SQLite/session state",
            "nanobot": "throwaway container workspace, config, session, and memory",
            "zeroclaw": "throwaway container config directory, workspace, and state",
            "generic": "per-attempt temp/config and clean-copied memory mounts",
        }
        native_clean = (
            self.resolved_config.raw["native_clean"]
            if self.resolved_config is not None
            else None
        )
        return {
            "config_name": (
                self.resolved_config.label if self.resolved_config is not None else None
            ),
            "resolved_config_sha256": (
                self.resolved_config.sha256 if self.resolved_config is not None else None
            ),
            "native_clean_baseline": {
                "identity": native_clean,
                "policy": (
                    "preserve pinned clean-install defaults, native tools, bundled assets, "
                    "and native context except where an envelope rule below requires a change"
                ),
                "tool_and_skill_evidence": "recorded separately; not normalized across harnesses",
            },
            "benchmark_envelope_rules": {
                "control_model": {
                    "resolved_value": self.model,
                    "implementation": "single native provider/model route through fixed gateway",
                    "evidence": "materialized config plus model-call ledger",
                },
                "harness_execution_timeout_seconds": {
                    "resolved_value": self.timeout,
                    "implementation": (
                        "runner active-time deadline from native harness startup until native "
                        "harness exit; benchmark-owned provider transient retry pauses the "
                        "agent container and clock; complete container termination on deadline"
                    ),
                    "evidence": "execution_timing and deadline termination test",
                },
                "control_model_request_attempts": {
                    "resolved_value": self.max_model_calls,
                    "implementation": (
                        "model gateway reserves one shared logical-call slot before forwarding; "
                        "benchmark-owned physical transient retries do not reserve extra slots"
                    ),
                    "evidence": "action-step-guard and model_call_ledger",
                },
                "action_steps": {
                    "resolved_value": self.max_action_steps,
                    "metric": "model_calls + tool_calls",
                    "implementation": (
                        "the shared model gateway reserves one step for every "
                        "logical model request and one step for each structured "
                        "tool invocation before delivering the response"
                    ),
                    "evidence": (
                        "action-step-guard, model_gateway_summary, and "
                        "model_call_ledger"
                    ),
                },
                "model_error_routing": {
                    "resolved_value": (
                        self.resolved_config.model_error_routing
                        if self.resolved_config is not None
                        else None
                    ),
                    "implementation": (
                        "fixed-route gateway classifies by source, HTTP status, structured "
                        "provider error, and transport phase; safe external transients are "
                        "hidden, request errors are returned to the native harness"
                    ),
                    "evidence": (
                        "action-step-guard-v1, physical-attempt ledger, pause timing, and "
                        "provider_infra_invalid record"
                    ),
                },
                "network": {
                    "resolved_value": self.network_policy(),
                    "implementation": "internal Docker network; optional allowlist proxy",
                    "evidence": "network-model-only validation preset",
                },
                "interaction": {
                    "resolved_value": (
                        self.resolved_config.raw["resolved"]["interaction"]
                        if self.resolved_config is not None
                        else {"mode": "noninteractive"}
                    ),
                    "implementation": interaction_surfaces.get(self.name, "adapter-defined"),
                    "evidence": "materialized native CLI/config",
                },
                "state_isolation": {
                    "resolved_value": (
                        self.resolved_config.raw["resolved"]["state_isolation"]
                        if self.resolved_config is not None
                        else None
                    ),
                    "implementation": state_surfaces.get(self.name, "adapter-defined"),
                    "evidence": "isolated path/config manifests",
                },
                "environment": {
                    "implementation": "fixed benchmark env plus gateway-only real credential",
                    "evidence": "environment-isolation validation preset",
                },
                "artifact_contract": {
                    "implementation": "byte snapshot of configured workspace delivery names",
                    "evidence": "frozen_workspace_artifacts and completion record",
                },
                "canonical_prompt": {
                    "implementation": "passed through unchanged",
                    "evidence": "canonical prompt and transport payload hashes",
                },
                "agent_tools": {
                    "resolved_value": self.agent_tools(),
                    "implementation": (
                        "optional condition-level CLI tools under "
                        "agent_formalizer/tools/<tool>/; pddl_solver mounts "
                        "/usr/local/bin/pddl-solver and a solver-gateway sidecar "
                        "that calls planning.domains (same backend as run_solver.py)"
                        if self.pddl_solver_tool_enabled()
                        else "none"
                    ),
                    "evidence": (
                        "agent_tools in resolved config, tool gateway status, "
                        "and shell invocations of the mounted CLI"
                        if self.agent_tools()
                        else "resolved agent_tools empty"
                    ),
                },
                "generation": {
                    "resolved_value": (
                        self.resolved_config.generation_overrides
                        if self.resolved_config is not None
                        else {}
                    ),
                    "implementation": (
                        "condition-level model-gateway request override; "
                        "OpenAI-compatible payloads use top-level fields and "
                        "native Gemini payloads use generationConfig"
                    ),
                    "evidence": (
                        "resolved config, model gateway effective config, and "
                        "per-request override ledger"
                    ),
                },
            },
        }

    def effective_config(self) -> dict:
        """Secret-free effective configuration for hashing and auditing."""
        value = {
            "model": self.model,
            "budgets": {
                "timeout_seconds": self.timeout,
                "max_model_calls": self.max_model_calls,
                "max_action_steps": self.max_action_steps,
            },
            "network": self.network_policy(),
            "model_route": self.model_auth(),
            "model_gateway": self.model_gateway(),
            "skills_mode": self.skills_mode,
            "agent_tools": self.agent_tools(),
            "tools": self.tool_policy(),
            "adapter_translation": self.translation_ledger(),
        }
        if self.resolved_config is not None:
            value["resolved_semantics"] = self.resolved_config.raw
            value["resolved_config_sha256"] = self.resolved_config.sha256
        return value

    def runtime_info(self) -> dict:
        return {"adapter_class": f"{type(self).__module__}.{type(self).__name__}"}

    def skills_info(self) -> dict:
        return {"mode": self.skills_mode, "manifest": []}


def decode_output(data) -> str:
    """Decode subprocess bytes output, or return string as-is."""
    if isinstance(data, bytes):
        return data.decode(errors="replace")
    return data or ""
