"""Public comparison API for level-one and level-two domain equivalence."""

from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any, Literal

from .mapping import SymbolMapping, extract_symbol_mapping
from .model import Domain
from .parser import parse_domain_file
from .semantic_graph import (
    DomainGraph,
    build_domain_graph,
    find_isomorphism,
    graph_profile,
)

EquivalenceLevel = Literal["auto", 1, 2]


@dataclass(frozen=True)
class EquivalenceResult:
    equivalent: bool
    relation: str
    reason: str
    mapping: SymbolMapping | None = None
    verified_by_level_one: bool = False
    left_summary: dict[str, int] = field(default_factory=dict)
    right_summary: dict[str, int] = field(default_factory=dict)
    left_graph_profile: dict[str, dict[str, int]] = field(default_factory=dict)
    right_graph_profile: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "equivalent": self.equivalent,
            "relation": self.relation,
            "reason": self.reason,
            "verified_by_level_one": self.verified_by_level_one,
            "mapping": self.mapping.to_dict() if self.mapping is not None else None,
            "left_summary": self.left_summary,
            "right_summary": self.right_summary,
            "left_graph_profile": self.left_graph_profile,
            "right_graph_profile": self.right_graph_profile,
        }


DomainInput = Domain | str | PathLike[str]


def _load_domain(value: DomainInput) -> Domain:
    if isinstance(value, Domain):
        return value
    return parse_domain_file(Path(value))


def _base_result(
    left: Domain,
    right: Domain,
    left_graph: DomainGraph,
    right_graph: DomainGraph,
    **values: Any,
) -> EquivalenceResult:
    return EquivalenceResult(
        left_summary=left.summary(),
        right_summary=right.summary(),
        left_graph_profile=graph_profile(left_graph),
        right_graph_profile=graph_profile(right_graph),
        **values,
    )


def _resolve_name_map(
    left_names: set[str],
    right_names: set[str],
    supplied: dict[str, str],
    *,
    section: str,
) -> tuple[dict[str, str] | None, str | None]:
    supplied = {key.lower(): value.lower() for key, value in supplied.items()}
    unknown_left = set(supplied) - left_names
    if unknown_left:
        return None, f"{section} mapping contains unknown left names: {sorted(unknown_left)}."

    resolved: dict[str, str] = {}
    for left_name in sorted(left_names):
        if left_name in supplied:
            target = supplied[left_name]
        elif left_name in right_names:
            target = left_name
        else:
            return (
                None,
                f"No fixed {section} mapping was supplied for {left_name!r}, "
                "and no same-named right symbol exists.",
            )
        if target not in right_names:
            return None, f"{section} mapping targets unknown right name {target!r}."
        resolved[left_name] = target

    if len(set(resolved.values())) != len(resolved):
        return None, f"{section} mapping is not one-to-one."
    if set(resolved.values()) != right_names:
        missing = sorted(right_names - set(resolved.values()))
        return None, f"{section} mapping does not cover right names: {missing}."
    return resolved, None


def _resolve_fixed_mapping(
    left: Domain,
    right: Domain,
    supplied: SymbolMapping | None,
) -> tuple[SymbolMapping | None, str | None]:
    supplied = supplied or SymbolMapping()
    sections = (
        (
            "types",
            set(left.type_parents),
            set(right.type_parents),
            supplied.types,
        ),
        (
            "predicates",
            set(left.predicates),
            set(right.predicates),
            supplied.predicates,
        ),
        (
            "actions",
            set(left.actions),
            set(right.actions),
            supplied.actions,
        ),
        (
            "constants",
            set(left.constants),
            set(right.constants),
            supplied.constants,
        ),
    )
    resolved: dict[str, dict[str, str]] = {}
    for section, left_names, right_names, values in sections:
        name_map, reason = _resolve_name_map(
            left_names,
            right_names,
            values,
            section=section,
        )
        if name_map is None:
            return None, reason
        resolved[section] = name_map

    predicate_parameters = {
        key.lower(): tuple(value)
        for key, value in supplied.predicate_parameters.items()
    }
    action_parameters = {
        key.lower(): tuple(value)
        for key, value in supplied.action_parameters.items()
    }
    unknown_predicates = set(predicate_parameters) - set(left.predicates)
    unknown_actions = set(action_parameters) - set(left.actions)
    if unknown_predicates:
        return None, (
            "predicate_parameters contains unknown left predicates: "
            f"{sorted(unknown_predicates)}."
        )
    if unknown_actions:
        return None, (
            "action_parameters contains unknown left actions: "
            f"{sorted(unknown_actions)}."
        )

    for left_name, permutation in predicate_parameters.items():
        right_name = resolved["predicates"][left_name]
        left_arity = left.predicates[left_name].arity
        right_arity = right.predicates[right_name].arity
        if (
            len(permutation) != left_arity
            or sorted(permutation) != list(range(right_arity))
        ):
            return None, (
                f"Invalid predicate parameter permutation for {left_name!r}: "
                f"{permutation!r}."
            )
    for left_name, permutation in action_parameters.items():
        right_name = resolved["actions"][left_name]
        left_arity = left.actions[left_name].arity
        right_arity = right.actions[right_name].arity
        if (
            len(permutation) != left_arity
            or sorted(permutation) != list(range(right_arity))
        ):
            return None, (
                f"Invalid action parameter permutation for {left_name!r}: "
                f"{permutation!r}."
            )

    return (
        SymbolMapping(
            types=resolved["types"],
            predicates=resolved["predicates"],
            actions=resolved["actions"],
            constants=resolved["constants"],
            predicate_parameters=predicate_parameters,
            action_parameters=action_parameters,
        ),
        None,
    )


def _forced_graph_nodes(
    left: DomainGraph,
    right: DomainGraph,
    mapping: SymbolMapping,
) -> dict[int, int]:
    forced: dict[int, int] = {}
    for left_name, right_name in mapping.types.items():
        forced[left.index.types[left_name]] = right.index.types[right_name]
    for left_name, right_name in mapping.predicates.items():
        forced[left.index.predicates[left_name]] = right.index.predicates[right_name]
    for left_name, right_name in mapping.actions.items():
        forced[left.index.actions[left_name]] = right.index.actions[right_name]
    for left_name, right_name in mapping.constants.items():
        forced[left.index.constants[left_name]] = right.index.constants[right_name]
    for owner, permutation in mapping.predicate_parameters.items():
        right_owner = mapping.predicates[owner]
        for left_position, right_position in enumerate(permutation):
            forced[left.index.predicate_parameters[(owner, left_position)]] = (
                right.index.predicate_parameters[(right_owner, right_position)]
            )
    for owner, permutation in mapping.action_parameters.items():
        right_owner = mapping.actions[owner]
        for left_position, right_position in enumerate(permutation):
            forced[left.index.action_parameters[(owner, left_position)]] = (
                right.index.action_parameters[(right_owner, right_position)]
            )
    return forced


def _compare_level_one_domains(
    left: Domain,
    right: Domain,
    mapping: SymbolMapping | None,
) -> EquivalenceResult:
    left_graph = build_domain_graph(left)
    right_graph = build_domain_graph(right)
    fixed_mapping, reason = _resolve_fixed_mapping(left, right, mapping)
    if fixed_mapping is None:
        return _base_result(
            left,
            right,
            left_graph,
            right_graph,
            equivalent=False,
            relation="not_equivalent",
            reason=reason or "The fixed symbol mapping is invalid.",
        )

    graph_mapping = find_isomorphism(
        left_graph,
        right_graph,
        forced_nodes=_forced_graph_nodes(left_graph, right_graph, fixed_mapping),
    )
    if graph_mapping is None:
        return _base_result(
            left,
            right,
            left_graph,
            right_graph,
            equivalent=False,
            relation="not_equivalent",
            reason=(
                "No exact structural isomorphism exists under the fixed symbol "
                "correspondence."
            ),
        )

    certificate = extract_symbol_mapping(left_graph, right_graph, graph_mapping)
    return _base_result(
        left,
        right,
        left_graph,
        right_graph,
        equivalent=True,
        relation="alpha_abi_equivalent",
        reason=(
            "The domains are structurally identical under the fixed symbol "
            "correspondence; local variable names and declaration/literal order "
            "are ignored."
        ),
        mapping=certificate,
        verified_by_level_one=True,
    )


def _compare_level_two_domains(left: Domain, right: Domain) -> EquivalenceResult:
    left_graph = build_domain_graph(left)
    right_graph = build_domain_graph(right)
    graph_mapping = find_isomorphism(left_graph, right_graph)
    if graph_mapping is None:
        profile_note = (
            " Their graph profiles differ."
            if graph_profile(left_graph) != graph_profile(right_graph)
            else ""
        )
        return _base_result(
            left,
            right,
            left_graph,
            right_graph,
            equivalent=False,
            relation="not_equivalent",
            reason=(
                "No global bijection over types, predicates, actions, constants, "
                "and signature parameters preserves all supported structures."
                + profile_note
            ),
        )

    certificate = extract_symbol_mapping(left_graph, right_graph, graph_mapping)
    # Level two is deliberately reduced back to level one.  This makes the
    # discovered mapping a checked certificate rather than an unverified matcher output.
    verification = _compare_level_one_domains(left, right, certificate)
    if not verification.equivalent:
        return _base_result(
            left,
            right,
            left_graph,
            right_graph,
            equivalent=False,
            relation="internal_verification_failure",
            reason=(
                "A schema mapping was found, but fixed-mapping verification failed: "
                f"{verification.reason}"
            ),
            mapping=certificate,
        )

    return _base_result(
        left,
        right,
        left_graph,
        right_graph,
        equivalent=True,
        relation="schema_isomorphic",
        reason=(
            "A global bijection over types, predicates, actions, constants, and "
            "signature parameters preserves all supported structures."
        ),
        mapping=certificate,
        verified_by_level_one=True,
    )


def compare_level_one(
    left: DomainInput,
    right: DomainInput,
    mapping: SymbolMapping | dict[str, Any] | None = None,
) -> EquivalenceResult:
    if isinstance(mapping, dict):
        mapping = SymbolMapping.from_dict(mapping)
    return _compare_level_one_domains(_load_domain(left), _load_domain(right), mapping)


def compare_level_two(left: DomainInput, right: DomainInput) -> EquivalenceResult:
    return _compare_level_two_domains(_load_domain(left), _load_domain(right))


def compare_domains(
    left: DomainInput,
    right: DomainInput,
    *,
    level: EquivalenceLevel = "auto",
    mapping: SymbolMapping | dict[str, Any] | None = None,
) -> EquivalenceResult:
    left_domain = _load_domain(left)
    right_domain = _load_domain(right)
    if isinstance(mapping, dict):
        mapping = SymbolMapping.from_dict(mapping)

    if level == 1:
        return _compare_level_one_domains(left_domain, right_domain, mapping)
    if level == 2:
        return _compare_level_two_domains(left_domain, right_domain)
    if level != "auto":
        raise ValueError("level must be 'auto', 1, or 2.")

    first = _compare_level_one_domains(left_domain, right_domain, mapping)
    if first.equivalent:
        return first
    return _compare_level_two_domains(left_domain, right_domain)
