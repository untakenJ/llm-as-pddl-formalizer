"""Serializable symbol and signature mapping certificates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .semantic_graph import DomainGraph


@dataclass(frozen=True)
class SymbolMapping:
    types: dict[str, str] = field(default_factory=dict)
    predicates: dict[str, str] = field(default_factory=dict)
    actions: dict[str, str] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    # A tuple maps each zero-based left parameter position to a right position.
    predicate_parameters: dict[str, tuple[int, ...]] = field(default_factory=dict)
    action_parameters: dict[str, tuple[int, ...]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SymbolMapping":
        allowed = {
            "types",
            "predicates",
            "actions",
            "constants",
            "predicate_parameters",
            "action_parameters",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown mapping sections: {sorted(unknown)}.")

        def string_map(section: str) -> dict[str, str]:
            raw = value.get(section, {})
            if not isinstance(raw, dict) or not all(
                isinstance(key, str) and isinstance(item, str)
                for key, item in raw.items()
            ):
                raise ValueError(f"Mapping section {section!r} must be string-to-string.")
            return dict(raw)

        def permutation_map(section: str) -> dict[str, tuple[int, ...]]:
            raw = value.get(section, {})
            if not isinstance(raw, dict):
                raise ValueError(f"Mapping section {section!r} must be an object.")
            result: dict[str, tuple[int, ...]] = {}
            for key, item in raw.items():
                if (
                    not isinstance(key, str)
                    or not isinstance(item, list)
                    or not all(isinstance(position, int) for position in item)
                ):
                    raise ValueError(
                        f"Mapping section {section!r} must contain integer arrays."
                    )
                result[key] = tuple(item)
            return result

        return cls(
            types=string_map("types"),
            predicates=string_map("predicates"),
            actions=string_map("actions"),
            constants=string_map("constants"),
            predicate_parameters=permutation_map("predicate_parameters"),
            action_parameters=permutation_map("action_parameters"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "types": dict(sorted(self.types.items())),
            "predicates": dict(sorted(self.predicates.items())),
            "actions": dict(sorted(self.actions.items())),
            "constants": dict(sorted(self.constants.items())),
            "predicate_parameters": {
                key: list(value)
                for key, value in sorted(self.predicate_parameters.items())
            },
            "action_parameters": {
                key: list(value)
                for key, value in sorted(self.action_parameters.items())
            },
        }


def extract_symbol_mapping(
    left: DomainGraph,
    right: DomainGraph,
    graph_mapping: dict[int, int],
) -> SymbolMapping:
    right_types = {node: name for name, node in right.index.types.items()}
    right_predicates = {
        node: name for name, node in right.index.predicates.items()
    }
    right_actions = {node: name for name, node in right.index.actions.items()}
    right_constants = {node: name for name, node in right.index.constants.items()}
    right_predicate_parameters = {
        node: (name, position)
        for (name, position), node in right.index.predicate_parameters.items()
    }
    right_action_parameters = {
        node: (name, position)
        for (name, position), node in right.index.action_parameters.items()
    }

    type_mapping = {
        name: right_types[graph_mapping[node]]
        for name, node in left.index.types.items()
    }
    predicate_mapping = {
        name: right_predicates[graph_mapping[node]]
        for name, node in left.index.predicates.items()
    }
    action_mapping = {
        name: right_actions[graph_mapping[node]]
        for name, node in left.index.actions.items()
    }
    constant_mapping = {
        name: right_constants[graph_mapping[node]]
        for name, node in left.index.constants.items()
    }

    predicate_parameters: dict[str, tuple[int, ...]] = {}
    for predicate_name in left.index.predicates:
        positions: list[int] = []
        position = 0
        while (predicate_name, position) in left.index.predicate_parameters:
            mapped = graph_mapping[
                left.index.predicate_parameters[(predicate_name, position)]
            ]
            right_owner, right_position = right_predicate_parameters[mapped]
            if right_owner != predicate_mapping[predicate_name]:
                raise AssertionError("Predicate parameter escaped its mapped owner.")
            positions.append(right_position)
            position += 1
        predicate_parameters[predicate_name] = tuple(positions)

    action_parameters: dict[str, tuple[int, ...]] = {}
    for action_name in left.index.actions:
        positions = []
        position = 0
        while (action_name, position) in left.index.action_parameters:
            mapped = graph_mapping[left.index.action_parameters[(action_name, position)]]
            right_owner, right_position = right_action_parameters[mapped]
            if right_owner != action_mapping[action_name]:
                raise AssertionError("Action parameter escaped its mapped owner.")
            positions.append(right_position)
            position += 1
        action_parameters[action_name] = tuple(positions)

    return SymbolMapping(
        types=type_mapping,
        predicates=predicate_mapping,
        actions=action_mapping,
        constants=constant_mapping,
        predicate_parameters=predicate_parameters,
        action_parameters=action_parameters,
    )
