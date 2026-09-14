"""Controller CLI: bundle, submit, status, events, collect and explicit resume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bundle import build
from .client import Client
from .protocol import identifier, private_json, read_json, safe_path, validate_job


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
    upload = commands.add_parser("upload")
    upload.add_argument("--archive", type=Path, required=True)
    upload.add_argument("--release-id", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--job", type=Path, required=True)
    commands.add_parser("health")
    commands.add_parser("list")
    for name in ("status", "events", "progress", "collect", "resume"):
        command = commands.add_parser(name)
        command.add_argument("job_id")
        if name == "events":
            command.add_argument("--after", type=int, default=0)
        if name == "collect":
            command.add_argument("--destination", type=Path, required=True)
            command.add_argument("--generation", type=int)
        if name == "resume":
            command.add_argument("--generation", type=int, required=True)
            command.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.command == "bundle":
        result = build(args.root, args.include, args.archive)
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
        else:
            result = client.resume(args.job_id, args.generation, args.reason)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
