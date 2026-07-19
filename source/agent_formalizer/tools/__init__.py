"""Optional condition-level agent tools shared across harnesses.

Each subdirectory under ``tools/`` is one optional capability (for example
``solver/``). Condition profiles enable tools via ``agent_tools: [...]``; the
registry below is the single place that maps those ids to files, gateway
sidecars, and prompt templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_formalizer.tools import solver as solver_tool

TOOLS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class AgentToolSpec:
    """Host-side description of one optional agent tool."""

    tool_id: str
    cli_host_path: Path
    cli_container_path: str
    gateway_host: str
    gateway_port: int
    gateway_dir_host: Path
    gateway_dir_container: str
    gateway_entrypoint: str
    prompt_template: Path
    infra_invalidator: str
    env_gateway: str


KNOWN_AGENT_TOOLS: dict[str, AgentToolSpec] = {
    solver_tool.TOOL_ID: AgentToolSpec(
        tool_id=solver_tool.TOOL_ID,
        cli_host_path=solver_tool.SOLVER_DIR / solver_tool.CLI_NAME,
        cli_container_path=solver_tool.CLI_CONTAINER_PATH,
        gateway_host=solver_tool.GATEWAY_HOST,
        gateway_port=solver_tool.GATEWAY_PORT,
        gateway_dir_host=solver_tool.SOLVER_DIR,
        gateway_dir_container=solver_tool.GATEWAY_CONTAINER_DIR,
        gateway_entrypoint=solver_tool.GATEWAY_ENTRYPOINT,
        prompt_template=solver_tool.SOLVER_DIR / solver_tool.PROMPT_NAME,
        infra_invalidator=solver_tool.INFRA_INVALIDATOR,
        env_gateway=solver_tool.ENV_GATEWAY,
    ),
}


def known_agent_tool_ids() -> frozenset[str]:
    return frozenset(KNOWN_AGENT_TOOLS)


def resolve_agent_tools(tool_ids: list[str]) -> list[AgentToolSpec]:
    """Return ordered specs for requested tool ids (unknown ids raise)."""
    unknown = sorted(set(tool_ids) - set(KNOWN_AGENT_TOOLS))
    if unknown:
        raise ValueError(
            "unsupported agent_tools: "
            + ", ".join(unknown)
            + "; known: "
            + ", ".join(sorted(KNOWN_AGENT_TOOLS))
        )
    seen: set[str] = set()
    ordered: list[AgentToolSpec] = []
    for tool_id in tool_ids:
        if tool_id in seen:
            continue
        seen.add(tool_id)
        ordered.append(KNOWN_AGENT_TOOLS[tool_id])
    return ordered


def prompt_template_for_tools(tool_ids: list[str] | None) -> Path | None:
    """Pick a condition prompt when tools supply templates.

    Multi-tool prompt composition can be added later; today the first tool that
    ships a template wins (currently only ``pddl_solver``).
    """
    if not tool_ids:
        return None
    for spec in resolve_agent_tools(list(tool_ids)):
        if spec.prompt_template.is_file():
            return spec.prompt_template
    return None
