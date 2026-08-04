"""Small, immutable semantic model for the supported PDDL fragment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, order=True)
class Parameter:
    name: str
    type_name: str = "object"


@dataclass(frozen=True, order=True)
class Predicate:
    name: str
    parameters: tuple[Parameter, ...]

    @property
    def arity(self) -> int:
        return len(self.parameters)


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class Action:
    name: str
    parameters: tuple[Parameter, ...]
    positive_preconditions: frozenset[Atom]
    negative_preconditions: frozenset[Atom]
    add_effects: frozenset[Atom]
    delete_effects: frozenset[Atom]

    @property
    def arity(self) -> int:
        return len(self.parameters)

    def literals(self) -> Iterable[tuple[str, Atom]]:
        for role, atoms in (
            ("pre_positive", self.positive_preconditions),
            ("pre_negative", self.negative_preconditions),
            ("effect_add", self.add_effects),
            ("effect_delete", self.delete_effects),
        ):
            for atom in sorted(atoms):
                yield role, atom


@dataclass(frozen=True)
class Domain:
    name: str
    requirements: frozenset[str]
    # Every domain contains object -> None.
    type_parents: dict[str, str | None]
    predicates: dict[str, Predicate]
    constants: dict[str, str]
    actions: dict[str, Action]

    def is_subtype(self, child: str, parent: str) -> bool:
        current: str | None = child
        visited: set[str] = set()
        while current is not None:
            if current == parent:
                return True
            if current in visited:
                return False
            visited.add(current)
            current = self.type_parents.get(current)
        return False

    def summary(self) -> dict[str, int]:
        return {
            "types": len(self.type_parents),
            "predicates": len(self.predicates),
            "predicate_parameters": sum(
                predicate.arity for predicate in self.predicates.values()
            ),
            "constants": len(self.constants),
            "actions": len(self.actions),
            "action_parameters": sum(action.arity for action in self.actions.values()),
            "literals": sum(
                1 for action in self.actions.values() for _ in action.literals()
            ),
        }
