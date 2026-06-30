"""Agentic PDDL formalizer pipeline.

This package mirrors the behaviour of ``source/llm-as-formalizer-api.py`` but,
instead of issuing a single LLM API call, it spins up a Docker container and
runs a full *agent harness* (a "claw", e.g. OpenClaw) inside it. The agent is
free to use its own tools (shell, file edit, ...) to author the PDDL domain and
problem files; we then read the result back out of the container and record the
complete execution trace (including tool calls).

The output layout is intentionally identical to the other ``llm-as-formalizer*``
pipelines so that ``source/run_solver.py`` and ``source/run_val.py`` can consume
the results unchanged (prediction_type ``llm-as-formalizer-agent``).

Adding a new harness only requires implementing :class:`BaseClawAdapter`
(see ``claws/base.py``) and registering it in ``claws/__init__.py``.
"""

PREDICTION_TYPE = "llm-as-formalizer-agent"

__all__ = ["PREDICTION_TYPE"]
