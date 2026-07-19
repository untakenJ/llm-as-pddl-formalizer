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
    problem_output_dir,
)
from agent_formalizer.prompt import build_prompt, extract_pddl_from_text
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


logger = logging.getLogger(__name__)
COMPLETION_NAME = "completion.json"
LEASE_NAME = ".attempt.lease"


class InfraInvalid(RuntimeError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


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
    contract = adapter.resolved_config.raw["resolved"]["artifact_contract"]
    return build_prompt(
        domain_description,
        problem_description,
        template_path=None,
        domain_output_name=contract["workspace_domain_file"],
        problem_output_name=contract["workspace_problem_file"],
        agent_tools=adapter.resolved_config.agent_tools,
    )


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


def _adapter_code_sha256() -> str:
    package = Path(__file__).resolve().parent
    paths = [
        path
        for path in package.glob("**/*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json", ".txt", ".sh"}
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


def _provenance(adapter, prompt: str, image: str, runtime_lock: dict) -> dict:
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
        "container_image": docker_image_info(image),
        "host_runtime": host_runtime_info(),
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
    step_count = 0
    try:
        with steps_path.open("w", buffering=1) as stream:
            for record in adapter.iter_agent_steps(
                session_agent_id,
                artifact_dir,
                session_id=session_id,
                session_file=session_file,
            ):
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                step_count += 1
    except Exception as exc:
        tracer.emit("optional_steps_error", error_type=type(exc).__name__)

    tool_count = 0
    try:
        for record in adapter.iter_tool_calls(
            session_agent_id,
            artifact_dir,
            session_id=session_id,
            session_file=session_file,
        ):
            tracer.emit("tool_exec", provider=adapter.name, **record)
            tool_count += 1
    except Exception as exc:
        tracer.emit("optional_tool_trace_error", error_type=type(exc).__name__)
    return tool_count, step_count, str(steps_path) if steps_path.exists() else None


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
    instance_id = f"{domain}-{data}-{problem}-a{attempt_index:03d}-e{execution_try:03d}"
    agent_id = f"pddl-{instance_id}-{model_label}".replace(".", "-").replace("/", "-")
    container = make_container_name(
        adapter.name, domain, data, model_label, f"{problem}-a{attempt_index}-e{execution_try}"
    )
    workspace = AgentWorkspace(instance_id, container, adapter, image=image)
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
    watchdog: threading.Timer | None = None
    watchdog_fired = threading.Event()
    optional = {"tool_call_count": 0, "step_count": 0, "agent_steps_path": None}

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
        model_guard_validation = workspace.validate_model_call_guard()
        validations.extend([
            runtime_lock,
            network_validation,
            environment_validation,
            model_guard_validation,
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
        adapter.begin_attempt_clock()
        def enforce_deadline() -> None:
            watchdog_fired.set()
            workspace.enforce_agent_deadline()

        watchdog = threading.Timer(adapter.remaining_timeout(), enforce_deadline)
        watchdog.daemon = True
        watchdog.start()
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
            subprocess.run(
                ["docker", "kill", container], capture_output=True
            )
            harness_exception = f"{type(exc).__name__}: {exc}"
            agent_result = _agent_error_result(harness_exception, clock_started)

        if (
            watchdog_fired.is_set() or adapter.deadline_exceeded()
        ) and agent_result and not agent_result.timeout:
            workspace.enforce_agent_deadline()
            agent_result.success = False
            agent_result.timeout = True
            agent_result.finish_reason = "timeout"

        if agent_result and agent_result.timeout:
            workspace.enforce_agent_deadline()

        # Stop the agent clock at native harness exit. Collection remains
        # operational work and cannot consume or extend the agent budget.
        clock_finished = time.monotonic()
        if watchdog is not None:
            watchdog.cancel()
        adapter.end_attempt_clock()
        harness_duration = round(clock_finished - clock_started, 6)

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
        tool_count, step_count, steps_path = _record_optional_evidence(
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
            "tool_call_count": tool_count,
            "step_count": step_count,
            "agent_steps_path": steps_path,
        }

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
                "deadline_exceeded": bool(agent_result and agent_result.timeout),
            },
            "operational_timing": {
                "scope": "execution_try_start_through_required_evidence_collection",
                "duration_seconds": round(time.monotonic() - operational_started, 6),
            },
            "validations": validations,
            "model_gateway_summary": gateway_summary,
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
        )
        return result, evidence
    finally:
        if watchdog is not None:
            watchdog.cancel()
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
    invalid_executions: list[dict] = []
    try:
        for execution_try in range(1, adapter.resolved_config.max_execution_tries + 1):
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
            result.completion_path = completion_path
            return result

        return FormalizerResult(
            problem=problem,
            status="infra_invalid",
            attempt_index=attempt_index,
            execution_try=adapter.resolved_config.max_execution_tries,
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
    _, frozen_image = _freeze_image_reference(image)
    try:
        runtime_lock = validate_runtime_lock(
            adapter, container_image_id=frozen_image
        )
    except RuntimeLockMismatch as exc:
        raise InfraInvalid("runtime_lock_mismatch", str(exc)) from exc
    runtime_identity_sha256 = canonical_sha256(
        {
            "runtime_lock": runtime_lock,
            "container_image_id": frozen_image,
            "adapter_code_sha256": _adapter_code_sha256(),
        }
    )
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
    _, frozen_image = _freeze_image_reference(image)
    try:
        runtime_lock = validate_runtime_lock(
            adapter, container_image_id=frozen_image
        )
    except RuntimeLockMismatch as exc:
        raise InfraInvalid("runtime_lock_mismatch", str(exc)) from exc
    runtime_identity_sha256 = canonical_sha256(
        {
            "runtime_lock": runtime_lock,
            "container_image_id": frozen_image,
            "adapter_code_sha256": _adapter_code_sha256(),
        }
    )
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
                        "generation_success": item.generation_success,
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
