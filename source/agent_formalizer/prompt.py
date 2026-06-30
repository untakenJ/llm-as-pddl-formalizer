"""Build the agent prompt and extract PDDL from agent output.

The prompt instructs the agent to author two files inside the container
workspace; the orchestrator reads those files back. As a fallback (if the agent
emitted the PDDL only in its final message), :func:`extract_pddl_from_text`
parses fenced/JSON blocks out of the transcript.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_formalizer.config import (
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
) -> str:
    """Render the formalizer prompt for the agent."""
    template = template_path.read_text() if template_path else _default_template()
    domain_path = f"{CONTAINER_WORKSPACE}/{DOMAIN_OUTPUT_NAME}"
    problem_path = f"{CONTAINER_WORKSPACE}/{PROBLEM_OUTPUT_NAME}"
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
