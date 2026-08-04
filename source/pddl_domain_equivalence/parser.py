"""A strict parser for the STRIPS-oriented fragment used by this checker.

The parser intentionally rejects constructs that the equivalence graph does not model.
Silently dropping an ADL or numeric construct would turn an exact checker into an
unsound one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypeAlias

from .model import Action, Atom, Domain, Parameter, Predicate

SExpr: TypeAlias = str | list["SExpr"]


class PDDLParseError(ValueError):
    """The input is malformed or internally inconsistent."""


class UnsupportedPDDL(PDDLParseError):
    """The input uses a valid-looking construct outside the supported fragment."""


_SUPPORTED_REQUIREMENTS = {
    ":strips",
    ":typing",
    ":negative-preconditions",
}
_UNSUPPORTED_SECTIONS = {
    ":constraints",
    ":derived",
    ":durative-action",
    ":functions",
}
_UNSUPPORTED_LOGICAL_FORMS = {
    "decrease",
    "either",
    "exists",
    "forall",
    "imply",
    "increase",
    "oneof",
    "or",
    "preference",
    "when",
}


def _tokenize(text: str) -> list[str]:
    without_comments = re.sub(r";[^\n\r]*", "", text)
    return re.findall(r"\(|\)|[^\s()]+", without_comments.lower())


def _parse_sexpr(tokens: list[str]) -> SExpr:
    if not tokens:
        raise PDDLParseError("The file is empty.")

    def parse_at(index: int) -> tuple[SExpr, int]:
        if index >= len(tokens):
            raise PDDLParseError("Unexpected end of input.")
        token = tokens[index]
        if token == ")":
            raise PDDLParseError("Unexpected ')'.")
        if token != "(":
            return token, index + 1

        result: list[SExpr] = []
        index += 1
        while True:
            if index >= len(tokens):
                raise PDDLParseError("Unclosed '('.")
            if tokens[index] == ")":
                return result, index + 1
            value, index = parse_at(index)
            result.append(value)

    expression, next_index = parse_at(0)
    if next_index != len(tokens):
        raise PDDLParseError("More than one top-level expression was found.")
    return expression


def _as_list(value: SExpr, context: str) -> list[SExpr]:
    if not isinstance(value, list):
        raise PDDLParseError(f"Expected a list for {context}.")
    return value


def _as_atom(value: SExpr, context: str) -> str:
    if not isinstance(value, str):
        raise UnsupportedPDDL(f"Nested expression is unsupported in {context}.")
    return value


def _typed_items(
    values: list[SExpr],
    *,
    default_type: str = "object",
    context: str,
) -> list[tuple[str, str]]:
    atoms = [_as_atom(value, context) for value in values]
    result: list[tuple[str, str]] = []
    pending: list[str] = []
    index = 0
    while index < len(atoms):
        token = atoms[index]
        if token == "-":
            if not pending or index + 1 >= len(atoms):
                raise PDDLParseError(f"Malformed typed list in {context}.")
            type_name = atoms[index + 1]
            if type_name.startswith("?") or type_name == "-":
                raise PDDLParseError(f"Invalid type {type_name!r} in {context}.")
            result.extend((name, type_name) for name in pending)
            pending = []
            index += 2
            continue
        pending.append(token)
        index += 1
    result.extend((name, default_type) for name in pending)
    return result


def _parse_atom(expression: SExpr, context: str) -> Atom:
    values = _as_list(expression, context)
    if not values:
        raise PDDLParseError(f"Empty atom in {context}.")
    predicate = _as_atom(values[0], context)
    if predicate in _UNSUPPORTED_LOGICAL_FORMS or predicate == "=":
        raise UnsupportedPDDL(
            f"Logical form or built-in predicate {predicate!r} is unsupported in {context}."
        )
    arguments = tuple(_as_atom(item, context) for item in values[1:])
    return Atom(predicate, arguments)


def _parse_literal(expression: SExpr, context: str) -> tuple[bool, Atom]:
    values = _as_list(expression, context)
    if values and values[0] == "not":
        if len(values) != 2:
            raise PDDLParseError(f"Malformed negation in {context}.")
        return True, _parse_atom(values[1], context)
    return False, _parse_atom(values, context)


def _parse_conjunction(expression: SExpr, context: str) -> list[tuple[bool, Atom]]:
    values = _as_list(expression, context)
    if not values:
        raise PDDLParseError(f"Empty expression in {context}; use (and) for true.")
    head = _as_atom(values[0], context)
    if head == "and":
        return [_parse_literal(item, context) for item in values[1:]]
    if head in _UNSUPPORTED_LOGICAL_FORMS:
        raise UnsupportedPDDL(f"{head!r} is unsupported in {context}.")
    return [_parse_literal(values, context)]


def _ensure_unique(names: list[str], context: str) -> None:
    if len(names) != len(set(names)):
        raise PDDLParseError(f"Duplicate name in {context}: {names!r}.")


def _parse_action(section: list[SExpr]) -> Action:
    if len(section) < 2:
        raise PDDLParseError("An :action section has no name.")
    name = _as_atom(section[1], "action name")
    fields: dict[str, SExpr] = {}
    index = 2
    while index < len(section):
        key = _as_atom(section[index], f"action {name}")
        if not key.startswith(":") or index + 1 >= len(section):
            raise PDDLParseError(f"Malformed field in action {name!r}.")
        if key in fields:
            raise PDDLParseError(f"Duplicate {key} field in action {name!r}.")
        fields[key] = section[index + 1]
        index += 2

    allowed_fields = {":parameters", ":precondition", ":effect"}
    unsupported = set(fields) - allowed_fields
    if unsupported:
        raise UnsupportedPDDL(
            f"Unsupported fields in action {name!r}: {sorted(unsupported)}."
        )
    missing = allowed_fields - set(fields)
    if missing:
        raise PDDLParseError(
            f"Missing fields in action {name!r}: {sorted(missing)}."
        )

    parameter_items = _typed_items(
        _as_list(fields[":parameters"], f"parameters of {name}"),
        context=f"parameters of {name}",
    )
    _ensure_unique([item[0] for item in parameter_items], f"parameters of {name}")
    if any(not variable.startswith("?") for variable, _ in parameter_items):
        raise PDDLParseError(f"Action parameters must start with '?' in {name!r}.")
    parameters = tuple(Parameter(variable, type_name) for variable, type_name in parameter_items)

    positive_preconditions: set[Atom] = set()
    negative_preconditions: set[Atom] = set()
    for negated, atom in _parse_conjunction(
        fields[":precondition"], f"precondition of {name}"
    ):
        (negative_preconditions if negated else positive_preconditions).add(atom)

    add_effects: set[Atom] = set()
    delete_effects: set[Atom] = set()
    for negated, atom in _parse_conjunction(fields[":effect"], f"effect of {name}"):
        (delete_effects if negated else add_effects).add(atom)

    if add_effects & delete_effects:
        overlap = sorted(add_effects & delete_effects)
        raise UnsupportedPDDL(
            f"Conflicting add/delete effects in action {name!r}: {overlap!r}."
        )

    return Action(
        name=name,
        parameters=parameters,
        positive_preconditions=frozenset(positive_preconditions),
        negative_preconditions=frozenset(negative_preconditions),
        add_effects=frozenset(add_effects),
        delete_effects=frozenset(delete_effects),
    )


def _validate_types(type_parents: dict[str, str | None]) -> None:
    for type_name, parent in type_parents.items():
        if parent is not None and parent not in type_parents:
            raise PDDLParseError(
                f"Type {type_name!r} has undeclared parent {parent!r}."
            )
        seen: set[str] = set()
        current: str | None = type_name
        while current is not None:
            if current in seen:
                raise PDDLParseError(f"Cycle in type hierarchy at {current!r}.")
            seen.add(current)
            current = type_parents.get(current)


def _validate_domain(domain: Domain) -> None:
    _validate_types(domain.type_parents)

    for predicate in domain.predicates.values():
        for parameter in predicate.parameters:
            if parameter.type_name not in domain.type_parents:
                raise PDDLParseError(
                    f"Predicate {predicate.name!r} uses undeclared type "
                    f"{parameter.type_name!r}."
                )

    for constant, type_name in domain.constants.items():
        if type_name not in domain.type_parents:
            raise PDDLParseError(
                f"Constant {constant!r} uses undeclared type {type_name!r}."
            )

    for action in domain.actions.values():
        variable_types = {parameter.name: parameter.type_name for parameter in action.parameters}
        for parameter in action.parameters:
            if parameter.type_name not in domain.type_parents:
                raise PDDLParseError(
                    f"Action {action.name!r} uses undeclared type "
                    f"{parameter.type_name!r}."
                )

        for _, atom in action.literals():
            predicate = domain.predicates.get(atom.predicate)
            if predicate is None:
                raise PDDLParseError(
                    f"Action {action.name!r} uses undeclared predicate "
                    f"{atom.predicate!r}."
                )
            if len(atom.arguments) != predicate.arity:
                raise PDDLParseError(
                    f"Predicate {atom.predicate!r} has arity {predicate.arity}, "
                    f"but action {action.name!r} uses {len(atom.arguments)} arguments."
                )
            for argument, expected in zip(atom.arguments, predicate.parameters):
                if argument.startswith("?"):
                    actual_type = variable_types.get(argument)
                    if actual_type is None:
                        raise PDDLParseError(
                            f"Action {action.name!r} uses undeclared variable "
                            f"{argument!r}."
                        )
                else:
                    actual_type = domain.constants.get(argument)
                    if actual_type is None:
                        raise PDDLParseError(
                            f"Action {action.name!r} uses undeclared constant "
                            f"{argument!r}."
                        )
                if not domain.is_subtype(actual_type, expected.type_name):
                    raise PDDLParseError(
                        f"Term {argument!r} of type {actual_type!r} is incompatible "
                        f"with {atom.predicate!r} parameter type "
                        f"{expected.type_name!r} in action {action.name!r}."
                    )


def parse_domain(text: str, *, source: str = "<string>") -> Domain:
    expression = _parse_sexpr(_tokenize(text))
    root = _as_list(expression, source)
    if not root or root[0] != "define":
        raise PDDLParseError(f"{source}: expected (define ...).")

    name: str | None = None
    requirements: set[str] = set()
    type_parents: dict[str, str | None] = {"object": None}
    predicates: dict[str, Predicate] = {}
    constants: dict[str, str] = {}
    actions: dict[str, Action] = {}

    for raw_section in root[1:]:
        section = _as_list(raw_section, f"top-level section in {source}")
        if not section:
            raise PDDLParseError(f"{source}: empty top-level section.")
        head = _as_atom(section[0], f"top-level section in {source}")

        if head == "domain":
            if len(section) != 2 or name is not None:
                raise PDDLParseError(f"{source}: malformed or duplicate domain name.")
            name = _as_atom(section[1], "domain name")
        elif head == ":requirements":
            requirements.update(_as_atom(item, ":requirements") for item in section[1:])
        elif head == ":types":
            for type_name, parent in _typed_items(
                section[1:], context=":types"
            ):
                if type_name == "object":
                    if parent != "object":
                        raise PDDLParseError("The built-in object type cannot have a parent.")
                    continue
                if type_name in type_parents:
                    raise PDDLParseError(f"Duplicate type {type_name!r}.")
                type_parents[type_name] = parent
        elif head == ":constants":
            items = _typed_items(section[1:], context=":constants")
            _ensure_unique([item[0] for item in items], ":constants")
            for constant, type_name in items:
                if constant.startswith("?"):
                    raise PDDLParseError("A domain constant cannot start with '?'.")
                if constant in constants:
                    raise PDDLParseError(f"Duplicate constant {constant!r}.")
                constants[constant] = type_name
        elif head == ":predicates":
            for raw_predicate in section[1:]:
                declaration = _as_list(raw_predicate, ":predicates")
                if not declaration:
                    raise PDDLParseError("Empty predicate declaration.")
                predicate_name = _as_atom(declaration[0], "predicate name")
                if predicate_name in predicates:
                    raise PDDLParseError(f"Duplicate predicate {predicate_name!r}.")
                items = _typed_items(
                    declaration[1:], context=f"predicate {predicate_name}"
                )
                # Some benchmark domains use the same placeholder spelling more
                # than once in a declaration, e.g. ``(in ?obj ?obj)``.  Predicate
                # declarations define typed positions rather than scoped variables,
                # so the graph keeps the positions distinct and ignores these names.
                if any(not variable.startswith("?") for variable, _ in items):
                    raise PDDLParseError(
                        f"Predicate parameters must start with '?' in {predicate_name!r}."
                    )
                predicates[predicate_name] = Predicate(
                    predicate_name,
                    tuple(Parameter(variable, type_name) for variable, type_name in items),
                )
        elif head == ":action":
            action = _parse_action(section)
            if action.name in actions:
                raise PDDLParseError(f"Duplicate action {action.name!r}.")
            actions[action.name] = action
        elif head in _UNSUPPORTED_SECTIONS or head.startswith(":"):
            raise UnsupportedPDDL(
                f"{source}: unsupported top-level PDDL section {head!r}."
            )
        else:
            raise PDDLParseError(f"{source}: unknown top-level form {head!r}.")

    if name is None:
        raise PDDLParseError(f"{source}: no domain name was declared.")
    if not predicates:
        raise PDDLParseError(f"{source}: no :predicates section was declared.")

    unsupported_requirements = requirements - _SUPPORTED_REQUIREMENTS
    if unsupported_requirements:
        raise UnsupportedPDDL(
            f"{source}: unsupported requirements "
            f"{sorted(unsupported_requirements)}."
        )

    domain = Domain(
        name=name,
        requirements=frozenset(requirements),
        type_parents=type_parents,
        predicates=predicates,
        constants=constants,
        actions=actions,
    )
    _validate_domain(domain)
    return domain


def parse_domain_file(path: str | Path) -> Domain:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise PDDLParseError(f"Cannot read {source}: {exc}") from exc
    return parse_domain(text, source=str(source))
