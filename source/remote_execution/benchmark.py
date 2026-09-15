"""Execute a frozen comparison cell with the existing local benchmark pipeline.

Run this entrypoint from the *release's* source tree. It changes only operational
paths, and checks the caller's resolved semantic identity before any task starts.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from remote_execution.protocol import digest, file_hash, private_json, read_json, safe_path, validate_job


def differences(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(before.keys() | after.keys()):
            rows.extend(differences(before.get(key), after.get(key), path + "/" + key))
        return rows
    return [] if before == after else [{"path": path, "baseline": before, "selected": after}]


def matches(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and matches(actual[key], value)
                                                for key, value in expected.items())
    return type(actual) is type(expected) and actual == expected


def service_preflight(services: dict, names: list[str], evidence: Path, *, secrets_env_file=None):
    """Read-only supervision/health checks; never starts or reconfigures services."""
    observations = {}
    opener = build_opener(ProxyHandler({}))
    for name in names:
        service = services[name]
        result = subprocess.run(["systemctl", "show", service["systemd_unit"],
            "-p", "ActiveState", "-p", "SubState", "-p", "Restart"],
            capture_output=True, text=True, timeout=15, check=True)
        supervision = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if supervision.get("ActiveState") != "active" or supervision.get("Restart") not in {"always", "on-failure"}:
            raise ValueError("Required node service is not supervised and active")
        headers = {}
        if "api_key_env" in service:
            from agent_formalizer.util import read_named_secret
            headers["Authorization"] = "Bearer " + read_named_secret(service["api_key_env"], secrets_env_file)
        with opener.open(Request(service["health_url"], headers=headers), timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Health response exceeds limit")
        health = json.loads(raw)
        if not matches(health, service["expected"]):
            raise ValueError("Node service differs from its declared configuration")
        observations[name] = {"at_unix": time.time(), "health": health,
                              "supervision": supervision, "provenance": service.get("provenance", {})}
    private_json(evidence, observations, replace=False)
    return observations


def prepare(spec, node, workspace: Path, directory: Path, generation: int):
    from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
    from agent_formalizer.configuration.operational_config import load_operational_config
    from agent_formalizer.configuration.config import DATASETS, DOMAINS

    validate_job(spec)
    p = spec["parameters"]
    if p["domain"] not in DOMAINS or p["dataset"] not in DATASETS:
        raise ValueError("Unknown benchmark dataset/domain")
    op_path = safe_path(workspace, p["operational_config"])
    profile = resolved = None
    if spec["kind"] == "agent_cell":
        profile_path = safe_path(workspace, p["benchmark_profile"])
        profile = load_benchmark_profile(profile_path)
        resolved = profile.resolve(p["harness"])
        if resolved.sha256 != p["resolved_config_sha256"]:
            raise ValueError("Resolved profile identity does not match the submitted job")
    op = load_operational_config(op_path)
    raw = deepcopy(op.raw)
    if raw["scheduling"]["formalizer_workers"] > node.get("max_formalizer_workers", 4):
        raise ValueError("Requested formalizer concurrency exceeds node capacity; not silently reduced")
    if raw["scheduling"]["resume"] is not True:
        raise ValueError("Execution-node jobs require native resume=true")
    if raw["evidence_collection"]["agent_trace"] is not True:
        raise ValueError("Execution-node jobs require agent_trace=true")
    registry = safe_path(workspace, raw["credential"]["registry_file"])
    if not registry.is_file():
        raise ValueError("Credential registry must be frozen inside the release")
    if raw["credential"]["secrets_env_file"] != "_private/.env":
        raise ValueError("Use node binding for _private/.env, not a controller absolute secret path")
    if "secrets_env_file" not in node.get("bindings", {}):
        raise ValueError("Node runner-only secret binding required")
    raw["credential"]["registry_file"] = str(registry)
    raw["credential"]["secrets_env_file"] = node["bindings"]["secrets_env_file"]
    raw["results"]["root"] = str(directory / "output")
    raw["infra_diagnostics"]["storage"]["root"] = str(directory / "output" / "infra-diagnostics")
    materialized = directory / "evidence" / f"operational-{generation}.json"
    private_json(materialized, raw, replace=False)
    # Retain user-selected semantics; only node-local paths were materialized.
    baseline = workspace / "source/agent_formalizer/configs/benchmark_profiles/native_baseline_v1.json"
    provenance = {"operational_source_sha256": file_hash(op_path),
                  "operational_materialization": differences(op.raw, raw)}
    if profile is not None:
        provenance.update({"baseline_path": str(baseline.relative_to(workspace)),
                           "baseline_sha256": file_hash(baseline), "profile_sha256": file_hash(profile_path),
                           "resolved_config_sha256": resolved.sha256,
                           "profile_differences": differences(read_json(baseline), profile.raw)})
    else:
        provenance.update({"api_condition": "direct-api-no-tools-v1", "request_sha256": digest(spec),
                           "generation_attempts": 1, "hosted_tools": False,
                           "entrypoint": "source/llm-as-formalizer-api.py",
                           "entrypoint_sha256": file_hash(workspace / "source/llm-as-formalizer-api.py"),
                           "note": "Standalone API prompt/retries; agent profile budgets do not apply"})
    private_json(directory / "evidence" / f"configuration-{generation}.json", provenance, replace=False)
    return profile, resolved, raw, materialized


def required_service_preflight(model, solver_backend, spec, node, op, directory, generation):
    p = spec["parameters"]
    names = p["services"]
    services = node.get("services", {})
    if solver_backend in {"local", "public_then_local"}:
        if "solver" not in names:
            raise ValueError("local/public_then_local requires the shared solver service preflight")
        expected = services["solver"]["expected"]
        config = expected.get("config", {})
        required = {"workers", "memory", "memory_swap", "cpus", "pids_limit",
                    "timeout_seconds", "worker_security", "allowed_solvers"}
        if (expected.get("status") != "ok" or expected.get("backend") != "local-planutils"
                or not expected.get("pool", {}).get("image_id") or not required <= config.keys()):
            raise ValueError("Solver preflight must declare its image and complete resource limits")
        if solver_backend == "public_then_local" and config["timeout_seconds"] != 90:
            raise ValueError("public_then_local requires a 90-second local solver")
        # The existing pipeline uses these fixed node-local origins. A health
        # check on some other service must not attest the selected solver.
        if services["solver"]["health_url"] != "http://127.0.0.1:8769/__benchmark__/health":
            raise ValueError("Solver preflight must target the benchmark's actual local endpoint")
    if model.startswith("self-hosted/") and "model" not in names:
        raise ValueError("Self-hosted model requires a supervised model service preflight")
    health = service_preflight(services, names, directory / "evidence" / f"services-{generation}.json",
                               secrets_env_file=op["credential"]["secrets_env_file"])
    if model.startswith("self-hosted/"):
        served = model.split("/", 1)[1]
        models = health["model"]["health"].get("data", [])
        if not any(isinstance(item, dict) and item.get("id") == served for item in models):
            raise ValueError("Model service does not expose the selected served-model ID")
        required = {"model_revision", "tokenizer_revision", "server_version", "dtype",
                    "quantization", "chat_template_sha256", "generation_config",
                    "max_model_len", "tool_call_parser", "reasoning_parser"}
        if not required <= services["model"].get("provenance", {}).keys():
            raise ValueError("Self-hosted model deployment provenance is incomplete")
    return health


def run(spec, node, workspace, directory, generation):
    if spec["kind"] == "api_cell":
        from remote_execution.api import run as run_api
        return run_api(spec, node, workspace, directory, generation)
    from agent_formalizer.configuration.config import agent_model_label
    from sweep_agent_pipeline import run_agent_pipeline

    profile, resolved, op, materialized = prepare(spec, node, workspace, directory, generation)
    p = spec["parameters"]
    required_service_preflight(resolved.model, resolved.solver_backend, spec, node, op, directory, generation)
    scheduling = op["scheduling"]
    result = run_agent_pipeline(
        claw=p["harness"], model=resolved.model, model_label=agent_model_label(p["harness"], resolved.model),
        domain=p["domain"], dataset=p["dataset"], indices=p["indices"],
        out_dir=directory / "output", log_dir=directory / "logs" / f"pipeline-{generation}",
        stages={"formalize", "solve", "val"},
        formalizer_workers=scheduling["formalizer_workers"], solver_workers=scheduling["solver_workers"],
        val_workers=scheduling["val_workers"], benchmark_config=str(workspace / p["benchmark_profile"]),
        operational_config=str(materialized), operational_run_id=f"{spec['job_id']}-g{generation}",
        timeout=None, max_action_steps=None, max_model_calls=None, network_mode=None,
        attempts_per_case=None, max_execution_tries=None, allow_final_message_recovery=None,
        solver_backend=None, solver_base_url=None, solver_container_base_url=None,
        api_key_env=None, secrets_env_file=op["credential"]["secrets_env_file"],
        vertex_project_env="GOOGLE_CLOUD_PROJECT", image=None, trace=True,
        tools_profile=None, tools_allow=None, tools_deny=None, resume=True)
    private_json(directory / "output" / f"cell-summary-{generation}.json", asdict(result), replace=False)
    # This reports pipeline completion, not correctness. A valid wrong answer
    # must not cause job retry. Incomplete/infra-invalid slots remain repairable.
    return 0 if (result.valid_attempts == len(p["indices"]) * resolved.attempts_per_case
                 and all(result.stages.get(stage) == "ok" for stage in ("formalize", "solve", "val"))) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--generation", type=int, required=True)
    args = parser.parse_args()
    raise SystemExit(run(read_json(args.job), read_json(args.node), Path(__file__).resolve().parents[2],
                         args.directory, args.generation))


if __name__ == "__main__":
    main()
