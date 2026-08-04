"""Case → attempt → infra execution lifecycle for agent formalization."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

from agent_formalizer.benchmark_profile import canonical_sha256
from agent_formalizer.config import (
    OUTPUT_DIR,
    ROOT_DIR,
    BASE_IMAGE,
    agent_model_label,
    container_name as make_container_name,
    domain_dir,
    new_runtime_id,
    problem_output_dir,
)
from agent_formalizer.prompt import extract_pddl_from_text
from agent_formalizer.provenance import (
    docker_image_info,
    file_manifest,
    git_info,
    host_runtime_info,
    sha256_bytes,
    sha256_text,
)
from agent_formalizer.result_types import AgentResult, FormalizerResult
from agent_formalizer.runtime_lock import RuntimeLockMismatch, validate_runtime_lock
from agent_formalizer.util import Tracer, format_problem_name, now_iso, run_parallel
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.minimum_workspace import MinimumHostWorkspace


logger = logging.getLogger(__name__)
COMPLETION_NAME = "completion.json"
LEASE_NAME = ".attempt.lease"


class InfraInvalid(RuntimeError):
    def __init__(
        self,
        reason: str,
        message: str,
        *,
        retry_execution: bool = True,
    ):
        super().__init__(message)
        self.reason = reason
        self.retry_execution = retry_execution


def _config_qualified_label(adapter, label: str | None) -> str:
    base = label or agent_model_label(adapter.name, adapter.model)
    suffix = f"__{adapter.resolved_config.label}"
    return base if base.endswith(suffix) else base + suffix


def _read_descriptions(domain: str, data: str, problem: str) -> tuple[str, str]:
    directory = domain_dir(domain, data)
    return (
        (directory / f"{problem}_domain.txt").read_text(),
        (directory / f"{problem}_problem.txt").read_text(),
    )


def _build_canonical_prompt(adapter, domain_description: str, problem_description: str) -> str:
    return adapter.build_task_prompt(domain_description, problem_description)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def _freeze_image_reference(image: str | None) -> tuple[str, str]:
    requested = image or BASE_IMAGE
    inspected = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", requested],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if inspected.returncode != 0 or not inspected.stdout.strip():
        raise InfraInvalid(
            "container_start_failed",
            f"benchmark image is not available locally: {requested}",
        )
    return requested, inspected.stdout.strip()


def _freeze_execution_reference(adapter, image: str | None) -> tuple[str | None, str | None]:
    """Freeze Docker only for native harnesses; minimum is host-only."""
    if adapter.name == "minimum":
        if image is not None:
            raise ValueError("--image is not applicable to the minimum host runtime")
        return None, None
    return _freeze_image_reference(image)


def _adapter_code_sha256() -> str:
    package = Path(__file__).resolve().parent
    paths = [
        path
        for path in package.glob("**/*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json", ".txt", ".sh"}
        # Credential registries are operational inputs with their own redacted
        # provenance hash.  Adding/rotating a named profile must not alter the
        # experiment/runtime identity used for labels and resume.
        and path.name != "credential_profiles.json"
    ]
    return canonical_sha256(file_manifest(paths, root=package))


def _task_identity(
    domain: str,
    data: str,
    problem: str,
    domain_description: str,
    problem_description: str,
    prompt: str,
) -> dict:
    raw = {
        "domain": domain,
        "dataset": data,
        "problem": problem,
        "domain_description_sha256": sha256_text(domain_description),
        "problem_description_sha256": sha256_text(problem_description),
        "canonical_prompt_sha256": sha256_text(prompt),
    }
    return {"sha256": canonical_sha256(raw), "raw": raw}


def _provenance(
    adapter, prompt: str, image: str | None, runtime_lock: dict
) -> dict:
    effective = adapter.effective_config()
    skills = adapter.skills_info()
    materialized_sha256 = canonical_sha256(effective)
    return {
        "schema_version": 2,
        "resolved_config": adapter.resolved_config.metadata(),
        "benchmark_repository": git_info(ROOT_DIR),
        "adapter_code_sha256": _adapter_code_sha256(),
        "effective_config": effective,
        "effective_config_sha256": materialized_sha256,
        "materialized_config_sha256": materialized_sha256,
        "prompt_sha256": sha256_text(prompt),
        "transport_payload_sha256": sha256_bytes(
            adapter.task_transport_payload(prompt)
        ),
        "tool_policy_sha256": canonical_sha256(adapter.tool_policy()),
        "skills": skills,
        "skills_sha256": canonical_sha256(skills),
        "runtime_lock": runtime_lock,
        "harness_runtime": adapter.runtime_info(),
        "container_image": (
            docker_image_info(image)
            if image is not None
            else {
                "required": False,
                "execution_backend": "host",
                "reason": "minimum runtime has no native harness environment",
            }
        ),
        "host_runtime": host_runtime_info(include_docker=adapter.name != "minimum"),
    }


def _record_optional_evidence(
    adapter,
    agent_id: str,
    artifact_dir: Path,
    problem: str,
    model_label: str,
    tracer: Tracer,
    agent_result: AgentResult | None,
    container_name: str,
) -> tuple[int, int, str | None]:
    session_agent_id = (
        (agent_result.openclaw_agent_id if agent_result else None) or agent_id
    )
    session_id = agent_result.session_id if agent_result else None
    session_file = agent_result.session_file if agent_result else None
    try:
        adapter.backup_session(
            session_agent_id,
            artifact_dir,
            session_id=session_id,
            session_file=session_file,
            container_name=container_name,
        )
    except Exception as exc:
        tracer.emit("optional_session_error", error_type=type(exc).__name__)

    steps_path = artifact_dir / f"{problem}_{model_label}_agent_steps.jsonl"
    trace_record_count = 0
    try:
        with steps_path.open("w", buffering=1) as stream:
            for record in adapter.iter_agent_steps(
                session_agent_id,
                artifact_dir,
                session_id=session_id,
                session_file=session_file,
            ):
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                trace_record_count += 1
    except Exception as exc:
        tracer.emit("optional_steps_error", error_type=type(exc).__name__)

    traced_tool_call_count = 0
    try:
        for record in adapter.iter_tool_calls(
            session_agent_id,
            artifact_dir,
            session_id=session_id,
            session_file=session_file,
        ):
            tracer.emit("tool_exec", provider=adapter.name, **record)
            if record.get("kind", "call") == "call":
                traced_tool_call_count += 1
    except Exception as exc:
        tracer.emit("optional_tool_trace_error", error_type=type(exc).__name__)
    return (
        traced_tool_call_count,
        trace_record_count,
        str(steps_path) if steps_path.exists() else None,
    )


def _agent_error_result(message: str, started: float) -> AgentResult:
    return AgentResult(
        success=False,
        timeout=False,
        exit_code=-1,
        finish_reason="error",
        duration_seconds=round(time.monotonic() - started, 3),
        final_text=None,
        usage={"harness_exception": message},
    )


def _write_ledger(path: Path, ledger: list[dict]) -> None:
    with path.open("w") as stream:
        for row in ledger:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _action_metrics(gateway_summary: dict, adapter, artifact_dir: Path | None = None) -> dict:
    model_calls = int(gateway_summary.get("model_calls", 0) or 0)
    tool_calls = int(gateway_summary.get("tool_calls", 0) or 0)
    metrics = {
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "action_steps": model_calls + tool_calls,
        "max_model_calls": adapter.max_model_calls,
        "max_action_steps": adapter.max_action_steps,
        "action_step_limit_reached": bool(
            gateway_summary.get("action_step_limit_reached")
        ),
    }
    metrics.update(adapter.additional_action_metrics(artifact_dir))
    return metrics


def _run_execution_try(
    adapter,
    domain: str,
    data: str,
    problem: str,
    *,
    attempt_index: int,
    execution_try: int,
    model_label: str,
    attempt_dir: Path,
    domain_description: str,
    problem_description: str,
    prompt: str,
    task_identity: dict,
    runtime_lock: dict,
    record_trace: bool,
    image: str | None,
) -> tuple[FormalizerResult, dict]:
    operational_started = time.monotonic()
    execution_dir = attempt_dir / "executions" / f"execution-{execution_try:03d}"
    execution_dir.mkdir(parents=True, exist_ok=True)
    trace_path = (
        execution_dir / f"{problem}_{model_label}_trace.jsonl"
        if record_trace
        else None
    )
    tracer = Tracer(str(trace_path) if trace_path else None)
    runtime_id = new_runtime_id()
    logical_instance_id = (
        f"{domain}-{data}-{problem}-a{attempt_index:03d}-e{execution_try:03d}"
    )
    # The runtime suffix also isolates harness-owned host state (for example,
    # GenericAgent's per-instance temp and memory directories) across sweeps.
    instance_id = f"{logical_instance_id}-r{runtime_id}"
    agent_id = f"pddl-{instance_id}-{model_label}".replace(".", "-").replace("/", "-")
    container = make_container_name(
        adapter.name,
        domain,
        data,
        model_label,
        f"{problem}-a{attempt_index}-e{execution_try}",
        runtime_id=runtime_id,
    )
    workspace = (
        MinimumHostWorkspace(
            instance_id,
            container,
            adapter,
            artifact_dir=execution_dir,
        )
        if adapter.name == "minimum"
        else AgentWorkspace(instance_id, container, adapter, image=image)
    )
    result = FormalizerResult(
        problem=problem,
        status="failed",
        attempt_index=attempt_index,
        execution_try=execution_try,
        attempt_valid=True,
        generation_success=False,
        model_label=model_label,
    )
    agent_result: AgentResult | None = None
    clock_started: float | None = None
    clock_finished: float | None = None
    gateway_summary: dict = {}
    ledger: list[dict] = []
    validations: list[dict] = []
    artifacts: dict[str, bytes | None] = {"domain": None, "problem": None}
    harness_exception: str | None = None
    watchdog_thread: threading.Thread | None = None
    watchdog_stop = threading.Event()
    watchdog_fired = threading.Event()
    attempt_clock = None
    optional = {
        "traced_tool_call_count": 0,
        "agent_trace_record_count": 0,
        "agent_trace_path": None,
    }

    try:
        try:
            workspace.start()
        except Exception as exc:
            message = str(exc).lower()
            if "solver gateway" in message:
                reason = "solver_gateway_start_failed"
            elif "gateway" in message:
                reason = "gateway_start_failed"
            else:
                reason = "container_start_failed"
            raise InfraInvalid(reason, str(exc)) from exc

        try:
            workspace.seed_workspace(domain_description, problem_description)
        except Exception as exc:
            raise InfraInvalid("task_seed_failed", str(exc)) from exc

        network_validation = workspace.validate_network_policy()
        environment_validation = workspace.validate_environment_policy()
        action_guard_validation = workspace.validate_action_step_guard()
        validations.extend([
            runtime_lock,
            network_validation,
            environment_validation,
            action_guard_validation,
        ])
        configured_validations = {
            row["preset"]: row["required"]
            for row in adapter.resolved_config.raw["resolved"]["validations"]
        }
        if any(
            row.get("status") != "pass"
            and configured_validations.get(row.get("preset"), False)
            for row in validations
        ):
            raise InfraInvalid("required_evidence_failed", "required validation failed")

        provenance = _provenance(adapter, prompt, workspace.image_name, runtime_lock)
        tracer.emit(
            "start",
            pipeline="llm-as-formalizer-agent",
            provider=adapter.name,
            model=adapter.model,
            model_label=model_label,
            attempt_index=attempt_index,
            execution_try=execution_try,
            task_input_sha256=task_identity["sha256"],
            resolved_config_sha256=adapter.resolved_config.sha256,
            prompt=prompt,
        )

        # Docker, sidecars, validation, and task seeding are infrastructure.
        # Native harness startup begins the measured envelope interval here.
        clock_started = time.monotonic()
        attempt_clock = adapter.begin_attempt_clock()
        workspace.start_model_gateway_monitor(attempt_clock)

        def enforce_deadline() -> None:
            while not watchdog_stop.is_set():
                remaining = attempt_clock.remaining()
                if remaining <= 0:
                    watchdog_fired.set()
                    workspace.enforce_agent_deadline()
                    return
                watchdog_stop.wait(min(0.25, max(0.01, remaining)))

        watchdog_thread = threading.Thread(
            target=enforce_deadline,
            name=f"attempt-watchdog-{instance_id}",
            daemon=True,
        )
        watchdog_thread.start()
        try:
            adapter.create_agent(agent_id)
            if adapter.deadline_exceeded():
                raise TimeoutError("harness deadline reached during startup")
            agent_result = adapter.send_task(
                prompt,
                agent_id=agent_id,
                container_name=container,
                artifact_dir=execution_dir,
                instance_id=instance_id,
            )
        except TimeoutError as exc:
            workspace.enforce_agent_deadline()
            agent_result = AgentResult(
                success=False,
                timeout=True,
                exit_code=-1,
                finish_reason="timeout",
                duration_seconds=round(time.monotonic() - clock_started, 3),
            )
            harness_exception = str(exc)
        except Exception as exc:
            # A native harness crash is a measured agent outcome, not infra.
            if adapter.name != "minimum":
                subprocess.run(
                    ["docker", "kill", container], capture_output=True
                )
            harness_exception = f"{type(exc).__name__}: {exc}"
            agent_result = _agent_error_result(harness_exception, clock_started)

        gateway_terminal = workspace.gateway_terminal_infra_error()
        gateway_monitor_error = workspace.gateway_monitor_error()
        action_step_limit_reached = (
            workspace.gateway_action_step_limit_reached()
        )
        workspace.stop_model_gateway_monitor()
        watchdog_stop.set()
        if watchdog_thread is not None:
            watchdog_thread.join(timeout=10)

        if gateway_terminal is not None or gateway_monitor_error is not None:
            clock_finished = time.monotonic()
            clock_snapshot = attempt_clock.snapshot()
            adapter.end_attempt_clock()
            gateway_summary = workspace.model_gateway_stats()
            ledger = workspace.model_gateway_ledger()
            ledger_path = execution_dir / "model_call_ledger.jsonl"
            _write_ledger(ledger_path, ledger)
            reason = gateway_monitor_error or gateway_terminal.get(
                "reason", "provider_transient_exhausted"
            )
            invalid_evidence = {
                "schema_version": 1,
                "attempt_valid": False,
                "infra_invalidator": reason,
                "terminal_infra_error": gateway_terminal,
                "execution_timing": clock_snapshot,
                "model_gateway_summary": gateway_summary,
                "actions": _action_metrics(gateway_summary, adapter, execution_dir),
                "model_call_ledger": {
                    "path": str(ledger_path),
                    "entries": len(ledger),
                    "sha256": sha256_bytes(ledger_path.read_bytes()),
                },
            }
            _atomic_json(execution_dir / "provider_infra_invalid.json", invalid_evidence)
            raise InfraInvalid(
                reason,
                f"model provider infrastructure did not yield a valid response: {reason}",
                retry_execution=False,
            )

        if (
            watchdog_fired.is_set() or adapter.deadline_exceeded()
        ) and agent_result and not agent_result.timeout:
            workspace.enforce_agent_deadline()
            agent_result.success = False
            agent_result.timeout = True
            agent_result.finish_reason = "timeout"

        if agent_result and agent_result.timeout:
            workspace.enforce_agent_deadline()

        if action_step_limit_reached and agent_result is not None:
            agent_result.success = False
            agent_result.timeout = False
            agent_result.finish_reason = "action_step_limit"

        # Stop the agent clock at native harness exit. Collection remains
        # operational work and cannot consume or extend the agent budget.
        clock_finished = time.monotonic()
        clock_snapshot = attempt_clock.snapshot()
        adapter.end_attempt_clock()
        harness_duration = clock_snapshot["active_duration_seconds"]
        if agent_result is not None:
            agent_result.duration_seconds = harness_duration

        artifacts = workspace.freeze_pddl_outputs()
        artifact_sources = {
            role: ("file" if payload is not None else None)
            for role, payload in artifacts.items()
        }
        result.agent_result = agent_result

        # Optional recovery is explicitly experimental and off by default.
        if adapter.resolved_config.allow_final_message_recovery and agent_result.final_text:
            recovered_domain, recovered_problem = extract_pddl_from_text(
                agent_result.final_text
            )
            if artifacts["domain"] is None and recovered_domain is not None:
                artifacts["domain"] = recovered_domain.encode()
                artifact_sources["domain"] = "parsed"
            if artifacts["problem"] is None and recovered_problem is not None:
                artifacts["problem"] = recovered_problem.encode()
                artifact_sources["problem"] = "parsed"
        present_sources = {source for source in artifact_sources.values() if source}
        extraction_source = (
            next(iter(present_sources)) if len(present_sources) == 1 else "mixed"
        )

        frozen_records: dict[str, dict] = {}
        frozen_dir = execution_dir / "frozen_workspace"
        contract = adapter.resolved_config.raw["resolved"]["artifact_contract"]
        for role, name_key in (
            ("domain", "workspace_domain_file"),
            ("problem", "workspace_problem_file"),
        ):
            payload = artifacts[role]
            if payload is None:
                continue
            frozen_dir.mkdir(parents=True, exist_ok=True)
            frozen_path = frozen_dir / contract[name_key]
            frozen_path.write_bytes(payload)
            frozen_records[role] = {
                "path": str(frozen_path),
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "source": artifact_sources[role],
            }

        try:
            usage = adapter.collect_usage(workspace, execution_dir) or {}
            if agent_result and usage:
                agent_result.usage = {**agent_result.usage, **usage}
        except Exception as exc:
            tracer.emit("optional_usage_error", error_type=type(exc).__name__)

        gateway_summary = workspace.model_gateway_stats()
        ledger = workspace.model_gateway_ledger()
        _write_ledger(execution_dir / "model_call_ledger.jsonl", ledger)
        traced_tool_calls, trace_records, trace_path = _record_optional_evidence(
            adapter,
            agent_id,
            execution_dir,
            problem,
            model_label,
            tracer,
            agent_result,
            container,
        )
        optional = {
            "traced_tool_call_count": traced_tool_calls,
            "agent_trace_record_count": trace_records,
            "agent_trace_path": trace_path,
        }
        actions = _action_metrics(gateway_summary, adapter, execution_dir)

        generated = artifacts["domain"] is not None and artifacts["problem"] is not None
        result.generation_success = generated
        result.status = "ok" if generated else "failed"
        result.extraction_source = extraction_source if generated else None
        if artifacts["domain"] is not None:
            result.domain_bytes = artifacts["domain"]
            result.domain_file = artifacts["domain"].decode(errors="replace")
        if artifacts["problem"] is not None:
            result.problem_bytes = artifacts["problem"]
            result.problem_file = artifacts["problem"].decode(errors="replace")
        if not generated:
            missing = [role for role, payload in artifacts.items() if payload is None]
            result.error = (
                "official delivery file(s) missing: " + ", ".join(missing)
            )

        evidence = {
            "schema_version": 2,
            "attempt_valid": True,
            "generation_success": generated,
            "harness_exception": harness_exception,
            "execution_timing": {
                "scope": "native_harness_startup_through_native_harness_exit",
                "timeout_seconds": adapter.timeout,
                "duration_seconds": harness_duration,
                "wall_duration_seconds": clock_snapshot["wall_duration_seconds"],
                "infra_pause_seconds": clock_snapshot["infra_pause_seconds"],
                "deadline_exceeded": bool(agent_result and agent_result.timeout),
            },
            "operational_timing": {
                "scope": "execution_try_start_through_required_evidence_collection",
                "duration_seconds": round(time.monotonic() - operational_started, 6),
            },
            "validations": validations,
            "model_gateway_summary": gateway_summary,
            "actions": actions,
            "frozen_workspace_artifacts": frozen_records,
            "model_call_ledger": {
                "path": str(execution_dir / "model_call_ledger.jsonl"),
                "entries": len(ledger),
                "sha256": sha256_bytes(
                    (execution_dir / "model_call_ledger.jsonl").read_bytes()
                ),
            },
            "provenance": provenance,
            "optional_evidence": optional,
        }
        tracer.emit(
            "final",
            attempt_valid=True,
            generation_success=generated,
            status=result.status,
            error=result.error,
            **actions,
        )
        return result, evidence
    finally:
        watchdog_stop.set()
        if watchdog_thread is not None and watchdog_thread is not threading.current_thread():
            watchdog_thread.join(timeout=10)
        workspace.stop_model_gateway_monitor()
        adapter.end_attempt_clock()
        try:
            workspace.cleanup()
        finally:
            try:
                adapter.delete_agent(agent_id)
            finally:
                tracer.close()


def _completion_matches(
    path: Path, config_hash: str, task_hash: str, runtime_hash: str
) -> bool:
    if not path.is_file():
        return False
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        value.get("complete") is True
        and value.get("attempt_valid") is True
        and value.get("resolved_config_sha256") == config_hash
        and value.get("task_input_sha256") == task_hash
        and value.get("runtime_identity_sha256") == runtime_hash
    )


def _result_from_completion(path: Path) -> FormalizerResult:
    value = json.loads(path.read_text())
    return FormalizerResult(
        problem=value["problem"],
        status="ok" if value["generation_success"] else "failed",
        attempt_index=value["attempt_index"],
        execution_try=value["selected_execution_try"],
        attempt_valid=True,
        generation_success=value["generation_success"],
        extraction_source=value.get("extraction_source"),
        error=value.get("error"),
        model_label=value["model_label"],
        completion_path=path,
    )


def _acquire_lease(attempt_dir: Path, identity: dict) -> int:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    path = attempt_dir / LEASE_NAME
    for _ in range(2):
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError as exc:
            try:
                previous = json.loads(path.read_text())
                pid = int(previous["pid"])
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                # A just-created lease may be observed before its small JSON
                # body is written. Only reclaim malformed leases that are old
                # enough to be unambiguously stale.
                try:
                    age = time.time() - path.stat().st_mtime
                except OSError:
                    continue
                if age > 300:
                    path.unlink(missing_ok=True)
                    continue
                raise RuntimeError(
                    f"attempt has a recent unreadable lease: {attempt_dir}"
                ) from exc
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                path.unlink(missing_ok=True)
                continue
            except PermissionError:
                pass
            raise RuntimeError(
                f"attempt already has an active lease owned by pid {pid}: {attempt_dir}"
            ) from exc
    else:
        raise RuntimeError(f"could not acquire attempt lease: {attempt_dir}")
    os.write(descriptor, json.dumps(identity).encode())
    return descriptor


def _run_attempt(
    adapter,
    domain: str,
    data: str,
    problem: str,
    *,
    attempt_index: int,
    model_label: str,
    record_trace: bool,
    out_dir_root: Path,
    image: str | None,
    domain_description: str,
    problem_description: str,
    prompt: str,
    task_identity: dict,
    runtime_lock: dict,
    runtime_identity_sha256: str,
) -> FormalizerResult:
    attempt_dir = problem_output_dir(
        out_dir_root, domain, data, model_label, problem
    )
    completion_path = attempt_dir / COMPLETION_NAME
    if _completion_matches(
        completion_path,
        adapter.resolved_config.sha256,
        task_identity["sha256"],
        runtime_identity_sha256,
    ):
        (attempt_dir / LEASE_NAME).unlink(missing_ok=True)
        return _result_from_completion(completion_path)
    if completion_path.exists():
        raise RuntimeError(
            f"existing completion identity differs; choose a new config/model label: "
            f"{completion_path}"
        )

    identity = {
        "resolved_config_sha256": adapter.resolved_config.sha256,
        "task_input_sha256": task_identity["sha256"],
        "runtime_identity_sha256": runtime_identity_sha256,
        "attempt_index": attempt_index,
        "pid": os.getpid(),
        "created_at": now_iso(),
    }
    lease = _acquire_lease(attempt_dir, identity)
    execution_root = attempt_dir / "executions"
    existing_indices: list[int] = []
    invalid_executions: list[dict] = []
    if execution_root.is_dir():
        for directory in sorted(execution_root.glob("execution-*")):
            try:
                existing_indices.append(int(directory.name.rsplit("-", 1)[-1]))
            except ValueError:
                continue
            invalid_path = directory / "infra_invalid.json"
            if invalid_path.is_file():
                try:
                    value = json.loads(invalid_path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    invalid_executions.append(value)
    first_execution_try = max(existing_indices, default=0) + 1
    last_execution_try = first_execution_try - 1
    try:
        for execution_try in range(
            first_execution_try,
            first_execution_try + adapter.resolved_config.max_execution_tries,
        ):
            last_execution_try = execution_try
            try:
                result, evidence = _run_execution_try(
                    adapter,
                    domain,
                    data,
                    problem,
                    attempt_index=attempt_index,
                    execution_try=execution_try,
                    model_label=model_label,
                    attempt_dir=attempt_dir,
                    domain_description=domain_description,
                    problem_description=problem_description,
                    prompt=prompt,
                    task_identity=task_identity,
                    runtime_lock=runtime_lock,
                    record_trace=record_trace,
                    image=image,
                )
            except InfraInvalid as exc:
                if exc.reason not in adapter.resolved_config.raw["infra_retry"][
                    "invalidators"
                ]:
                    raise
                invalid = {
                    "execution_try": execution_try,
                    "attempt_valid": False,
                    "infra_invalidator": exc.reason,
                    "error": str(exc),
                    "recorded_at": now_iso(),
                }
                invalid_executions.append(invalid)
                _atomic_json(
                    attempt_dir
                    / "executions"
                    / f"execution-{execution_try:03d}"
                    / "infra_invalid.json",
                    invalid,
                )
                if not exc.retry_execution:
                    attempt_invalid = {
                        "schema_version": 1,
                        "complete": False,
                        "problem": problem,
                        "model_label": model_label,
                        "attempt_index": attempt_index,
                        "attempt_valid": False,
                        "current": True,
                        "status": "infra_invalid",
                        "invalid_executions": invalid_executions,
                        "error": str(exc),
                        "recorded_at": now_iso(),
                    }
                    _atomic_json(attempt_dir / "invalid_attempt.json", attempt_invalid)
                    return FormalizerResult(
                        problem=problem,
                        status="infra_invalid",
                        attempt_index=attempt_index,
                        execution_try=execution_try,
                        attempt_valid=False,
                        generation_success=False,
                        model_label=model_label,
                        error=str(exc),
                    )
                continue
            except Exception as exc:
                reason = "runner_internal_error"
                if reason not in adapter.resolved_config.raw["infra_retry"][
                    "invalidators"
                ]:
                    raise
                invalid = {
                    "execution_try": execution_try,
                    "attempt_valid": False,
                    "infra_invalidator": reason,
                    "error": f"{type(exc).__name__}: {exc}",
                    "recorded_at": now_iso(),
                }
                invalid_executions.append(invalid)
                _atomic_json(
                    attempt_dir
                    / "executions"
                    / f"execution-{execution_try:03d}"
                    / "infra_invalid.json",
                    invalid,
                )
                continue

            artifact_records: dict[str, dict] = {}
            if result.generation_success:
                source_contract = adapter.resolved_config.raw["resolved"][
                    "artifact_contract"
                ]
                source_names = {
                    "domain": source_contract["workspace_domain_file"],
                    "problem": source_contract["workspace_problem_file"],
                }
                payloads = {
                    "domain": result.domain_bytes,
                    "problem": result.problem_bytes,
                }
                output_names = {
                    "domain": f"{problem}_{model_label}_df.pddl",
                    "problem": f"{problem}_{model_label}_pf.pddl",
                }
                for role in ("domain", "problem"):
                    # For ordinary file delivery recover the original bytes from
                    # the frozen snapshot, stored as evidence by re-copying the
                    # result string only when experimental parsing was enabled.
                    content = payloads[role]
                    destination = attempt_dir / output_names[role]
                    destination.write_bytes(content)
                    digest = sha256_bytes(content)
                    if sha256_bytes(destination.read_bytes()) != digest:
                        raise InfraInvalid("required_evidence_failed", "artifact hash mismatch")
                    artifact_records[role] = {
                        "workspace_name": source_names[role],
                        "delivery_name": output_names[role],
                        "bytes": len(content),
                        "sha256": digest,
                    }

            completion = {
                "schema_version": 2,
                "complete": True,
                "profile_name": adapter.resolved_config.label,
                "resolved_config_sha256": adapter.resolved_config.sha256,
                "task_input_sha256": task_identity["sha256"],
                "runtime_identity_sha256": runtime_identity_sha256,
                "problem": problem,
                "model_label": model_label,
                "attempt_index": attempt_index,
                "attempt_valid": True,
                "generation_success": result.generation_success,
                "actions": evidence["actions"],
                "selected_execution_try": execution_try,
                "invalid_executions": invalid_executions,
                "extraction_source": result.extraction_source,
                "error": result.error,
                "artifacts": artifact_records,
                "agent": (
                    {
                        "success": result.agent_result.success,
                        "finish_reason": result.agent_result.finish_reason,
                        "exit_code": result.agent_result.exit_code,
                        "timeout": result.agent_result.timeout,
                        "duration_seconds": result.agent_result.duration_seconds,
                        "usage": result.agent_result.usage,
                    }
                    if result.agent_result
                    else None
                ),
                "evidence": evidence,
                "completed_at": now_iso(),
            }
            _atomic_json(attempt_dir / "metadata.json", completion)
            _atomic_json(completion_path, completion)
            previous_invalid_path = attempt_dir / "invalid_attempt.json"
            if previous_invalid_path.is_file():
                try:
                    previous_invalid = json.loads(previous_invalid_path.read_text())
                except (OSError, json.JSONDecodeError):
                    previous_invalid = {}
                if isinstance(previous_invalid, dict):
                    previous_invalid["current"] = False
                    previous_invalid["superseded_by_valid_execution_try"] = execution_try
                    previous_invalid["superseded_at"] = now_iso()
                    _atomic_json(previous_invalid_path, previous_invalid)
            result.completion_path = completion_path
            return result

        return FormalizerResult(
            problem=problem,
            status="infra_invalid",
            attempt_index=attempt_index,
            execution_try=last_execution_try,
            attempt_valid=False,
            generation_success=False,
            model_label=model_label,
            error=(
                "all execution tries were invalidated by infrastructure: "
                + ", ".join(row["infra_invalidator"] for row in invalid_executions)
            ),
        )
    finally:
        os.close(lease)
        (attempt_dir / LEASE_NAME).unlink(missing_ok=True)


def run_one_problem(
    adapter,
    domain: str,
    data: str,
    problem: str,
    *,
    model_label: str | None = None,
    record_trace: bool = True,
    out_dir_root: Path | None = None,
    image: str | None = None,
    attempt_index: int = 1,
) -> FormalizerResult:
    """Run one fixed attempt (compatibility entry point used by tests/tools)."""
    adapter.validate_runtime()
    _, frozen_image = _freeze_execution_reference(adapter, image)
    try:
        runtime_lock = validate_runtime_lock(
            adapter, container_image_id=frozen_image
        )
    except RuntimeLockMismatch as exc:
        raise InfraInvalid("runtime_lock_mismatch", str(exc)) from exc
    runtime_identity = {
        "runtime_lock": runtime_lock,
        "container_image_id": frozen_image,
        "adapter_code_sha256": _adapter_code_sha256(),
    }
    if adapter.name == "minimum":
        runtime_identity["execution_backend"] = "host"
    runtime_identity_sha256 = canonical_sha256(runtime_identity)
    domain_description, problem_description = _read_descriptions(domain, data, problem)
    prompt = _build_canonical_prompt(
        adapter, domain_description, problem_description
    )
    task = _task_identity(
        domain,
        data,
        problem,
        domain_description,
        problem_description,
        prompt,
    )
    base_label = _config_qualified_label(adapter, model_label)
    total = adapter.resolved_config.attempts_per_case
    actual_label = (
        base_label if total == 1 else f"{base_label}__attempt_{attempt_index:03d}"
    )
    root = Path(out_dir_root) if out_dir_root else OUTPUT_DIR
    return _run_attempt(
        adapter,
        domain,
        data,
        problem,
        attempt_index=attempt_index,
        model_label=actual_label,
        record_trace=record_trace,
        out_dir_root=root,
        image=frozen_image,
        domain_description=domain_description,
        problem_description=problem_description,
        prompt=prompt,
        task_identity=task,
        runtime_lock=runtime_lock,
        runtime_identity_sha256=runtime_identity_sha256,
    )


def run_batch(
    adapter,
    domain: str,
    data: str,
    problem_numbers,
    *,
    model_label: str | None = None,
    record_trace: bool = True,
    out_dir_root: Path | None = None,
    image: str | None = None,
    workers: int = 1,
) -> list[FormalizerResult]:
    """Run every fixed case/attempt; outcomes never affect attempt count."""
    adapter.validate_runtime()
    _, frozen_image = _freeze_execution_reference(adapter, image)
    try:
        runtime_lock = validate_runtime_lock(
            adapter, container_image_id=frozen_image
        )
    except RuntimeLockMismatch as exc:
        raise InfraInvalid("runtime_lock_mismatch", str(exc)) from exc
    runtime_identity = {
        "runtime_lock": runtime_lock,
        "container_image_id": frozen_image,
        "adapter_code_sha256": _adapter_code_sha256(),
    }
    if adapter.name == "minimum":
        runtime_identity["execution_backend"] = "host"
    runtime_identity_sha256 = canonical_sha256(runtime_identity)
    root = Path(out_dir_root) if out_dir_root else OUTPUT_DIR
    base_label = _config_qualified_label(adapter, model_label)
    attempts = adapter.resolved_config.attempts_per_case
    jobs = [
        (problem_number, attempt_index)
        for problem_number in problem_numbers
        for attempt_index in range(1, attempts + 1)
    ]

    def worker(job) -> FormalizerResult:
        problem_number, attempt_index = job
        problem = format_problem_name(problem_number)
        domain_description, problem_description = _read_descriptions(domain, data, problem)
        prompt = _build_canonical_prompt(
            adapter, domain_description, problem_description
        )
        task = _task_identity(
            domain,
            data,
            problem,
            domain_description,
            problem_description,
            prompt,
        )
        actual_label = (
            base_label
            if attempts == 1
            else f"{base_label}__attempt_{attempt_index:03d}"
        )
        print(f"Running {problem} attempt {attempt_index}/{attempts}", flush=True)
        return _run_attempt(
            adapter,
            domain,
            data,
            problem,
            attempt_index=attempt_index,
            model_label=actual_label,
            record_trace=record_trace,
            out_dir_root=root,
            image=frozen_image,
            domain_description=domain_description,
            problem_description=problem_description,
            prompt=prompt,
            task_identity=task,
            runtime_lock=runtime_lock,
            runtime_identity_sha256=runtime_identity_sha256,
        )

    results = run_parallel(jobs, worker, workers=workers)
    by_problem: dict[str, list[FormalizerResult]] = {}
    for result in results:
        by_problem.setdefault(result.problem, []).append(result)
    for problem, problem_results in by_problem.items():
        case_dir = problem_output_dir(root, domain, data, base_label, problem)
        _atomic_json(
            case_dir / "case.json",
            {
                "schema_version": 1,
                "problem": problem,
                "profile_name": adapter.resolved_config.label,
                "resolved_config_sha256": adapter.resolved_config.sha256,
                "runtime_identity_sha256": runtime_identity_sha256,
                "attempts_per_case": attempts,
                "attempts": [
                    {
                        "attempt_index": item.attempt_index,
                        "model_label": item.model_label,
                        "attempt_valid": item.attempt_valid,
                        "status": item.status,
                        "generation_success": item.generation_success,
                        "error": item.error,
                        "completion_path": (
                            str(item.completion_path) if item.completion_path else None
                        ),
                    }
                    for item in sorted(
                        problem_results, key=lambda value: value.attempt_index
                    )
                ],
            },
        )
    valid = sum(1 for result in results if result.attempt_valid)
    generated = sum(1 for result in results if result.generation_success)
    print(
        f"Done: {valid}/{len(results)} valid attempts; "
        f"{generated}/{len(results)} produced official delivery files.",
        flush=True,
    )
    return results
