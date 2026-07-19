"""Agentic variant of ``llm-as-formalizer-api.py``.

Instead of a single LLM API call, this spins up a Docker container and runs a
full agent harness (a "claw", e.g. OpenClaw) inside it. The agent authors the
PDDL domain/problem files with its own tools; we read them back, record the
complete execution trace (including tool calls), and write the result in the
same layout the other formalizer pipelines use so ``run_solver.py`` /
``run_val.py`` work unchanged (prediction_type ``llm-as-formalizer-agent``).

Examples::

    # Build the base image once (see docker/Dockerfile):
    docker build -t pddl-agent-base:latest source/agent_formalizer/docker

    uv run python source/agent_formalizer/run_formalizer_agent.py \\
        --claw openclaw --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --index_start 1 --index_end 11

    uv run python source/agent_formalizer/run_formalizer_agent.py \\
        --claw openclaw --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --model google-vertex/gemini-3.1-flash-lite --indices 1,2,3

Then evaluate (note the sanitized model label, slashes -> ``__``)::

    uv run python source/run_solver.py --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --model openclaw__openrouter__anthropic__claude-opus-4.6 \\
        --prediction_type llm-as-formalizer-agent --indices 1,2,3
    uv run python source/run_val.py --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --model openclaw__openrouter__anthropic__claude-opus-4.6 \\
        --prediction_type llm-as-formalizer-agent --indices 1,2,3 --csv_result
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Make the package importable when run as a script
# (source/agent_formalizer/run_formalizer_agent.py -> add source/ to path).
SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

from agent_formalizer.claws import CLAWS, get_adapter
from agent_formalizer.benchmark_profile import load_benchmark_profile
from agent_formalizer.config import (
    DATASETS,
    DEFAULT_SECRETS_ENV_FILE,
    DOMAINS,
    agent_model_label,
    api_key_env_for_model,
)
from agent_formalizer.orchestrator import run_batch
from agent_formalizer.util import read_named_secret, read_named_setting


def _resolve_problem_numbers(args) -> list[int]:
    if args.indices:
        return [int(x.strip()) for x in args.indices.split(",") if x.strip()]
    if args.index_start is None or args.index_end is None:
        raise SystemExit("Must provide either --indices or both --index_start and --index_end.")
    return list(range(int(args.index_start), int(args.index_end)))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run an agent harness on PDDL formalization problems inside Docker."
    )
    p.add_argument("--claw", default="openclaw", choices=sorted(CLAWS),
                   help="which agent harness to run (default: openclaw)")
    p.add_argument("--domain", required=True, choices=DOMAINS,
                   help="which domain to evaluate")
    p.add_argument("--data", required=True, choices=DATASETS,
                   help="which dataset to formalize")
    p.add_argument("--model", default=None,
                   help="model id passed to the claw (default: benchmark profile)")
    p.add_argument("--benchmark-config", default=None,
                   help="JSON benchmark profile (default: bundled benchmark_profile.json)")
    p.add_argument("--api-key-env", default=None,
                   help="the one runner environment variable holding the API key "
                        "for --model; overrides the per-harness model_api_keys "
                        "map and provider default")
    p.add_argument("--secrets-env-file", default=str(DEFAULT_SECRETS_ENV_FILE),
                   help="runner-only dotenv source for explicitly named provider "
                        "inputs; never mounted or passed to the agent container")
    p.add_argument("--model_label", default=None,
                   help="filesystem/solver-safe label for output dirs "
                        "(the resolved config name/hash is always appended; pass the "
                        "resulting label to run_solver.py / run_val.py via --model)")
    p.add_argument("--index_start", help="index to start from (inclusive)")
    p.add_argument("--index_end", help="index to end at (exclusive)")
    p.add_argument("--indices", default=None,
                   help="comma-separated problem numbers (e.g. '1,5,17'); "
                        "overrides --index_start/--index_end when provided")
    p.add_argument("--out_dir", default=None,
                   help="base output directory; defaults to {ROOT_DIR}/output")
    p.add_argument("--image", default=None,
                   help="Docker base image to run the agent in "
                        "(must resolve to the image ID in runtime_lock.json)")
    p.add_argument("--timeout", type=int, default=None,
                   help="agent timeout in seconds (default: benchmark profile)")
    p.add_argument("--max_turns", type=int, default=None,
                   help="max agent turns (default: benchmark profile)")
    p.add_argument("--max-model-calls", type=int, default=None,
                   help="maximum model API calls per problem (default: benchmark profile)")
    p.add_argument("--network-mode", choices=("model_only", "controlled_web"),
                   default=None, help="network condition override")
    p.add_argument("--attempts-per-case", type=int, default=None,
                   help="fixed independent attempts for every case")
    p.add_argument("--max-execution-tries", type=int, default=None,
                   help="maximum infra-only execution tries per attempt")
    p.add_argument("--allow-final-message-recovery",
                   action=argparse.BooleanOptionalAction, default=None,
                   help="experimental recovery from final text; default false")
    p.add_argument("--vertex-project", default=None,
                   help="explicit Vertex project override")
    p.add_argument("--vertex-project-env", default="GOOGLE_CLOUD_PROJECT",
                   help="runner variable read when the profile has no Vertex project")
    p.add_argument("--vertex-location", default=None,
                   help="Vertex location override (default from profile)")
    p.add_argument("--trace", action=argparse.BooleanOptionalAction, default=True,
                   help="record per-problem JSONL trace (default on; "
                        "pass --no-trace to disable)")
    p.add_argument("--workers", type=int, default=1,
                   help="parallel worker threads for independent problems "
                        "(default 1 = sequential)")
    p.add_argument("--tools-profile", default=None,
                   help="OpenClaw tools.profile for benchmark runs "
                        "(default: per-claw default, usually 'coding')")
    p.add_argument("--tools-allow", default=None,
                   help="comma-separated OpenClaw tool allow list "
                        "(optional; narrows the profile)")
    p.add_argument("--tools-deny", default=None,
                   help="comma-separated OpenClaw tool deny list "
                        "(default: no condition-level tool override)")
    return p


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = build_parser().parse_args()
    profile = load_benchmark_profile(args.benchmark_config)

    openclaw_tool_flags = (
        args.tools_profile is not None
        or args.tools_allow is not None
        or args.tools_deny is not None
    )
    if args.claw != "openclaw" and openclaw_tool_flags:
        raise SystemExit(
            "--tools-profile/--tools-allow/--tools-deny apply only to "
            "--claw openclaw; other adapters use repository-pinned tool policies."
        )

    model = args.model or profile.default_model
    key_name = args.api_key_env or api_key_env_for_model(model)
    if not key_name:
        raise SystemExit(
            f"No credential variable mapping for model {model!r}; pass --api-key-env"
        )
    try:
        api_key = read_named_secret(key_name, args.secrets_env_file)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    adapter_kwargs: dict = {}
    if args.tools_profile is not None:
        adapter_kwargs["tools_profile"] = args.tools_profile
    if args.tools_allow is not None:
        adapter_kwargs["tools_allow"] = [
            x.strip() for x in args.tools_allow.split(",") if x.strip()
        ]
    if args.tools_deny is not None:
        adapter_kwargs["tools_deny"] = [
            x.strip() for x in args.tools_deny.split(",") if x.strip()
        ]
    vertex_project = args.vertex_project
    if (
        model.startswith("google-vertex/")
        and vertex_project is None
        and profile.raw["providers"]["google_vertex"]["project"] is None
    ):
        try:
            vertex_project = read_named_setting(
                args.vertex_project_env, args.secrets_env_file
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    provider_options = None
    if vertex_project is not None or args.vertex_location is not None:
        provider_options = {"google_vertex": {}}
        if vertex_project is not None:
            provider_options["google_vertex"]["project"] = vertex_project
        if args.vertex_location is not None:
            provider_options["google_vertex"]["location"] = args.vertex_location

    adapter = get_adapter(
        args.claw,
        model=model,
        timeout=args.timeout,
        max_turns=args.max_turns,
        max_model_calls=args.max_model_calls,
        network_mode=args.network_mode,
        attempts_per_case=args.attempts_per_case,
        max_execution_tries=args.max_execution_tries,
        allow_final_message_recovery=args.allow_final_message_recovery,
        provider_options=provider_options,
        api_key=api_key,
        api_key_name=key_name,
        benchmark_profile=profile,
        **adapter_kwargs,
    )
    base_label = args.model_label or agent_model_label(args.claw, model)
    config_suffix = f"__{adapter.resolved_config.label}"
    model_label = (
        base_label if base_label.endswith(config_suffix) else base_label + config_suffix
    )

    problem_numbers = _resolve_problem_numbers(args)
    logging.getLogger(__name__).info(
        "claw=%s domain=%s data=%s model=%s label=%s problems=%s",
        args.claw, args.domain, args.data, model, model_label, problem_numbers,
    )

    results = run_batch(
        adapter,
        domain=args.domain,
        data=args.data,
        problem_numbers=problem_numbers,
        model_label=model_label,
        record_trace=args.trace,
        out_dir_root=args.out_dir,
        image=args.image,
        workers=args.workers,
    )
    if any(not result.attempt_valid for result in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
