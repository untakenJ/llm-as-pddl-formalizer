"""JELIA-inspired semantic graph construction.

The published LDMG representation connects actions directly to predicates with
parameter-binding edge labels.  This implementation expands those labels into nodes
so that a stock, edge-labelled NetworkX DiGraphMatcher can recover symbol and
signature-parameter permutations.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from .model import Domain


@dataclass
class GraphIndex:
    types: dict[str, int] = field(default_factory=dict)
    predicates: dict[str, int] = field(default_factory=dict)
    predicate_parameters: dict[tuple[str, int], int] = field(default_factory=dict)
    constants: dict[str, int] = field(default_factory=dict)
    actions: dict[str, int] = field(default_factory=dict)
    action_parameters: dict[tuple[str, int], int] = field(default_factory=dict)


@dataclass
class DomainGraph:
    graph: nx.DiGraph
    index: GraphIndex


def build_domain_graph(domain: Domain) -> DomainGraph:
    graph = nx.DiGraph()
    index = GraphIndex()
    next_node = 0

    def add_node(kind: str, **metadata: Any) -> int:
        nonlocal next_node
        node = next_node
        next_node += 1
        graph.add_node(node, kind=kind, pin=None, **metadata)
        return node

    def add_edge(source: int, target: int, kind: str) -> None:
        if graph.has_edge(source, target):
            previous = graph.edges[source, target]["kind"]
            raise AssertionError(
                f"Graph encoding attempted parallel edges {previous!r}/{kind!r} "
                f"between {source} and {target}."
            )
        graph.add_edge(source, target, kind=kind)

    for type_name in sorted(domain.type_parents):
        kind = "root_type" if type_name == "object" else "type"
        index.types[type_name] = add_node(kind, name=type_name)
    for type_name, parent in sorted(domain.type_parents.items()):
        if parent is not None:
            add_edge(index.types[type_name], index.types[parent], "type_parent")

    for predicate_name, predicate in sorted(domain.predicates.items()):
        predicate_node = add_node("predicate", name=predicate_name)
        index.predicates[predicate_name] = predicate_node
        for position, parameter in enumerate(predicate.parameters):
            parameter_node = add_node(
                "predicate_parameter",
                owner=predicate_name,
                position=position,
                source_name=parameter.name,
            )
            index.predicate_parameters[(predicate_name, position)] = parameter_node
            add_edge(predicate_node, parameter_node, "declares_parameter")
            add_edge(parameter_node, index.types[parameter.type_name], "parameter_type")

    for constant_name, type_name in sorted(domain.constants.items()):
        constant_node = add_node("constant", name=constant_name)
        index.constants[constant_name] = constant_node
        add_edge(constant_node, index.types[type_name], "constant_type")

    for action_name, action in sorted(domain.actions.items()):
        action_node = add_node("action", name=action_name)
        index.actions[action_name] = action_node
        variable_nodes: dict[str, int] = {}
        for position, parameter in enumerate(action.parameters):
            parameter_node = add_node(
                "action_parameter",
                owner=action_name,
                position=position,
                source_name=parameter.name,
            )
            index.action_parameters[(action_name, position)] = parameter_node
            variable_nodes[parameter.name] = parameter_node
            add_edge(action_node, parameter_node, "declares_parameter")
            add_edge(parameter_node, index.types[parameter.type_name], "parameter_type")

        for ordinal, (role, atom) in enumerate(action.literals()):
            occurrence_node = add_node(
                f"literal:{role}",
                owner=action_name,
                ordinal=ordinal,
            )
            add_edge(action_node, occurrence_node, "contains_literal")
            add_edge(
                occurrence_node,
                index.predicates[atom.predicate],
                "uses_predicate",
            )
            for position, argument in enumerate(atom.arguments):
                binding_node = add_node(
                    "argument_binding",
                    owner=action_name,
                    position=position,
                )
                add_edge(occurrence_node, binding_node, "has_binding")
                add_edge(
                    binding_node,
                    index.predicate_parameters[(atom.predicate, position)],
                    "predicate_position",
                )
                term_node = (
                    variable_nodes[argument]
                    if argument.startswith("?")
                    else index.constants[argument]
                )
                add_edge(binding_node, term_node, "bound_term")

    return DomainGraph(graph, index)


def graph_profile(domain_graph: DomainGraph) -> dict[str, dict[str, int]]:
    node_kinds = Counter(
        attributes["kind"] for _, attributes in domain_graph.graph.nodes(data=True)
    )
    edge_kinds = Counter(
        attributes["kind"]
        for _, _, attributes in domain_graph.graph.edges(data=True)
    )
    return {
        "nodes": dict(sorted(node_kinds.items())),
        "edges": dict(sorted(edge_kinds.items())),
    }


def copy_with_pins(
    domain_graph: DomainGraph,
    pins: dict[int, str],
) -> nx.DiGraph:
    graph = domain_graph.graph.copy()
    nx.set_node_attributes(graph, None, "pin")
    for node, pin in pins.items():
        graph.nodes[node]["pin"] = pin
    return graph


def find_isomorphism(
    left: DomainGraph,
    right: DomainGraph,
    *,
    forced_nodes: dict[int, int] | None = None,
) -> dict[int, int] | None:
    """Return an exact left-to-right graph isomorphism, if one exists.

    ``forced_nodes`` turns the general schema search into a level-one check.  Every
    forced pair receives the same unique pin on both graph copies, which makes all
    other pairings illegal under the node matcher.
    """

    forced_nodes = forced_nodes or {}
    if len(set(forced_nodes.values())) != len(forced_nodes):
        return None
    for left_node, right_node in forced_nodes.items():
        if left.graph.nodes[left_node]["kind"] != right.graph.nodes[right_node]["kind"]:
            return None

    left_pins: dict[int, str] = {}
    right_pins: dict[int, str] = {}
    for ordinal, (left_node, right_node) in enumerate(sorted(forced_nodes.items())):
        pin = f"forced:{ordinal}"
        left_pins[left_node] = pin
        right_pins[right_node] = pin

    left_graph = copy_with_pins(left, left_pins)
    right_graph = copy_with_pins(right, right_pins)
    node_match = nx.algorithms.isomorphism.categorical_node_match(
        ["kind", "pin"], [None, None]
    )
    edge_match = nx.algorithms.isomorphism.categorical_edge_match("kind", None)
    matcher = nx.algorithms.isomorphism.DiGraphMatcher(
        left_graph,
        right_graph,
        node_match=node_match,
        edge_match=edge_match,
    )
    if not matcher.is_isomorphic():
        return None
    mapping = dict(matcher.mapping)
    if any(mapping.get(left_node) != right_node for left_node, right_node in forced_nodes.items()):
        raise AssertionError("NetworkX returned an isomorphism that violates forced pins.")
    return mapping
