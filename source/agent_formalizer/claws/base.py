"""Base interface every claw (agent harness) adapter implements.

Ported from ``claw-swe-bench`` (``claw_swebench/claws/base.py``). The
orchestrator and workspace are claw-agnostic; everything specific to a claw
(how its runtime gets into the container, how a task is launched, how
sessions/usage/tool-traces are collected) lives behind this interface.

Hook call order for one problem (see orchestrator.run_one_problem):

    container_run_args(instance_id)         # extra `docker run` args (mounts, env)
    post_container_start(workspace)         # provision config inside container
    create_agent(agent_id, instance_id=...) # optional isolation setup
    send_task(prompt, ...)                  # run the agent, return AgentResult
    collect_usage(workspace, artifact_dir)  # claw-specific usage, container alive
    backup_session(agent_id, artifact_dir)  # save/report raw session logs
    iter_agent_steps(agent_id, artifact_dir) # yield normalized agent records
    iter_tool_calls(agent_id, artifact_dir) # yield normalized tool-call records
    prepare_agent_cleanup(...)              # restore access to private mounts
    workspace.cleanup()                     # unmount runtime/state paths
    delete_agent(agent_id, instance_id=...) # teardown (always called)
"""

from __future__ import annotations

import logging
import math
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable

from agent_formalizer.result_types import AgentResult
from agent_formalizer.runtime import process_lifecycle

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
        self._external_charged_seconds = 0.0
        self._cancel_reason: str | None = None

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

    def charge_active(self, seconds: float) -> None:
        """Commit a delivered external operation's elapsed time from escrow."""
        if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("external elapsed time must be finite and non-negative")
        with self._lock:
            self._external_charged_seconds += seconds
            self._deadline -= seconds

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

    def cancel(self, reason: str) -> None:
        """Request prompt harness-process termination without posing as timeout."""
        with self._lock:
            if self._cancel_reason is None:
                self._cancel_reason = str(reason)

    def cancellation_reason(self) -> str | None:
        with self._lock:
            return self._cancel_reason

    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            live_pause = (
                now - self._pause_started
                if self._pause_depth > 0 and self._pause_started is not None
                else 0.0
            )
            paused = max(0.0, self._paused_seconds + live_pause - self._external_charged_seconds)
            wall = now - self.started_monotonic
            return {
                "limit_seconds": self.limit_seconds,
                "wall_duration_seconds": round(wall, 6),
                "infra_pause_seconds": round(paused, 6),
                "active_duration_seconds": round(max(0.0, wall - paused), 6),
                "paused": self._pause_depth > 0,
                "deadline_exceeded": self.remaining() <= 0.0,
                "cancellation_reason": self._cancel_reason,
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
        process_lifecycle.command(cmd),
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        env=env,
        start_new_session=True,
    )
    try:
        while True:
            if clock.cancellation_reason() is not None:
                process_lifecycle.terminate(proc)
                stdout, stderr = proc.communicate()
                return subprocess.CompletedProcess(cmd, -1, stdout, stderr)
            remaining = clock.remaining()
            if remaining <= 0:
                process_lifecycle.terminate(proc)
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
    finally:
        # A monitor/decoder exception must not detach a still-running command.
        process_lifecycle.terminate(proc)


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
        from local_solver import DEFAULT_SOLVER_BACKEND, base_urls_for_backend

        backend = (
            self.resolved_config.solver_backend
            if self.resolved_config is not None
            else DEFAULT_SOLVER_BACKEND
        )
        host_url, container_url = base_urls_for_backend(backend)
        self._solver_backend = backend
        self._solver_host_base_url = host_url
        self._solver_container_base_url = container_url

    def configure_solver_backend(
        self,
        backend: str,
        *,
        host_base_url: str | None = None,
        container_base_url: str | None = None,
    ) -> None:
        """Bind operational endpoints for the profile-hashed backend mode."""
        from local_solver import SUPPORTED_BACKENDS, base_urls_for_backend

        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"unsupported solver backend: {backend}")
        expected = (
            self.resolved_config.solver_backend
            if self.resolved_config is not None
            else backend
        )
        if backend != expected:
            raise ValueError(
                f"solver backend {backend!r} does not match resolved mode {expected!r}"
            )
        default_host, default_container = base_urls_for_backend(backend)
        self._solver_backend = backend
        self._solver_host_base_url = (
            host_base_url or default_host
        ).rstrip("/")
        self._solver_container_base_url = (
            container_base_url or default_container
        ).rstrip("/")

    def solver_backend(self) -> str:
        return self._solver_backend

    def solver_upstream_base(self, *, containerized: bool) -> str:
        return (
            self._solver_container_base_url
            if containerized
            else self._solver_host_base_url
        )

    def solver_fallback_base(self, *, containerized: bool) -> str | None:
        from local_solver import fallback_url_for_backend

        return fallback_url_for_backend(self.solver_backend(), containerized=containerized)

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
        from agent_formalizer.timing.deadline_integration import validate
        validate(self)

    def output_token_policy(self) -> dict | None:
        return self.resolved_config.output_token_policy if self.resolved_config else None

    def native_max_output_tokens(self) -> int | None:
        from agent_formalizer.configuration.model_capabilities import native_output_hint
        return native_output_hint(self.output_token_policy())

    def container_run_args(self, instance_id: str) -> list[str]:
        """Extra arguments for ``docker run`` (bind mounts, env vars)."""
        return []

    def post_container_start(self, workspace) -> None:
        """Provision the running container (e.g. copy a config file in)."""
        pass

    # ------------------------------------------------------------------
    # Agent lifecycle (no-ops for stateless claws)
    # ------------------------------------------------------------------

    def create_agent(
        self, agent_id: str, *, instance_id: str | None = None
    ) -> None:
        pass

    def delete_agent(
        self, agent_id: str, *, instance_id: str | None = None
    ) -> None:
        pass

    def prepare_agent_cleanup(
        self,
        agent_id: str,
        *,
        instance_id: str | None = None,
        container_name: str | None = None,
    ) -> None:
        """Prepare attempt-private host mounts for teardown while container lives."""
        pass

    @staticmethod
    def _run_container_cleanup_command(
        container_name: str, command: list[str]
    ) -> subprocess.CompletedProcess:
        """Run a teardown command even when the attempt container was stopped.

        Deadline enforcement kills the container before evidence collection.
        Restarting its inert top-level ``tail`` process after the measured run
        lets teardown fix ownership on exact private bind mounts; the container
        is force-removed immediately afterward.
        """
        inspected = subprocess.run(
            [
                "docker", "inspect", "--format",
                "{{.State.Running}} {{.State.Paused}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if inspected.returncode != 0:
            return inspected
        state = inspected.stdout.strip().split()
        running = state[:1] == ["true"]
        paused = state[1:2] == ["true"]
        if paused:
            unpaused = subprocess.run(
                ["docker", "unpause", container_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if unpaused.returncode != 0:
                return unpaused
            running = True
        if not running:
            started = subprocess.run(
                ["docker", "start", container_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if started.returncode != 0:
                return started
        return subprocess.run(
            ["docker", "exec", container_name, *command],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def state_isolation_spec(self, instance_id: str) -> dict:
        """Declare per-attempt writable host surfaces for runtime validation.

        The current benchmark implements only isolated state. A future
        controlled-sharing condition should override this through a new,
        profile-hashed policy rather than making a shared cache or recycle bin
        incidentally visible.
        """
        configured = (
            self.resolved_config.raw["resolved"]["state_isolation"]
            if self.resolved_config is not None
            else {
                "scope": "per_attempt",
                "personal_harness_state": "excluded",
                "cross_attempt_reuse": False,
            }
        )
        return {
            "mode": "isolated",
            "scope": configured["scope"],
            "personal_harness_state": configured["personal_harness_state"],
            "cross_attempt_reuse": configured["cross_attempt_reuse"],
            "attempt_root": None,
            "writable_bind_sources": [],
            "private_readonly_bind_sources": [],
            "shared_readonly_bind_sources": [],
            "tests": {},
        }

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> dict:
        """Persist raw native evidence and return a content-free status report.

        The default explicitly reports that no adapter capture exists.  This
        prevents a no-op collector from being mistaken for a model that emitted
        no analysis.  Overrides must not include transcript text or secrets in
        their report.
        """
        return {
            "status": "not_exposed",
            "collector": "none",
            "reason": "adapter_has_no_raw_session_collector",
            "files_copied": 0,
        }

    def raw_evidence_roots(self, artifact_dir: Path) -> list[Path]:
        """Return attempt-local roots included in the optional raw manifest."""
        return [artifact_dir / "sessions", artifact_dir / "gateway"]

    def analysis_evidence_spec(self) -> dict:
        """Declare native exposure and adapter persistence semantics."""
        from agent_formalizer.results.optional_evidence import default_analysis_evidence_spec

        return default_analysis_evidence_spec()

    def inspect_analysis_evidence(self, artifact_dir: Path) -> dict:
        """Inspect persisted analysis metadata without retaining its content."""
        return {
            "status": "not_persisted",
            "records_examined": 0,
            "evidence_files": [],
        }

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
        from agent_formalizer.prompts.prompt import build_prompt

        contract = self.resolved_config.raw["resolved"]["artifact_contract"]
        prompt = build_prompt(
            domain_description,
            problem_description,
            template_path=None,
            domain_output_name=contract["workspace_domain_file"],
            problem_output_name=contract["workspace_problem_file"],
            agent_tools=self.resolved_config.agent_tools,
        )
        bundle = self.resolved_config.skill_bundle
        return prompt + bundle.catalog() if bundle.skills else prompt

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
            "provider": self.model.split("/", 1)[0],
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
            value["response_delivery"] = (
                self.resolved_config.model_response_delivery["mode"]
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
            value["response_delivery"] = "buffered_atomic"
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
            "openclaw": "per-attempt state, workspace, session, memory, and Trash",
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
        checkpoint = bool(self.resolved_config and
                          self.resolved_config.raw['resolved'].get('external_call_timing') == 'call-checkpoint-v1')
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
                        "host call-boundary business-time settlement; retained native continuation; "
                        "hidden external retries excluded; native healthy concurrency remains running"
                        if checkpoint else
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
                        "the shared model gateway streams successful response bytes, "
                        "commits the complete structured tool batch on normal stream "
                        "completion, and applies the action threshold to the next "
                        "request; final-batch overshoot remains visible"
                        if self.resolved_config is not None
                        and self.resolved_config.model_response_delivery["mode"]
                        == "native_streaming"
                        else "the shared model gateway reserves one step for every "
                        "logical model request and one step for each structured "
                        "tool invocation before delivering the response"
                    ),
                    "evidence": (
                        "action-step-guard, model_gateway_summary, and "
                        "model_call_ledger"
                    ),
                },
                "model_response_delivery": {
                    "resolved_value": (
                        self.resolved_config.model_response_delivery
                        if self.resolved_config is not None
                        else {
                            "mode": "buffered_atomic",
                            "first_event_commit": False,
                            "action_step_admission": "exact_complete_batch",
                        }
                    ),
                    "implementation": (
                        "versioned common gateway response-delivery path"
                    ),
                    "evidence": (
                        "model_gateway_summary and per-call stream ledger"
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
                        "that calls the selected planning.domains-compatible "
                        "backend (same backend as run_solver.py)"
                        if self.pddl_solver_tool_enabled()
                        else "none"
                    ),
                    "solver_backend": (
                        {
                            "mode": self.solver_backend(),
                            "host_base_url": self.solver_upstream_base(
                                containerized=False
                            ),
                            "container_base_url": self.solver_upstream_base(
                                containerized=True
                            ),
                        }
                        if self.pddl_solver_tool_enabled()
                        else None
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
                **({"external_call_timing": {
                    "resolved_value": "call-checkpoint-v1",
                    "implementation": "named, version-checked native cancellation sites; original request/continuation retained",
                    "native_fields": "per-harness coverage in logical_deadline_manifest.json",
                    "evidence": ["logical_deadline_manifest.json", "gateway/call_checkpoints.jsonl", "model_call_ledger.jsonl"],
                    "limits": "actual unsafe concurrent recovery invalidates; no filesystem or committed-stream rollback",
                }} if checkpoint else {}),
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
            timing = self.resolved_config.raw["resolved"].get("external_call_timing")
            if timing:
                value["external_call_timing"] = {
                    "policy": timing,
                    "implementation": "host settlement + versioned native deadline runtime",
                    "evidence": ["logical_deadline_manifest.json",
                                 "gateway/call_checkpoints.jsonl" if timing == 'call-checkpoint-v1' else "gateway/logical_time.jsonl"],
                    "physical_clocks_modified": False,
                }
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
