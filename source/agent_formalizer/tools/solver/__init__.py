"""Optional PDDL solver tool for condition ``agent_tools: ["pddl_solver"]``.

Layout:
  remote_client.py  shared planning.domains client (also used by run_solver.py)
  gateway.py        per-attempt sidecar routed to the selected backend
  pddl-solver       agent-facing CLI mounted at /usr/local/bin/pddl-solver
  prompt.txt        condition prompt documenting the CLI
"""

from __future__ import annotations

from pathlib import Path

SOLVER_DIR = Path(__file__).resolve().parent
CLI_NAME = "pddl-solver"
GATEWAY_ENTRYPOINT = "gateway.py"
PROMPT_NAME = "prompt.txt"
TOOL_ID = "pddl_solver"
GATEWAY_HOST = "solver-gateway"
GATEWAY_PORT = 8768
GATEWAY_CONTAINER_DIR = "/opt/pddl-benchmark/tools/solver"
CLI_CONTAINER_PATH = "/usr/local/bin/pddl-solver"
INFRA_INVALIDATOR = "solver_gateway_start_failed"
ENV_GATEWAY = "PDDL_SOLVER_GATEWAY"

from agent_formalizer.tools.solver.remote_client import (  # noqa: E402
    DEFAULT_SOLVER,
    SOLVER_BASE_URL,
    plan_text_from_solver_result,
    solve_pddl,
)

__all__ = [
    "CLI_CONTAINER_PATH",
    "CLI_NAME",
    "DEFAULT_SOLVER",
    "ENV_GATEWAY",
    "GATEWAY_CONTAINER_DIR",
    "GATEWAY_ENTRYPOINT",
    "GATEWAY_HOST",
    "GATEWAY_PORT",
    "INFRA_INVALIDATOR",
    "PROMPT_NAME",
    "SOLVER_BASE_URL",
    "SOLVER_DIR",
    "TOOL_ID",
    "plan_text_from_solver_result",
    "solve_pddl",
]
