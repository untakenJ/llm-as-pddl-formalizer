"""Cohesive execution-node installation and lifecycle commands.

The checkout is the operator-facing outer directory.  Generated state, pinned
third-party runtimes, service candidates and immutable worker releases live in
one managed root (``.local/remote-node`` by default).  Nothing here changes a
benchmark profile or the ordinary local runner.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

from . import deploy, vllm
from .protocol import (digest, exact, file_hash, identifier, positive,
                       private_json, read_json, secret_file)
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = Path(__file__).with_name("deploy") / "node.local.example.json"
DEFAULT_CONFIG = Path(__file__).with_name("node.local.json")
MARKER = {"schema_version": 1, "purpose": "formalizer-remote-execution-node"}
NATIVE = {"openclaw", "hermes", "nanobot", "generic", "zeroclaw"}


def _path(value: str, root: Path = ROOT) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Deployment paths must be nonempty strings")
    path = Path(value).expanduser()
    path = path if path.is_absolute() else root / path
    return Path(os.path.abspath(path))


def _unit_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]+\.service", value):
        raise ValueError("Invalid systemd unit name")
    return value


def validate(raw, *, repository=ROOT):
    exact(raw, {"schema_version", "node_id", "managed_root", "secrets_env_file",
                "control", "install", "solver", "model"})
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Unsupported node-local configuration schema")
    identifier(raw["node_id"])
    managed = _path(raw["managed_root"], repository)
    if managed == repository or repository.is_relative_to(managed):
        raise ValueError("managed_root must not contain the repository")
    _path(raw["secrets_env_file"], repository)

    control = raw["control"]
    exact(control, {"listen_host", "port", "max_jobs", "max_formalizer_workers"})
    if control["listen_host"] != "127.0.0.1":
        raise ValueError("Control service currently binds 127.0.0.1; use an SSH tunnel")
    positive(control["port"], 65535)
    positive(control["max_jobs"], 64)
    positive(control["max_formalizer_workers"], 256)

    install = raw["install"]
    exact(install, {"harnesses", "openclaw_npm_spec", "node_binary",
                    "build_agent_image", "agent_image", "val_repository", "val_revision"})
    if (not isinstance(install["harnesses"], list) or
            set(install["harnesses"]) != NATIVE or len(install["harnesses"]) != len(NATIVE)):
        raise ValueError("Install exactly the five native harnesses once; experiment selection stays controller-side")
    if not re.fullmatch(r"openclaw@[0-9]+\.[0-9]+\.[0-9]+", install["openclaw_npm_spec"]):
        raise ValueError("OpenClaw npm package must be pinned to an exact version")
    node = _path(install["node_binary"], repository)
    if not node.is_absolute():
        raise ValueError("node_binary must resolve to an absolute path")
    if type(install["build_agent_image"]) is not bool or install["agent_image"] != "pddl-agent-base:latest":
        raise ValueError("Remote node must provision the existing adapter's pddl-agent-base:latest image")
    if install["val_repository"] != "https://github.com/KCL-Planning/VAL.git":
        raise ValueError("VAL must use the reviewed KCL-Planning repository")
    if not re.fullmatch(r"[0-9a-f]{40}", install["val_revision"]):
        raise ValueError("Pin VAL to a reviewed full commit hash")

    solver = raw["solver"]
    exact(solver, {"enabled", "systemd_unit", "image", "build_image", "workers", "memory",
                   "memory_swap", "cpus", "pids_limit", "timeout_seconds", "worker_security",
                   "allowed_solvers"})
    if type(solver["enabled"]) is not bool or type(solver["build_image"]) is not bool:
        raise ValueError("Solver enable/build flags must be boolean")
    _unit_name(solver["systemd_unit"])
    positive(solver["workers"], 64); positive(solver["pids_limit"], 65535)
    positive(solver["timeout_seconds"], 3600)
    if type(solver["cpus"]) not in {int, float} or solver["cpus"] <= 0:
        raise ValueError("Solver CPUs must be positive")
    if not all(isinstance(solver[key], str) and solver[key] for key in ("image", "memory", "memory_swap")):
        raise ValueError("Solver image/memory settings must be nonempty")
    if solver["worker_security"] not in {"privileged", "restricted", "userns"}:
        raise ValueError("Unknown solver worker security mode")
    if solver["allowed_solvers"] != ["dual-bfws-ffparser"]:
        raise ValueError("Current benchmark closure supports the pinned dual-bfws-ffparser solver")

    model = raw["model"]
    exact(model, {"mode", "vllm_config", "pull_image", "download_weights", "startup_timeout_seconds"})
    if model["mode"] not in {"external", "vllm"}:
        raise ValueError("model.mode must be external or vllm")
    if any(type(model[key]) is not bool for key in ("pull_image", "download_weights")):
        raise ValueError("Model preparation flags must be boolean")
    positive(model["startup_timeout_seconds"], 86400)
    if model["mode"] == "vllm":
        if not isinstance(model["vllm_config"], str):
            raise ValueError("vllm mode requires a node-local vllm_config path")
        vllm.validate(read_json(_path(model["vllm_config"], repository)))
    elif model["vllm_config"] is not None or model["pull_image"] or model["download_weights"]:
        raise ValueError("External model mode cannot declare vLLM preparation")
    return raw


def paths(config, *, repository=ROOT, deployment_id=None):
    root = _path(config["managed_root"], repository)
    components = root / "components" / deployment_id if deployment_id else root / "components"
    return {
        "repository": repository,
        "root": root,
        "state": root / "state",
        "private": root / "private",
        "token": root / "private/control-token",
        "components": components,
        "runtimes": components / "harness-runtimes",
        "openclaw": components / "openclaw",
        "zeroclaw_deadlines": components / "zeroclaw-deadlines",
        "val": components / "VAL",
        "generated": root / "generated",
        "deployments": root / "deployments",
        "secrets": _path(config["secrets_env_file"], repository),
    }


def init_config(destination=DEFAULT_CONFIG):
    destination = _path(str(destination))
    if destination.exists():
        raise ValueError(f"Refusing to overwrite existing local configuration: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EXAMPLE, destination)
    destination.chmod(0o600)
    return {"status": "created", "config": str(destination),
            "next": "Edit only node-local paths/resources/pins, then run node plan"}


def _source_identity(repository):
    inventory = deploy.bundle.inventory(repository, deploy.INCLUDES)
    return digest(inventory)


def plan(config_path=DEFAULT_CONFIG, *, repository=ROOT):
    repository = _path(str(repository))
    config_path = _path(str(config_path), repository)
    config = validate(read_json(config_path), repository=repository)
    resolved = paths(config, repository=repository)
    request = {"schema_version": 1, "config_sha256": digest(config),
               "source_release_id": _source_identity(repository),
               "repository": str(repository), "config": str(config_path),
               "managed_root": str(resolved["root"])}
    if config["model"]["mode"] == "vllm":
        request["vllm_config_sha256"] = file_hash(_path(config["model"]["vllm_config"], repository))
    actions = [
        "create an owner-only managed node root and durable queue",
        "install pinned harness runtimes and OpenClaw under managed_root/components",
        ("build the repository-owned agent image" if config["install"]["build_agent_image"]
         else "verify the explicitly pre-provisioned agent image during runtime checks"),
        "checkout/build pinned KCL-Planning/VAL under managed_root/components",
    ]
    if config["solver"]["enabled"]:
        actions += [("build and supervise" if config["solver"]["build_image"] else "verify and supervise") +
                    " one shared local solver service on the compatibility port 8769"]
    if config["model"]["mode"] == "vllm":
        actions += ["validate the pinned vLLM deployment and generate its supervised service"]
        if config["model"]["pull_image"]:
            actions += ["pull the explicitly digest-pinned vLLM image"]
        if config["model"]["download_weights"]:
            actions += ["download the explicitly revision-pinned model directly on this node"]
    actions += ["stage an immutable worker release and candidate systemd units; do not activate"]
    return {"plan_sha256": digest(request), "request": request, "actions": actions,
            "generated_root": str(resolved["root"]),
            "manual_boundaries": [
                "OS packages, GPU driver and NVIDIA container runtime are host prerequisites checked by doctor",
                "secrets stay in the configured owner-only env file and are never generated or copied",
                "apply does not activate services; activate is an explicit maintenance action",
                "model/harness canaries remain required before a formal campaign",
            ]}


def _run(args, *, cwd=None, env=None, timeout=3600):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f"Provisioning command failed ({Path(args[0]).name}, rc={result.returncode})")
    return result


def _owned_root(root):
    if root.exists():
        marker = root / "node-root.json"
        if not marker.is_file() or read_json(marker) != MARKER:
            raise ValueError("managed_root exists without the expected ownership marker")
    else:
        root.mkdir(parents=True, mode=0o700)
        private_json(root / "node-root.json", MARKER, replace=False)
    root.chmod(0o700)


def _ensure_token(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48) + "\n")
        path.chmod(0o600)
    secret_file(path)


def _require_secrets(path):
    if not path.is_file():
        raise ValueError(f"Create the node-only secrets file before apply: {path}")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Node secrets file must be an owner-only regular file (chmod 600)")


def _checkout_val(config, target):
    install = config["install"]
    if not (target / ".git").is_dir():
        if target.exists():
            raise ValueError("Refusing to replace a non-git VAL component directory")
        _run(["git", "clone", "--filter=blob:none", "--no-checkout", install["val_repository"], str(target)])
    if (target / ".git/index").exists():
        for args in (["git", "-C", str(target), "diff", "--quiet"],
                     ["git", "-C", str(target), "diff", "--cached", "--quiet"]):
            _run(args)
    _run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", install["val_revision"]])
    _run(["git", "-C", str(target), "checkout", "--detach", install["val_revision"]])
    validator = target / "build/linux64/Release/bin/Validate"
    if not os.access(validator, os.X_OK):
        _run(["bash", "scripts/linux/build_linux64.sh"], cwd=target, timeout=1800)
    if not os.access(validator, os.X_OK):
        raise ValueError("Pinned VAL build did not produce the expected Validate executable")


def _install_components(config, resolved):
    required = ["uv", "git", "docker", "gcc", "cargo", "cmake", "make", "npm",
                str(_path(config["install"]["node_binary"]))]
    missing = [name for name in required if not (Path(name).is_file() if "/" in name else shutil.which(name))]
    if missing:
        raise ValueError("Missing host prerequisites: " + ", ".join(missing))
    version = _run([str(_path(config["install"]["node_binary"])), "--version"], timeout=30).stdout
    if not re.fullmatch(r"v22(?:\.[0-9]+){2}\s*", version):
        raise ValueError("Pinned OpenClaw runtime requires Node.js 22.x")
    resolved["components"].mkdir(parents=True, exist_ok=True, mode=0o700)
    env = dict(os.environ)
    env["FORMALIZER_HARNESS_RUNTIME_ROOT"] = str(resolved["runtimes"])
    script = resolved["repository"] / "source/agent_formalizer/runtime/install_harnesses.sh"
    # OpenClaw is installed separately because the repository installer owns the
    # other four harnesses plus the logits bridge.
    _run(["bash", str(script), "hermes", "nanobot", "generic", "zeroclaw", "logits"],
         cwd=resolved["repository"], env=env, timeout=7200)
    _run(["npm", "install", "--prefix", str(resolved["openclaw"]), "--omit=dev", "--no-audit", "--no-fund",
          config["install"]["openclaw_npm_spec"]], timeout=1800)
    module = resolved["openclaw"] / "node_modules/openclaw"
    if not (module / "openclaw.mjs").is_file():
        raise ValueError("Pinned OpenClaw install lacks openclaw.mjs")
    if config["install"]["build_agent_image"]:
        _run(["docker", "build", "-t", config["install"]["agent_image"],
              "source/agent_formalizer/docker"], cwd=resolved["repository"], timeout=3600)
    _checkout_val(config, resolved["val"])
    solver = config["solver"]
    if solver["enabled"] and solver["build_image"]:
        _run(["docker", "build", "-t", solver["image"], "source/local_solver"],
             cwd=resolved["repository"], timeout=3600)
    resolved["zeroclaw_deadlines"].mkdir(parents=True, exist_ok=True, mode=0o700)


def _prepare_model(config, resolved):
    model = config["model"]
    if model["mode"] != "vllm":
        return None
    source = _path(model["vllm_config"], resolved["repository"])
    deployment = vllm.validate(read_json(source))
    if model["pull_image"]:
        _run(["docker", "pull", deployment["image"]], timeout=3600)
    if model["download_weights"]:
        hf = shutil.which("hf") or str(resolved["runtimes"] / "logits-bridge/venv/bin/hf")
        if not Path(hf).is_file():
            hf = None
        if not hf:
            raise ValueError("download_weights requires the Hugging Face hf CLI")
        target = Path(deployment["model_path"])
        target.mkdir(parents=True, exist_ok=True)
        _run([hf, "download", deployment["model_repository"], "--revision", deployment["model_revision"],
              "--local-dir", str(target)], timeout=86400)
    vllm.inspect(deployment)
    # vLLM and benchmark gateway must authenticate with the same secret, but
    # neither value is ever copied into generated JSON or command lines.
    import hmac
    from agent_formalizer.util import read_named_secret
    runner_key = read_named_secret("SELF_HOSTED_API_KEY", resolved["secrets"])
    env_lines = [line.strip() for line in Path(deployment["api_env_file"]).read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
    if len(env_lines) != 1 or not env_lines[0].startswith("VLLM_API_KEY=") or not hmac.compare_digest(
            runner_key, env_lines[0].split("=", 1)[1]):
        raise ValueError("SELF_HOSTED_API_KEY and VLLM_API_KEY must be identical")
    return deployment


def _solver_service(config, image_id):
    solver = config["solver"]
    expected = {"status": "ok", "backend": "local-planutils",
                "pool": {"image_id": image_id},
                "config": {"workers": solver["workers"], "memory": solver["memory"],
                           "memory_swap": solver["memory_swap"], "cpus": solver["cpus"],
                           "pids_limit": solver["pids_limit"], "timeout_seconds": float(solver["timeout_seconds"]),
                           "worker_security": solver["worker_security"],
                           "allowed_solvers": solver["allowed_solvers"]}}
    return {"health_url": "http://127.0.0.1:8769/__benchmark__/health",
            "expected": expected, "systemd_unit": solver["systemd_unit"],
            "provenance": {"image": solver["image"], "image_id": image_id,
                           "managed_by": "remote_execution.node"}}


def _node_config(config, resolved, model_deployment):
    services = {}
    if config["solver"]["enabled"]:
        image_id = _run(["docker", "image", "inspect", config["solver"]["image"], "--format", "{{.Id}}"],
                        timeout=30).stdout.strip()
        services["solver"] = _solver_service(config, image_id)
    if model_deployment is not None:
        services["model"] = vllm.service_config(model_deployment)
    return {"schema_version": 1, "node_id": config["node_id"], "state_dir": str(resolved["state"]),
            "python": sys.executable, "token_file": str(resolved["token"]),
            "control_port": config["control"]["port"], "max_jobs": config["control"]["max_jobs"],
            "max_formalizer_workers": config["control"]["max_formalizer_workers"], "allow_probe": False,
            "bindings": {"harness_runtimes": str(resolved["runtimes"]),
                         "zeroclaw_deadlines": str(resolved["zeroclaw_deadlines"]),
                         "val": str(resolved["val"]), "secrets_env_file": str(resolved["secrets"]),
                         "openclaw_node_bin": str(_path(config["install"]["node_binary"])),
                         "openclaw_module_dir": str(resolved["openclaw"] / "node_modules/openclaw")},
            "services": services}


def _quote(value):
    value = str(value)
    if any(c in value for c in ('\n', '\r', '\x00', '"', '\\')):
        raise ValueError("Unsafe systemd value")
    return '"' + value.replace("%", "%%") + '"'


def _solver_unit(workspace, python, config):
    solver = config["solver"]
    user = pwd.getpwuid(os.getuid()).pw_name
    args = [python, "-B", str(workspace / "source/local_solver/server.py"), "--port", "8769",
            "--workers", str(solver["workers"]), "--memory", solver["memory"], "--memory-swap", solver["memory_swap"],
            "--cpus", str(solver["cpus"]), "--pids-limit", str(solver["pids_limit"]),
            "--timeout", str(solver["timeout_seconds"]), "--image", solver["image"],
            "--worker-security", solver["worker_security"]]
    for name in solver["allowed_solvers"]:
        args += ["--solver", name]
    return ("[Unit]\nDescription=Formalizer shared local solver\nAfter=docker.service\nRequires=docker.service\n\n"
            "[Service]\nType=simple\nUser=" + user + "\nWorkingDirectory=" + str(workspace).replace("%", "%%") + "\n"
            "ExecStart=:" + " ".join(_quote(value) for value in args) + "\nRestart=on-failure\nRestartSec=3\n"
            "UMask=0077\nKillMode=mixed\nTimeoutStopSec=120\n\n[Install]\nWantedBy=multi-user.target\n")


def _model_unit(workspace, python, model_config, evidence_dir, deployment):
    user = pwd.getpwuid(os.getuid()).pw_name
    args = [python, "-B", "-m", "remote_execution.vllm", "run", "--config", str(model_config),
            "--evidence-dir", str(evidence_dir)]
    return ("[Unit]\nDescription=Formalizer vLLM model service\nAfter=docker.service\nRequires=docker.service\n\n"
            "[Service]\nType=simple\nUser=" + user + "\nWorkingDirectory=" + str(workspace).replace("%", "%%") + "\n"
            "Environment=" + _quote("PYTHONPATH=" + str(workspace / "source")) + "\n"
            "ExecStart=:" + " ".join(_quote(value) for value in args) + "\n"
            "ExecStop=/usr/bin/docker stop -t 90 " + deployment["container_name"] + "\n"
            "Restart=on-failure\nRestartSec=10\nUMask=0077\nKillMode=process\nTimeoutStartSec=0\n"
            "TimeoutStopSec=120\n\n[Install]\nWantedBy=multi-user.target\n")


def apply(config_path=DEFAULT_CONFIG, *, expected, repository=ROOT):
    preview = plan(config_path, repository=repository)
    if preview["plan_sha256"] != expected:
        raise ValueError("Deployment plan changed; inspect a fresh plan")
    repository = Path(preview["request"]["repository"])
    config = validate(read_json(Path(preview["request"]["config"])), repository=repository)
    if digest(config) != preview["request"]["config_sha256"] or _source_identity(repository) != preview["request"]["source_release_id"]:
        raise ValueError("Configuration or source changed after planning")
    base = paths(config, repository=repository)
    resolved = paths(config, repository=repository, deployment_id=expected)
    _owned_root(base["root"])
    _require_secrets(base["secrets"])
    _ensure_token(base["token"])
    Store(base["state"])
    active = subprocess.run(["systemctl", "is-active", "formalizer-remote-worker.service"],
                            capture_output=True, text=True).returncode == 0
    if active:
        raise ValueError("Stop remote worker admission before applying node components")
    # Hold the same queue/owner guards used by the immutable deployment tool
    # while changing shared harnesses/images/VAL.
    with deploy.idle_node({"state_dir": str(base["state"])}):
        _install_components(config, resolved)
    model = _prepare_model(config, resolved)
    node = _node_config(config, resolved, model)
    generation = resolved["generated"] / expected
    generation.mkdir(parents=True, exist_ok=True, mode=0o700)
    node_path = generation / "node.json"
    deploy.create_same(node_path, node)
    staged_plan = deploy.plan(repository, node_path, resolved["deployments"],
                              harnesses=[*sorted(NATIVE), "minimum", "api"])
    staged = deploy.apply(staged_plan, staged_plan["plan_sha256"])
    prepared = Path(staged["prepared"])
    workspace = Path(staged["workspace"]); python = staged["python"]
    units = {"worker": {"name": "formalizer-remote-worker.service", "path": str(prepared / "worker.service")}}
    if config["solver"]["enabled"]:
        path = prepared / config["solver"]["systemd_unit"]
        text = _solver_unit(workspace, python, config)
        if path.exists() and path.read_text() != text:
            raise ValueError("Prepared solver unit changed for the same deployment")
        if not path.exists():
            path.write_text(text); path.chmod(0o600)
        units["solver"] = {"name": config["solver"]["systemd_unit"], "path": str(path)}
    if model is not None:
        model_config = generation / "vllm.json"
        deploy.create_same(model_config, model)
        # Keep the service generator pure and avoid embedding credentials.
        name = model["container_name"] + ".service"
        text = _model_unit(workspace, python, model_config, resolved["root"] / "model-launches", model)
        path = prepared / name
        if path.exists() and path.read_text() != text:
            raise ValueError("Prepared model unit changed for the same deployment")
        if not path.exists():
            path.write_text(text); path.chmod(0o600)
        units["model"] = {"name": name, "path": str(path)}
    timeouts = {"solver": 180}
    if model is not None:
        timeouts["model"] = config["model"]["startup_timeout_seconds"]
    record = {"schema_version": 1, "plan_sha256": expected, "prepared": str(prepared),
              "workspace": str(workspace), "python": python, "node_config": str(prepared / "node.json"),
              "units": units, "service_startup_timeout_seconds": timeouts, "created_at_unix": time.time()}
    record_path = generation / "apply.json"
    if record_path.exists():
        old = read_json(record_path)
        record["created_at_unix"] = old.get("created_at_unix")
        if old != record:
            raise ValueError("Prepared deployment record changed for the same plan")
    else:
        private_json(record_path, record, replace=False)
    return {"status": "prepared_not_activated", "record": str(record_path),
            "prepared": str(prepared), "units": units,
            "next": "Run node doctor, then node activate --record ... --sudo during a maintenance window"}


def _systemctl(args, sudo):
    prefix = ["sudo"] if sudo else []
    return _run(prefix + ["systemctl", *args], timeout=180)


def _wait_health(service, timeout, secrets_env_file):
    opener = build_opener(ProxyHandler({})); deadline = time.monotonic() + timeout
    last = None
    headers = {}
    if "api_key_env" in service:
        from agent_formalizer.util import read_named_secret
        headers["Authorization"] = "Bearer " + read_named_secret(service["api_key_env"], secrets_env_file)
    while time.monotonic() < deadline:
        try:
            with opener.open(Request(service["health_url"], headers=headers), timeout=10) as response:
                if response.status == 200:
                    return
        except OSError as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise ValueError(f"Service health did not become ready ({last or 'unknown'})")


def activate(record_path, *, sudo=False):
    record = read_json(_path(str(record_path)))
    exact(record, {"schema_version", "plan_sha256", "prepared", "workspace", "python", "node_config", "units",
                   "service_startup_timeout_seconds", "created_at_unix"})
    config = read_json(Path(record["node_config"])); control_port = config.get("control_port", 8876)
    prefix = ["sudo"] if sudo else []
    active = [unit["name"] for unit in record["units"].values() if
              subprocess.run(["systemctl", "is-active", unit["name"]],
                             capture_output=True, text=True).returncode == 0]
    if active:
        raise ValueError("Stop active candidate services before replacing a deployment: " + ", ".join(active))
    for unit in record["units"].values():
        _unit_name(unit["name"])
        source = Path(unit["path"])
        if not source.is_file() or not source.resolve().is_relative_to(Path(record["prepared"]).resolve()):
            raise ValueError("Candidate unit is outside the reviewed prepared deployment")
        verification = deploy.verify_unit(source)
        if verification["status"] != "pass":
            raise ValueError("Candidate systemd unit did not pass the host parser")
        _run(prefix + ["install", "-m", "0644", str(source), "/etc/systemd/system/" + unit["name"]])
    _systemctl(["daemon-reload"], sudo)
    for name in ("solver", "model"):
        if name in record["units"]:
            _systemctl(["enable", "--now", record["units"][name]["name"]], sudo)
    for name, service in config.get("services", {}).items():
        timeout = record["service_startup_timeout_seconds"].get(name, 180)
        _wait_health(service, timeout, config.get("bindings", {}).get("secrets_env_file"))
    checked = deploy.check(Path(record["prepared"]))
    if checked["status"] != "pass":
        raise ValueError("Prepared deployment check did not pass; worker was not started")
    _systemctl(["enable", "--now", record["units"]["worker"]["name"]], sudo)
    return {"status": "active", "control_endpoint": f"http://127.0.0.1:{control_port}",
            "check_report": checked["report"], "units": record["units"]}


def doctor(config_path=DEFAULT_CONFIG, *, repository=ROOT):
    config = validate(read_json(_path(str(config_path), _path(str(repository)))), repository=_path(str(repository)))
    resolved = paths(config, repository=_path(str(repository)))
    checks = {}
    for command in ("uv", "git", "docker", "gcc", "cargo", "cmake", "make", "npm", "systemctl"):
        checks["command:" + command] = {"status": "pass" if shutil.which(command) else "fail"}
    node_binary = _path(config["install"]["node_binary"])
    node_version = subprocess.run([str(node_binary), "--version"], capture_output=True, text=True) \
        if node_binary.is_file() and os.access(node_binary, os.X_OK) else None
    checks["node"] = {"status": "pass" if node_version and node_version.returncode == 0 and
                       re.fullmatch(r"v22(?:\.[0-9]+){2}\s*", node_version.stdout) else "fail",
                       "version": node_version.stdout.strip() if node_version else None}
    try:
        _require_secrets(resolved["secrets"])
        secret_status = "pass"
    except (OSError, ValueError):
        secret_status = "fail"
    checks["secrets"] = {"status": secret_status, "path": str(resolved["secrets"])}
    checks["managed_root"] = {"status": "pass" if not resolved["root"].exists() or
                               (resolved["root"] / "node-root.json").is_file() else "fail",
                               "path": str(resolved["root"])}
    for unit in ("apt-daily.service", "apt-daily-upgrade.service", "unattended-upgrades.service"):
        if shutil.which("systemctl"):
            result = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
            checks["maintenance:" + unit] = {"status": "warning" if result.returncode == 0 else "pass",
                                             "active": result.returncode == 0}
        else:
            checks["maintenance:" + unit] = {"status": "fail", "reason": "systemctl unavailable"}
    if config["model"]["mode"] == "vllm":
        nvidia = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True) if shutil.which("nvidia-smi") else None
        checks["nvidia-smi"] = {"status": "pass" if nvidia and nvidia.returncode == 0 else "fail",
                                 "gpu_count": len(nvidia.stdout.splitlines()) if nvidia and nvidia.returncode == 0 else 0}
    if shutil.which("docker"):
        result = subprocess.run(["docker", "info", "--format", "{{json .Runtimes}}"],
                                capture_output=True, text=True)
        checks["docker_daemon"] = {"status": "pass" if result.returncode == 0 else "fail"}
        if config["model"]["mode"] == "vllm":
            try:
                runtimes = json.loads(result.stdout) if result.returncode == 0 else {}
            except json.JSONDecodeError:
                runtimes = {}
            checks["nvidia_container_runtime"] = {"status": "pass" if "nvidia" in runtimes else "fail"}
    parent = resolved["root"] if resolved["root"].exists() else resolved["root"].parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    usage = shutil.disk_usage(parent)
    checks["storage"] = {"status": "pass" if usage.free >= 20 * 1024**3 else "warning",
                         "free_gib": round(usage.free / 1024**3, 1), "filesystem_path": str(parent)}
    overall = "fail" if any(row["status"] == "fail" for row in checks.values()) else "warning" if any(
        row["status"] == "warning" for row in checks.values()) else "pass"
    return {"status": overall, "checks": checks,
            "note": "Active OS maintenance is a launch warning; this command never disables updates"}


def service_status(config_path=DEFAULT_CONFIG, *, repository=ROOT):
    repository = _path(str(repository))
    config = validate(read_json(_path(str(config_path), repository)), repository=repository)
    names = ["formalizer-remote-worker.service"]
    if config["solver"]["enabled"]:
        names.append(config["solver"]["systemd_unit"])
    if config["model"]["mode"] == "vllm":
        deployment = read_json(_path(config["model"]["vllm_config"], _path(str(repository))))
        names.append(deployment["container_name"] + ".service")
    units = {}
    for name in names:
        result = subprocess.run(["systemctl", "show", name, "-p", "LoadState", "-p", "ActiveState", "-p", "SubState"],
                                capture_output=True, text=True)
        units[name] = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    resolved = paths(config, repository=repository)
    queue = {"status": "uninitialized", "jobs": []}
    if (resolved["state"] / "queue.sqlite3").is_file():
        rows = deploy.queue_snapshot({"state_dir": str(resolved["state"])})
        queue = {"status": "ok", "jobs": rows,
                 "counts": {state: sum(row["status"] == state for row in rows)
                            for state in sorted({row["status"] for row in rows})}}
    control = {"status": "unavailable"}
    if resolved["token"].is_file():
        try:
            request = Request(f"http://127.0.0.1:{config['control']['port']}/health",
                              headers={"Authorization": "Bearer " + secret_file(resolved["token"])})
            with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
                control = json.loads(response.read(1024 * 1024))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return {"status": "ok", "units": units, "control": control, "queue": queue}


def stop(config_path=DEFAULT_CONFIG, *, repository=ROOT, sudo=False, all_services=False):
    repository = _path(str(repository))
    config = validate(read_json(_path(str(config_path), repository)), repository=repository)
    names = ["formalizer-remote-worker.service"]
    _systemctl(["stop", names[0]], sudo)
    if all_services:
        # The control service has released worker.lock, but detached accepted
        # executions may still own their per-job locks. Never remove their
        # model/solver dependencies underneath them.
        with deploy.idle_node({"state_dir": str(paths(config, repository=repository)["state"])}):
            extra = []
            if config["model"]["mode"] == "vllm":
                model = read_json(_path(config["model"]["vllm_config"], repository))
                extra.append(model["container_name"] + ".service")
            if config["solver"]["enabled"]:
                extra.append(config["solver"]["systemd_unit"])
            for name in extra:
                _systemctl(["stop", name], sudo)
            names.extend(extra)
    return {"status": "stopped", "units": names,
            "note": "Stopping admission never deletes queues, releases, results or completed checkpoints"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repository", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("--destination", type=Path, default=DEFAULT_CONFIG)
    commands.add_parser("plan")
    apply_cmd = commands.add_parser("apply"); apply_cmd.add_argument("--expect-plan", required=True)
    activate_cmd = commands.add_parser("activate"); activate_cmd.add_argument("--record", type=Path, required=True); activate_cmd.add_argument("--sudo", action="store_true")
    commands.add_parser("doctor"); commands.add_parser("status")
    stop_cmd = commands.add_parser("stop"); stop_cmd.add_argument("--all", action="store_true"); stop_cmd.add_argument("--sudo", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "init": value = init_config(args.destination)
        elif args.command == "plan": value = plan(args.config, repository=args.repository)
        elif args.command == "apply": value = apply(args.config, expected=args.expect_plan, repository=args.repository)
        elif args.command == "activate": value = activate(args.record, sudo=args.sudo)
        elif args.command == "doctor": value = doctor(args.config, repository=args.repository)
        elif args.command == "status": value = service_status(args.config, repository=args.repository)
        else: value = stop(args.config, repository=args.repository, sudo=args.sudo, all_services=args.all)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "detail": str(exc)}))
        return 2
    print(json.dumps(value, indent=2))
    return 2 if value.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
