"""Auditable execution validity and selection for one comparison cell.

The immutable execution directories and their automatic terminal records are the
source of truth.  ``execution_validity.json`` is a deterministic materialized
view of those records plus the append-only manual event ledger; editing the view
does not change the effective selection because every consumer rebuilds it.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


SCHEMA_VERSION = 1
STATE_NAME = "execution_validity.json"
EVENTS_NAME = "execution_validity_events.jsonl"
LOCK_NAME = ".execution_validity.lock"
EXECUTION_RESULT_NAME = "execution_result.json"
_ATTEMPT_SUFFIX = re.compile(r"^(?P<base>.+)__attempt_(?P<index>[0-9]{3})$")
_PROBLEM_NAME = re.compile(r"^p[0-9]+$")
_EXECUTION_NAME = re.compile(r"^execution-(?P<index>[0-9]+)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionValidityError(RuntimeError):
    """The validity ledger or its requested mutation is invalid."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _relative(path: Path, cell_dir: Path) -> str:
    return os.path.relpath(path.resolve(), cell_dir.resolve())


def _from_relative(value: str, cell_dir: Path) -> Path:
    return (cell_dir / value).resolve()


@contextlib.contextmanager
def _cell_lock(cell_dir: Path) -> Iterator[None]:
    cell_dir.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(cell_dir / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def split_attempt_model_label(model_label: str) -> tuple[str, int]:
    """Return the comparison-cell label and attempt represented by a label."""
    match = _ATTEMPT_SUFFIX.fullmatch(model_label)
    if match is None:
        return model_label, 1
    return match.group("base"), int(match.group("index"))


def cell_dir_for_model_dir(model_dir: Path) -> tuple[Path, int]:
    base_label, attempt_index = split_attempt_model_label(model_dir.name)
    return model_dir.parent / base_label, attempt_index


def validity_is_managed_for_model_dir(model_dir: Path, problem: str) -> bool:
    """Whether an agent output has execution records governed by this layer."""
    model_dir = Path(model_dir)
    cell_dir, _ = cell_dir_for_model_dir(model_dir)
    problem_dir = model_dir / problem
    return any(
        path.exists()
        for path in (
            cell_dir / STATE_NAME,
            cell_dir / EVENTS_NAME,
            problem_dir / "completion.json",
            problem_dir / "executions",
            problem_dir / "invalid_attempt.json",
        )
    )


def attempt_dir_for(
    cell_dir: Path, problem: str, attempt_index: int, attempts_per_case: int
) -> Path:
    if attempts_per_case == 1:
        return cell_dir / problem
    return (
        cell_dir.parent
        / f"{cell_dir.name}__attempt_{attempt_index:03d}"
        / problem
    )


def _load_verified_previous_state(cell_dir: Path) -> dict | None:
    path = cell_dir / STATE_NAME
    value = _read_json(path)
    if not path.exists():
        return None
    if value is None or value.get("schema_version") != SCHEMA_VERSION:
        raise ExecutionValidityError(
            f"materialized validity state is unreadable or has an unsupported schema: {path}"
        )
    recorded = value.get("state_sha256")
    unsigned = dict(value)
    unsigned.pop("state_sha256", None)
    if recorded != _sha256_bytes(_canonical_bytes(unsigned)):
        raise ExecutionValidityError(
            f"materialized validity state hash mismatch; do not edit it directly: {path}"
        )
    return value


def _load_events(cell_dir: Path) -> tuple[list[dict], dict]:
    path = cell_dir / EVENTS_NAME
    if not path.is_file():
        return [], {
            "path": EVENTS_NAME,
            "count": 0,
            "sha256": None,
            "last_event_sha256": None,
        }
    raw = path.read_bytes()
    events: list[dict] = []
    previous_hash: str | None = None
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExecutionValidityError(
                f"invalid JSON in {path} line {line_number}: {exc}"
            ) from exc
        if not isinstance(event, dict):
            raise ExecutionValidityError(
                f"event in {path} line {line_number} is not an object"
            )
        recorded_hash = event.get("event_sha256")
        unsigned = dict(event)
        unsigned.pop("event_sha256", None)
        computed_hash = _sha256_bytes(_canonical_bytes(unsigned))
        if recorded_hash != computed_hash:
            raise ExecutionValidityError(
                f"event hash mismatch in {path} line {line_number}"
            )
        if event.get("previous_event_sha256") != previous_hash:
            raise ExecutionValidityError(
                f"event chain mismatch in {path} line {line_number}"
            )
        if event.get("action") not in {"invalidate", "reinstate", "authorize_repair"}:
            raise ExecutionValidityError(
                f"unsupported action in {path} line {line_number}"
            )
        previous_hash = recorded_hash
        events.append(event)
    return events, {
        "path": EVENTS_NAME,
        "count": len(events),
        "sha256": _sha256_bytes(raw),
        "last_event_sha256": previous_hash,
    }


def _discover_pairs(
    cell_dir: Path,
    *,
    expected_problems: Iterable[str] | None,
    attempts_per_case: int | None,
    previous_state: dict | None,
) -> tuple[list[tuple[str, int]], int]:
    problems = {str(value) for value in (expected_problems or [])}
    discovered_attempts = int(attempts_per_case or 0)

    if previous_state:
        expected = previous_state.get("expected", {})
        problems.update(
            value
            for value in expected.get("problems", [])
            if isinstance(value, str)
        )
        discovered_attempts = max(
            discovered_attempts, int(expected.get("attempts_per_case", 0) or 0)
        )

    if cell_dir.is_dir():
        for path in cell_dir.iterdir():
            if path.is_dir() and _PROBLEM_NAME.fullmatch(path.name):
                problems.add(path.name)
                case = _read_json(path / "case.json") or {}
                discovered_attempts = max(
                    discovered_attempts,
                    int(case.get("attempts_per_case", 0) or 0),
                )

    sibling_prefix = f"{cell_dir.name}__attempt_"
    if cell_dir.parent.is_dir():
        for sibling in cell_dir.parent.iterdir():
            if not sibling.is_dir() or not sibling.name.startswith(sibling_prefix):
                continue
            _, index = split_attempt_model_label(sibling.name)
            discovered_attempts = max(discovered_attempts, index)
            for path in sibling.iterdir():
                if path.is_dir() and _PROBLEM_NAME.fullmatch(path.name):
                    problems.add(path.name)

    if discovered_attempts <= 0:
        discovered_attempts = 1
    return (
        [
            (problem, attempt_index)
            for problem in sorted(problems)
            for attempt_index in range(1, discovered_attempts + 1)
        ],
        discovered_attempts,
    )


def _record_reference(path: Path, cell_dir: Path) -> dict:
    return {
        "path": _relative(path, cell_dir),
        "sha256": _sha256_file(path),
    }


def _artifact_reference(
    execution_dir: Path,
    role: str,
    source: dict | None,
    cell_dir: Path,
    *,
    allow_delivery_fallback: bool,
) -> dict | None:
    expected_sha256: str | None = None
    candidates: list[Path] = [
        execution_dir / "frozen_workspace" / f"{role}.pddl",
        execution_dir / "frozen_workspace" / (
            "domain.pddl" if role == "domain" else "problem.pddl"
        ),
    ]
    if source:
        frozen = source.get("evidence", {}).get("frozen_workspace_artifacts", {})
        record = frozen.get(role) if isinstance(frozen, dict) else None
        if isinstance(record, dict) and isinstance(record.get("path"), str):
            if isinstance(record.get("sha256"), str):
                expected_sha256 = record["sha256"]
            stored = Path(record["path"])
            candidates.append(execution_dir / "frozen_workspace" / stored.name)
            candidates.append(stored if stored.is_absolute() else cell_dir / stored)
        if allow_delivery_fallback:
            delivered = source.get("artifacts", {}).get(role)
            if isinstance(delivered, dict) and isinstance(
                delivered.get("delivery_name"), str
            ):
                if expected_sha256 is None and isinstance(
                    delivered.get("sha256"), str
                ):
                    expected_sha256 = delivered["sha256"]
                candidates.append(
                    execution_dir.parents[1] / delivered["delivery_name"]
                )
    for candidate in candidates:
        if candidate.is_file():
            digest = _sha256_file(candidate)
            if expected_sha256 is not None and digest != expected_sha256:
                raise ExecutionValidityError(
                    f"selected frozen artifact hash mismatch: {candidate}"
                )
            return {
                "path": _relative(candidate, cell_dir),
                "bytes": candidate.stat().st_size,
                "sha256": digest,
            }
    return None


def _scan_attempt(
    cell_dir: Path,
    attempt_dir: Path,
    *,
    problem: str,
    attempt_index: int,
    latest_events: dict[tuple[str, int, int], dict],
) -> dict:
    completion_path = attempt_dir / "completion.json"
    completion = _read_json(completion_path)
    metadata = _read_json(attempt_dir / "metadata.json")
    if completion is not None and metadata is not None and completion != metadata:
        raise ExecutionValidityError(
            f"completion.json differs from its immutable metadata mirror: {attempt_dir}"
        )
    invalid_attempt_path = attempt_dir / "invalid_attempt.json"
    invalid_attempt = _read_json(invalid_attempt_path)
    selected_by_completion = (
        int(completion.get("selected_execution_try", 1))
        if completion
        and completion.get("complete") is True
        and completion.get("attempt_valid") is True
        else None
    )
    execution_dirs: dict[int, Path] = {}
    fallback_invalid_execution_try: int | None = None
    execution_root = attempt_dir / "executions"
    if execution_root.is_dir():
        for path in execution_root.iterdir():
            match = _EXECUTION_NAME.fullmatch(path.name)
            if path.is_dir() and match:
                execution_dirs[int(match.group("index"))] = path
    if selected_by_completion is not None:
        execution_dirs.setdefault(
            selected_by_completion,
            execution_root / f"execution-{selected_by_completion:03d}",
        )
    if (
        not execution_dirs
        and invalid_attempt
        and invalid_attempt.get("attempt_valid") is False
        and invalid_attempt.get("status") in {"infra_invalid", "incomplete"}
    ):
        invalid_rows = invalid_attempt.get("invalid_executions", [])
        fallback_try = max(
            (
                int(row.get("execution_try", 0))
                for row in invalid_rows
                if isinstance(row, dict)
            ),
            default=1,
        )
        execution_dirs[fallback_try] = (
            execution_root / f"execution-{fallback_try:03d}"
        )
        fallback_invalid_execution_try = fallback_try

    completion_invalid = {}
    if completion:
        for value in completion.get("invalid_executions", []):
            if isinstance(value, dict) and value.get("execution_try") is not None:
                completion_invalid[int(value["execution_try"])] = value

    executions: dict[str, dict] = {}
    for execution_try, execution_dir in sorted(execution_dirs.items()):
        result_path = execution_dir / EXECUTION_RESULT_NAME
        invalid_path = execution_dir / "infra_invalid.json"
        result_record = _read_json(result_path)
        invalid_record = _read_json(invalid_path)
        source_path: Path | None = None
        source: dict | None = None
        automatic_valid: bool | None
        if (
            execution_try == selected_by_completion
            and completion is not None
            and result_record is not None
            and completion != result_record
        ):
            raise ExecutionValidityError(
                f"completion.json differs from execution result: {result_path}"
            )
        if execution_try == selected_by_completion and completion is not None:
            # Keep the historical root completion as the compatibility source
            # for the first valid execution.  Later repair executions are
            # sourced from their own immutable execution_result.json.
            automatic_valid = True
            source_path, source = completion_path, completion
        elif result_record and result_record.get("attempt_valid") is True:
            automatic_valid = True
            source_path, source = result_path, result_record
        elif invalid_record and invalid_record.get("attempt_valid") is False:
            automatic_valid = False
            source_path, source = invalid_path, invalid_record
        elif execution_try in completion_invalid:
            automatic_valid = False
            source = completion_invalid[execution_try]
        elif (
            execution_try == fallback_invalid_execution_try
            and invalid_attempt
            and invalid_attempt.get("attempt_valid") is False
        ):
            automatic_valid = False
            source_path, source = invalid_attempt_path, invalid_attempt
        else:
            automatic_valid = None
            source = None

        event = latest_events.get((problem, attempt_index, execution_try))
        manually_invalid = bool(event and event.get("action") == "invalidate")
        effective_valid = automatic_valid is True and not manually_invalid
        record = {
            "execution_try": execution_try,
            "automatic_valid": automatic_valid,
            "effective_valid": effective_valid,
            "generation_success": (
                bool(source.get("generation_success"))
                if source and source.get("generation_success") is not None
                else None
            ),
            "source_record": (
                _record_reference(source_path, cell_dir) if source_path else None
            ),
            "manual_override": event,
            "identity": (
                {
                    key: source.get(key)
                    for key in (
                        "resolved_config_sha256",
                        "task_input_sha256",
                        "runtime_identity_sha256",
                    )
                    if source.get(key) is not None
                }
                if source
                else {}
            ),
            "artifacts": {},
        }
        for role in ("domain", "problem"):
            artifact = _artifact_reference(
                execution_dir,
                role,
                source,
                cell_dir,
                allow_delivery_fallback=(source_path == completion_path),
            )
            if artifact:
                record["artifacts"][role] = artifact
        executions[str(execution_try)] = record

    selected = next(
        (
            int(key)
            for key, value in executions.items()
            if value["effective_valid"] is True
        ),
        None,
    )
    return {
        "attempt_index": attempt_index,
        "attempt_dir": _relative(attempt_dir, cell_dir),
        "executions": executions,
        "selected_execution": selected,
        "repair_required": selected is None,
    }


def _identity_from_sources(
    cell_dir: Path,
    pairs: list[tuple[str, int]],
    attempts_per_case: int,
    supplied_config_hash: str | None,
    supplied_runtime_hash: str | None,
    latest_events: dict[tuple[str, int, int], dict],
) -> tuple[str | None, str | None, list[str]]:
    config_hashes = {supplied_config_hash} if supplied_config_hash else set()
    runtime_hashes = {supplied_runtime_hash} if supplied_runtime_hash else set()
    for problem, attempt_index in pairs:
        attempt_dir = attempt_dir_for(
            cell_dir, problem, attempt_index, attempts_per_case
        )
        for name in ("completion.json", "metadata.json", "invalid_attempt.json"):
            value = _read_json(attempt_dir / name)
            if not value:
                continue
            if value.get("resolved_config_sha256"):
                config_hashes.add(value["resolved_config_sha256"])
            if value.get("runtime_identity_sha256"):
                runtime_hashes.add(value["runtime_identity_sha256"])
    if len(config_hashes) > 1:
        raise ExecutionValidityError(
            "comparison cell contains mixed resolved configuration identities"
        )
    authorized_repair_runtime_hashes = sorted(
        {
            str(event["replacement_runtime_identity_sha256"])
            for event in latest_events.values()
            if event.get("action") in {"invalidate", "authorize_repair"}
            and str(event.get("reason_code", "")).startswith(
                ("dataset_update.", "tool_infra.")
            )
            and _SHA256.fullmatch(
                str(event.get("replacement_runtime_identity_sha256", ""))
            )
        }
    )
    if len(runtime_hashes) > 1:
        # Repaired automatically-invalid attempts can create their FIRST root
        # completion under the authorized runtime. Subsequent read-only audits
        # still supply the historical cell identity; accept only explicitly
        # authorized replacements alongside that one historical identity.
        historical_runtime_hashes = runtime_hashes - set(authorized_repair_runtime_hashes)
        if len(historical_runtime_hashes) != 1:
            raise ExecutionValidityError(
                "comparison cell contains mixed runtime identities without an "
                "exact authorized repair runtime"
            )
        runtime_hash = next(iter(historical_runtime_hashes))
    else:
        runtime_hash = next(iter(runtime_hashes), None)
    return (
        next(iter(config_hashes), None),
        runtime_hash,
        authorized_repair_runtime_hashes,
    )


def _build_state_unlocked(
    cell_dir: Path,
    *,
    expected_problems: Iterable[str] | None = None,
    attempts_per_case: int | None = None,
    resolved_config_sha256: str | None = None,
    runtime_identity_sha256: str | None = None,
) -> dict:
    previous = _load_verified_previous_state(cell_dir)
    pairs, discovered_attempts = _discover_pairs(
        cell_dir,
        expected_problems=expected_problems,
        attempts_per_case=attempts_per_case,
        previous_state=previous,
    )
    events, event_metadata = _load_events(cell_dir)
    latest_events: dict[tuple[str, int, int], dict] = {}
    for event in events:
        latest_events[
            (
                str(event["problem"]),
                int(event["attempt_index"]),
                int(event["execution_try"]),
            )
        ] = event
    config_hash, runtime_hash, authorized_repair_runtime_hashes = _identity_from_sources(
        cell_dir,
        pairs,
        discovered_attempts,
        resolved_config_sha256
        or (
            previous.get("cell", {}).get("resolved_config_sha256")
            if previous
            else None
        ),
        runtime_identity_sha256
        or (
            previous.get("cell", {}).get("runtime_identity_sha256")
            if previous
            else None
        ),
        latest_events,
    )

    problems: dict[str, dict] = {}
    selected_count = 0
    automatic_records = 0
    for problem, attempt_index in pairs:
        attempt_dir = attempt_dir_for(
            cell_dir, problem, attempt_index, discovered_attempts
        )
        attempt = _scan_attempt(
            cell_dir,
            attempt_dir,
            problem=problem,
            attempt_index=attempt_index,
            latest_events=latest_events,
        )
        problems.setdefault(problem, {"attempts": {}})["attempts"][
            str(attempt_index)
        ] = attempt
        selected_count += int(attempt["selected_execution"] is not None)
        automatic_records += sum(
            value["automatic_valid"] is not None
            for value in attempt["executions"].values()
        )

    expected_problem_names = sorted({problem for problem, _ in pairs})
    expected_pair_count = len(pairs)
    observed_runtime_hashes = sorted(
        {
            identity["runtime_identity_sha256"]
            for problem_value in problems.values()
            for attempt in problem_value["attempts"].values()
            for execution in attempt["executions"].values()
            if (
                (identity := execution.get("identity", {})).get(
                    "runtime_identity_sha256"
                )
            )
        }
    )
    state = {
        "schema_version": SCHEMA_VERSION,
        "policy": {
            "automatic_default": "terminal execution records",
            "manual_override": "append-only invalidate/reinstate events",
            "selection": "chronologically first effective-valid execution",
            "evaluation_infra_affects_execution_validity": False,
        },
        "revision": automatic_records + len(events),
        "cell": {
            "path": ".",
            "resolved_config_sha256": config_hash,
            "runtime_identity_sha256": runtime_hash,
            "observed_runtime_identity_sha256s": observed_runtime_hashes,
            "authorized_dataset_update_repair_runtime_identity_sha256s": (
                sorted(
                    {
                        str(event["replacement_runtime_identity_sha256"])
                        for event in latest_events.values()
                        if event.get("action") == "invalidate"
                        and str(event.get("reason_code", "")).startswith(
                            "dataset_update."
                        )
                        and _SHA256.fullmatch(
                            str(event.get("replacement_runtime_identity_sha256", ""))
                        )
                    }
                )
            ),
            "authorized_repair_runtime_identity_sha256s": (
                authorized_repair_runtime_hashes
            ),
        },
        "expected": {
            "problems": expected_problem_names,
            "attempts_per_case": discovered_attempts,
            "problem_attempt_pairs": expected_pair_count,
        },
        "events": event_metadata,
        "problems": problems,
        "selected_problem_attempt_pairs": selected_count,
        "repair_required_pairs": expected_pair_count - selected_count,
        "complete": expected_pair_count > 0 and selected_count == expected_pair_count,
    }
    state["state_sha256"] = _sha256_bytes(_canonical_bytes(state))
    return state


def refresh_cell_state(
    cell_dir: Path,
    *,
    expected_problems: Iterable[str] | None = None,
    attempts_per_case: int | None = None,
    resolved_config_sha256: str | None = None,
    runtime_identity_sha256: str | None = None,
) -> dict:
    """Rebuild and atomically persist a cell's effective validity view."""
    cell_dir = Path(cell_dir)
    with _cell_lock(cell_dir):
        state = _build_state_unlocked(
            cell_dir,
            expected_problems=expected_problems,
            attempts_per_case=attempts_per_case,
            resolved_config_sha256=resolved_config_sha256,
            runtime_identity_sha256=runtime_identity_sha256,
        )
        _atomic_json(cell_dir / STATE_NAME, state)
        return state


def selected_attempt(
    state: dict, problem: str, attempt_index: int = 1
) -> dict | None:
    try:
        attempt = state["problems"][problem]["attempts"][str(attempt_index)]
    except (KeyError, TypeError):
        return None
    return attempt if attempt.get("selected_execution") is not None else None


def repair_identity_migration_authorized(
    state: dict,
    problem: str,
    attempt_index: int,
    *,
    task_input_sha256: str,
    runtime_identity_sha256: str,
) -> bool:
    """Whether a pending repair is bound to the supplied replacement identity.

    Dataset-update events may bind a changed task and runtime.  A tool-infra
    adjudication may bind only an unchanged task to an explicitly reviewed
    infra-transparent runtime revision; ``append_manual_event`` enforces the
    unchanged-task constraint when the event is created.
    """
    try:
        attempt = state["problems"][problem]["attempts"][str(attempt_index)]
    except (KeyError, TypeError):
        return False
    if attempt.get("selected_execution") is not None:
        return False
    return any(
        event.get("action") in {"invalidate", "authorize_repair"}
        and str(event.get("reason_code", "")).startswith(
            ("dataset_update.", "tool_infra.")
        )
        and event.get("replacement_task_input_sha256") == task_input_sha256
        and event.get("replacement_runtime_identity_sha256")
        == runtime_identity_sha256
        for execution in attempt.get("executions", {}).values()
        if (event := execution.get("manual_override"))
    )


def dataset_update_identity_migration_authorized(
    state: dict,
    problem: str,
    attempt_index: int,
    *,
    task_input_sha256: str,
    runtime_identity_sha256: str,
) -> bool:
    """Backward-compatible alias for callers predating tool-infra revisions."""
    return repair_identity_migration_authorized(
        state,
        problem,
        attempt_index,
        task_input_sha256=task_input_sha256,
        runtime_identity_sha256=runtime_identity_sha256,
    )


def selected_execution_record(
    state: dict, problem: str, attempt_index: int = 1
) -> dict | None:
    attempt = selected_attempt(state, problem, attempt_index)
    if attempt is None:
        return None
    return attempt["executions"][str(attempt["selected_execution"])]


def selected_source_path(
    cell_dir: Path, state: dict, problem: str, attempt_index: int = 1
) -> Path | None:
    record = selected_execution_record(state, problem, attempt_index)
    source = record.get("source_record") if record else None
    return _from_relative(source["path"], Path(cell_dir)) if source else None


def selected_artifact_paths_for_model_dir(
    model_dir: Path, problem: str
) -> tuple[Path, Path] | None:
    """Resolve immutable PDDL selected for a model-label/attempt directory."""
    cell_dir, attempt_index = cell_dir_for_model_dir(Path(model_dir))
    state = refresh_cell_state(cell_dir)
    record = selected_execution_record(state, problem, attempt_index)
    if not record or record.get("generation_success") is not True:
        return None
    artifacts = record.get("artifacts", {})
    if not all(role in artifacts for role in ("domain", "problem")):
        return None
    paths = tuple(
        _from_relative(artifacts[role]["path"], cell_dir)
        for role in ("domain", "problem")
    )
    return paths if all(path.is_file() for path in paths) else None


def effective_attempt_for_model_dir(
    model_dir: Path, problem: str
) -> tuple[dict, dict | None, int]:
    cell_dir, attempt_index = cell_dir_for_model_dir(Path(model_dir))
    state = refresh_cell_state(cell_dir)
    return state, selected_attempt(state, problem, attempt_index), attempt_index


def write_execution_result(execution_dir: Path, value: dict) -> Path:
    """Write the immutable terminal record for an automatically valid execution."""
    path = Path(execution_dir) / EXECUTION_RESULT_NAME
    if path.exists():
        existing = _read_json(path)
        if existing != value:
            raise ExecutionValidityError(
                f"immutable execution result already differs: {path}"
            )
        return path
    _atomic_json(path, value)
    return path


def append_manual_event(
    cell_dir: Path,
    *,
    action: str,
    problem: str,
    attempt_index: int,
    execution_try: int,
    operator: str,
    reason_code: str,
    reason: str,
    evidence_paths: Iterable[Path],
    result_visibility: str,
    timestamp: str,
    replacement_task_input_sha256: str | None = None,
    replacement_runtime_identity_sha256: str | None = None,
) -> tuple[dict, dict]:
    """Validate, append, and apply one manual adjudication event."""
    if action not in {"invalidate", "reinstate", "authorize_repair"}:
        raise ExecutionValidityError("unsupported adjudication action")
    if not operator.strip() or not reason.strip():
        raise ExecutionValidityError("operator and reason are required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", reason_code):
        raise ExecutionValidityError(
            "reason_code must use lowercase letters, digits, dot, underscore, or dash"
        )
    allowed_prefixes = (
        ("tool_infra.", "dataset_update.")
        if action in {"invalidate", "authorize_repair"}
        else ("tool_infra.", "dataset_update.", "adjudication.")
    )
    if not reason_code.startswith(allowed_prefixes):
        raise ExecutionValidityError(
            f"{action} reason_code must start with one of: "
            + ", ".join(allowed_prefixes)
        )
    if result_visibility not in {"blind", "score_visible", "unknown"}:
        raise ExecutionValidityError(
            "result_visibility must be blind, score_visible, or unknown"
        )
    is_dataset_update = reason_code.startswith("dataset_update.")
    is_tool_infra = reason_code.startswith("tool_infra.")
    replacement_values = (
        replacement_task_input_sha256,
        replacement_runtime_identity_sha256,
    )
    if action == "authorize_repair" and (
        not is_tool_infra
        or not all(value and _SHA256.fullmatch(value) for value in replacement_values)
    ):
        raise ExecutionValidityError(
            "authorize_repair requires tool_infra reason and exact replacement task/runtime identities"
        )
    if action == "invalidate" and is_dataset_update:
        if not all(value and _SHA256.fullmatch(value) for value in replacement_values):
            raise ExecutionValidityError(
                "dataset_update invalidation requires exact replacement task and "
                "runtime SHA-256 identities"
            )
    elif action in {"invalidate", "authorize_repair"} and is_tool_infra and any(
        value is not None for value in replacement_values
    ):
        if not all(value and _SHA256.fullmatch(value) for value in replacement_values):
            raise ExecutionValidityError(
                "tool_infra runtime migration requires exact replacement task "
                "and runtime SHA-256 identities"
            )
    elif any(value is not None for value in replacement_values):
        raise ExecutionValidityError(
            "replacement identities are only valid for dataset_update or "
            "tool_infra invalidation"
        )
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionValidityError("timestamp must be ISO-8601") from exc
    if parsed_timestamp.tzinfo is None:
        raise ExecutionValidityError("timestamp must include a timezone")
    evidence: list[dict] = []
    for supplied in evidence_paths:
        path = Path(supplied).expanduser().resolve()
        if not path.is_file():
            raise ExecutionValidityError(f"evidence is not a regular file: {path}")
        evidence.append(
            {
                "path": _relative(path, Path(cell_dir)),
                "sha256": _sha256_file(path),
            }
        )
    if not evidence:
        raise ExecutionValidityError("at least one evidence file is required")

    cell_dir = Path(cell_dir)
    with _cell_lock(cell_dir):
        before = _build_state_unlocked(cell_dir)
        try:
            execution = before["problems"][problem]["attempts"][
                str(attempt_index)
            ]["executions"][str(execution_try)]
        except (KeyError, TypeError) as exc:
            raise ExecutionValidityError(
                "target problem/attempt/execution does not exist"
            ) from exc
        if action == "invalidate" and execution.get("automatic_valid") is not True:
            raise ExecutionValidityError(
                "only an automatically valid execution can be manually invalidated"
            )
        if action == "authorize_repair":
            attempt = before["problems"][problem]["attempts"][str(attempt_index)]
            if execution.get("automatic_valid") is not False or not attempt["repair_required"]:
                raise ExecutionValidityError(
                    "authorize_repair requires an automatically-invalid execution and no valid execution"
                )
            if execution.get("manual_override"):
                raise ExecutionValidityError("execution already has an adjudication event")
            # Legacy infra_invalid.json lacks identity fields. Its immutable
            # task_input.json plus root invalid_attempt identity binds the task.
            attempt_dir = attempt_dir_for(
                cell_dir, problem, attempt_index, before["expected"]["attempts_per_case"]
            )
            original = _read_json(attempt_dir / "invalid_attempt.json") or {}
            if original.get("task_input_sha256") != replacement_task_input_sha256:
                raise ExecutionValidityError("repair must preserve the exact task identity")
        if (
            action == "invalidate"
            and is_tool_infra
            and any(value is not None for value in replacement_values)
            and execution.get("identity", {}).get("task_input_sha256")
            != replacement_task_input_sha256
        ):
            raise ExecutionValidityError(
                "tool_infra runtime migration must preserve the exact task identity"
            )
        if (
            action == "invalidate"
            and (execution.get("manual_override") or {}).get("action")
            == "invalidate"
        ):
            raise ExecutionValidityError("execution is already manually invalid")
        if action == "reinstate":
            override = execution.get("manual_override")
            if not override or override.get("action") != "invalidate":
                raise ExecutionValidityError(
                    "reinstate requires a currently manual-invalid execution"
                )

        events, metadata = _load_events(cell_dir)
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "action": action,
            "problem": problem,
            "attempt_index": int(attempt_index),
            "execution_try": int(execution_try),
            "operator": operator.strip(),
            "reason_code": reason_code,
            "reason": reason.strip(),
            "evidence": evidence,
            "result_visibility": result_visibility,
            "previous_event_sha256": metadata["last_event_sha256"],
        }
        if action in {"invalidate", "authorize_repair"} and (
            is_dataset_update
            or (is_tool_infra and any(value is not None for value in replacement_values))
        ):
            event["replacement_task_input_sha256"] = replacement_task_input_sha256
            event["replacement_runtime_identity_sha256"] = (
                replacement_runtime_identity_sha256
            )
        event["event_sha256"] = _sha256_bytes(_canonical_bytes(event))
        events_path = cell_dir / EVENTS_NAME
        with events_path.open("ab") as stream:
            stream.write(_canonical_bytes(event) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

        after = _build_state_unlocked(cell_dir)
        _atomic_json(cell_dir / STATE_NAME, after)
        return event, after


def validity_metadata(state: dict) -> dict:
    return {
        "revision": state.get("revision"),
        "state_sha256": state.get("state_sha256"),
        "complete": state.get("complete"),
    }
