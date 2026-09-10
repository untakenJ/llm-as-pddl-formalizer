"""Aggregate v5 streaming overshoot and discarded-execution operations.

Official denominators are built only from atomic ``metadata.json`` records for
selected valid executions. Provider-infra-invalid execution evidence is read
separately and never merged into agent score or action metrics.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


def _read_object(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _nearest_rank_p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _overshoot_summary(rows: Iterable[tuple[str, int]]) -> dict:
    by_harness: dict[str, list[int]] = defaultdict(list)
    values: list[int] = []
    for harness, overshoot in rows:
        value = max(0, int(overshoot))
        values.append(value)
        by_harness[harness].append(value)

    affected = [value for value in values if value > 0]

    def summarize(group: list[int]) -> dict:
        impacted = [value for value in group if value > 0]
        return {
            "valid_executions": len(group),
            "affected_valid_executions": len(impacted),
            "affected_fraction": (
                round(len(impacted) / len(group), 6) if group else 0.0
            ),
            "overshoot_mean": (
                round(sum(impacted) / len(impacted), 6) if impacted else 0.0
            ),
            "overshoot_p95": _nearest_rank_p95(impacted),
            "overshoot_max": max(impacted, default=0),
        }

    result = summarize(values)
    result["harness_breakdown"] = {
        harness: summarize(group) for harness, group in sorted(by_harness.items())
    }
    return result


def summarize_streaming_outputs(roots: Iterable[str | Path]) -> dict:
    official_rows: list[tuple[str, int]] = []
    invalid_reasons: Counter[str] = Counter()
    invalid_upstream_attempts = 0
    invalid_wall_seconds = 0.0
    invalid_upstream_bytes = 0
    invalid_downstream_bytes = 0
    invalid_provider_usage: Counter[str] = Counter()
    invalid_paths: set[Path] = set()

    for root_value in roots:
        root = Path(root_value)
        for path in root.glob("**/metadata.json"):
            record = _read_object(path)
            if not record or record.get("attempt_valid") is not True:
                continue
            evidence = record.get("evidence")
            if not isinstance(evidence, dict):
                continue
            provenance = evidence.get("provenance")
            resolved = (
                provenance.get("resolved_config", {}).get("raw", {})
                if isinstance(provenance, dict)
                else {}
            )
            delivery = resolved.get("resolved", {}).get(
                "model_response_delivery", {}
            )
            if delivery.get("mode") != "native_streaming":
                continue
            harness = str(resolved.get("harness") or "unknown")
            actions = evidence.get("actions") or {}
            official_rows.append(
                (harness, int(actions.get("action_step_overshoot", 0) or 0))
            )

        for path in root.glob("**/provider_infra_invalid.json"):
            resolved_path = path.resolve()
            if resolved_path in invalid_paths:
                continue
            invalid_paths.add(resolved_path)
            record = _read_object(path)
            if not record:
                continue
            reason = str(record.get("infra_invalidator") or "unknown")
            invalid_reasons[reason] += 1
            summary = record.get("model_gateway_summary") or {}
            invalid_upstream_attempts += int(
                summary.get("upstream_attempts", 0) or 0
            )
            timing = record.get("execution_timing") or {}
            invalid_wall_seconds += float(
                timing.get("wall_duration_seconds", 0) or 0
            )
            ledger_info = record.get("model_call_ledger") or {}
            ledger_path_value = ledger_info.get("path")
            ledger_path = Path(ledger_path_value) if ledger_path_value else None
            if ledger_path is not None and not ledger_path.is_file():
                ledger_path = path.parent / ledger_path.name
            if ledger_path is not None and ledger_path.is_file():
                for line in ledger_path.read_text().splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    invalid_upstream_bytes += int(row.get("upstream_bytes", 0) or 0)
                    invalid_downstream_bytes += int(
                        row.get("downstream_bytes", 0) or 0
                    )
                    usage = row.get("provider_usage_observed") or {}
                    if isinstance(usage, dict):
                        for name, value in usage.items():
                            if isinstance(value, (int, float)) and not isinstance(
                                value, bool
                            ):
                                invalid_provider_usage[str(name)] += value

    return {
        "schema_version": 1,
        "official_selected_valid_executions": _overshoot_summary(official_rows),
        "operational_discarded_executions": {
            "count": sum(invalid_reasons.values()),
            "reasons": dict(sorted(invalid_reasons.items())),
            "physical_upstream_attempts": invalid_upstream_attempts,
            "wall_duration_seconds": round(invalid_wall_seconds, 6),
            "upstream_bytes": invalid_upstream_bytes,
            "downstream_bytes": invalid_downstream_bytes,
            "provider_usage_observed": dict(sorted(invalid_provider_usage.items())),
        },
        "metric_isolation": (
            "official metrics use selected valid metadata only; discarded "
            "execution evidence is operational"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize native-safety-v5-streaming execution evidence"
    )
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize_streaming_outputs(args.roots), indent=2))


if __name__ == "__main__":
    main()
