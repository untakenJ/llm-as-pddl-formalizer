"""Controller CLI: frozen jobs, incremental sync, collect and explicit recovery."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from .bundle import build
from .client import Client
from .protocol import identifier, private_json, read_json, safe_path, validate_job
from .checkpoints import recovery_bundle, restore
from .store import lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8876")
    parser.add_argument("--token-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("bundle")
    package.add_argument("--root", type=Path, default=Path.cwd())
    package.add_argument("--include", action="append", required=True)
    package.add_argument("--archive", type=Path, required=True)
    plan = commands.add_parser("job", help="Create a strict, frozen single-cell job request without submitting it")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--job-id", required=True)
    plan.add_argument("--release-id", required=True)
    plan.add_argument("--harness", required=True)
    plan.add_argument("--domain", required=True)
    plan.add_argument("--dataset", required=True)
    plan.add_argument("--indices", required=True, help="Explicit fixed comma-separated indices")
    plan.add_argument("--profile", required=True, help="Release-relative complete benchmark profile")
    plan.add_argument("--operational", required=True, help="Release-relative operational config")
    plan.add_argument("--service", action="append", default=[])
    plan.add_argument("--destination", type=Path, required=True)
    api = commands.add_parser("api-job", help="Freeze an API-only cell (no agent tools or reflection)")
    api.add_argument("--root", type=Path, default=Path.cwd())
    for name in ("job-id", "release-id", "model", "domain", "dataset", "indices", "operational"):
        api.add_argument("--" + name, required=True)
    api.add_argument("--solver-backend", choices=("local", "public", "public_then_local"), default="local")
    api.add_argument("--max-output-tokens", default=None, help="model_max, native, or a positive integer; default from canonical baseline")
    api.add_argument("--model-capabilities", type=Path)
    api.add_argument("--service", action="append", default=[])
    api.add_argument("--destination", type=Path, required=True)
    upload = commands.add_parser("upload")
    upload.add_argument("--archive", type=Path, required=True)
    upload.add_argument("--release-id", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--job", type=Path, required=True)
    commands.add_parser("health")
    commands.add_parser("list")
    export = commands.add_parser("recovery-bundle", help="Package only durably received execution checkpoints")
    export.add_argument("--mirror", type=Path, required=True, help="DEST/JOB_ID from sync")
    export.add_argument("--archive", type=Path, required=True)
    recover = commands.add_parser("restore", help="Offline restore on an empty replacement node; worker must be stopped")
    recover.add_argument("--config", type=Path, required=True)
    recover.add_argument("--archive", type=Path, required=True)
    recover.add_argument("--reason", required=True)
    recover.add_argument("--source-node-retired", action="store_true",
                         help="Attest old VM is terminated/fenced, not just unreachable")
    for name in ("status", "events", "progress", "collect", "resume", "sync"):
        command = commands.add_parser(name)
        command.add_argument("job_id")
        if name == "events":
            command.add_argument("--after", type=int, default=0)
        if name in {"collect", "sync"}:
            command.add_argument("--destination", type=Path, required=True)
        if name == "collect":
            command.add_argument("--generation", type=int)
        if name == "sync":
            command.add_argument("--follow", action="store_true", help="Reconnect and collect until pipeline terminal")
            command.add_argument("--interval", type=int, default=5)
        if name == "resume":
            command.add_argument("--generation", type=int, required=True)
            command.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.command == "bundle":
        result = build(args.root, args.include, args.archive)
    elif args.command == "recovery-bundle":
        with lock(args.mirror / ".sync.lock", blocking=True):
            result = recovery_bundle(args.mirror, args.archive)
    elif args.command == "restore":
        result = restore(args.archive, read_json(args.config), reason=args.reason,
                         source_node_retired=args.source_node_retired)
    elif args.command == "api-job":
        from api_providers import validate_api_model, model_capability_route
        from agent_formalizer.configuration.model_capabilities import load_registry, resolve_output_policy
        from agent_formalizer.configuration.benchmark_profile import DEFAULT_BENCHMARK_PROFILE
        selection = args.max_output_tokens
        if selection is None:
            selection = DEFAULT_BENCHMARK_PROFILE.raw["condition_profile"]["overrides"].get("generation", {}).get("max_output_tokens", "native")
        elif selection.isdigit():
            selection = int(selection)
        output_policy = resolve_output_policy(model_capability_route(args.model), selection,
            load_registry(args.model_capabilities) if args.model_capabilities else None)
        safe_path(args.root, args.operational).resolve(strict=True)
        result = validate_job({"schema_version": 1, "job_id": args.job_id, "release_id": args.release_id,
            "kind": "api_cell", "parameters": {"model": validate_api_model(args.model), "domain": args.domain,
                "dataset": args.dataset, "indices": [int(item) for item in args.indices.split(",")],
                "operational_config": args.operational, "solver_backend": args.solver_backend,
                "services": args.service,
                **({"output_token_policy": output_policy} if output_policy else {})}})
        private_json(args.destination, result, replace=False)
    elif args.command == "job":
        from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
        profile = load_benchmark_profile(safe_path(args.root, args.profile))
        safe_path(args.root, args.operational).resolve(strict=True)
        result = validate_job({"schema_version": 1, "job_id": args.job_id, "release_id": args.release_id,
            "kind": "agent_cell", "parameters": {"harness": args.harness, "domain": args.domain,
                "dataset": args.dataset, "indices": [int(item) for item in args.indices.split(",")],
                "benchmark_profile": args.profile, "operational_config": args.operational,
                "resolved_config_sha256": profile.resolve(args.harness).sha256, "services": args.service}})
        private_json(args.destination, result, replace=False)
    else:
        if args.token_file is None:
            parser.error("--token-file is required")
        client = Client(args.endpoint, args.token_file)
        if args.command == "upload":
            result = client.upload(args.archive, args.release_id)
        elif args.command == "submit":
            result = client.submit(read_json(args.job))
        elif args.command == "health":
            result = client.request("/health")
        elif args.command == "list":
            result = client.request("/jobs")
        elif args.command == "status":
            result = client.status(args.job_id)
        elif args.command == "events":
            result = client.request(f"/jobs/{identifier(args.job_id)}/events?after={args.after}")
        elif args.command == "progress":
            result = client.request(f"/jobs/{identifier(args.job_id)}/progress")
        elif args.command == "collect":
            result = client.collect(args.job_id, args.destination, generation=args.generation)
        elif args.command == "sync":
            if not 1 <= args.interval <= 60:
                parser.error("--interval must be between 1 and 60 seconds")
            while True:
                try:
                    result = client.sync(args.job_id, args.destination)
                    if not args.follow:
                        break
                    print(json.dumps(result), flush=True)
                    if result["status"] in {"completed", "failed"}:
                        result["final_collection"] = client.collect(args.job_id, args.destination)
                        break
                    if result["status"] == "needs_attention":
                        break  # Do not guess ownership or automatically resample.
                except HTTPError as exc:
                    if not args.follow or exc.code < 500:
                        raise
                    print(json.dumps({"sync": "reconnecting", "http_status": exc.code}), flush=True)
                except (URLError, ConnectionError, TimeoutError):
                    if not args.follow:
                        raise
                    print(json.dumps({"sync": "reconnecting"}), flush=True)
                time.sleep(args.interval)
        else:
            result = client.resume(args.job_id, args.generation, args.reason)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
