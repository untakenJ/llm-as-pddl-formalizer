"""Node-local, explicit deployment preparation; never hot-updates a service.

Plan is read-only. Apply stages immutable code and, only if necessary, a new uv
environment. Check probes that staged installation. Activation stays an explicit
operator step; old node configs, job records, runtimes and services are untouched.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

from . import bundle
from .protocol import digest, file_hash, private_json, read_json, safe_path, validate_node
from .store import group_alive, lock

INCLUDES = ["source", "pyproject.toml", "uv.lock", "README.md"]
NATIVE = ("openclaw", "hermes", "nanobot", "generic", "zeroclaw")
COMPONENTS = {
    "worker": ("source/remote_execution/",),
    "python_dependencies": ("pyproject.toml", "uv.lock"),
    "harness_requirements": ("source/agent_formalizer/runtime/",),
    "agent_image": ("source/agent_formalizer/docker/",),
    "timing": ("source/agent_formalizer/timing/", "source/agent_formalizer/results/native_audit.py"),
    "solver": ("source/local_solver/",),
}


def absolute(path):
    """Reject links in managed paths, not the normal venv python symlink."""
    path = Path(os.path.abspath(path))
    if any(ord(c) < 32 for c in str(path)):
        raise ValueError("Control characters in path")
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError(f"Managed path contains a symbolic link: {part}")
    return path


def environment(root, python_env=None):
    # Never inherit model secrets, proxy variables or ambient UV_PROJECT_ENVIRONMENT.
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
           "HOME": str(Path.home()), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PYTHONPATH": str(root / "source"), "PYTHONDONTWRITEBYTECODE": "1"}
    if python_env is not None:
        env["UV_PROJECT_ENVIRONMENT"] = str(python_env)
    return env


def uv_command(source, *, check):
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("uv is required on the execution node")
    args = [uv, "sync", "--locked", "--no-dev", "--no-install-project",
            "--project", str(source), "--python", "3.12"]
    # Compatible optional extras may remain in an existing environment. Never
    # run a mutating sync on it. Check cannot download or update the lockfile.
    return args + (["--check", "--inexact", "--offline", "--no-cache"] if check else [])


def environment_matches(source, python):
    env_path = Path(python).parent.parent
    if not (env_path / "pyvenv.cfg").is_file() or not Path(python).is_file():
        return False
    result = subprocess.run(uv_command(source, check=True), env=environment(source, env_path),
                            capture_output=True, timeout=120)
    return result.returncode == 0


def queue_snapshot(config):
    """Do not instantiate Store: that initializes/migrates the queue."""
    state = absolute(config["state_dir"])
    db_path = safe_path(state, "queue.sqlite3")
    if not db_path.is_file():
        raise ValueError("Expected an initialized execution-node queue")
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5) as db:
        rows = [{"id": r[0], "status": r[1]} for r in db.execute("SELECT id,status FROM jobs ORDER BY id")]
    return rows


@contextmanager
def idle_node(config):
    """Use the existing lifetime worker lock; this also works with old workers.

    Stopping systemd alone is insufficient: detached owners can still be alive.
    Hold all owner locks until preparation/check completes. Never kill a job.
    """
    state = absolute(config["state_dir"])
    with ExitStack() as stack:
        try:
            stack.enter_context(lock(safe_path(state, "worker.lock")))
        except BlockingIOError as exc:
            raise ValueError("Control worker is running; stop admission before deployment") from exc
        for row in queue_snapshot(config):
            if row["status"] not in {"completed", "failed"}:
                raise ValueError(f"Unsettled job blocks deployment: {row['id']} ({row['status']})")
            directory = safe_path(state, "jobs/" + row["id"])
            try:
                stack.enter_context(lock(safe_path(directory, "owner.lock")))
            except BlockingIOError as exc:
                raise ValueError(f"Detached owner still active: {row['id']}") from exc
            if group_alive(directory):
                raise ValueError(f"Execution process group still active: {row['id']}")
        yield


def plan(source, config_path, destination, harnesses=None, services=None, installed_source=None):
    source, config_path, destination = map(absolute, (source, config_path, destination))
    config = validate_node(read_json(config_path))
    if destination == source or source.is_relative_to(destination):
        raise ValueError("Deployment directory must not contain the source checkout")
    if destination.is_relative_to(Path(config["state_dir"])):
        raise ValueError("Use a deployment directory separate from node queue/releases/results")
    for name in INCLUDES:
        if destination.is_relative_to(source / name):
            raise ValueError("Deployment directory overlaps packaged source")
    manifest = bundle.inventory(source, INCLUDES)
    if "source/remote_execution/deploy.py" not in manifest["files"]:
        raise ValueError("Target source lacks the deployment checker")
    harnesses = sorted(set(harnesses or (*NATIVE, "minimum", "api")))
    if set(harnesses) - {*NATIVE, "minimum", "api"}:
        raise ValueError("Unknown harness")
    services = sorted(set(config.get("services", {}) if services is None else services))
    if set(services) - config.get("services", {}).keys():
        raise ValueError("Unconfigured service requested")
    compatible = environment_matches(source, config["python"])
    dependencies = {name: manifest["files"][name]["sha256"] for name in ("pyproject.toml", "uv.lock")}
    dependency_id = digest({"files": dependencies, "python": "3.12", "extras": [], "dev": False})
    python = config["python"] if compatible else str(destination / "environments" / dependency_id / "venv/bin/python")
    request = {"schema_version": 1, "source": str(source), "config_path": str(config_path),
               "node_config_sha256": digest(config), "destination": str(destination),
               "release_id": digest(manifest), "dependency_id": dependency_id,
               "python": python, "reuse_node_python": compatible,
               "harnesses": harnesses, "services": services}
    components = {}
    previous = bundle.inventory(absolute(installed_source), INCLUDES) if installed_source else None
    for name, prefixes in COMPONENTS.items():
        current = {p: row for p, row in manifest["files"].items() if p.startswith(prefixes)}
        old = {p: row for p, row in previous["files"].items() if p.startswith(prefixes)} if previous else None
        components[name] = {"target_sha256": digest(current),
                            "source_changed": digest(current) != digest(old) if old is not None else None}
    return {"plan_sha256": digest(request), "request": request, "components": components,
            "jobs": queue_snapshot(config),
            "actions": ["stage immutable worker/benchmark source",
                        "reuse compatible node Python (no sync)" if compatible else "prepare isolated locked Python environment",
                        "write candidate node config and systemd unit; do not activate"],
            "manual_boundaries": ["harness/image/overlay mismatches require explicit provisioning",
                                  "solver, VAL, vLLM, weights, drivers and secrets are never updated",
                                  "check probes required before activation; a real-model canary is separate",
                                  "old jobs retain their original node config and runtime bindings"]}


def create_same(path, value):
    path = absolute(path)
    if path.exists():
        if read_json(path) != value:
            raise ValueError(f"Refusing different existing deployment record: {path}")
    else:
        private_json(path, value, replace=False)


def unit_text(workspace, python, config_path):
    def quote(value):
        return json.dumps(str(value).replace("%", "%%"))
    user = pwd.getpwuid(os.getuid()).pw_name
    return ("[Unit]\nDescription=Benchmark execution-node control service\nAfter=network-online.target docker.service\n\n"
            "[Service]\nType=simple\nUser=" + user + "\nWorkingDirectory=" + quote(workspace) + "\n"
            "Environment=" + quote("PYTHONPATH=" + str(workspace / "source")) + "\n"
            "Environment=PYTHONDONTWRITEBYTECODE=1\n"
            "ExecStart=:" + quote(python) + " -B -m remote_execution.worker --config " + quote(config_path) + " --port 8876\n"
            "Restart=on-failure\nRestartSec=3\nUMask=0077\nKillMode=process\n\n[Install]\nWantedBy=multi-user.target\n")


def apply(preview, expected):
    request = preview["request"]
    if digest(request) != expected or preview["plan_sha256"] != expected:
        raise ValueError("Plan changed; review a fresh plan before applying")
    source, dest = Path(request["source"]), absolute(request["destination"])
    config = validate_node(read_json(Path(request["config_path"])))
    if digest(config) != request["node_config_sha256"]:
        raise ValueError("Node configuration changed")
    if digest(bundle.inventory(source, INCLUDES)) != request["release_id"]:
        raise ValueError("Source changed after planning")
    with idle_node(config):
        marker = {"schema_version": 1, "purpose": "remote-execution-deployments"}
        if dest.exists() and not (dest / "deployment-root.json").is_file():
            raise ValueError("Destination already exists without a deployment ownership marker; use a new directory")
        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
        create_same(safe_path(dest, "deployment-root.json"), marker)
        with lock(safe_path(dest, "deploy.lock")):
            archive = safe_path(dest, "archives/" + request["release_id"] + ".tar.gz")
            if not archive.exists():
                info = bundle.build(source, INCLUDES, archive)
                if info["release_id"] != request["release_id"]:
                    raise ValueError("Source changed during packaging; retain archive for inspection")
            release = bundle.install(archive, safe_path(dest, "releases"), request["release_id"])
            workspace = release / "workspace"
            python = request["python"]
            if request["reuse_node_python"]:
                if not environment_matches(workspace, python):
                    raise ValueError("Existing Python environment changed; refuse in-place sync")
            else:
                env_root = safe_path(dest, "environments/" + request["dependency_id"])
                env_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                safe_path(env_root, "venv")  # Never let uv follow an injected environment link.
                create_same(env_root / "request.json", {"dependency_id": request["dependency_id"]})
                ready = env_root / "ready.json"
                if not ready.exists():
                    result = subprocess.run(uv_command(workspace, check=False),
                        env=environment(workspace, env_root / "venv"), capture_output=True, timeout=1800)
                    if result.returncode:
                        raise ValueError("Isolated uv sync failed; old environments untouched (retry same plan)")
                if not environment_matches(workspace, python):
                    raise ValueError("Prepared Python differs from lock; a used environment is never repaired in place")
                create_same(ready, {"dependency_id": request["dependency_id"], "python": python})
            candidate = deepcopy(config)
            candidate["python"] = python
            bundle.bind_runtime(release, candidate.get("bindings", {}))
            prepared = safe_path(dest, "prepared/" + expected)
            prepared.mkdir(parents=True, exist_ok=True, mode=0o700)
            create_same(prepared / "request.json", request)
            create_same(prepared / "original-node.json", config)
            create_same(prepared / "node.json", candidate)
            text = unit_text(workspace, python, prepared / "node.json")
            service = safe_path(prepared, "worker.service")
            if service.exists():
                if service.read_text() != text:
                    raise ValueError("Prepared service unit changed")
            else:
                with service.open("x") as stream:
                    stream.write(text)
                service.chmod(0o600)
            return {"status": "prepared_not_activated", "prepared": str(prepared),
                    "workspace": str(workspace), "python": python,
                    "node_config_sha256": digest(candidate),
                    "old_job_config_compatible": candidate == config,
                    "next": "Run check --prepared PATH, then explicitly install/start the candidate service"}


def probe(config, harnesses, services):
    """Executed by the staged Python FROM the staged source, never the caller's imports."""
    from .benchmark import service_preflight
    from agent_formalizer.claws import get_adapter
    from agent_formalizer.configuration.config import BASE_IMAGE
    from agent_formalizer.runtime.runtime_lock import TEXT_LOCK_PATH, RuntimeLockMismatch, validate_runtime_lock
    from agent_formalizer.timing.zeroclaw_deadlines import prepared as zeroclaw_prepared
    import tempfile

    rows = {}
    for name in harnesses:
        try:
            if name in NATIVE:
                image = subprocess.run(["docker", "image", "inspect", BASE_IMAGE, "--format", "{{.Id}}"],
                                       capture_output=True, text=True, check=True, timeout=30).stdout.strip()
                rows[name] = validate_runtime_lock(get_adapter(name), container_image_id=image, lock_path=TEXT_LOCK_PATH)
                if name == "zeroclaw":
                    binary, _ = zeroclaw_prepared()
                    rows[name]["checkpoint_overlay"] = {"path": str(binary), "sha256": file_hash(binary)}
            else:
                # Host-only paths need no container/runtime installation. This
                # is an import test, NOT validation of an arbitrary future profile.
                __import__("remote_execution.api" if name == "api" else "agent_formalizer.claws.minimum.runtime")
                rows[name] = {"status": "pass", "scope": "host imports only"}
        except Exception as exc:
            rows[name] = {"status": "fail", "error_type": type(exc).__name__,
                          "action": "inspect pinned harness/image or rebuild matching timing overlay; do not rewrite lock"}
            if isinstance(exc, RuntimeLockMismatch):
                # These are finite, secret-free runtime observations, not API bodies.
                rows[name]["runtime_diagnostic"] = str(exc)[:16000]
    for name in services:
        try:
            with tempfile.TemporaryDirectory(prefix="remote-deploy-health-") as scratch:
                rows["service:" + name] = {"status": "pass", "evidence": service_preflight(
                    config.get("services", {}), [name], Path(scratch) / "health.json",
                    secrets_env_file=config.get("bindings", {}).get("secrets_env_file"))}
        except Exception as exc:
            rows["service:" + name] = {"status": "fail", "error_type": type(exc).__name__,
                                      "action": "check declared service supervision, health and limits"}
    val = config.get("bindings", {}).get("val")
    rows["val"] = {"status": "pass" if val and os.access(Path(val) / "build/linux64/Release/bin/Validate", os.X_OK) else "fail",
                   "scope": "expected executable exists; semantic canary is separate"}
    return {"status": "pass" if all(row["status"] == "pass" for row in rows.values()) else "fail", "checks": rows}


class _ProbeCancelled(BaseException):
    pass


def cancel_probe(_signum, _frame):
    # Unwind the runtime probe's finally block so its own Docker container is
    # removed. Do not swallow cancellation as just another failed harness.
    raise _ProbeCancelled()


def run_probe(args, *, cwd, env):
    with subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=900)
        except BaseException:
            process.terminate()
            try:
                process.communicate(timeout=45)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
                raise ValueError("Probe cleanup did not finish; inspect deployment probe resources before retrying")
            raise
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def check(prepared):
    prepared = absolute(prepared)
    request = read_json(safe_path(prepared, "request.json"))
    if prepared.name != digest(request):
        raise ValueError("Prepared deployment identity changed")
    dest = absolute(request["destination"])
    if prepared != dest / "prepared" / digest(request):
        raise ValueError("Prepared deployment relocated")
    release = safe_path(dest, "releases/" + request["release_id"])
    if digest(bundle.verify(release)) != request["release_id"]:
        raise ValueError("Staged code changed")
    config = validate_node(read_json(safe_path(prepared, "node.json")))
    original = validate_node(read_json(safe_path(prepared, "original-node.json")))
    expected_config = deepcopy(original); expected_config["python"] = request["python"]
    if digest(original) != request["node_config_sha256"] or config != expected_config:
        raise ValueError("Prepared node configuration changed")
    workspace = release / "workspace"
    with idle_node(config):
        if not environment_matches(workspace, config["python"]):
            raise ValueError("Prepared environment no longer matches uv.lock")
        result = run_probe([config["python"], "-B", "-m", "remote_execution.deploy", "_probe",
            "--config", str(prepared / "node.json"), "--harnesses", ",".join(request["harnesses"]),
            "--services", ",".join(request["services"])], cwd=workspace, env=environment(workspace))
        if result.returncode:
            report = {"status": "fail", "error_type": "probe_process_failed", "returncode": result.returncode}
        else:
            report = json.loads(result.stdout)
        report.update({"deployment_id": digest(request), "at_unix": time.time(),
                       "not_a_real_model_canary": True, "no_service_activated": True})
        target = prepared / "checks" / (str(time.time_ns()) + ".json")
        private_json(target, report, replace=False)
        return report | {"report": str(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
        cmd.add_argument("--config", type=Path, required=True)
        cmd.add_argument("--destination", type=Path, required=True, help="Dedicated managed directory, outside node state")
        cmd.add_argument("--installed-source", type=Path, help="Optional previous installation, for component diff only")
        cmd.add_argument("--harness", action="append", choices=[*NATIVE, "minimum", "api"])
        cmd.add_argument("--service", action="append", help="Default: all services declared in node config")
        if name == "apply":
            cmd.add_argument("--expect-plan", required=True, help="Exact plan_sha256 previously reviewed")
    cmd = commands.add_parser("check")
    cmd.add_argument("--prepared", type=Path, required=True)
    cmd = commands.add_parser("_probe", help="Internal staged-runtime probe; use check instead")
    cmd.add_argument("--config", type=Path, required=True)
    cmd.add_argument("--harnesses", required=True)
    cmd.add_argument("--services", required=True)
    args = parser.parse_args()
    try:
        if args.command in {"plan", "apply"}:
            value = plan(args.source, args.config, args.destination, args.harness, args.service, args.installed_source)
            if args.command == "apply":
                value = apply(value, args.expect_plan)
        elif args.command == "check":
            value = check(args.prepared)
        else:
            signal.signal(signal.SIGTERM, cancel_probe)
            signal.signal(signal.SIGINT, cancel_probe)
            value = probe(validate_node(read_json(args.config)), args.harnesses.split(","),
                          args.services.split(",") if args.services else [])
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        # Do not serialize raw subprocess output or arbitrary provider text.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, ValueError) else "Deployment operation failed; no activation performed"}))
        return 2
    print(json.dumps(value, indent=2))
    return 2 if value.get("status") == "fail" and args.command != "_probe" else 0


if __name__ == "__main__":
    raise SystemExit(main())
