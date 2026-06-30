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

    python3 source/agent_formalizer/run_formalizer_agent.py \\
        --claw openclaw --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --index_start 1 --index_end 11

    python3 source/agent_formalizer/run_formalizer_agent.py \\
        --claw openclaw --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --model openrouter/anthropic/claude-opus-4.6 --indices 1,2,3

Then evaluate (note the sanitized model label, slashes -> ``__``)::

    python3 source/run_solver.py --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --model openrouter__anthropic__claude-opus-4.6 \\
        --prediction_type llm-as-formalizer-agent --indices 1,2,3
    python3 source/run_val.py --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --model openrouter__anthropic__claude-opus-4.6 \\
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
from agent_formalizer.config import (
    CLAW_DEFAULTS,
    DATASETS,
    DOMAINS,
    sanitize_model_name,
)
from agent_formalizer.orchestrator import run_batch
from agent_formalizer.util import load_private_secrets


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
                   help="model id passed to the claw (default: per-claw default)")
    p.add_argument("--api-key-env", default=None,
                   help="env var (defined in _private/.env) holding the API key "
                        "for --model; overrides the per-harness model_api_keys "
                        "map and the provider default. Lets harness, model, and "
                        "API key be combined freely.")
    p.add_argument("--model_label", default=None,
                   help="filesystem/solver-safe label for output dirs "
                        "(default: sanitized --model; pass this same value to "
                        "run_solver.py / run_val.py via --model)")
    p.add_argument("--index_start", help="index to start from (inclusive)")
    p.add_argument("--index_end", help="index to end at (exclusive)")
    p.add_argument("--indices", default=None,
                   help="comma-separated problem numbers (e.g. '1,5,17'); "
                        "overrides --index_start/--index_end when provided")
    p.add_argument("--out_dir", default=None,
                   help="base output directory; defaults to {ROOT_DIR}/output")
    p.add_argument("--image", default=None,
                   help="Docker base image to run the agent in "
                        "(default: $PDDL_AGENT_IMAGE or pddl-agent-base:latest)")
    p.add_argument("--timeout", type=int, default=None,
                   help="agent timeout in seconds (default: per-claw default)")
    p.add_argument("--max_turns", type=int, default=None,
                   help="max tool-use turns (default: per-claw default; "
                        "ignored by claws without a turn limit)")
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
                        "(default: per-claw benchmark deny list)")
    return p


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = build_parser().parse_args()
    load_private_secrets()

    defaults = CLAW_DEFAULTS[args.claw]
    model = args.model or defaults["model"]
    model_label = args.model_label or sanitize_model_name(model)

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
    if args.api_key_env is not None:
        adapter_kwargs["model_api_keys"] = {model: args.api_key_env}

    adapter = get_adapter(
        args.claw,
        model=model,
        timeout=args.timeout,
        max_turns=args.max_turns,
        **adapter_kwargs,
    )

    problem_numbers = _resolve_problem_numbers(args)
    logging.getLogger(__name__).info(
        "claw=%s domain=%s data=%s model=%s label=%s problems=%s",
        args.claw, args.domain, args.data, model, model_label, problem_numbers,
    )

    run_batch(
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


if __name__ == "__main__":
    main()
