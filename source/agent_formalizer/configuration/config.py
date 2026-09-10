"""Global configuration and constants for the agentic formalizer harness.

All benchmark behavior is repository-owned. Host environment variables do not
override runtime paths, images, provider routes, budgets, or tool policy.

Ported and trimmed from ``claw-swe-bench`` (``claw_swebench/config.py``); the
SWE-bench-specific bits (dataset images, gold-patch stripping) are dropped and
replaced with the PDDL-formalizer equivalents.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from agent_formalizer.configuration.benchmark_profile import DEFAULT_BENCHMARK_PROFILE
from . import PACKAGE_DIR

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------
# PACKAGE_DIR remains <repo>/source/agent_formalizer after source relocation.
SOURCE_DIR = PACKAGE_DIR.parent
ROOT_DIR = SOURCE_DIR.parent

DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
PROMPTS_DIR = PACKAGE_DIR / "prompts"
CACHE_DIR = ROOT_DIR / ".cache"
DEFAULT_SECRETS_ENV_FILE = ROOT_DIR / "_private" / ".env"
MODEL_GATEWAY_SCRIPT = PACKAGE_DIR / "gateways" / "model_gateway.py"
MODEL_GATEWAY_CONTAINER_PATH = "/opt/pddl-benchmark/model_gateway.py"
PROVIDER_REASONING_MODULE = PACKAGE_DIR / "results" / "provider_reasoning.py"
PROVIDER_REASONING_CONTAINER_PATH = "/opt/pddl-benchmark/provider_reasoning.py"
INFRA_DIAGNOSTICS_PACKAGE = PACKAGE_DIR / "infra_diagnostics"
INFRA_DIAGNOSTICS_CONTAINER_PATH = "/opt/pddl-benchmark/infra_diagnostics"
EXTERNAL_CALLS_PACKAGE = PACKAGE_DIR / "external_calls"
EXTERNAL_CALLS_CONTAINER_PATH = "/opt/pddl-benchmark/external_calls"
MODEL_GATEWAY_HOST = "model-gateway"
MODEL_GATEWAY_PORT = 8766
LOGITS_GATEWAY_SCRIPT = PACKAGE_DIR / "compute_platforms" / "logits" / "logits_gateway.py"
LOGITS_GATEWAY_CONTAINER_PATH = "/opt/pddl-benchmark/logits_gateway.py"
LOGITS_BRIDGE_SCRIPT = PACKAGE_DIR / "compute_platforms" / "logits" / "logits_openai_bridge.py"
LOGITS_BRIDGE_CONTAINER_PATH = "/opt/pddl-benchmark/logits_openai_bridge.py"
LOGITS_BRIDGE_PORT = 8769
WEB_GATEWAY_SCRIPT = PACKAGE_DIR / "gateways" / "web_gateway.py"
WEB_GATEWAY_CONTAINER_PATH = "/opt/pddl-benchmark/web_gateway.py"
WEB_GATEWAY_HOST = "web-gateway"
WEB_GATEWAY_PORT = 8767
# Optional agent tools live under ``agent_formalizer/tools/<tool>/``.
# Path constants for the solver tool are owned by ``tools.solver``.
TOOLS_DIR = PACKAGE_DIR / "tools"

# Pipeline identifier; used as the top-level output folder so run_solver.py /
# run_val.py can find the generated PDDL (prediction_type).
PREDICTION_TYPE = "llm-as-formalizer-agent"

# ---------------------------------------------------------------------------
# Docker base image / container naming
# ---------------------------------------------------------------------------
# Base image the agent runs inside. Build it with docker/Dockerfile
# (``docker build -t pddl-agent-base:latest source/agent_formalizer/docker``)
# or point this at any Linux image that is glibc-compatible with the host's
# Node.js binary (OpenClaw bind-mounts the host node into the container).
BASE_IMAGE = "pddl-agent-base:latest"

# Keep resource names comfortably below Docker's implementation-specific
# limits.  Uniqueness is carried in a fixed suffix, never in a truncatable tail.
DOCKER_RESOURCE_NAME_MAX = 120

# Working directory inside the container where the agent authors PDDL files.
CONTAINER_WORKSPACE = "/workspace"

# File names the agent is asked to produce inside CONTAINER_WORKSPACE.
DOMAIN_OUTPUT_NAME = "domain.pddl"
PROBLEM_OUTPUT_NAME = "problem.pddl"

# ---------------------------------------------------------------------------
# Domains / datasets (kept in sync with the other formalizer scripts)
# ---------------------------------------------------------------------------
DOMAINS = ["blocksworld", "mystery_blocksworld", "barman", "logistics"]
DATASETS = [
    "Heavily_Templated_BlocksWorld-100",
    "Moderately_Templated_BlocksWorld-100",
    "Natural_BlocksWorld-100",
    "Heavily_Templated_Mystery_BlocksWorld-100",
    "Heavily_Templated_Barman-100",
    "Heavily_Templated_Logistics-100",
    "Moderately_Templated_Logistics-100",
    "Natural_Logistics-100",
]

# ---------------------------------------------------------------------------
# Per-claw defaults. Shared model and budgets come from the default profile in
# configs/benchmark_profiles/; adapter-only settings stay here.
# ---------------------------------------------------------------------------
# OpenClaw keeps its official clean ``coding`` profile unless a condition
# explicitly provides a narrow tools override.

CLAW_DEFAULTS: dict[str, dict] = {
    "openclaw": {
        "model": DEFAULT_BENCHMARK_PROFILE.default_model,
        "timeout": DEFAULT_BENCHMARK_PROFILE.timeout,
        "max_action_steps": DEFAULT_BENCHMARK_PROFILE.max_action_steps,
        "max_model_calls": DEFAULT_BENCHMARK_PROFILE.max_model_calls,
        "allow_network": DEFAULT_BENCHMARK_PROFILE.allow_network,
        "skills_mode": DEFAULT_BENCHMARK_PROFILE.harness("openclaw").get(
            "skills_mode", "official"
        ),
        "tools_profile": DEFAULT_BENCHMARK_PROFILE.harness("openclaw").get(
            "tools_profile", "coding"
        ),
        "tools_allow": None,
        "tools_deny": None,
        # Programmatic compatibility override. CLI runs use the named,
        # provider/model-scoped registry in credential_profiles.json.
        "model_api_keys": {},
    },
    "hermes": {
        "model": DEFAULT_BENCHMARK_PROFILE.default_model,
        "timeout": DEFAULT_BENCHMARK_PROFILE.timeout,
        "max_action_steps": DEFAULT_BENCHMARK_PROFILE.max_action_steps,
        "max_model_calls": DEFAULT_BENCHMARK_PROFILE.max_model_calls,
        "allow_network": DEFAULT_BENCHMARK_PROFILE.allow_network,
        "skills_mode": DEFAULT_BENCHMARK_PROFILE.harness("hermes").get(
            "skills_mode", "official"
        ),
        "model_api_keys": {},
    },
    "nanobot": {
        "model": DEFAULT_BENCHMARK_PROFILE.default_model,
        "timeout": DEFAULT_BENCHMARK_PROFILE.timeout,
        "max_action_steps": DEFAULT_BENCHMARK_PROFILE.max_action_steps,
        "max_model_calls": DEFAULT_BENCHMARK_PROFILE.max_model_calls,
        "allow_network": DEFAULT_BENCHMARK_PROFILE.allow_network,
        "skills_mode": DEFAULT_BENCHMARK_PROFILE.harness("nanobot").get(
            "skills_mode", "official"
        ),
        "model_api_keys": {},
    },
    "zeroclaw": {
        "model": DEFAULT_BENCHMARK_PROFILE.default_model,
        "timeout": DEFAULT_BENCHMARK_PROFILE.timeout,
        "max_action_steps": DEFAULT_BENCHMARK_PROFILE.max_action_steps,
        "max_model_calls": DEFAULT_BENCHMARK_PROFILE.max_model_calls,
        "allow_network": DEFAULT_BENCHMARK_PROFILE.allow_network,
        "skills_mode": DEFAULT_BENCHMARK_PROFILE.harness("zeroclaw").get(
            "skills_mode", "official"
        ),
        "model_api_keys": {},
    },
    "generic": {
        "model": DEFAULT_BENCHMARK_PROFILE.default_model,
        "timeout": DEFAULT_BENCHMARK_PROFILE.timeout,
        "max_action_steps": DEFAULT_BENCHMARK_PROFILE.max_action_steps,
        "max_model_calls": DEFAULT_BENCHMARK_PROFILE.max_model_calls,
        "allow_network": DEFAULT_BENCHMARK_PROFILE.allow_network,
        "skills_mode": DEFAULT_BENCHMARK_PROFILE.harness("generic").get(
            "skills_mode", "official"
        ),
        "model_api_keys": {},
    },
    "minimum": {
        "model": DEFAULT_BENCHMARK_PROFILE.default_model,
        "timeout": DEFAULT_BENCHMARK_PROFILE.timeout,
        "max_action_steps": DEFAULT_BENCHMARK_PROFILE.max_action_steps,
        "max_model_calls": DEFAULT_BENCHMARK_PROFILE.max_model_calls,
        "allow_network": DEFAULT_BENCHMARK_PROFILE.allow_network,
        "skills_mode": "none",
        "model_api_keys": {},
    },
}

DEFAULT_AGENT_TIMEOUT = DEFAULT_BENCHMARK_PROFILE.timeout

# ---------------------------------------------------------------------------
# Model authentication
# ---------------------------------------------------------------------------
# The runner resolves exactly one explicitly named credential and gives the
# value only to the model gateway. Its default source is the repository-local,
# git-ignored ``_private/.env``; an explicitly named process variable remains a
# CI-compatible fallback. It never imports a harness's personal credential
# store or passes the dotenv file into an agent container.
#
# Direct adapter construction retains a one-variable provider default and an
# optional ``model_api_keys`` override for compatibility. Runner/sweep commands
# instead resolve a named credential profile, which binds the key reference to
# provider availability settings before constructing the adapter.
PROVIDER_API_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "google": "GEMINI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google-vertex": "GOOGLE_CLOUD_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "logits": "LOGITS_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
}

PROVIDER_API_BASE: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # The project/location-qualified route is constructed from resolved config.
    "google-vertex": "https://aiplatform.googleapis.com",
    "deepseek": "https://api.deepseek.com/v1",
    # Logits' public service speaks its native sampling REST protocol.  The
    # per-attempt gateway translates the OpenAI Chat Completions wire format;
    # this origin is still the auditable external route.
    "logits": "https://api.logits.dev",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

def provider_for_model(model: str) -> str:
    """Provider id = first path segment of the model id."""
    return model.split("/", 1)[0] if "/" in model else model


def api_key_env_for_model(
    model: str, model_api_keys: dict[str, str] | None = None
) -> str | None:
    """Env var holding the API key for ``model``.

    Resolution order: explicit per-model override in ``model_api_keys``, then the
    provider default from ``PROVIDER_API_KEY_ENV``.
    """
    if model_api_keys and model in model_api_keys:
        return model_api_keys[model]
    return PROVIDER_API_KEY_ENV.get(provider_for_model(model))


# ---------------------------------------------------------------------------
# OpenClaw runtime locations on the HOST (bind-mounted into containers).
# These repository-owned paths are part of the runtime lock; ambient
# environment variables do not override them.
# ---------------------------------------------------------------------------
OPENCLAW_NODE_BIN = "/usr/bin/node"
OPENCLAW_MODULE_DIR = "/usr/lib/node_modules/openclaw"
# Operator's personal OpenClaw install (NOT used for benchmark agent runs).
OPENCLAW_STATE_DIR = Path.home() / ".openclaw"
# Isolated OpenClaw state for benchmark containers. Tool policy and agent
# registrations live here so runs do not inherit ~/.openclaw settings.
OPENCLAW_BENCHMARK_STATE_DIR = ROOT_DIR / ".cache" / "openclaw-benchmark-state"

# Repository-local third-party harness runtimes. The installer populates this
# ignored directory; adapters never read the harnesses' personal user config.
HARNESS_RUNTIME_ROOT = (CACHE_DIR / "harness-runtimes").resolve()

LOGITS_BRIDGE_RUNTIME_ROOT = (HARNESS_RUNTIME_ROOT / "logits-bridge").resolve()
LOGITS_BRIDGE_ENV_PATH = (LOGITS_BRIDGE_RUNTIME_ROOT / "venv").resolve()
LOGITS_MODEL_ASSETS_ROOT = (LOGITS_BRIDGE_RUNTIME_ROOT / "models").resolve()

HERMES_ENV_PATH = (HARNESS_RUNTIME_ROOT / "hermes").resolve()
NANOBOT_ENV_PATH = (HARNESS_RUNTIME_ROOT / "nanobot").resolve()
ZEROCLAW_BIN = (
    HARNESS_RUNTIME_ROOT / "zeroclaw" / ".cargo" / "bin" / "zeroclaw"
).resolve()
ZEROCLAW_PREFIX = (HARNESS_RUNTIME_ROOT / "zeroclaw").resolve()
ZEROCLAW_VERSION_NOTE_PATH = (ZEROCLAW_PREFIX / "VERSION_NOTE").resolve()
ZEROCLAW_SOURCE_PATH = (HARNESS_RUNTIME_ROOT / "zeroclaw-source").resolve()
GENERIC_REPO_PATH = (HARNESS_RUNTIME_ROOT / "genericagent" / "repo").resolve()
GENERIC_ENV_PATH = (HARNESS_RUNTIME_ROOT / "genericagent" / "venv").resolve()

GENERIC_BENCHMARK_STATE_DIR = (CACHE_DIR / "generic-benchmark-state").resolve()

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def sanitize_model_name(model: str) -> str:
    """Turn a model id into a filesystem- and solver/val-safe label.

    ``run_solver.py`` / ``run_val.py`` split the model name on ``/`` expecting
    exactly two parts, so models like ``openrouter/anthropic/claude-opus-4.6``
    would crash them. We collapse slashes (and a couple of other awkward
    characters) so the resulting directory name round-trips cleanly. Pass the
    *sanitized* name to run_solver.py / run_val.py via ``--model``.
    """
    return model.replace("/", "__").replace(":", "_").replace(" ", "_")


def agent_model_label(claw: str, model: str) -> str:
    """Default output label, unique across both harness and model."""
    return f"{sanitize_model_name(claw)}__{sanitize_model_name(model)}"


def domain_dir(domain: str, data: str) -> Path:
    """Directory holding the textual ``p*_domain.txt`` / ``p*_problem.txt``."""
    return DATA_DIR / f"textual_{domain}" / data


def problem_output_dir(out_root: Path, domain: str, data: str, model_label: str,
                       problem: str) -> Path:
    """Output dir for one problem, matching the other formalizer pipelines.

    ``<out_root>/llm-as-formalizer-agent/<domain>/<data>/<model_label>/<problem>/``
    """
    return out_root / PREDICTION_TYPE / domain / data / model_label / problem


def new_runtime_id() -> str:
    """Return an opaque identifier for one live execution environment."""
    return uuid.uuid4().hex[:16]


def _safe_docker_name(value: str) -> str:
    """Sanitize ``value`` to Docker's ASCII resource-name character set."""
    safe = "".join(
        c if c.isascii() and (c.isalnum() or c in "_.-") else "-"
        for c in value
    )
    safe = safe.lstrip("_.-")
    return safe or "pddl"


def _bounded_docker_name(readable: str, unique_suffix: str) -> str:
    """Fit a readable name while preserving the complete unique suffix."""
    safe = _safe_docker_name(readable)
    suffix = "-" + _safe_docker_name(unique_suffix)
    prefix_limit = DOCKER_RESOURCE_NAME_MAX - len(suffix)
    if prefix_limit < 1:
        raise ValueError("Docker resource unique suffix is too long")
    prefix = safe[:prefix_limit].rstrip("_.-") or "pddl"
    return f"{prefix}{suffix}"


def container_name(
    claw_name: str,
    domain: str,
    data: str,
    model_label: str,
    problem: str,
    *,
    runtime_id: str | None = None,
) -> str:
    """Return a readable, per-execution unique Docker container name.

    The logical-identity digest distinguishes tasks whose readable prefixes are
    truncated.  The runtime token distinguishes concurrent executions of the
    same logical task in separate sweeps.
    """
    logical = f"{claw_name}-pddl-{domain}-{data}-{model_label}-{problem}"
    readable = f"{claw_name}-pddl-{domain}-{data}-{problem}"
    logical_digest = hashlib.sha256(logical.encode()).hexdigest()[:10]
    token = runtime_id or new_runtime_id()
    runtime_digest = hashlib.sha256(token.encode()).hexdigest()[:16]
    return _bounded_docker_name(
        readable,
        f"{logical_digest}-{runtime_digest}",
    )


def related_docker_resource_name(container: str, role: str) -> str:
    """Derive a unique sidecar/network name without dropping container entropy."""
    parent_digest = hashlib.sha256(container.encode()).hexdigest()[:16]
    return _bounded_docker_name(container, f"{parent_digest}-{role}")
