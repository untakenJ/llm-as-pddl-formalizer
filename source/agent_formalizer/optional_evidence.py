"""Auditable manifests for optional harness-native analysis evidence.

The manifest deliberately records metadata about raw evidence, never its
contents.  Optional collection failures remain valid benchmark outcomes, but
they are no longer indistinguishable from a model or native-harness omission.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from agent_formalizer.benchmark_profile import canonical_sha256
from agent_formalizer.provider_reasoning import reasoning_capture_capability


SCHEMA_VERSION = 1
MAX_STRUCTURED_PARSE_BYTES = 16 * 1024 * 1024


def default_analysis_evidence_spec() -> dict[str, Any]:
    """Return the conservative declaration used by an unknown adapter."""
    return {
        "schema_version": 1,
        "analysis_source": {
            "kind": "unknown",
            "native_harness_exposure": "unknown",
            "absence_is_model_attributable": False,
        },
        "raw_session": {
            "adapter_persistence": "not_implemented",
            "collector": "none",
        },
        "normalized_analysis": {
            "status": "not_implemented",
            "known_loss_modes": [],
        },
    }


def normalize_collection_report(
    report: object,
    *,
    none_status: str = "unknown",
    none_reason: str = "collector_returned_no_status",
) -> dict[str, Any]:
    """Normalize adapter hook reports without admitting exception messages."""
    if not isinstance(report, dict):
        return {"status": none_status, "reason": none_reason}
    normalized: dict[str, Any] = {}
    for key, value in report.items():
        if key in {"error", "stderr", "stdout", "message"}:
            continue
        if isinstance(value, Path):
            normalized[str(key)] = str(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            normalized[str(key)] = value
        elif isinstance(value, list):
            normalized[str(key)] = [
                str(item) if isinstance(item, Path) else item
                for item in value
                if isinstance(item, (str, int, float, bool, Path)) or item is None
            ]
        elif isinstance(value, dict):
            nested = normalize_collection_report(
                value, none_status="unknown", none_reason="nested_report_missing"
            )
            if "status" not in value:
                nested.pop("status", None)
            normalized[str(key)] = nested
    normalized.setdefault("status", none_status)
    return normalized


def _relative(path: Path, artifact_dir: Path) -> str:
    try:
        return path.relative_to(artifact_dir).as_posix()
    except ValueError:
        return f"<outside-artifact-dir>/{path.name}"


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _jsonl_metrics(path: Path) -> dict[str, Any]:
    nonempty = 0
    valid = 0
    malformed = 0
    with path.open("rb") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped:
                continue
            nonempty += 1
            try:
                json.loads(stripped)
            except (json.JSONDecodeError, UnicodeDecodeError):
                malformed += 1
            else:
                valid += 1
    return {
        "record_count": nonempty,
        "record_count_kind": "nonempty_jsonl_lines",
        "parseable_json_records": valid,
        "malformed_records": malformed,
    }


def _json_metrics(path: Path, size: int) -> dict[str, Any]:
    if size > MAX_STRUCTURED_PARSE_BYTES:
        return {
            "record_count": None,
            "record_count_kind": "not_parsed_size_limit",
            "parse_status": "not_parsed",
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "record_count": None,
            "record_count_kind": "unavailable",
            "parse_status": "error",
            "parse_error_type": type(exc).__name__,
        }
    if isinstance(value, list):
        count = len(value)
        kind = "top_level_array_items"
    elif isinstance(value, dict) and isinstance(value.get("events"), list):
        count = len(value["events"])
        kind = "events_array_items"
    elif isinstance(value, dict) and isinstance(value.get("messages"), list):
        count = len(value["messages"])
        kind = "messages_array_items"
    else:
        count = 1
        kind = "top_level_json_value"
    return {
        "record_count": count,
        "record_count_kind": kind,
        "parse_status": "ok",
    }


def _sqlite_metrics(path: Path) -> dict[str, Any]:
    table_rows: dict[str, int] = {}
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            names = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            ]
            for name in names:
                quoted = name.replace('"', '""')
                table_rows[name] = int(
                    connection.execute(
                        f'SELECT COUNT(*) FROM "{quoted}"'
                    ).fetchone()[0]
                )
    except (OSError, sqlite3.DatabaseError) as exc:
        return {
            "record_count": None,
            "record_count_kind": "unavailable",
            "parse_status": "error",
            "parse_error_type": type(exc).__name__,
        }
    return {
        "record_count": sum(table_rows.values()),
        "record_count_kind": "rows_across_sqlite_tables",
        "table_rows": table_rows,
        "parse_status": "ok",
    }


def _text_metrics(path: Path) -> dict[str, Any]:
    lines = 0
    with path.open("rb") as stream:
        for _ in stream:
            lines += 1
    return {"record_count": lines, "record_count_kind": "physical_lines"}


def _file_role(relative_path: str) -> str:
    lowered = relative_path.lower()
    if lowered.endswith("gateway/provider_reasoning.jsonl"):
        return "provider_readable_reasoning_transcript"
    if lowered.endswith("gateway/reasoning_capture_status.json"):
        return "provider_reasoning_capture_status"
    if lowered.endswith("usage.json") or lowered.endswith("costs.jsonl"):
        return "native_usage"
    if lowered.endswith((".db", ".sqlite", ".sqlite3")):
        return "native_session_database"
    if "model_responses" in lowered:
        return "native_model_response_log"
    if lowered.endswith("transcript.json"):
        return "native_transcript"
    if lowered.endswith(".jsonl"):
        return "native_session_log"
    return "native_supporting_evidence"


def _inventory_file(path: Path, artifact_dir: Path) -> dict[str, Any]:
    relative = _relative(path, artifact_dir)
    row: dict[str, Any] = {"path": relative, "role": _file_role(relative)}
    try:
        digest, size = _hash_file(path)
        row.update({"status": "ok", "bytes": size, "sha256": digest})
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            row.update(_jsonl_metrics(path))
        elif suffix == ".json":
            row.update(_json_metrics(path, size))
        elif suffix in {".db", ".sqlite", ".sqlite3"}:
            row.update(_sqlite_metrics(path))
        elif suffix in {".txt", ".log", ".md", ".yaml", ".yml", ".toml"}:
            row.update(_text_metrics(path))
        else:
            row.update(
                {
                    "record_count": None,
                    "record_count_kind": "not_defined_for_binary_format",
                }
            )
    except OSError as exc:
        row.update({"status": "error", "error_type": type(exc).__name__})
    return row


def inventory_raw_evidence(
    artifact_dir: Path, roots: Iterable[Path | str]
) -> dict[str, Any]:
    """Inventory exact files below adapter-declared raw evidence roots."""
    artifact_dir = Path(artifact_dir)
    root_rows: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    for declared in roots:
        root = Path(declared)
        if not root.is_absolute():
            root = artifact_dir / root
        label = _relative(root, artifact_dir)
        root_row: dict[str, Any] = {
            "path": label,
            "exists": root.exists(),
            "files_discovered": 0,
            "symlinks_skipped": 0,
        }
        if label.startswith("<outside-artifact-dir>"):
            root_row["status"] = "rejected_outside_artifact_dir"
            root_rows.append(root_row)
            continue
        if root.is_symlink():
            root_row["status"] = "rejected_symlink_root"
            root_row["symlinks_skipped"] = 1
            root_rows.append(root_row)
            continue
        try:
            root.resolve(strict=False).relative_to(artifact_dir.resolve())
        except (OSError, ValueError):
            root_row["status"] = "rejected_resolved_outside_artifact_dir"
            root_rows.append(root_row)
            continue
        if not root.exists():
            root_row["status"] = "missing"
            root_rows.append(root_row)
            continue
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if path.is_symlink():
                root_row["symlinks_skipped"] += 1
                continue
            if not path.is_file():
                continue
            relative = _relative(path, artifact_dir)
            paths.setdefault(relative, path)
        root_row["files_discovered"] = sum(
            1
            for relative in paths
            if relative == label or relative.startswith(label + "/")
        )
        root_row["status"] = "present"
        root_rows.append(root_row)

    files = [_inventory_file(paths[label], artifact_dir) for label in sorted(paths)]
    readable = [row for row in files if row.get("status") == "ok"]
    manifest_identity = [
        {
            "path": row["path"],
            "bytes": row.get("bytes"),
            "sha256": row.get("sha256"),
            "record_count": row.get("record_count"),
            "record_count_kind": row.get("record_count_kind"),
        }
        for row in files
    ]
    return {
        "roots": root_rows,
        "files": files,
        "file_count": len(files),
        "readable_file_count": len(readable),
        "total_bytes": sum(int(row.get("bytes", 0) or 0) for row in readable),
        "files_manifest_sha256": canonical_sha256(manifest_identity),
    }


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def inspect_json_analysis_fields(
    paths: Iterable[Path],
    *,
    artifact_dir: Path,
    text_fields: Iterable[str],
    opaque_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Count analysis-bearing JSON fields without retaining their values."""
    text_fields = set(text_fields)
    opaque_fields = set(opaque_fields)
    field_counts = {name: 0 for name in sorted(text_fields | opaque_fields)}
    nonempty_text = 0
    explicit_empty = 0
    opaque = 0
    structured_objects = 0
    records = 0
    parse_errors = 0
    evidence_files: list[str] = []

    def inspect_value(value: Any) -> None:
        nonlocal structured_objects, nonempty_text, explicit_empty, opaque
        for obj in _walk_json(value):
            structured_objects += 1
            for key in text_fields | opaque_fields:
                if key not in obj:
                    continue
                field_counts[key] += 1
                item = obj[key]
                populated = bool(item.strip()) if isinstance(item, str) else bool(item)
                if key in opaque_fields:
                    if populated:
                        opaque += 1
                elif populated:
                    nonempty_text += 1
                else:
                    explicit_empty += 1

    for path in sorted({Path(item) for item in paths}, key=lambda item: str(item)):
        if not path.is_file():
            continue
        evidence_files.append(_relative(path, artifact_dir))
        try:
            if path.suffix.lower() == ".jsonl":
                with path.open("rb") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        records += 1
                        try:
                            inspect_value(json.loads(line))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            parse_errors += 1
            else:
                records += 1
                inspect_value(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            parse_errors += 1

    if nonempty_text:
        status = "text_observed"
    elif opaque:
        status = "opaque_only"
    elif explicit_empty:
        status = "explicit_absence"
    elif evidence_files:
        status = "not_observed"
    else:
        status = "not_persisted"
    return {
        "status": status,
        "records_examined": records,
        "structured_objects_examined": structured_objects,
        "nonempty_text_field_occurrences": nonempty_text,
        "explicit_empty_field_occurrences": explicit_empty,
        "opaque_field_occurrences": opaque,
        "field_occurrences": field_counts,
        "parse_errors": parse_errors,
        "evidence_files": evidence_files,
    }


def inspect_sqlite_analysis_fields(
    path: Path,
    *,
    artifact_dir: Path,
    text_fields: Iterable[str],
    opaque_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Inspect Hermes-style message columns without reading their contents."""
    path = Path(path)
    if not path.is_file():
        return {
            "status": "not_persisted",
            "records_examined": 0,
            "evidence_files": [],
        }
    counts: dict[str, int] = {}
    assistant_records = 0
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(messages)")
            }
            if not columns:
                return {
                    "status": "not_inspectable",
                    "reason": "messages_table_missing",
                    "records_examined": 0,
                    "evidence_files": [_relative(path, artifact_dir)],
                }
            assistant_records = int(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
                ).fetchone()[0]
            )
            for field in sorted(set(text_fields) | set(opaque_fields)):
                if field not in columns:
                    continue
                quoted = field.replace('"', '""')
                counts[field] = int(
                    connection.execute(
                        f'SELECT COUNT(*) FROM messages WHERE role = \'assistant\' '
                        f'AND "{quoted}" IS NOT NULL '
                        f'AND TRIM(CAST("{quoted}" AS TEXT)) <> \'\''
                    ).fetchone()[0]
                )
    except (OSError, sqlite3.DatabaseError) as exc:
        return {
            "status": "inspection_failed",
            "error_type": type(exc).__name__,
            "records_examined": 0,
            "evidence_files": [_relative(path, artifact_dir)],
        }
    text_names = set(text_fields)
    text_count = sum(count for name, count in counts.items() if name in text_names)
    opaque_count = sum(count for name, count in counts.items() if name not in text_names)
    if text_count:
        status = "text_observed"
    elif opaque_count:
        status = "opaque_only"
    elif assistant_records:
        status = "explicit_absence"
    else:
        status = "not_observed"
    return {
        "status": status,
        "records_examined": assistant_records,
        "nonempty_text_field_occurrences": text_count,
        "opaque_field_occurrences": opaque_count,
        "field_occurrences": counts,
        "evidence_files": [_relative(path, artifact_dir)],
    }


def inspect_tagged_response_logs(
    paths: Iterable[Path], *, artifact_dir: Path
) -> dict[str, Any]:
    """Inspect GenericAgent response sections for native thinking blocks."""
    response_sections = 0
    nonempty_thinking = 0
    evidence_files: list[str] = []
    parse_errors = 0
    for path in sorted({Path(item) for item in paths}, key=lambda item: str(item)):
        if not path.is_file():
            continue
        evidence_files.append(_relative(path, artifact_dir))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            parse_errors += 1
            continue
        sections = re.findall(
            r"(?ms)^=== Response ===[^\n]*\n(.*?)(?=^=== Prompt ===|\Z)", text
        )
        response_sections += len(sections)
        for section in sections:
            tagged = re.findall(r"(?is)<thinking>(.*?)</thinking>", section)
            typed = re.findall(
                r"(?is)['\"]type['\"]\s*:\s*['\"]thinking['\"](.*?)(?=\}\s*,?|\]\s*,?|\Z)",
                section,
            )
            nonempty_thinking += sum(bool(item.strip()) for item in [*tagged, *typed])
    status = (
        "text_observed"
        if nonempty_thinking
        else "not_observed" if evidence_files else "not_persisted"
    )
    return {
        "status": status,
        "records_examined": response_sections,
        "nonempty_text_field_occurrences": nonempty_thinking,
        "parse_errors": parse_errors,
        "evidence_files": evidence_files,
    }


def inspect_provider_reasoning_capture(artifact_dir: Path) -> dict[str, Any]:
    """Inspect the gateway capture while keeping its readable text out of metadata."""
    artifact_dir = Path(artifact_dir)
    gateway_dir = artifact_dir / "gateway"
    status_path = gateway_dir / "reasoning_capture_status.json"
    records_path = gateway_dir / "provider_reasoning.jsonl"
    status_value: dict[str, Any] = {}
    status_error_type: str | None = None
    try:
        value = json.loads(status_path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            status_value = value
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        status_error_type = type(exc).__name__

    fragments = 0
    characters = 0
    utf8_bytes = 0
    boundaries = 0
    complete_boundaries = 0
    partial_boundaries = 0
    parse_errors = 0
    extractors: set[str] = set()
    downstream_states: dict[str, int] = {}
    if records_path.is_file():
        try:
            with records_path.open("rb") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        parse_errors += 1
                        continue
                    if not isinstance(record, dict):
                        parse_errors += 1
                        continue
                    if record.get("record_type") == "reasoning_fragment":
                        fragments += 1
                        text = record.get("text")
                        if isinstance(text, str):
                            characters += len(text)
                            utf8_bytes += len(text.encode("utf-8"))
                        extractor = record.get("extractor_id")
                        if isinstance(extractor, str):
                            extractors.add(extractor)
                    elif record.get("record_type") == "response_boundary":
                        boundaries += 1
                        if record.get("response_complete") is True:
                            complete_boundaries += 1
                        else:
                            partial_boundaries += 1
                        state = record.get("downstream_state")
                        if isinstance(state, str):
                            downstream_states[state] = downstream_states.get(state, 0) + 1
        except OSError as exc:
            status_error_type = type(exc).__name__

    support = status_value.get("support", "unknown")
    persistence = status_value.get("persistence", "unknown")
    write_errors = int(status_value.get("write_errors", 0) or 0)
    capture_errors = int(status_value.get("capture_errors", 0) or 0)
    if fragments:
        observation_status = "text_observed"
    elif status_error_type or write_errors or capture_errors:
        observation_status = "capture_failed"
    elif support == "not_implemented":
        observation_status = "provider_not_supported"
    elif status_path.is_file():
        observation_status = "not_observed"
    else:
        observation_status = "not_persisted"

    if status_error_type or write_errors or capture_errors:
        collection_status = "failed_partial" if fragments else "failed"
    elif support == "not_implemented":
        collection_status = "not_implemented"
    elif records_path.is_file():
        collection_status = "persisted" if fragments else "empty"
    elif status_path.is_file() and persistence == "enabled":
        collection_status = "empty"
    else:
        collection_status = "not_attempted"

    return {
        "status": observation_status,
        "collection_status": collection_status,
        "support": support,
        "persistence": persistence,
        "provider": status_value.get("provider", "unknown"),
        "normalized_provider": status_value.get("normalized_provider", "unknown"),
        "fragments_examined": fragments,
        "characters_observed": characters,
        "utf8_bytes_observed": utf8_bytes,
        "response_boundaries": boundaries,
        "complete_response_boundaries": complete_boundaries,
        "partial_response_boundaries": partial_boundaries,
        "downstream_states": downstream_states,
        "extractor_ids_observed": sorted(extractors),
        "parse_errors": parse_errors,
        "write_errors": write_errors,
        "capture_errors": capture_errors,
        "status_error_type": status_error_type,
        "evidence_files": [
            _relative(path, artifact_dir)
            for path in (status_path, records_path)
            if path.is_file()
        ],
        "agent_visibility": "not_inferred_by_gateway_capture",
    }


def _derive_attribution(
    spec: dict[str, Any],
    session_collection: dict[str, Any],
    observation: dict[str, Any],
    provider_observation: dict[str, Any],
) -> dict[str, str]:
    source = spec.get("analysis_source", {})
    raw = spec.get("raw_session", {})
    observation_status = observation.get("status", "unknown")
    provider_status = provider_observation.get("status", "unknown")
    collection_status = session_collection.get("status", "unknown")
    if provider_status == "text_observed":
        status = "api_readable_analysis_captured"
        model_conclusion = "readable_analysis_returned_by_provider_api"
    elif observation_status == "text_observed":
        status = (
            "native_analysis_text_observed_provider_capture_failed"
            if provider_status == "capture_failed"
            else "analysis_text_observed"
        )
        model_conclusion = "analysis_emission_observed"
    elif provider_status == "capture_failed":
        status = "provider_analysis_capture_failed"
        model_conclusion = "not_determined"
    elif observation_status == "opaque_only":
        status = "opaque_analysis_observed"
        model_conclusion = "opaque_analysis_emission_observed"
    elif collection_status in {"failed", "failed_partial"}:
        status = "adapter_collection_failed"
        model_conclusion = "not_determined"
    elif raw.get("adapter_persistence") == "not_implemented":
        status = "adapter_did_not_persist_native_evidence"
        model_conclusion = "not_determined"
    elif source.get("native_harness_exposure") == "not_exposed":
        status = "native_harness_did_not_expose_analysis"
        model_conclusion = "not_determined"
    elif observation_status == "explicit_absence" and source.get(
        "absence_is_model_attributable"
    ):
        status = "model_omitted_analysis"
        model_conclusion = "model_omission_supported_by_direct_record"
    elif observation_status in {"inspection_failed", "not_inspectable"}:
        status = "evidence_inspection_failed"
        model_conclusion = "not_determined"
    elif observation_status == "not_persisted":
        status = "raw_analysis_evidence_not_persisted"
        model_conclusion = "not_determined"
    elif observation_status in {"explicit_absence", "not_observed"}:
        status = "not_observed_in_persisted_native_evidence"
        model_conclusion = "not_determined"
    else:
        status = "unknown"
        model_conclusion = "not_determined"
    return {
        "status": status,
        "model_behavior_conclusion": model_conclusion,
        "agent_visibility_conclusion": "not_inferred; governed by native harness rules",
        "policy": (
            "Do not attribute missing analysis to the model unless a direct, "
            "semantically authoritative record explicitly supports that conclusion."
        ),
    }


def build_analysis_evidence_manifest(
    adapter,
    artifact_dir: Path,
    *,
    session_collection: dict[str, Any],
    usage_collection: dict[str, Any],
    steps_collection: dict[str, Any],
    tool_trace_collection: dict[str, Any],
) -> dict[str, Any]:
    """Build one relocatable, content-free optional evidence manifest."""
    raw_spec = adapter.analysis_evidence_spec()
    spec = normalize_collection_report(
        raw_spec,
        none_status="unknown",
        none_reason="adapter_spec_missing",
    )
    if isinstance(raw_spec, dict) and "status" not in raw_spec:
        spec.pop("status", None)
    provider_capability = reasoning_capture_capability(
        str(getattr(adapter, "model", "unknown")).split("/", 1)[0]
    )
    spec["provider_analysis_capture"] = provider_capability
    raw_inventory = inventory_raw_evidence(
        artifact_dir, adapter.raw_evidence_roots(artifact_dir)
    )
    try:
        observation = normalize_collection_report(
            adapter.inspect_analysis_evidence(artifact_dir),
            none_status="unknown",
            none_reason="adapter_inspection_missing",
        )
    except Exception as exc:  # optional diagnostics never invalidate an attempt
        observation = {
            "status": "inspection_failed",
            "error_type": type(exc).__name__,
        }
    provider_observation = inspect_provider_reasoning_capture(artifact_dir)
    session_collection = normalize_collection_report(session_collection)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope": "optional_harness_analysis_evidence",
        "harness": adapter.name,
        "model": adapter.model,
        "manifest_status": "complete",
        "capabilities": spec,
        "collection": {
            "raw_session": session_collection,
            "provider_reasoning": {
                "status": provider_observation["collection_status"],
                "support": provider_observation["support"],
                "persistence": provider_observation["persistence"],
                "write_errors": provider_observation["write_errors"],
                "capture_errors": provider_observation["capture_errors"],
            },
            "usage": normalize_collection_report(usage_collection),
            "normalized_agent_steps": normalize_collection_report(steps_collection),
            "normalized_tool_trace": normalize_collection_report(
                tool_trace_collection
            ),
        },
        "raw_evidence": raw_inventory,
        "analysis_observation": observation,
        "provider_analysis_observation": provider_observation,
        "analysis_attribution": _derive_attribution(
            spec, session_collection, observation, provider_observation
        ),
    }
    manifest["content_free_manifest_sha256"] = canonical_sha256(manifest)
    manifest["content_free_manifest_sha256_scope"] = (
        "canonical manifest before the hash and hash-scope fields are added"
    )
    return manifest
