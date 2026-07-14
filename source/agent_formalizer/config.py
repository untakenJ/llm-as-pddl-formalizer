"""Global configuration and constants for the agentic formalizer harness.

All paths, naming conventions, timeouts, and defaults live here so the rest of
the package never hardcodes values. Host-machine paths (claw runtimes, base
image name) can be overridden via environment variables so the framework is
portable across machines.

Ported and trimmed from ``claw-swe-bench`` (``claw_swebench/config.py``); the
SWE-bench-specific bits (dataset images, gold-patch stripping) are dropped and
replaced with the PDDL-formalizer equivalents.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------
# This file lives at <repo>/source/agent_formalizer/config.py
PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = PACKAGE_DIR.parent
ROOT_DIR = SOURCE_DIR.parent

DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
PROMPTS_DIR = PACKAGE_DIR / "prompts"
CACHE_DIR = ROOT_DIR / ".cache"

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
BASE_IMAGE = os.environ.get("PDDL_AGENT_IMAGE", "pddl-agent-base:latest")

# Working directory inside the container where the agent authors PDDL files.
CONTAINER_WORKSPACE = os.environ.get("PDDL_AGENT_WORKSPACE", "/workspace")

# File names the agent is asked to produce inside CONTAINER_WORKSPACE.
DOMAIN_OUTPUT_NAME = "domain.pddl"
PROBLEM_OUTPUT_NAME = "problem.pddl"

# Per-container resource limits — protect the host when running many agents in
# parallel.
CONTAINER_PIDS_LIMIT = int(os.environ.get("PDDL_AGENT_PIDS_LIMIT", "300"))
CONTAINER_MEMORY = os.environ.get("PDDL_AGENT_CONTAINER_MEMORY", "8g")

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
# Per-claw defaults (model semantics differ per claw; see each adapter).
# ---------------------------------------------------------------------------
# OpenClaw tool policy for benchmark runs (isolated OPENCLAW_BENCHMARK_STATE_DIR).
# Profile matches local onboarding default (``coding``); deny list is ported from
# ``opensquilla/claw-swe-bench`` (``claw_swebench/claws/openclaw.py`` DENY_TOOLS).
# Override per run via --tools-profile / --tools-allow / --tools-deny.
OPENCLAW_DENY_TOOLS = [
    "memory_search", "memory_get",
    "web_search", "web_fetch",
    "sessions_list", "sessions_history", "sessions_send",
    "sessions_yield", "sessions_spawn",
    "subagents", "session_status",
    "cron", "image",
]

CLAW_DEFAULTS: dict[str, dict] = {
    "openclaw": {
        "model": "openrouter/anthropic/claude-opus-4.6",
        "timeout": 1800,
        "max_turns": 200,
        "tools_profile": "coding",
        "tools_allow": None,
        "tools_deny": OPENCLAW_DENY_TOOLS,
        # Per-model API-key env override (model id -> env var name). Models not
        # listed fall back to PROVIDER_API_KEY_ENV by provider prefix. This is
        # how harness / model / API-key env are decoupled and freely combined,
        # e.g. {"openai/gpt-5.4-mini": "OPENAI_API_KEY_BENCH"}.
        "model_api_keys": {},
    },
    "hermes": {
        "model": "openai/gpt-5.4-mini",
        "timeout": 1800,
        "max_turns": 200,
        "model_api_keys": {},
    },
    "nanobot": {
        "model": "openai/gpt-5.4-mini",
        "timeout": 1800,
        "max_turns": 200,
        "model_api_keys": {},
    },
    "zeroclaw": {
        "model": "openai/gpt-5.4-mini",
        "timeout": 1800,
        "max_turns": 200,
        "model_api_keys": {},
    },
    "generic": {
        "model": "openai/gpt-5.4-mini",
        "timeout": 1800,
        # GenericAgent 0.1.0 currently hardcodes this limit in agentmain.py.
        "max_turns": 180,
        "model_api_keys": {},
    },
}

DEFAULT_AGENT_TIMEOUT = 1800  # seconds

# ---------------------------------------------------------------------------
# Model authentication
# ---------------------------------------------------------------------------
# All credentials come from _private/.env (loaded by util.load_private_secrets,
# which makes .env the highest-priority source). The benchmark does NOT read the
# operator's personal harness credential store.
#
# Each model resolves its API key from one environment variable. By default the
# variable is chosen by the model's provider (first path segment of the model
# id; e.g. "openai/gpt-5.4-mini" -> provider "openai"). A per-harness
# ``model_api_keys`` mapping overrides this per model, so harness, model id, and
# API-key env var stay fully decoupled and freely combinable.
PROVIDER_API_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "google": "GEMINI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google-vertex": "GOOGLE_CLOUD_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
}

PROVIDER_API_BASE: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # The project/location-qualified OpenAI-compatible URL is constructed in
    # claws.common from repository-loaded environment variables.
    "google-vertex": "https://aiplatform.googleapis.com",
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

PROVIDER_API_BASE_ENV: dict[str, str] = {
    "openai": "OPENAI_BASE_URL",
    "anthropic": "ANTHROPIC_BASE_URL",
    "openrouter": "OPENROUTER_BASE_URL",
    "google": "GEMINI_BASE_URL",
    "gemini": "GEMINI_BASE_URL",
    "google-vertex": "GOOGLE_VERTEX_BASE_URL",
    "deepseek": "DEEPSEEK_BASE_URL",
    "dashscope": "DASHSCOPE_BASE_URL",
    "qwen": "DASHSCOPE_BASE_URL",
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
# Override via environment variables to match your installation.
# ---------------------------------------------------------------------------
OPENCLAW_NODE_BIN = os.environ.get("OPENCLAW_NODE_BIN", "/usr/bin/node")
OPENCLAW_MODULE_DIR = os.environ.get(
    "OPENCLAW_MODULE_DIR", "/usr/lib/node_modules/openclaw"
)
# Operator's personal OpenClaw install (NOT used for benchmark agent runs).
OPENCLAW_STATE_DIR = Path(
    os.environ.get("OPENCLAW_STATE_DIR", str(Path.home() / ".openclaw"))
)
# Isolated OpenClaw state for benchmark containers. Tool policy and agent
# registrations live here so runs do not inherit ~/.openclaw settings.
OPENCLAW_BENCHMARK_STATE_DIR = Path(
    os.environ.get(
        "OPENCLAW_BENCHMARK_STATE_DIR",
        str(ROOT_DIR / ".cache" / "openclaw-benchmark-state"),
    )
)

# Repository-local third-party harness runtimes. The installer populates this
# ignored directory; adapters never read the harnesses' personal user config.
HARNESS_RUNTIME_ROOT = Path(
    os.environ.get(
        "PDDL_HARNESS_RUNTIME_ROOT",
        str(CACHE_DIR / "harness-runtimes"),
    )
).resolve()

HERMES_ENV_PATH = Path(
    os.environ.get("HERMES_BENCHMARK_ENV", str(HARNESS_RUNTIME_ROOT / "hermes"))
).resolve()
NANOBOT_ENV_PATH = Path(
    os.environ.get("NANOBOT_BENCHMARK_ENV", str(HARNESS_RUNTIME_ROOT / "nanobot"))
).resolve()
ZEROCLAW_BIN = Path(
    os.environ.get(
        "ZEROCLAW_BENCHMARK_BIN",
        str(HARNESS_RUNTIME_ROOT / "zeroclaw" / ".cargo" / "bin" / "zeroclaw"),
    )
).resolve()
GENERIC_REPO_PATH = Path(
    os.environ.get(
        "GENERIC_AGENT_REPO",
        str(HARNESS_RUNTIME_ROOT / "genericagent" / "repo"),
    )
).resolve()
GENERIC_ENV_PATH = Path(
    os.environ.get(
        "GENERIC_AGENT_ENV",
        str(HARNESS_RUNTIME_ROOT / "genericagent" / "venv"),
    )
).resolve()

GENERIC_BENCHMARK_STATE_DIR = Path(
    os.environ.get(
        "GENERIC_AGENT_BENCHMARK_STATE_DIR",
        str(CACHE_DIR / "generic-benchmark-state"),
    )
).resolve()

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


def container_name(claw_name: str, domain: str, data: str, model_label: str,
                   problem: str) -> str:
    """Stable, collision-resistant container name for one problem run."""
    raw = f"{claw_name}-pddl-{domain}-{data}-{model_label}-{problem}"
    # Docker names allow [a-zA-Z0-9][a-zA-Z0-9_.-]*
    safe = "".join(c if (c.isalnum() or c in "_.-") else "-" for c in raw)
    return safe[:120]
