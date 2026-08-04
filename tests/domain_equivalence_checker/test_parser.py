from __future__ import annotations

import unittest
from pathlib import Path

from pddl_domain_equivalence import PDDLParseError, UnsupportedPDDL, parse_domain
from pddl_domain_equivalence.parser import parse_domain_file


ROOT = Path(__file__).resolve().parents[2]


class ParserTests(unittest.TestCase):
    def test_parses_all_official_repository_domains(self) -> None:
        paths = (
            ROOT / "data/textual_blocksworld/BlocksWorld-100_PDDL/domain.pddl",
            ROOT
            / "data/textual_mystery_blocksworld/"
            "Mystery_BlocksWorld-100_PDDL/domain.pddl",
            ROOT / "data/textual_logistics/Logistics-100_PDDL/domain.pddl",
            ROOT / "data/textual_barman/Barman-100_PDDL/domain.pddl",
        )
        for path in paths:
            with self.subTest(path=path):
                domain = parse_domain_file(path)
                self.assertTrue(domain.actions)
                self.assertTrue(domain.predicates)

    def test_rejects_conditional_effect_instead_of_ignoring_it(self) -> None:
        text = """
        (define (domain unsupported)
          (:requirements :strips)
          (:predicates (p) (q))
          (:action a
            :parameters ()
            :precondition (p)
            :effect (when (p) (q))))
        """
        with self.assertRaises(UnsupportedPDDL):
            parse_domain(text)

    def test_rejects_undeclared_variable(self) -> None:
        text = """
        (define (domain broken)
          (:requirements :strips)
          (:predicates (p ?x))
          (:action a
            :parameters (?y)
            :precondition (p ?x)
            :effect (p ?y)))
        """
        with self.assertRaises(PDDLParseError):
            parse_domain(text)

    def test_parses_negative_preconditions(self) -> None:
        text = """
        (define (domain negative)
          (:requirements :strips :negative-preconditions)
          (:predicates (p ?x) (q ?x))
          (:action a
            :parameters (?x)
            :precondition (and (p ?x) (not (q ?x)))
            :effect (q ?x)))
        """
        domain = parse_domain(text)
        action = domain.actions["a"]
        self.assertEqual(1, len(action.positive_preconditions))
        self.assertEqual(1, len(action.negative_preconditions))


if __name__ == "__main__":
    unittest.main()
