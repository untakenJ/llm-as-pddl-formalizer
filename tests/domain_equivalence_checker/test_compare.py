from __future__ import annotations

import unittest
from pathlib import Path

from pddl_domain_equivalence import (
    compare_domains,
    compare_level_one,
    compare_level_two,
    parse_domain,
)


ROOT = Path(__file__).resolve().parents[2]


BASE = """
(define (domain transport)
  (:requirements :strips :typing)
  (:types vehicle location - object)
  (:predicates
    (at ?vehicle - vehicle ?location - location)
    (connected ?from - location ?to - location))
  (:action move
    :parameters (?vehicle - vehicle ?from - location ?to - location)
    :precondition
      (and (at ?vehicle ?from) (connected ?from ?to))
    :effect
      (and (not (at ?vehicle ?from)) (at ?vehicle ?to))))
"""


REORDERED = """
(define (domain transport-renamed-locals)
  (:requirements :typing :strips)
  (:types location vehicle - object)
  (:predicates
    (connected ?to - location ?from - location)
    (at ?place - location ?thing - vehicle))
  (:action move
    :parameters (?destination - location ?source - location ?item - vehicle)
    :precondition
      (and (connected ?destination ?source) (at ?source ?item))
    :effect
      (and (at ?destination ?item) (not (at ?source ?item)))))
"""


RENAMED_GLOBALS = """
(define (domain travel)
  (:requirements :strips :typing)
  (:types site conveyance - object)
  (:predicates
    (located ?x - conveyance ?where - site)
    (linked ?source - site ?destination - site))
  (:action travel
    :parameters (?x - conveyance ?source - site ?destination - site)
    :precondition
      (and (linked ?source ?destination) (located ?x ?source))
    :effect
      (and (located ?x ?destination) (not (located ?x ?source)))))
"""


WRONG_DELETE = """
(define (domain transport)
  (:requirements :strips :typing)
  (:types vehicle location - object)
  (:predicates
    (at ?vehicle - vehicle ?location - location)
    (connected ?from - location ?to - location))
  (:action move
    :parameters (?vehicle - vehicle ?from - location ?to - location)
    :precondition
      (and (at ?vehicle ?from) (connected ?from ?to))
    :effect (at ?vehicle ?to)))
"""


GENERIC_LOAD = """
(define (domain generic)
  (:requirements :strips :typing)
  (:types package vehicle location - object truck airplane - vehicle)
  (:predicates (at ?x - object ?l - location) (inside ?p - package ?v - vehicle))
  (:action load
    :parameters (?p - package ?v - vehicle ?l - location)
    :precondition (at ?p ?l)
    :effect (and (not (at ?p ?l)) (inside ?p ?v))))
"""


SPECIALIZED_LOAD = """
(define (domain specialized)
  (:requirements :strips :typing)
  (:types package vehicle location - object truck airplane - vehicle)
  (:predicates (at ?x - object ?l - location) (inside ?p - package ?v - vehicle))
  (:action load-truck
    :parameters (?p - package ?v - truck ?l - location)
    :precondition (at ?p ?l)
    :effect (and (not (at ?p ?l)) (inside ?p ?v)))
  (:action load-airplane
    :parameters (?p - package ?v - airplane ?l - location)
    :precondition (at ?p ?l)
    :effect (and (not (at ?p ?l)) (inside ?p ?v))))
"""


class CompareTests(unittest.TestCase):
    def test_level_one_ignores_local_names_order_and_parameter_permutations(self) -> None:
        result = compare_level_one(parse_domain(BASE), parse_domain(REORDERED))
        self.assertTrue(result.equivalent, result.reason)
        self.assertEqual("alpha_abi_equivalent", result.relation)
        self.assertNotEqual((0, 1), result.mapping.predicate_parameters["at"])
        self.assertNotEqual((0, 1, 2), result.mapping.action_parameters["move"])

    def test_level_one_rejects_unknown_global_renaming(self) -> None:
        result = compare_level_one(parse_domain(BASE), parse_domain(RENAMED_GLOBALS))
        self.assertFalse(result.equivalent)

    def test_level_two_discovers_global_renaming(self) -> None:
        result = compare_level_two(parse_domain(BASE), parse_domain(RENAMED_GLOBALS))
        self.assertTrue(result.equivalent, result.reason)
        self.assertEqual("schema_isomorphic", result.relation)
        self.assertTrue(result.verified_by_level_one)
        self.assertEqual("travel", result.mapping.actions["move"])

    def test_explicit_global_mapping_turns_level_two_case_into_level_one(self) -> None:
        mapping = {
            "types": {
                "object": "object",
                "vehicle": "conveyance",
                "location": "site",
            },
            "predicates": {"at": "located", "connected": "linked"},
            "actions": {"move": "travel"},
        }
        result = compare_level_one(
            parse_domain(BASE), parse_domain(RENAMED_GLOBALS), mapping
        )
        self.assertTrue(result.equivalent, result.reason)
        self.assertEqual("alpha_abi_equivalent", result.relation)

    def test_missing_delete_effect_is_not_equivalent(self) -> None:
        result = compare_domains(parse_domain(BASE), parse_domain(WRONG_DELETE))
        self.assertFalse(result.equivalent)

    def test_different_type_hierarchy_is_not_equivalent(self) -> None:
        altered = RENAMED_GLOBALS.replace(
            "(:types site conveyance - object)",
            "(:types site - object conveyance - site)",
        )
        result = compare_level_two(parse_domain(BASE), parse_domain(altered))
        self.assertFalse(result.equivalent)

    def test_non_bijective_action_specialization_is_level_three(self) -> None:
        result = compare_level_two(
            parse_domain(GENERIC_LOAD), parse_domain(SPECIALIZED_LOAD)
        )
        self.assertFalse(result.equivalent)

    def test_official_blocksworld_and_mystery_are_schema_isomorphic(self) -> None:
        blocksworld = (
            ROOT / "data/textual_blocksworld/BlocksWorld-100_PDDL/domain.pddl"
        )
        mystery = (
            ROOT
            / "data/textual_mystery_blocksworld/"
            "Mystery_BlocksWorld-100_PDDL/domain.pddl"
        )
        first = compare_level_one(blocksworld, mystery)
        second = compare_level_two(blocksworld, mystery)
        self.assertFalse(first.equivalent)
        self.assertTrue(second.equivalent, second.reason)
        self.assertTrue(second.verified_by_level_one)

    def test_real_agent_natural_logistics_requires_level_three(self) -> None:
        reference = ROOT / "data/textual_logistics/Logistics-100_PDDL/domain.pddl"
        generated = (
            ROOT
            / "output/agent_sweep_20260712-203003_full_all5_google_vertex_"
            "gemini31_flash_lite/llm-as-formalizer-agent/logistics/"
            "Natural_Logistics-100/openclaw__google-vertex__gemini-3.1-flash-lite/"
            "p01/p01_openclaw__google-vertex__gemini-3.1-flash-lite_df.pddl"
        )
        if not generated.exists():
            self.skipTest("The archived agent-generated integration fixture is absent.")
        result = compare_level_two(reference, generated)
        self.assertFalse(result.equivalent)
        self.assertNotEqual(result.left_summary["actions"], result.right_summary["actions"])

    def test_real_agent_natural_blocksworld_is_schema_isomorphic(self) -> None:
        reference = (
            ROOT / "data/textual_blocksworld/BlocksWorld-100_PDDL/domain.pddl"
        )
        generated = (
            ROOT
            / "output/agent_sweep_20260712-203003_full_all5_google_vertex_"
            "gemini31_flash_lite/llm-as-formalizer-agent/blocksworld/"
            "Natural_BlocksWorld-100/hermes__google-vertex__gemini-3.1-flash-lite/"
            "p01/p01_hermes__google-vertex__gemini-3.1-flash-lite_df.pddl"
        )
        if not generated.exists():
            self.skipTest("The archived agent-generated integration fixture is absent.")
        result = compare_domains(reference, generated)
        self.assertTrue(result.equivalent, result.reason)
        self.assertEqual("schema_isomorphic", result.relation)
        self.assertEqual("handempty", result.mapping.predicates["arm-empty"])


if __name__ == "__main__":
    unittest.main()
