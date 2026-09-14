"""Explicit, version-checked native deadline and call-checkpoint integration."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import logical_time, call_checkpoint
from ..external_calls.control import read_json, write_json

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
SUPPORTED_HARNESSES = frozenset({"generic", "nanobot", "hermes", "openclaw"})
CHECKPOINT_HARNESSES = SUPPORTED_HARNESSES | {"zeroclaw"}
ENVIRONMENT_KEYS = ("BENCHMARK_DEADLINE_DIR", "BENCHMARK_DEADLINE_HARNESS", "PYTHONPATH", "LD_PRELOAD", "BENCHMARK_EXTERNAL_CALL_TIMING")


def policy(adapter):
    resolved = getattr(getattr(adapter, "resolved_config", None), "raw", {}).get("resolved", {})
    return resolved.get("external_call_timing")


def selected(adapter):
    return policy(adapter) in {logical_time.POLICY_ID, call_checkpoint.POLICY_ID}


def validate(adapter):
    if selected(adapter):
        supported = CHECKPOINT_HARNESSES if policy(adapter) == call_checkpoint.POLICY_ID else SUPPORTED_HARNESSES
        if adapter.name not in supported:
            raise RuntimeError(f"{policy(adapter)}: native deadline coverage not implemented for {adapter.name}")
        if adapter.model_gateway().get("transport") is not None:
            raise RuntimeError(f"{logical_time.POLICY_ID}: custom model gateway transports are not supported")


def prepare(workspace):
    from ..results import native_audit
    adapter = workspace.adapter
    validate(adapter)
    checkpoint = policy(adapter) == call_checkpoint.POLICY_ID
    files = [ROOT / "logical_time.py", ROOT / "openclaw_deadlines.py", *sorted(path for path in RUNTIME.iterdir() if path.suffix in {".py", ".c", ".cjs", ".mjs"})]
    files.append(Path(native_audit.__file__))
    if checkpoint:
        files.extend([ROOT / "call_checkpoint.py", ROOT / "checkpoint_monitor.py"])
        if adapter.name == 'zeroclaw':
            files.extend([ROOT / 'zeroclaw_deadlines.py', RUNTIME / 'zeroclaw-deadline.rs'])
    if adapter.name == "openclaw":
        from . import openclaw_deadlines
        from ..configuration.config import OPENCLAW_MODULE_DIR
        files += openclaw_deadlines.sources(Path(OPENCLAW_MODULE_DIR), checkpoint=checkpoint)
    digest = hashlib.sha256(policy(adapter).encode() + b"".join(p.name.encode() + p.read_bytes() for p in files)).hexdigest()
    bundle = ROOT.parent.parent.parent / ".cache" / "deadline-runtime" / digest
    bundle.mkdir(parents=True, exist_ok=True)
    # The bundle is derived, isolated build output, never the installed harness.
    sources = [(path, path.name) for path in RUNTIME.iterdir() if path.suffix in {".py", ".cjs", ".mjs"}]
    sources.append((ROOT / "logical_time.py", "benchmark_logical_time.py"))
    sources.append((Path(native_audit.__file__), "native_audit.py"))
    for path, name in sources:
        destination = bundle / name
        if not destination.exists():
            temporary = bundle / f"{name}.{uuid.uuid4().hex}.tmp"
            shutil.copyfile(path, temporary)
            temporary.replace(destination)
    audit_node = bundle / "native-audit.cjs"
    if not audit_node.exists():
        temporary = bundle / f"native-audit.{uuid.uuid4().hex}.tmp"
        temporary.write_text(native_audit.NODE_SOURCE)
        temporary.replace(audit_node)
    library = bundle / "timeout_deadline.so"
    if not library.exists():
        temporary = bundle / f"timeout_deadline.{uuid.uuid4().hex}.so"
        subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-o", str(temporary), str(RUNTIME / "timeout_deadline.c"),
                        "-ldl", "-pthread", "-lm"], check=True, capture_output=True, text=True)
        temporary.replace(library)
    # Check the exact installed source before spending model budget. The native
    # import loader applies the same AST transformation to the read-only source.
    sys.modules.setdefault("benchmark_logical_time", logical_time)
    spec = importlib.util.spec_from_file_location("_deadline_native_check", RUNTIME / "native_deadlines.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    native_manifest = None
    if adapter.name == "openclaw":
        native_manifest = openclaw_deadlines.build(Path(OPENCLAW_MODULE_DIR), bundle, checkpoint=checkpoint)
        source = Path(OPENCLAW_MODULE_DIR) / "package.json"
        name = "OpenClaw Node watchdog overlays"
    elif adapter.name == 'zeroclaw':
        from . import zeroclaw_deadlines
        _, native_manifest = zeroclaw_deadlines.prepared()
        source = zeroclaw_deadlines.SOURCE / zeroclaw_deadlines.SHELL
        name = 'ZeroClaw Rust shell cancellation deadline'
    elif adapter.name == "generic":
        source = adapter.runtime_repo / "ga.py"
        name = "ga"
    else:
        site = next((adapter.runtime_env / "lib").glob("python*/site-packages"))
        name = ("nanobot.agent.tools.shell" if adapter.name == "nanobot" else "tools.environments.base")
        source = site / (name.replace(".", "/") + ".py")
    if adapter.name not in {'openclaw', 'zeroclaw'}:
        if checkpoint:
            native_spec = importlib.util.spec_from_file_location('_python_checkpoint_native_check', RUNTIME / 'python_native_checkpoints.py')
            native_module = importlib.util.module_from_spec(native_spec)
            native_spec.loader.exec_module(native_module)
            source_root = adapter.runtime_repo if adapter.name == 'generic' else site
            native_manifest = {'sources': {}, 'physical_clocks_modified': False}
            for target in sorted(native_module.TARGETS[adapter.name]):
                path = source_root / (target.replace('.', '/') + '.py')
                native_module.transform(path.read_text(), target, str(path))
                native_manifest['sources'][target] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            module.transform(source.read_text(), name, str(source))
    attempt_root = adapter.state_isolation_spec(workspace.instance_id).get("attempt_root")
    state_root = (Path(attempt_root) if attempt_root else
                  workspace.artifact_dir / "runtime" if workspace.artifact_dir else
                  workspace._gateway_control_dir / "native-time")
    directory = state_root / "logical-deadlines"
    evidence = workspace.artifact_dir / "gateway" / ("call_checkpoints.jsonl" if checkpoint else "logical_time.jsonl") if workspace.artifact_dir else None
    broker_type = call_checkpoint.CheckpointBroker if checkpoint else logical_time.DeadlineBroker
    workspace._deadline_broker = broker_type(directory, evidence)
    workspace._native_audit_collector = native_audit.Collector(directory, workspace.artifact_dir / 'native_audit') if workspace.artifact_dir else None
    workspace._deadline_bundle = bundle
    workspace._deadline_directory = directory
    if workspace.artifact_dir:
        write_json(workspace.artifact_dir / "logical_deadline_manifest.json", {
            "policy": policy(adapter), "harness": adapter.name,
            "implementation_revision": call_checkpoint.IMPLEMENTATION_REVISION if checkpoint else None,
            "bundle_source_sha256": digest,
            "native_source": str(source), "native_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "timer_driver_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
            "physical_clocks_modified": False,
            "checkpoint_scope": "uncommitted external call; native continuation retained" if checkpoint else None,
            "node_stream_event_ipc": False if checkpoint else True,
            "native_overlays": native_manifest,
            "coverage": ([name, "GNU timeout POSIX timer"] +
                         (native_manifest['coverage'] if adapter.name == 'zeroclaw' else
                          ["Python gateway socket reads", "httpcore AnyIO reads"])) +
                        (["OpenClaw LLM idle watchdog", "OpenClaw run/foreground exec deadlines",
                          "OpenClaw fetch and OpenAI SDK abort deadlines"] if adapter.name == 'openclaw' else []),
            "limitations": ["arbitrary user timers",
                             "transparent recovery after concurrent native progress" if checkpoint else "parallel/background observational equivalence",
                             "post-commit stream recovery"] +
                           (["unlisted provider-specific SDK watchdogs", "local-provider startup guards",
                             "physical timing metadata and cleanup timers"] if adapter.name == 'openclaw' else []),
        })
    args = ["-v", f"{directory}:{logical_time.CONTAINER_DIR}:ro",
            "-v", f"{bundle}:{logical_time.RUNTIME_DIR}:ro",
            "-e", f"BENCHMARK_DEADLINE_DIR={logical_time.CONTAINER_DIR}",
            "-e", f"BENCHMARK_DEADLINE_HARNESS={adapter.name}",
            "-e", f"PYTHONPATH={logical_time.RUNTIME_DIR}",
            "-e", f"LD_PRELOAD={logical_time.RUNTIME_DIR}/timeout_deadline.so"]
    if adapter.name == "openclaw":
        args.extend(["-e", f"NODE_OPTIONS=--import={logical_time.RUNTIME_DIR}/node-bootstrap.mjs"])
    if checkpoint:
        args.extend(["-e", f"BENCHMARK_EXTERNAL_CALL_TIMING={call_checkpoint.POLICY_ID}"])
    return args


def monitor(workspace, clock, stop):
    """One acknowledged settlement owner; reject overlapping committed streams.

All arithmetic is host-owned. Container leases only decide native cancellation;
they cannot grant extra time, change a retry policy, or deliver an API result.
"""
    if isinstance(workspace._deadline_broker, call_checkpoint.CheckpointBroker):
        from .checkpoint_monitor import monitor as checkpoint_monitor
        return checkpoint_monitor(workspace, clock, stop)
    broker = workspace._deadline_broker
    checkpoint = isinstance(broker, call_checkpoint.CheckpointBroker)
    broker.attach(clock)
    directory = workspace._gateway_control_dir
    paths = [directory / "model-timing.json"]
    if workspace._solver_control_monitor:
        paths.append(workspace._solver_control_monitor.path)
    paused = False
    owner = None
    settled = None
    release_started = None
    completed = set()
    last_liveness_check = 0.0

    def docker(action):
        result = subprocess.run(["docker", action, workspace.container_name],
                                capture_output=True, timeout=5)
        if result.returncode:
            raise RuntimeError(f"logical deadline container {action} failed")

    def ack(path, state, status):
        value = {"call_id": state["call_id"], "status": status}
        if settled is not None:
            value["charged_seconds"] = settled["charged_seconds"]
        if read_json(path.with_suffix(".ack.json")) != value:
            write_json(path.with_suffix(".ack.json"), value)

    try:
        # Native cancellation can make the harness process exit before the
        # gateway sees the acknowledgement. Finish that delivery barrier even
        # when the orchestrator concurrently asks the monitor to stop.
        while not stop.is_set() or release_started is not None:
            model = workspace._read_gateway_control() or {}
            if checkpoint and broker.failure:
                raise RuntimeError(broker.failure)
            now = time.monotonic()
            if model.get("active_committed_streams", 0) and now - last_liveness_check >= 0.25:
                last_liveness_check = now
                result = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", workspace.gateway_name],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode or result.stdout.strip() != "true":
                    workspace._gateway_terminal_error = {"reason": "post_commit_stream_failure", "stream_error_type": "GatewaySidecarExit"}
                    docker("kill")
                    return
            if model.get("terminal_infra_error"):
                workspace._gateway_terminal_error = model["terminal_infra_error"]
                docker("kill")
                return
            if model.get("action_step_limit_reached"):
                workspace._gateway_action_step_limit_reached = True
                docker("kill")
                return
            active = []
            for path in paths:
                state = read_json(path) or {}
                if state.get("phase") == "invalid":
                    workspace._gateway_terminal_error = state["terminal_infra_error"]
                    docker("kill")
                    return
                if state.get("phase") in {"running", "settle", "ready"} and state.get("call_id") not in completed:
                    active.append((path, state))
            if len(active) > 1 or (active and model.get("active_committed_streams", 0)):
                workspace._gateway_terminal_error = {"reason": "external_call_stream_overlap", "source": call_checkpoint.POLICY_ID if checkpoint else logical_time.POLICY_ID}
                docker("kill")
                return
            if not active:
                if owner is not None:
                    raise RuntimeError("active logical call control disappeared")
                stop.wait(0.02)
                continue
            path, state = active[0]
            key = state["call_id"]
            if time.time() - state.get("pause_started_unix", time.time()) > 600:
                raise RuntimeError("logical deadline recovery watchdog")
            if owner is None:
                owner = key
                if checkpoint:
                    broker.freeze(key)
                else:
                    broker.freeze()
                if not checkpoint:
                    docker("pause")
                    paused = True
            if owner != key:
                raise RuntimeError("logical deadline lease owner changed")
            if state["phase"] == "running":
                ack(path, state, "paused")
            elif state["phase"] == "settle":
                if checkpoint:
                    settled = broker.settle(key, float(state["charged_seconds"]),
                                            rollback=bool(state.get("rollback_count")))
                else:
                    settled = broker.settle(key, float(state["charged_seconds"]))
                if settled["benchmark_due"]:
                    ack(path, state, "deadline")
                    workspace.enforce_agent_deadline()
                    return
                ack(path, state, "charged")
            elif state["phase"] == "ready":
                if settled is None:
                    raise RuntimeError("release without logical settlement")
                if paused:
                    # Native watchdogs must run while the caller still cannot
                    # consume the candidate result. Physical clocks are intact.
                    docker("unpause")
                    paused = False
                    release_started = time.monotonic()
                elif release_started is None:
                    release_started = time.monotonic()
                due = settled["native_due"]
                if due and broker.pending(due):
                    if time.monotonic() - release_started > 10:
                        raise RuntimeError("native timeout cleanup did not acknowledge")
                elif due and time.monotonic() - release_started < 0.15:
                    pass  # Native async exception handlers get a short cleanup turn.
                else:
                    broker.resume()
                    ack(path, state, "native_deadline" if due else "released")
                    if due:
                        # The native process can exit before the sidecar has
                        # durably recorded cancellation. Preserve that evidence
                        # before workspace cleanup is allowed to kill sidecars.
                        evidence_deadline = time.monotonic() + 2
                        while True:
                            final = read_json(path) or {}
                            if final.get("phase") == "native_done" or final.get("call_id") != key:
                                break
                            if time.monotonic() >= evidence_deadline:
                                raise RuntimeError("native cancellation evidence not acknowledged")
                            time.sleep(0.01)
                    completed.add(key)
                    owner = settled = release_started = None
            stop.wait(0.02)
    except Exception:
        logging.getLogger(__name__).exception("Logical deadline controller failed")
        workspace._gateway_monitor_error = "external_call_control_failed"
        clock.cancel("external_call_control_failed")
        try:
            docker("kill")
        except Exception:
            pass
    finally:
        try:
            if paused:
                subprocess.run(["docker", "unpause", workspace.container_name], capture_output=True, timeout=5)
        finally:
            broker.resume()
