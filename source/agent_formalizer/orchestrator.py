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

from agent_formalizer.configuration.benchmark_profile import canonical_sha256
from agent_formalizer.configuration.config import (
    OUTPUT_DIR,
    ROOT_DIR,
    BASE_IMAGE,
    agent_model_label,
    container_name as make_container_name,
    domain_dir,
    new_runtime_id,
    problem_output_dir,
)
from agent_formalizer.prompts.prompt import extract_pddl_from_text
from agent_formalizer.results.provenance import (
    docker_image_info,
    file_manifest,
    git_info,
    host_runtime_info,
    sha256_bytes,
    sha256_text,
)
from agent_formalizer.result_types import AgentResult, FormalizerResult
from agent_formalizer.runtime.runtime_lock import (
    RuntimeLockMismatch, execution_runtime_identity, validate_runtime_lock,
)
from agent_formalizer.util import Tracer, format_problem_name, now_iso, run_parallel
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.docker.network_resources import NetworkResources, options_from
from agent_formalizer.claws.minimum.workspace import MinimumHostWorkspace
from agent_formalizer.results.optional_evidence import build_analysis_evidence_manifest
from agent_formalizer.results.execution_validity import (
    ExecutionValidityError,
    refresh_cell_state,
    selected_source_path,
    repair_identity_migration_authorized,
    split_attempt_model_label,
    write_execution_result,
)


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
        and path.suffix in {".py", ".json", ".txt", ".sh", ".c", ".rs", ".js", ".cjs", ".mjs"}
        # Credential registries are operational inputs with their own redacted
        # provenance hash.  Adding/rotating a named profile must not alter the
        # experiment/runtime identity used for labels and resume.
        and path.name != "credential_profiles.json"
        # Selected model semantics are frozen separately; unrelated registry
        # rows must not invalidate an existing study's implementation identity.
        and path.relative_to(package).as_posix() != "configs/model_capabilities.json"
        # Experimental skill payloads have selected-content semantic hashes.
        # Unselected library files must not change any run's runtime identity.
        and path.relative_to(package).parts[0] != "skills"
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
    bundle = adapter.resolved_config.skill_bundle
    if bundle.skills:
        skills = {**skills, "experimental": {
            **bundle.manifest(), "sha256": bundle.sha256,
        }}
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
    usage_collection: dict,
) -> dict:
    session_agent_id = (
        (agent_result.openclaw_agent_id if agent_result else None) or agent_id
    )
    session_id = agent_result.session_id if agent_result else None
    session_file = agent_result.session_file if agent_result else None
    from agent_formalizer.results.optional_evidence import collect_full_trace_evidence
    try:
        collect_full_trace_evidence(artifact_dir, adapter.name, container_name)
    except Exception as exc:
        tracer.emit("full_trace_collection_error", error_type=type(exc).__name__)
    try:
        session_collection = adapter.backup_session(
            session_agent_id,
            artifact_dir,
            session_id=session_id,
            session_file=session_file,
            container_name=container_name,
        )
    except Exception as exc:
        tracer.emit("optional_session_error", error_type=type(exc).__name__)
        session_collection = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "files_copied": 0,
        }

    steps_path = artifact_dir / f"{problem}_{model_label}_agent_steps.jsonl"
    trace_record_count = 0
    steps_error_type: str | None = None
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
        steps_error_type = type(exc).__name__
        tracer.emit("optional_steps_error", error_type=type(exc).__name__)
    steps_collection = {
        "status": (
            "failed_partial"
            if steps_error_type and trace_record_count
            else "failed" if steps_error_type
            else "persisted" if trace_record_count
            else "empty"
        ),
        "path": steps_path.name if steps_path.exists() else None,
        "records": trace_record_count,
        "error_type": steps_error_type,
    }

    traced_tool_call_count = 0
    tool_error_type: str | None = None
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
        tool_error_type = type(exc).__name__
        tracer.emit("optional_tool_trace_error", error_type=type(exc).__name__)
    if tool_error_type:
        tool_status = "failed_partial" if traced_tool_call_count else "failed"
    elif tracer.path:
        tool_status = "persisted" if traced_tool_call_count else "empty"
    else:
        tool_status = (
            "observed_not_persisted" if traced_tool_call_count else "disabled"
        )
    tool_collection = {
        "status": tool_status,
        "records": traced_tool_call_count,
        "trace_path": (
            Path(tracer.path).name if tracer.path else None
        ),
        "error_type": tool_error_type,
    }

    manifest_path = artifact_dir / "analysis_evidence_manifest.json"
    try:
        manifest = build_analysis_evidence_manifest(
            adapter,
            artifact_dir,
            session_collection=session_collection,
            usage_collection=usage_collection,
            steps_collection=steps_collection,
            tool_trace_collection=tool_collection,
        )
    except Exception as exc:
        tracer.emit(
            "optional_evidence_manifest_error", error_type=type(exc).__name__
        )
        manifest = {
            "schema_version": 1,
            "scope": "optional_harness_analysis_evidence",
            "harness": getattr(adapter, "name", "unknown"),
            "model": getattr(adapter, "model", "unknown"),
            "manifest_status": "failed",
            "error_type": type(exc).__name__,
            "collection": {
                "raw_session": session_collection,
                "usage": usage_collection,
                "normalized_agent_steps": steps_collection,
                "normalized_tool_trace": tool_collection,
            },
        }
    manifest_record: dict = {
        "status": manifest.get("manifest_status", "unknown"),
        "schema_version": manifest.get("schema_version"),
        "path": None,
        "sha256": None,
    }
    try:
        _atomic_json(manifest_path, manifest)
        manifest_record.update(
            {
                "path": str(manifest_path),
                "sha256": sha256_bytes(manifest_path.read_bytes()),
            }
        )
    except OSError as exc:
        tracer.emit(
            "optional_evidence_manifest_write_error", error_type=type(exc).__name__
        )
        manifest_record.update(
            {"status": "write_failed", "error_type": type(exc).__name__}
        )

    return {
        "traced_tool_call_count": traced_tool_call_count,
        "agent_trace_record_count": trace_record_count,
        "agent_trace_path": str(steps_path) if steps_path.exists() else None,
        "collection": {
            "raw_session": session_collection,
            "usage": usage_collection,
            "normalized_agent_steps": steps_collection,
            "normalized_tool_trace": tool_collection,
        },
        "analysis_evidence_manifest": manifest_record,
    }


def _ensure_uncollected_analysis_manifest(
    adapter, execution_dir: Path, *, reason: str
) -> dict:
    """Leave an explicit marker when execution ended before normal collection."""
    path = execution_dir / "analysis_evidence_manifest.json"
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        return {
            "status": existing.get("manifest_status", "unknown"),
            "path": str(path),
            "sha256": sha256_bytes(path.read_bytes()),
        }
    empty = {"status": "not_attempted", "reason": reason}
    try:
        manifest = build_analysis_evidence_manifest(
            adapter,
            execution_dir,
            session_collection=empty,
            usage_collection=empty,
            steps_collection=empty,
            tool_trace_collection=empty,
        )
        manifest.pop("content_free_manifest_sha256", None)
        manifest.pop("content_free_manifest_sha256_scope", None)
        manifest["manifest_status"] = "collection_not_reached"
        manifest["collection_boundary_reason"] = reason
        manifest["content_free_manifest_sha256"] = canonical_sha256(manifest)
        manifest["content_free_manifest_sha256_scope"] = (
            "canonical manifest before the hash and hash-scope fields are added"
        )
    except Exception as exc:
        manifest = {
            "schema_version": 1,
            "scope": "optional_harness_analysis_evidence",
            "harness": getattr(adapter, "name", "unknown"),
            "model": getattr(adapter, "model", "unknown"),
            "manifest_status": "failed",
            "collection_boundary_reason": reason,
            "error_type": type(exc).__name__,
        }
    try:
        _atomic_json(path, manifest)
        return {
            "status": manifest["manifest_status"],
            "path": str(path),
            "sha256": sha256_bytes(path.read_bytes()),
        }
    except OSError as exc:
        return {
            "status": "write_failed",
            "path": None,
            "sha256": None,
            "error_type": type(exc).__name__,
        }


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
        "action_step_admission_threshold": int(
            gateway_summary.get("action_step_admission_threshold")
            or adapter.max_action_steps
        ),
        "final_action_steps": int(
            gateway_summary.get("final_action_steps")
            or (model_calls + tool_calls)
        ),
        "action_step_overshoot": int(
            gateway_summary.get("action_step_overshoot", 0) or 0
        ),
        "final_tool_batch_size": int(
            gateway_summary.get("final_tool_batch_size", 0) or 0
        ),
        "max_tool_batch_size": int(
            gateway_summary.get("max_tool_batch_size", 0) or 0
        ),
        "overshoot_causing_logical_call": gateway_summary.get(
            "overshoot_causing_logical_call"
        ),
        "in_flight_at_threshold_crossing": gateway_summary.get(
            "in_flight_at_threshold_crossing"
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
    operational_config=None,
    operational_run_id: str | None = None,
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
    diagnostics_plan = None
    if operational_config is not None:
        diagnostics_plan = operational_config.execution_diagnostics_plan(
            provider=adapter.model_gateway().get("provider", "unknown"),
            run_id=operational_run_id or "standalone",
            domain=domain,
            data=data,
            problem=problem,
            model_label=model_label,
            attempt_index=attempt_index,
            execution_try=execution_try,
            runtime_id=runtime_id,
        )
    workspace = (
        MinimumHostWorkspace(
            instance_id,
            container,
            adapter,
            artifact_dir=execution_dir,
            diagnostics_plan=diagnostics_plan,
        )
        if adapter.name == "minimum"
        else AgentWorkspace(
            instance_id,
            container,
            adapter,
            image=image,
            artifact_dir=execution_dir,
            diagnostics_plan=diagnostics_plan,
            network_options=options_from(operational_config),
            operational_run_id=operational_run_id,
        )
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
    usage_collection = {
        "status": "not_attempted",
        "reason": "native_harness_has_not_exited",
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
        state_isolation_validation = workspace.validate_state_isolation()
        validations.extend([
            runtime_lock,
            network_validation,
            environment_validation,
            action_guard_validation,
            state_isolation_validation,
        ])
        configured_validations = {
            row["preset"]: row
            for row in adapter.resolved_config.raw["resolved"]["validations"]
        }
        if any(
            configured_validations.get(row.get("preset"), {}).get("required", False)
            and (
                row.get("status") != "pass"
                or row.get("version")
                != configured_validations[row.get("preset")]["version"]
            )
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
            adapter.create_agent(agent_id, instance_id=instance_id)
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

        # The measured envelope ends when the native harness returns. Keep the
        # gateway monitor alive for operational settlement, but do not let that
        # bounded collection work consume agent time or trigger the watchdog.
        watchdog_stop.set()
        if watchdog_thread is not None:
            watchdog_thread.join(timeout=10)
        native_exit_clock_snapshot = attempt_clock.snapshot()
        native_exit_finalization = (
            workspace.finalize_model_gateway_after_native_exit()
        )
        gateway_terminal = workspace.gateway_terminal_infra_error()
        gateway_monitor_error = workspace.gateway_monitor_error()
        action_step_limit_reached = (
            workspace.gateway_action_step_limit_reached()
        )
        workspace.stop_model_gateway_monitor()

        if gateway_terminal is not None or gateway_monitor_error is not None:
            clock_finished = time.monotonic()
            clock_snapshot = native_exit_clock_snapshot
            adapter.end_attempt_clock()
            gateway_summary = workspace.model_gateway_stats()
            ledger = workspace.model_gateway_ledger()
            ledger_path = execution_dir / "model_call_ledger.jsonl"
            _write_ledger(ledger_path, ledger)
            reason = gateway_monitor_error or gateway_terminal.get(
                "reason", "provider_transient_exhausted"
            )
            try:
                usage = adapter.collect_usage(workspace, execution_dir) or {}
                if agent_result and usage:
                    agent_result.usage = {**agent_result.usage, **usage}
                usage_collection = {
                    "status": "completed",
                    "values_present": bool(usage),
                    "normalized_fields": (
                        len(usage) if isinstance(usage, dict) else 0
                    ),
                }
            except Exception as exc:
                usage_collection = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "values_present": False,
                }
                tracer.emit("optional_usage_error", error_type=type(exc).__name__)
            optional = _record_optional_evidence(
                adapter,
                agent_id,
                execution_dir,
                problem,
                model_label,
                tracer,
                agent_result,
                container,
                usage_collection,
            )
            invalid_evidence = {
                "schema_version": 1,
                "attempt_valid": False,
                "infra_invalidator": reason,
                "terminal_infra_error": gateway_terminal,
                "native_exit_finalization": native_exit_finalization,
                "execution_timing": clock_snapshot,
                "model_gateway_summary": gateway_summary,
                "actions": _action_metrics(gateway_summary, adapter, execution_dir),
                "model_call_ledger": {
                    "path": str(ledger_path),
                    "entries": len(ledger),
                    "sha256": sha256_bytes(ledger_path.read_bytes()),
                },
                "optional_evidence": optional,
            }
            _atomic_json(execution_dir / "provider_infra_invalid.json", invalid_evidence)
            if gateway_terminal and gateway_terminal.get("source") == "external_calls":
                _atomic_json(execution_dir / "external_call_infra_invalid.json", invalid_evidence)
            raise InfraInvalid(
                reason,
                f"external infrastructure did not yield a valid response: {reason}",
                retry_execution=(
                    adapter.resolved_config.model_response_delivery["mode"]
                    == "native_streaming"
                    and reason == "post_commit_stream_failure"
                ),
            )

        if (
            watchdog_fired.is_set()
            or native_exit_clock_snapshot["deadline_exceeded"]
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
        clock_snapshot = native_exit_clock_snapshot
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
            usage_collection = {
                "status": "completed",
                "values_present": bool(usage),
                "normalized_fields": len(usage) if isinstance(usage, dict) else 0,
            }
        except Exception as exc:
            usage_collection = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "values_present": False,
            }
            tracer.emit("optional_usage_error", error_type=type(exc).__name__)

        gateway_summary = workspace.model_gateway_stats()
        ledger = workspace.model_gateway_ledger()
        _write_ledger(execution_dir / "model_call_ledger.jsonl", ledger)
        optional = _record_optional_evidence(
            adapter,
            agent_id,
            execution_dir,
            problem,
            model_label,
            tracer,
            agent_result,
            container,
            usage_collection,
        )
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
            "native_exit_finalization": native_exit_finalization,
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
        try:
            workspace.stop_model_gateway_monitor()
            adapter.end_attempt_clock()
        except Exception:
            logger.exception("Failed to close clock/monitor; continuing resource cleanup")
        try:
            try:
                adapter.prepare_agent_cleanup(
                    agent_id,
                    instance_id=instance_id,
                    container_name=container,
                )
            except Exception as exc:
                logger.warning(
                    "Could not prepare private harness state cleanup for %s: %s",
                    instance_id,
                    exc,
                )
            workspace.cleanup()
        finally:
            try:
                adapter.delete_agent(agent_id, instance_id=instance_id)
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


def _read_completion(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionValidityError(f"cannot read selected result {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExecutionValidityError(f"selected result is not an object: {path}")
    return value


def _result_from_completion(path: Path) -> FormalizerResult:
    value = _read_completion(path)
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
    operational_config=None,
    operational_run_id: str | None = None,
    validity_cell_dir: Path | None = None,
    attempts_per_case: int | None = None,
) -> FormalizerResult:
    attempt_dir = problem_output_dir(
        out_dir_root, domain, data, model_label, problem
    )
    configured_attempts = int(
        attempts_per_case or adapter.resolved_config.attempts_per_case
    )
    if validity_cell_dir is None:
        base_label, _ = split_attempt_model_label(model_label)
        validity_cell_dir = problem_output_dir(
            out_dir_root, domain, data, base_label, problem
        ).parent
    completion_path = attempt_dir / COMPLETION_NAME
    completion_identity_matches = _completion_matches(
        completion_path,
        adapter.resolved_config.sha256,
        task_identity["sha256"],
        runtime_identity_sha256,
    )
    root_completion_preexisting = completion_path.exists()
    validity_state = refresh_cell_state(
        validity_cell_dir,
        expected_problems=[problem],
        attempts_per_case=configured_attempts,
        resolved_config_sha256=adapter.resolved_config.sha256,
        runtime_identity_sha256=runtime_identity_sha256,
    )
    if (
        completion_path.exists()
        and not completion_identity_matches
        and not repair_identity_migration_authorized(
            validity_state,
            problem,
            attempt_index,
            task_input_sha256=task_identity["sha256"],
            runtime_identity_sha256=runtime_identity_sha256,
        )
    ):
        raise RuntimeError(
            f"existing completion identity differs; choose a new config/model label: "
            f"{completion_path}"
        )
    previous_invalid_path = attempt_dir / "invalid_attempt.json"
    previous_invalid = _read_completion(previous_invalid_path) if previous_invalid_path.is_file() else None
    if (
        not completion_path.exists()
        and previous_invalid
        and previous_invalid.get("runtime_identity_sha256") != runtime_identity_sha256
        and not repair_identity_migration_authorized(
            validity_state, problem, attempt_index,
            task_input_sha256=task_identity["sha256"],
            runtime_identity_sha256=runtime_identity_sha256,
        )
    ):
        raise ExecutionValidityError(
            f"automatically-invalid attempt needs an exact authorized repair runtime: {attempt_dir}"
        )
    effective_source = selected_source_path(
        validity_cell_dir, validity_state, problem, attempt_index
    )
    if effective_source is not None:
        value = _read_completion(effective_source)
        if not (
            value.get("resolved_config_sha256") == adapter.resolved_config.sha256
            and value.get("task_input_sha256") == task_identity["sha256"]
            and value.get("runtime_identity_sha256") == runtime_identity_sha256
        ):
            raise ExecutionValidityError(
                f"selected execution identity differs from current attempt: {effective_source}"
            )
        (attempt_dir / LEASE_NAME).unlink(missing_ok=True)
        return _result_from_completion(effective_source)

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
    try:
        existing_indices: list[int] = [
            int(value)
            for value in validity_state["problems"][problem]["attempts"][
                str(attempt_index)
            ]["executions"]
        ]
    except (KeyError, TypeError, ValueError):
        existing_indices = []
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
                    operational_config=operational_config,
                    operational_run_id=operational_run_id,
                )
            except InfraInvalid as exc:
                if exc.reason not in adapter.resolved_config.raw["infra_retry"][
                    "invalidators"
                ]:
                    raise
                execution_dir = (
                    attempt_dir
                    / "executions"
                    / f"execution-{execution_try:03d}"
                )
                analysis_manifest = _ensure_uncollected_analysis_manifest(
                    adapter, execution_dir, reason=exc.reason
                )
                invalid = {
                    "execution_try": execution_try,
                    "attempt_valid": False,
                    "infra_invalidator": exc.reason,
                    "error": str(exc),
                    "analysis_evidence_manifest": analysis_manifest,
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
                refresh_cell_state(
                    validity_cell_dir,
                    expected_problems=[problem],
                    attempts_per_case=configured_attempts,
                    resolved_config_sha256=adapter.resolved_config.sha256,
                    runtime_identity_sha256=runtime_identity_sha256,
                )
                if not exc.retry_execution:
                    attempt_invalid = {
                        "schema_version": 1,
                        "complete": False,
                        "problem": problem,
                        "model_label": model_label,
                        "attempt_index": attempt_index,
                        "resolved_config_sha256": adapter.resolved_config.sha256,
                        "task_input_sha256": task_identity["sha256"],
                        "runtime_identity_sha256": runtime_identity_sha256,
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
                execution_dir = (
                    attempt_dir
                    / "executions"
                    / f"execution-{execution_try:03d}"
                )
                analysis_manifest = _ensure_uncollected_analysis_manifest(
                    adapter, execution_dir, reason=reason
                )
                invalid = {
                    "execution_try": execution_try,
                    "attempt_valid": False,
                    "infra_invalidator": reason,
                    "error": f"{type(exc).__name__}: {exc}",
                    "analysis_evidence_manifest": analysis_manifest,
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
                refresh_cell_state(
                    validity_cell_dir,
                    expected_problems=[problem],
                    attempts_per_case=configured_attempts,
                    resolved_config_sha256=adapter.resolved_config.sha256,
                    runtime_identity_sha256=runtime_identity_sha256,
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
                    digest = sha256_bytes(content)
                    if not root_completion_preexisting:
                        destination.write_bytes(content)
                        if sha256_bytes(destination.read_bytes()) != digest:
                            raise InfraInvalid(
                                "required_evidence_failed", "artifact hash mismatch"
                            )
                    artifact_records[role] = {
                        "workspace_name": source_names[role],
                        "delivery_name": output_names[role],
                        "bytes": len(content),
                        "sha256": digest,
                        "materialized_at_attempt_root": (
                            not root_completion_preexisting
                        ),
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
            execution_result_path = write_execution_result(
                attempt_dir
                / "executions"
                / f"execution-{execution_try:03d}",
                completion,
            )
            # ``completion.json`` is the immutable first automatically valid
            # completion for compatibility.  Manual adjudication and repairs
            # are represented only by the cell ledger and per-execution result.
            if not completion_path.exists():
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
            validity_state = refresh_cell_state(
                validity_cell_dir,
                expected_problems=[problem],
                attempts_per_case=configured_attempts,
                resolved_config_sha256=adapter.resolved_config.sha256,
                runtime_identity_sha256=runtime_identity_sha256,
            )
            effective_source = selected_source_path(
                validity_cell_dir, validity_state, problem, attempt_index
            )
            acceptable_sources = {execution_result_path.resolve()}
            if not root_completion_preexisting:
                acceptable_sources.add(completion_path.resolve())
            if effective_source not in acceptable_sources:
                raise ExecutionValidityError(
                    "new valid execution was not selected by chronological policy"
                )
            result.completion_path = (
                execution_result_path
                if root_completion_preexisting
                else completion_path
            )
            return result

        exhausted_status = (
            "incomplete"
            if adapter.resolved_config.model_response_delivery["mode"]
            == "native_streaming"
            else "infra_invalid"
        )
        _atomic_json(
            attempt_dir / "invalid_attempt.json",
            {
                "schema_version": 1,
                "complete": False,
                "problem": problem,
                "model_label": model_label,
                "attempt_index": attempt_index,
                "resolved_config_sha256": adapter.resolved_config.sha256,
                "task_input_sha256": task_identity["sha256"],
                "runtime_identity_sha256": runtime_identity_sha256,
                "attempt_valid": False,
                "current": True,
                "status": exhausted_status,
                "invalid_executions": invalid_executions,
                "recorded_at": now_iso(),
            },
        )
        refresh_cell_state(
            validity_cell_dir,
            expected_problems=[problem],
            attempts_per_case=configured_attempts,
            resolved_config_sha256=adapter.resolved_config.sha256,
            runtime_identity_sha256=runtime_identity_sha256,
        )
        return FormalizerResult(
            problem=problem,
            status=exhausted_status,
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
    operational_config=None,
    operational_run_id: str | None = None,
    runtime_lock_path: Path | str | None = None,
) -> FormalizerResult:
    """Run one fixed attempt (compatibility entry point used by tests/tools)."""
    adapter.validate_runtime()
    _, frozen_image = _freeze_execution_reference(adapter, image)
    try:
        runtime_lock = validate_runtime_lock(
            adapter, container_image_id=frozen_image,
            **({"lock_path": runtime_lock_path} if runtime_lock_path is not None else {}),
        )
    except RuntimeLockMismatch as exc:
        raise InfraInvalid("runtime_lock_mismatch", str(exc)) from exc
    runtime_identity = execution_runtime_identity(
        runtime_lock, frozen_image, _adapter_code_sha256(), host_only=adapter.name == "minimum")
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
    validity_cell_dir = problem_output_dir(
        root, domain, data, base_label, problem
    ).parent
    refresh_cell_state(
        validity_cell_dir,
        expected_problems=[problem],
        attempts_per_case=total,
        resolved_config_sha256=adapter.resolved_config.sha256,
        runtime_identity_sha256=runtime_identity_sha256,
    )
    resolved_operational_run_id = operational_run_id or (
        f"formalizer-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    )
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
        operational_config=operational_config,
        operational_run_id=resolved_operational_run_id,
        validity_cell_dir=validity_cell_dir,
        attempts_per_case=total,
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
    operational_config=None,
    operational_run_id: str | None = None,
    runtime_lock_path: Path | str | None = None,
) -> list[FormalizerResult]:
    """Run every fixed case/attempt; outcomes never affect attempt count."""
    adapter.validate_runtime()
    _, frozen_image = _freeze_execution_reference(adapter, image)
    try:
        runtime_lock = validate_runtime_lock(
            adapter, container_image_id=frozen_image,
            **({"lock_path": runtime_lock_path} if runtime_lock_path is not None else {}),
        )
    except RuntimeLockMismatch as exc:
        raise InfraInvalid("runtime_lock_mismatch", str(exc)) from exc
    runtime_identity = execution_runtime_identity(
        runtime_lock, frozen_image, _adapter_code_sha256(), host_only=adapter.name == "minimum")
    runtime_identity_sha256 = canonical_sha256(runtime_identity)
    root = Path(out_dir_root) if out_dir_root else OUTPUT_DIR
    base_label = _config_qualified_label(adapter, model_label)
    attempts = adapter.resolved_config.attempts_per_case
    resolved_operational_run_id = operational_run_id or (
        f"formalizer-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    )
    problem_numbers = list(problem_numbers)
    expected_problems = [format_problem_name(value) for value in problem_numbers]
    validity_cell_dir = problem_output_dir(
        root, domain, data, base_label, expected_problems[0] if expected_problems else "p00"
    ).parent
    validity_state = refresh_cell_state(
        validity_cell_dir,
        expected_problems=expected_problems,
        attempts_per_case=attempts,
        resolved_config_sha256=adapter.resolved_config.sha256,
        runtime_identity_sha256=runtime_identity_sha256,
    )
    jobs = [
        (problem_number, attempt_index)
        for problem_number in problem_numbers
        for attempt_index in range(1, attempts + 1)
    ]

    pending_jobs = [
        job for job in jobs
        if validity_state.get("problems", {}).get(format_problem_name(job[0]), {})
        .get("attempts", {}).get(str(job[1]), {}).get("selected_execution") is None
    ]
    if pending_jobs and adapter.name != "minimum":
        # Before worker dispatch and before execution retries/agent clocks.
        NetworkResources(
            options=options_from(operational_config),
            evidence_dir=root / "network_preflight",
        ).preflight(min(workers, len(pending_jobs)))

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
            operational_config=operational_config,
            operational_run_id=resolved_operational_run_id,
            validity_cell_dir=validity_cell_dir,
            attempts_per_case=attempts,
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
