"""Shared data types used across the agentic formalizer package.

``AgentResult`` is ported verbatim from ``claw-swe-bench`` so adapters written
against that interface drop straight in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentResult:
    """Structured result from a single claw agent run."""

    success: bool
    timeout: bool
    exit_code: int
    finish_reason: str  # "stop" / "timeout" / "action_step_limit" / "error" / "empty"
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    session_id: str | None = None
    session_file: str | None = None  # host path to session JSONL, when known
    openclaw_agent_id: str | None = None  # normalized OpenClaw agent dir name
    duration_seconds: float = 0.0
    usage: dict = field(default_factory=dict)  # token usage from agent meta
    final_text: str | None = None  # last assistant message text, if available


@dataclass
class FormalizerResult:
    """Outcome of formalizing one problem with an agent harness."""

    problem: str
    status: str  # "ok" / "failed" / "infra_invalid"
    domain_file: str | None = None
    problem_file: str | None = None
    extraction_source: str | None = None  # "file" / "parsed" / None
    agent_result: AgentResult | None = None
    error: str | None = None
    attempt_index: int = 1
    execution_try: int = 1
    attempt_valid: bool = True
    generation_success: bool = False
    model_label: str | None = None
    completion_path: Path | None = None
    domain_bytes: bytes | None = None
    problem_bytes: bytes | None = None
