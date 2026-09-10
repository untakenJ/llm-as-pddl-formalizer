"""Build the agent prompt and extract PDDL from agent output.

The prompt instructs the agent to author two files inside the container
workspace; only those files count by default. ``extract_pddl_from_text`` exists
for the explicitly enabled experimental final-message recovery condition.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_formalizer.configuration.config import (
    CONTAINER_WORKSPACE,
    DOMAIN_OUTPUT_NAME,
    PROBLEM_OUTPUT_NAME,
    PROMPTS_DIR,
)


def _default_template() -> str:
    return (PROMPTS_DIR / "default.txt").read_text()


def build_prompt(
    domain_description: str,
    problem_description: str,
    template_path: Path | None = None,
    *,
    domain_output_name: str = DOMAIN_OUTPUT_NAME,
    problem_output_name: str = PROBLEM_OUTPUT_NAME,
    agent_tools: list[str] | None = None,
) -> str:
    """Render the formalizer prompt for the agent."""
    if template_path is not None:
        template = template_path.read_text()
    elif agent_tools:
        from agent_formalizer.tools import prompt_template_for_tools

        tool_template = prompt_template_for_tools(agent_tools)
        template = tool_template.read_text() if tool_template else _default_template()
    else:
        template = _default_template()
    domain_path = f"{CONTAINER_WORKSPACE}/{domain_output_name}"
    problem_path = f"{CONTAINER_WORKSPACE}/{problem_output_name}"
    return template.format(
        workspace=CONTAINER_WORKSPACE,
        domain_description=domain_description,
        problem_description=problem_description,
        domain_path=domain_path,
        problem_path=problem_path,
    )


def extract_pddl_from_text(text: str) -> tuple[str | None, str | None]:
    """Best-effort recovery of (domain_file, problem_file) from a transcript.

    Tries, in order:
    1. A JSON object with ``"domain file"`` / ``"problem file"`` keys
       (the schema used by the API formalizer pipelines).
    2. Two ``(define (domain ...))`` / ``(define (problem ...))`` blocks.
    """
    if not text:
        return None, None

    # 1. JSON object.
    for candidate in _iter_json_objects(text):
        if "domain file" in candidate and "problem file" in candidate:
            return candidate["domain file"], candidate["problem file"]

    # 2. Raw balanced define blocks (also handles content inside fences).
    domain_file = _first_define(text, "domain")
    problem_file = _first_define(text, "problem")
    return domain_file, problem_file


def _first_define(text: str, kind: str) -> str | None:
    """Extract the first balanced ``(define (<kind> ...))`` block."""
    marker = f"(define"
    lowered = text.lower()
    search_from = 0
    while True:
        start = lowered.find(marker, search_from)
        if start == -1:
            return None
        # Confirm this define is for the requested kind.
        head = lowered[start:start + 40]
        if f"({kind}" not in head and f"( {kind}" not in head:
            search_from = start + len(marker)
            continue
        # Balance parentheses from start.
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text[start:]  # unbalanced; return the rest


def _iter_json_objects(text: str):
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                yield obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
