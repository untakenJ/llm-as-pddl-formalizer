from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BARMAN_TEXT = ROOT / "data/textual_barman/Heavily_Templated_Barman-100"
BARMAN_GOLD = ROOT / "data/textual_barman/Barman-100_PDDL/domain.pddl"
LOGISTICS_TEXT = ROOT / "data/textual_logistics/Natural_Logistics-100"
LOGISTICS_GOLD = ROOT / "data/textual_logistics/Logistics-100_PDDL"


def _pddl_action(text: str, action_name: str) -> str:
    start = text.lower().index(f"(:action {action_name.lower()}")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated PDDL action: {action_name}")


def _contains_token(text: str, token: str) -> bool:
    return re.search(
        rf"(?<![A-Za-z0-9-]){re.escape(token)}(?![A-Za-z0-9-])",
        text,
        flags=re.IGNORECASE,
    ) is not None


def test_barman_pour_shaker_to_shot_text_effects_match_gold() -> None:
    action = _pddl_action(BARMAN_GOLD.read_text(encoding="utf-8"), "pour-shaker-to-shot")
    effect = action.lower().split(":effect", maxsplit=1)[1]
    gold_effects = {
        "contains-cocktail": "(contains ?d ?b)" in effect,
        "used-with-cocktail": "(used ?d ?b)" in effect,
        "new-shaker-level": "(shaker-level ?s ?l1)" in effect,
        "not-clean": "(not (clean ?d))" in effect,
        "not-empty": "(not (empty ?d))" in effect,
        "not-old-shaker-level": "(not (shaker-level ?s ?l))" in effect,
    }

    domain_files = sorted(BARMAN_TEXT.glob("p*_domain.txt"))
    assert len(domain_files) == 100
    for path in domain_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        true_line = next(
            line.lower()
            for line in lines
            if line.strip().lower().startswith(
                "once pour-shaker-to-shot action is performed the following will be true:"
            )
        )
        false_line = next(
            line.lower()
            for line in lines
            if line.strip().lower().startswith(
                "once pour-shaker-to-shot action is performed the following will be false:"
            )
        )
        text_effects = {
            "contains-cocktail": "shot glass contains cocktail" in true_line,
            "used-with-cocktail": "shot glass used with cocktail" in true_line,
            "new-shaker-level": "shaker-level of shaker is l1" in true_line,
            "not-clean": "clean shot glass" in false_line,
            "not-empty": "empty shot glass" in false_line,
            "not-old-shaker-level": "shaker-level of shaker is l" in false_line,
        }
        assert text_effects == gold_effects, path


def test_logistics_p14_and_p29_state_packages_are_co_located() -> None:
    p14 = (LOGISTICS_TEXT / "p14_problem.txt").read_text(encoding="utf-8").lower()
    p29 = (LOGISTICS_TEXT / "p29_problem.txt").read_text(encoding="utf-8").lower()
    for index in range(1, 5):
        packages = f"obj{index}1, obj{index}2, and obj{index}3"
        assert (
            f"truck tru{index} and packages {packages} are at position pos{index}" in p14
        )
    for index in range(1, 7):
        packages = f"obj{index}1, obj{index}2, and obj{index}3"
        assert f"tru{index} and packages {packages} are at pos{index}" in p29


def test_logistics_p70_contains_the_missing_gold_goal() -> None:
    natural = (LOGISTICS_TEXT / "p70_problem.txt").read_text(encoding="utf-8")
    golden = (LOGISTICS_GOLD / "p70.pddl").read_text(encoding="utf-8")
    assert "(AT OBJ103 APT7)" in golden
    assert "obj13 and obj103 to apt7" in natural


def test_logistics_location_identifiers_are_literal() -> None:
    for problem in ("p25", "p85", "p96"):
        natural = (LOGISTICS_TEXT / f"{problem}_problem.txt").read_text(
            encoding="utf-8"
        )
        golden = (LOGISTICS_GOLD / f"{problem}.pddl").read_text(encoding="utf-8")
        referenced_locations = set(
            re.findall(
                r"\(at\s+[^\s()]+\s+(city\d+-[123])\)",
                golden,
                flags=re.IGNORECASE,
            )
        )
        assert referenced_locations
        missing = sorted(
            location
            for location in referenced_locations
            if not _contains_token(natural, location)
        )
        assert not missing, f"{problem} omits literal location identifiers: {missing}"
