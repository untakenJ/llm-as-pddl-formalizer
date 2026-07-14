"""Claw adapter registry.

Add a new harness by implementing :class:`BaseClawAdapter` (see ``base.py``)
and registering the class in ``CLAWS`` below. ``get_adapter`` fills any unset
constructor arguments from ``CLAW_DEFAULTS``.
"""

from __future__ import annotations

from agent_formalizer.config import CLAW_DEFAULTS
from agent_formalizer.claws.base import BaseClawAdapter
from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.openclaw import OpenClawAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter

CLAWS: dict[str, type[BaseClawAdapter]] = {
    "generic": GenericAgentAdapter,
    "hermes": HermesAdapter,
    "nanobot": NanoBotAdapter,
    "openclaw": OpenClawAdapter,
    "zeroclaw": ZeroClawAdapter,
}


def get_adapter(
    name: str,
    model: str | None = None,
    timeout: int | None = None,
    max_turns: int | None = None,
    **extra,
) -> BaseClawAdapter:
    """Construct a claw adapter, filling unset arguments from CLAW_DEFAULTS."""
    if name not in CLAWS:
        raise ValueError(f"Unknown claw '{name}'. Available: {sorted(CLAWS)}")

    defaults = CLAW_DEFAULTS[name]
    kwargs = {
        "model": model or defaults["model"],
        "timeout": timeout or defaults["timeout"],
        "max_turns": max_turns if max_turns is not None else defaults["max_turns"],
    }
    for key in ("tools_profile", "tools_allow", "tools_deny", "model_api_keys"):
        if key in defaults and key not in extra:
            kwargs[key] = defaults[key]
    kwargs.update(extra)
    return CLAWS[name](**kwargs)
