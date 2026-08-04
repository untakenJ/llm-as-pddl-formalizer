"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .compare import SymbolMapping, compare_domains
from .parser import PDDLParseError


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pddl-domain-equivalence",
        description=(
            "Check fixed-symbol alpha/ABI equivalence (level 1) or global schema "
            "isomorphism (level 2) for conservative STRIPS PDDL domains."
        ),
    )
    parser.add_argument("left", type=Path, help="First PDDL domain file.")
    parser.add_argument("right", type=Path, help="Second PDDL domain file.")
    parser.add_argument(
        "--level",
        choices=("auto", "1", "2"),
        default="auto",
        help="Comparison level; auto tries level 1 and then level 2 (default: auto).",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        help="Optional level-one JSON symbol/parameter mapping.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the complete result as JSON.",
    )
    return parser


def _load_mapping(path: Path | None) -> SymbolMapping | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load mapping file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("The mapping JSON root must be an object.")
    return SymbolMapping.from_dict(value)


def _non_identity(mapping: dict[str, str]) -> list[str]:
    return [
        f"{left} -> {right}"
        for left, right in sorted(mapping.items())
        if left != right
    ]


def _format_human(result: object) -> str:
    # Local import-free duck typing keeps this helper easy to test.
    equivalent = result.equivalent
    lines = [
        f"equivalent: {'yes' if equivalent else 'no'}",
        f"relation: {result.relation}",
        f"reason: {result.reason}",
    ]
    if result.mapping is not None:
        mapping = result.mapping
        for title, values in (
            ("type mappings", mapping.types),
            ("predicate mappings", mapping.predicates),
            ("action mappings", mapping.actions),
            ("constant mappings", mapping.constants),
        ):
            changed = _non_identity(values)
            if changed:
                lines.append(f"{title}:")
                lines.extend(f"  {item}" for item in changed)
        parameter_changes = []
        for kind, values in (
            ("predicate", mapping.predicate_parameters),
            ("action", mapping.action_parameters),
        ):
            for owner, permutation in sorted(values.items()):
                if permutation != tuple(range(len(permutation))):
                    parameter_changes.append(
                        f"{kind} {owner}: {list(permutation)}"
                    )
        if parameter_changes:
            lines.append("parameter permutations (zero-based left -> right):")
            lines.extend(f"  {item}" for item in parameter_changes)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    arguments = parser.parse_args(argv)
    try:
        mapping = _load_mapping(arguments.mapping)
        level = arguments.level if arguments.level == "auto" else int(arguments.level)
        result = compare_domains(
            arguments.left,
            arguments.right,
            level=level,
            mapping=mapping,
        )
    except (PDDLParseError, ValueError) as exc:
        if arguments.json:
            print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if arguments.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(_format_human(result))
    return 0 if result.equivalent else 1
