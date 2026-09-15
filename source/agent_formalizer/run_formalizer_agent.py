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
from copy import deepcopy
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# Make the package importable when run as a script
# (source/agent_formalizer/run_formalizer_agent.py -> add source/ to path).
SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

from agent_formalizer.claws import CLAWS, get_adapter
from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.configuration.config import (
    DATASETS,
    DOMAINS,
    agent_model_label,
)
from agent_formalizer.configuration.credentials import (
    load_credential_registry,
)
from agent_formalizer.orchestrator import run_batch
from agent_formalizer.runtime.runtime_lock import load_runtime_lock
from agent_formalizer.configuration.benchmark_profile import canonical_sha256
from agent_formalizer.configuration.operational_config import (
    load_operational_config,
    safe_operational_component,
)
from agent_formalizer.util import read_named_setting
from local_solver import SUPPORTED_BACKENDS


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
                   help="JSON benchmark profile (default: bundled "
                        "configs/benchmark_profiles/native_baseline_v1.json)")
    p.add_argument("--runtime-lock", default=None,
                   help="explicit frozen runtime lock; omitted retains byte-strict local validation")
    p.add_argument(
        "--operational-config",
        default=None,
        help=(
            "strict JSON operational config for credentials, scheduling, optional "
            "evidence, infrastructure diagnostics, and output locations"
        ),
    )
    p.add_argument("--credential-profile", default=None,
                   help="named credential profile for --model (default: model/provider "
                        "mapping in credential_profiles.json)")
    p.add_argument("--credential-profiles-file",
                   default=None,
                   help="secret-free named credential registry; contains only variable "
                        "references and provider settings")
    p.add_argument("--api-key-env", default=None,
                   help="legacy API-key variable override inside the selected credential "
                        "profile; prefer --credential-profile")
    p.add_argument("--secrets-env-file", default=None,
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
                        "(must pass the selected runtime lock; local default requires exact image ID)")
    p.add_argument("--timeout", type=int, default=None,
                   help="agent timeout in seconds (default: benchmark profile)")
    p.add_argument("--max-action-steps", type=int, default=None,
                   help="maximum model_calls + tool_calls per problem "
                        "(default: benchmark profile)")
    p.add_argument("--max-model-calls", type=int, default=None,
                   help="maximum model API calls per problem (default: benchmark profile)")
    p.add_argument("--network-mode", choices=("model_only", "controlled_web"),
                   default=None, help="network condition override")
    p.add_argument(
        "--solver-backend",
        choices=sorted(SUPPORTED_BACKENDS),
        default=None,
        help=(
            "solver backend condition; omitted preserves the benchmark profile "
            "(current bundled profiles use local)"
        ),
    )
    p.add_argument(
        "--solver-base-url",
        default=None,
        help="host-visible solver origin (used by host/minimum execution)",
    )
    p.add_argument(
        "--solver-container-base-url",
        default=None,
        help="solver origin visible from the per-attempt gateway sidecar",
    )
    p.add_argument("--attempts-per-case", type=int, default=None,
                   help="fixed independent attempts for every case")
    p.add_argument("--max-execution-tries", type=int, default=None,
                   help="maximum infra-only execution tries per attempt")
    p.add_argument("--allow-final-message-recovery",
                   action=argparse.BooleanOptionalAction, default=None,
                   help="experimental recovery from final text; default false")
    p.add_argument("--vertex-project", default=None,
                   help="legacy credential-owned Vertex project override; prefer a "
                        "named credential profile")
    p.add_argument("--vertex-project-env", default="GOOGLE_CLOUD_PROJECT",
                   help="legacy runner variable used when the credential profile and "
                        "benchmark compatibility config have no Vertex project")
    p.add_argument("--vertex-location", default=None,
                   help="legacy credential-owned Vertex location override; prefer a "
                        "named credential profile")
    p.add_argument("--trace", action=argparse.BooleanOptionalAction, default=None,
                   help="record per-problem JSONL trace (default on; "
                        "pass --no-trace to disable)")
    p.add_argument("--workers", type=int, default=None,
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
    p.add_argument(
        "--operational-run-id",
        default=None,
        help=argparse.SUPPRESS,
    )
    return p


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = build_parser().parse_args()
    if args.operational_config and any(
        value is not None
        for value in (args.api_key_env, args.vertex_project, args.vertex_location)
    ):
        raise SystemExit(
            "legacy --api-key-env/--vertex-project/--vertex-location overrides "
            "cannot be combined with --operational-config; use a named credential "
            "profile in the operational config"
        )
    if args.credential_profile and any(
        value is not None
        for value in (args.api_key_env, args.vertex_project, args.vertex_location)
    ):
        raise SystemExit(
            "--credential-profile cannot be combined with --api-key-env, "
            "--vertex-project, or --vertex-location; put the bound values in "
            "the named credential profile"
        )
    try:
        operational = load_operational_config(
            args.operational_config,
            credential_profiles_file=args.credential_profiles_file,
            credential_profile=args.credential_profile,
            secrets_env_file=args.secrets_env_file,
            formalizer_workers=args.workers,
            agent_trace=args.trace,
            results_root=args.out_dir,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
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
    try:
        credential_registry = load_credential_registry(
            operational.credential_registry_path
        )
        credential = credential_registry.resolve(
            model,
            name=operational.credential_profile,
            env_file=operational.secrets_env_path,
            api_key_env_override=args.api_key_env,
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    api_key = credential.api_key
    key_name = credential.api_key_env

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
    provider_options = deepcopy(credential.provider_options)
    vertex_options = provider_options.setdefault("google_vertex", {}) if (
        model.startswith("google-vertex/")
    ) else None
    vertex_project = args.vertex_project or (
        vertex_options.get("project") if vertex_options is not None else None
    )
    if (
        model.startswith("google-vertex/")
        and vertex_project is None
        and profile.raw["providers"]["google_vertex"]["project"] is None
    ):
        try:
            vertex_project = read_named_setting(
                args.vertex_project_env, operational.secrets_env_path
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    if vertex_options is not None:
        if vertex_project is not None:
            vertex_options["project"] = vertex_project
        if args.vertex_location is not None:
            vertex_options["location"] = args.vertex_location
    if not provider_options:
        provider_options = None

    credential_metadata = credential.metadata()
    legacy_overrides = [
        name
        for name, value in (
            ("api_key_env", args.api_key_env),
            ("vertex_project", args.vertex_project),
            ("vertex_location", args.vertex_location),
        )
        if value is not None
    ]
    if legacy_overrides:
        credential_metadata["legacy_overrides"] = legacy_overrides

    adapter = get_adapter(
        args.claw,
        model=model,
        timeout=args.timeout,
        max_action_steps=args.max_action_steps,
        max_model_calls=args.max_model_calls,
        network_mode=args.network_mode,
        attempts_per_case=args.attempts_per_case,
        max_execution_tries=args.max_execution_tries,
        allow_final_message_recovery=args.allow_final_message_recovery,
        solver_backend=args.solver_backend,
        solver_host_base_url=args.solver_base_url,
        solver_container_base_url=args.solver_container_base_url,
        credential_provider_options=provider_options,
        api_key=api_key,
        api_key_name=key_name,
        credential_metadata=credential_metadata,
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
        "claw=%s domain=%s data=%s model=%s credential=%s label=%s problems=%s",
        args.claw, args.domain, args.data, model, credential.profile_name,
        model_label, problem_numbers,
    )

    operational_run_id = args.operational_run_id or (
        f"formalizer-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    )
    manifest_path = (
        operational.results_root
        / ".operational"
        / f"{safe_operational_component(operational_run_id)}-{os.getpid()}.json"
    )
    operational_manifest = {
        **operational.metadata(),
        "run_id": operational_run_id,
        "pid": os.getpid(),
        "credential": credential.metadata(),
        "credential_registry_sha256": credential_registry.sha256,
        "solver_backend": {
            "mode": adapter.solver_backend(),
            "host_base_url": adapter.solver_upstream_base(containerized=False),
            "container_base_url": adapter.solver_upstream_base(containerized=True),
            "experiment_identity": "included in resolved benchmark configuration",
        },
        "diagnostics_root": (
            str(
                operational.diagnostics_root
                / safe_operational_component(operational_run_id)
            )
            if operational.diagnostics_enabled
            else None
        ),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "running",
    }
    if args.runtime_lock is not None:
        selected_lock = load_runtime_lock(args.runtime_lock)
        operational_manifest["runtime_validation"] = {
            "path": str(Path(args.runtime_lock).resolve()),
            "lock_id": selected_lock["lock_id"],
            "policy": selected_lock.get("policy", "byte-strict-v1"),
            "lock_sha256": canonical_sha256(selected_lock),
        }
    _atomic_json(manifest_path, operational_manifest)
    try:
        results = run_batch(
            adapter,
            domain=args.domain,
            data=args.data,
            problem_numbers=problem_numbers,
            model_label=model_label,
            record_trace=operational.raw["evidence_collection"]["agent_trace"],
            out_dir_root=operational.results_root,
            image=args.image,
            workers=operational.raw["scheduling"]["formalizer_workers"],
            operational_config=operational,
            operational_run_id=operational_run_id,
            **({"runtime_lock_path": args.runtime_lock} if args.runtime_lock is not None else {}),
        )
    except BaseException as exc:
        operational_manifest.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "finished_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            }
        )
        _atomic_json(manifest_path, operational_manifest)
        raise
    operational_manifest.update(
        {
            "status": "completed",
            "attempt_results": len(results),
            "valid_attempts": sum(result.attempt_valid for result in results),
            "infra_invalid_attempts": sum(
                not result.attempt_valid for result in results
            ),
            "finished_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
        }
    )
    _atomic_json(manifest_path, operational_manifest)
    if any(not result.attempt_valid for result in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
