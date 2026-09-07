#!/usr/bin/env python3
"""CLI for auditable execution invalidation, reinstatement, and repair audit."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    source_dir = Path(__file__).resolve().parents[1]
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

from agent_formalizer.execution_validity import (  # noqa: E402
    ExecutionValidityError,
    append_manual_event,
    refresh_cell_state,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _problems(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cell",
        required=True,
        type=Path,
        help="comparison-cell directory containing pXX case directories",
    )


def _add_event_fields(parser: argparse.ArgumentParser) -> None:
    _add_target(parser)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--attempt", required=True, type=int, dest="attempt_index")
    parser.add_argument("--execution", required=True, type=int, dest="execution_try")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--evidence",
        required=True,
        action="append",
        type=Path,
        help="evidence file; repeat for multiple files",
    )
    parser.add_argument(
        "--result-visibility",
        required=True,
        choices=["blind", "score_visible", "unknown"],
        help="whether benchmark outcome/score was visible when adjudicating",
    )
    parser.add_argument(
        "--replacement-task-input-sha256",
        help=(
            "exact replacement task identity; required for dataset_update and "
            "required with --replacement-runtime-identity-sha256 for a reviewed "
            "tool_infra runtime migration"
        ),
    )
    parser.add_argument(
        "--replacement-runtime-identity-sha256",
        help=(
            "exact replacement runtime identity for dataset_update or a reviewed "
            "infra-transparent tool_infra repair"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Maintain the append-only manual execution-validity ledger. "
            "Never edit completion.json or execution_validity.json by hand."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser(
        "audit", help="rebuild the materialized state and report missing valid attempts"
    )
    _add_target(audit)
    audit.add_argument(
        "--problems",
        help="optional comma-separated frozen problem set, for initial creation",
    )
    audit.add_argument("--attempts-per-case", type=int)
    audit.add_argument("--resolved-config-sha256")
    audit.add_argument("--runtime-identity-sha256")
    audit.add_argument(
        "--json", action="store_true", help="print the complete materialized state"
    )

    invalidate = commands.add_parser(
        "invalidate", help="manually invalidate one automatically valid execution"
    )
    _add_event_fields(invalidate)

    reinstate = commands.add_parser(
        "reinstate", help="remove the current manual invalidation for one execution"
    )
    _add_event_fields(reinstate)
    return parser


def _summary(state: dict) -> dict:
    repairs: list[dict] = []
    for problem, problem_value in state.get("problems", {}).items():
        for attempt_index, attempt in problem_value.get("attempts", {}).items():
            if attempt.get("repair_required"):
                repairs.append(
                    {"problem": problem, "attempt_index": int(attempt_index)}
                )
    return {
        "cell": state.get("cell"),
        "revision": state.get("revision"),
        "state_sha256": state.get("state_sha256"),
        "complete": state.get("complete"),
        "selected_problem_attempt_pairs": state.get(
            "selected_problem_attempt_pairs"
        ),
        "repair_required_pairs": repairs,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "audit":
            state = refresh_cell_state(
                args.cell,
                expected_problems=_problems(args.problems),
                attempts_per_case=args.attempts_per_case,
                resolved_config_sha256=args.resolved_config_sha256,
                runtime_identity_sha256=args.runtime_identity_sha256,
            )
            print(json.dumps(state if args.json else _summary(state), indent=2))
            return 0 if state.get("complete") else 2

        event, state = append_manual_event(
            args.cell,
            action=args.command,
            problem=args.problem,
            attempt_index=args.attempt_index,
            execution_try=args.execution_try,
            operator=args.operator,
            reason_code=args.reason_code,
            reason=args.reason,
            evidence_paths=args.evidence,
            result_visibility=args.result_visibility,
            timestamp=_timestamp(),
            replacement_task_input_sha256=args.replacement_task_input_sha256,
            replacement_runtime_identity_sha256=(
                args.replacement_runtime_identity_sha256
            ),
        )
        print(
            json.dumps(
                {"event": event, "state": _summary(state)},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except ExecutionValidityError as exc:
        print(f"execution validity error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
