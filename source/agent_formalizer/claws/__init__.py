"""Claw adapter registry.

Add a new harness by implementing :class:`BaseClawAdapter` (see ``base.py``)
and registering the class in ``CLAWS`` below. ``get_adapter`` fills any unset
constructor arguments from ``CLAW_DEFAULTS``.
"""

from __future__ import annotations

from copy import deepcopy

from agent_formalizer.benchmark_profile import DEFAULT_BENCHMARK_PROFILE
from agent_formalizer.claws.base import BaseClawAdapter
from agent_formalizer.claws.generic import GenericAgentAdapter
from agent_formalizer.claws.hermes import HermesAdapter
from agent_formalizer.claws.minimum import MinimumAgentAdapter
from agent_formalizer.claws.nanobot import NanoBotAdapter
from agent_formalizer.claws.openclaw import OpenClawAdapter
from agent_formalizer.claws.zeroclaw import ZeroClawAdapter

CLAWS: dict[str, type[BaseClawAdapter]] = {
    "generic": GenericAgentAdapter,
    "hermes": HermesAdapter,
    "minimum": MinimumAgentAdapter,
    "nanobot": NanoBotAdapter,
    "openclaw": OpenClawAdapter,
    "zeroclaw": ZeroClawAdapter,
}


def get_adapter(
    name: str,
    model: str | None = None,
    timeout: int | None = None,
    max_action_steps: int | None = None,
    max_model_calls: int | None = None,
    allow_network: bool | None = None,
    network_mode: str | None = None,
    skills_mode: str | None = None,
    benchmark_profile=None,
    resolved_config=None,
    attempts_per_case: int | None = None,
    max_execution_tries: int | None = None,
    allow_final_message_recovery: bool | None = None,
    provider_options: dict | None = None,
    credential_provider_options: dict | None = None,
    api_key: str | None = None,
    api_key_name: str | None = None,
    credential_metadata: dict | None = None,
    **extra,
) -> BaseClawAdapter:
    """Construct a claw adapter, filling unset arguments from CLAW_DEFAULTS."""
    if name not in CLAWS:
        raise ValueError(f"Unknown claw '{name}'. Available: {sorted(CLAWS)}")

    profile = benchmark_profile or DEFAULT_BENCHMARK_PROFILE
    harness_profile = profile.harness(name)
    if network_mode is None and allow_network is not None:
        if allow_network:
            raise ValueError(
                "--allow-network no longer means unrestricted egress; use "
                "network_mode=controlled_web with an explicit allowlist"
            )
        network_mode = "model_only"
    if resolved_config is None:
        resolved_config = profile.resolve(
            name,
            model=model,
            timeout=timeout,
            max_action_steps=max_action_steps,
            max_model_calls=max_model_calls,
            network_mode=network_mode,
            attempts_per_case=attempts_per_case,
            max_execution_tries=max_execution_tries,
            allow_final_message_recovery=allow_final_message_recovery,
            skills_mode=skills_mode,
            provider_options=provider_options,
            harness_overrides={
                key: extra[key]
                for key in ("tools_profile", "tools_allow", "tools_deny")
                if key in extra
            },
        )
    runtime_provider_options = deepcopy(resolved_config.provider_options)
    for provider, options in (credential_provider_options or {}).items():
        current = runtime_provider_options.setdefault(provider, {})
        if not isinstance(current, dict) or not isinstance(options, dict):
            runtime_provider_options[provider] = deepcopy(options)
        else:
            current.update(deepcopy(options))

    kwargs = {
        "model": resolved_config.model,
        "timeout": resolved_config.timeout,
        "max_action_steps": resolved_config.max_action_steps,
        "max_model_calls": resolved_config.max_model_calls,
        "network_mode": resolved_config.network_mode,
        "allow_network": False,
        "skills_mode": resolved_config.skills_mode,
        "benchmark_profile": profile,
        "resolved_config": resolved_config,
        # Credential-owned route material is applied only to the live gateway
        # translation.  It is intentionally absent from resolved_config, whose
        # hash/label defines experimental identity.
        "provider_options": runtime_provider_options,
        "api_key": api_key,
        "api_key_name": api_key_name,
        "credential_metadata": credential_metadata,
    }
    kwargs.update(extra)
    if name == "openclaw":
        configured = resolved_config.harness_overrides
        kwargs["tools_profile"] = configured.get(
            "tools_profile", harness_profile.get("tools_profile", "coding")
        )
        kwargs["tools_allow"] = configured.get("tools_allow")
        kwargs["tools_deny"] = configured.get("tools_deny")
    return CLAWS[name](**kwargs)
