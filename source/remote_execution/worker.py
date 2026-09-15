"""Loopback-only control service and durable, independently owned job processes.

The service never implements a harness loop, retries a model, edits a completion,
or kills a Docker resource. Those remain execution-node-local benchmark duties.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import platform
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import bundle
from . import checkpoints
from .protocol import (CHUNK_SIZE, TERMINAL, canonical, digest, exact, file_hash,
                       private_json, read_json, safe_path, secret_file, sha256,
                       validate_job, validate_node)
from .store import Store, group_alive, lock, process_identity, seal_artifacts


class Node:
    def __init__(self, config):
        self.config = validate_node(config)
        self.store = Store(Path(config["state_dir"]))
        self.token = secret_file(Path(config["token_file"]))
        self.children = {}

    def submit(self, spec):
        validate_job(spec)
        if spec["kind"] == "probe" and not self.config.get("allow_probe", False):
            raise ValueError("Simulation jobs are disabled on this node")
        release = self.store.root / "releases" / spec["release_id"]
        manifest = read_json(release / "manifest.json")
        if digest(manifest) != spec["release_id"]:
            raise ValueError("Release is not installed with the requested identity")
        if spec["kind"] in {"agent_cell", "api_cell"}:
            p = spec["parameters"]
            keys = ("benchmark_profile", "operational_config") if spec["kind"] == "agent_cell" else ("operational_config",)
            for key in keys:
                if p[key] not in manifest["files"]:
                    raise ValueError("Job configuration must be part of the frozen release")
            for name in p["services"]:
                if name not in self.config.get("services", {}):
                    raise ValueError("Job requires an unconfigured node service")
        return self.store.submit(spec)

    def tick(self):
        # Reap direct children even though they also publish their own outcome.
        for job_id, child in list(self.children.items()):
            if child.poll() is not None:
                self.children.pop(job_id)
                row = self.store.get(job_id)
                if row["status"] in {"launching", "running"}:
                    self.store.transition(job_id, "needs_attention", {"reason": "job_process_exit_without_terminal_record"})
        rows = self.store.list()
        for row in rows:
            if row["status"] not in {"launching", "running"} or row["id"] in self.children:
                continue
            try:
                with lock(self.store.directory(row["id"]) / "owner.lock"):
                    # A new process may not have acquired its lock yet. Never
                    # duplicate uncertain dispatches after a supervisor crash.
                    if time.time() - row["updated"] > 30 and not group_alive(self.store.directory(row["id"])):
                        self.store.transition(row["id"], "needs_attention", {"reason": "owner_missing_after_worker_restart"},
                                              expected={"launching", "running"})
            except BlockingIOError:
                pass  # A detached owner is alive; adopt it without relaunching.
        active = sum(row["status"] in {"launching", "running"} for row in self.store.list())
        if any(row["status"] == "needs_attention" and group_alive(self.store.directory(row["id"]))
               for row in self.store.list()):
            return  # Orphaned live work still consumes node capacity.
        for row in self.store.list():
            if active >= self.config.get("max_jobs", 1):
                break
            if row["status"] != "queued":
                continue
            job_id = row["id"]; directory = self.store.directory(job_id)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            config_path = directory / "node.json"
            if config_path.exists():
                if read_json(config_path) != self.config:
                    self.store.transition(job_id, "needs_attention", {"reason": "node_configuration_drift"}, expected={"queued"})
                    continue
            else:
                private_json(config_path, self.config, replace=False)
            self.store.transition(job_id, "launching", expected={"queued"})
            env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "LANG": "C.UTF-8", "TZ": "UTC"}
            logs = directory / "logs"; logs.mkdir(exist_ok=True, mode=0o700)
            try:
                with (logs / f"owner-{row['generation']}.log").open("xb") as output:
                    child = subprocess.Popen([sys.executable, "-B", "-m", "remote_execution.worker",
                        "--config", str(config_path), "--execute", job_id], env=env,
                        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                        start_new_session=True, close_fds=True)
                self.children[job_id] = child
                active += 1
            except OSError as exc:
                self.store.transition(job_id, "needs_attention", {"reason": "dispatch_failed", "error_type": type(exc).__name__})

    def manifest(self, job_id, generation):
        row = self.store.get(job_id)
        if generation < 1 or generation > row["generation"]:
            raise ValueError("Unknown artifact generation")
        return read_json(self.store.directory(job_id) / f"artifacts-{generation}.json")

    def progress(self, job_id):
        """Read materialized validity only; never mutate the benchmark's ledger."""
        row = self.store.get(job_id)
        root = self.store.directory(job_id) / "output"
        cells = []; warnings = []
        if row["spec"]["kind"] == "api_cell" and root.is_dir() and not root.is_symlink():
            from batch_utils import format_problem_name
            from .api import case_directory, selected_case
            selected = 0
            p = row["spec"]["parameters"]
            for number in p["indices"]:
                problem = format_problem_name(number)
                path = case_directory(root, p, problem)
                try:
                    safe_path(root, path.relative_to(root).as_posix())
                    # Status is a lightweight terminal-record snapshot. Resume
                    # and evaluation verify complete trace/artifact hashes.
                    selected += selected_case(path, verify_files=False) is not None
                except (OSError, ValueError, KeyError, TypeError):
                    warnings.append(problem)
            cells.append({"path": "llm-as-formalizer-api", "selected_valid_attempts": selected,
                          "known_unfilled_attempts": len(p["indices"]) - selected})
        if root.is_dir() and not root.is_symlink():
            for path in sorted(root.rglob("execution_validity.json")):
                name = path.relative_to(root).as_posix()
                try:
                    safe_path(root, name)
                    if path.stat().st_size > 32 * 1024**2:
                        raise ValueError("Validity snapshot too large")
                    state = read_json(path)
                    selected = missing = 0
                    for problem in state.get("problems", {}).values():
                        for attempt in problem.get("attempts", {}).values():
                            if attempt.get("selected_execution") is not None:
                                selected += 1
                            else:
                                missing += 1
                    cells.append({"path": name, "selected_valid_attempts": selected,
                                  "known_unfilled_attempts": missing})
                except (OSError, ValueError, TypeError, AttributeError):
                    warnings.append(name)
        units = checkpoints.catalog(self.store.directory(job_id))["checkpoints"]
        ack_root = self.store.directory(job_id) / "checkpoint-acks"
        health_path = self.store.directory(job_id) / "checkpoint-status.json"
        return {"job_id": job_id, "status": row["status"], "generation": row["generation"],
                "cells": cells, "unreadable": warnings,
                "sealed_execution_checkpoints": sum(u["kind"] == "execution" for u in units),
                "acknowledged_checkpoints": sum((ack_root / (u["checkpoint_id"] + ".json")).is_file() for u in units),
                "checkpoint_health": read_json(health_path) if health_path.is_file() else {"status": "not_started"},
                "note": "Read-only partial validity snapshots; not a correctness score or final denominator"}

    def read_artifact(self, job_id, generation, name, offset):
        manifest = self.manifest(job_id, generation)
        if name not in manifest["files"]:
            raise ValueError("File is not in the sealed artifact manifest")
        row = manifest["files"][name]
        if not 0 <= offset <= row["size"]:
            raise ValueError("Invalid artifact offset")
        path = safe_path(self.store.directory(job_id) / "snapshots" / str(generation), name)
        with path.open("rb") as stream:
            stream.seek(offset)
            return stream.read(CHUNK_SIZE)


def execute(config, job_id):
    """Owner survives control-service/SSH loss. A reboot requires reconciliation."""
    os.umask(0o077)
    store = Store(Path(config["state_dir"]))
    directory = store.directory(job_id)
    with lock(directory / "owner.lock") as owner_lock:
        row = store.get(job_id)
        if row["status"] != "launching":
            raise ValueError("No matching launch reservation")
        store.transition(job_id, "running", {"owner_pid": os.getpid()}, expected={"launching"})
        generation = row["generation"]
        private_json(directory / "process-owner.json", process_identity())
        evidence = directory / "evidence"; evidence.mkdir(exist_ok=True, mode=0o700)
        status = "failed"; detail = {}; phase = "verify_release"
        try:
            spec = row["spec"]
            release = store.root / "releases" / spec["release_id"]
            if digest(bundle.verify(release)) != spec["release_id"]:
                raise ValueError("Release drift")
            private_json(evidence / f"request-{generation}.json", spec, replace=False)
            private_json(evidence / f"node-{generation}.json", {
                "node_id": config["node_id"], "node_config_sha256": digest(config),
                "platform": platform.platform(), "machine": platform.machine(),
                "cpu_count": os.cpu_count(), "python": config["python"],
                "release_id": spec["release_id"], "transport_timing": "outside_agent_execution",
            }, replace=False)
            if spec["kind"] == "probe":
                if not config.get("allow_probe", False):
                    raise ValueError("Simulation disabled")
                time.sleep(spec["parameters"].get("delay_seconds", 0))
                private_json(directory / "output" / "probe.json", {
                    "simulation_only": True, "not_a_benchmark_result": True,
                    "job_id": job_id, "release_id": spec["release_id"],
                    "generation": generation}, replace=False)
                status = "completed"
            else:
                phase = "bind_node_runtime"
                bundle.bind_runtime(release, config.get("bindings", {}))
                workspace = release / "workspace"
                entry = safe_path(workspace, "source/remote_execution/benchmark.py")
                if "source/remote_execution/benchmark.py" not in read_json(release / "manifest.json")["files"]:
                    raise ValueError("Release lacks benchmark entrypoint")
                home = directory / "home"; home.mkdir(exist_ok=True, mode=0o700)
                env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home),
                       "PYTHONPATH": str(workspace / "source"), "PYTHONDONTWRITEBYTECODE": "1",
                       "PYTHONUNBUFFERED": "1", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"}
                with (directory / "logs" / f"benchmark-{generation}.log").open("xb") as output:
                    phase = "run_benchmark_pipeline"
                    with subprocess.Popen([config["python"], "-B", str(entry),
                        "--job", str(evidence / f"request-{generation}.json"), "--node", str(directory / "node.json"),
                        "--directory", str(directory), "--generation", str(generation)],
                        cwd=workspace, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                        pass_fds=(owner_lock.fileno(),)) as process:
                        while True:
                            try:
                                code = process.wait(timeout=config.get("checkpoint_interval_seconds", 2))
                            except subprocess.TimeoutExpired:
                                code = None
                            try:
                                checkpoints.publish_ready(directory, spec, config, generation)
                                private_json(directory / "checkpoint-status.json", {"status": "ok", "generation": generation})
                            except (OSError, ValueError, TypeError, KeyError) as exc:
                                # Transport trouble must not invalidate or resample a
                                # measured agent. Retry the SAME evidence next poll.
                                private_json(directory / "checkpoint-status.json", {
                                    "status": "retrying", "generation": generation, "error_type": type(exc).__name__})
                            if code is not None:
                                break
                detail = {"returncode": code}
                status = "completed" if code == 0 else "failed"
                # Snapshot/resume needs the original node paths; never rewrite
                # completion records during transfer to make them look local.
                private_json(evidence / f"path-map-{generation}.json", {
                    "remote_workspace": str(workspace), "remote_output": str(directory / "output"),
                    "local_output_relative": "output", "read_only_mirror": True}, replace=False)
        except Exception as exc:
            # Do not serialize arbitrary exception text (provider secrets etc.).
            detail = {"reason": "node_execution_error", "phase": phase, "error_type": type(exc).__name__}
        try:
            manifest = seal_artifacts(directory, generation)
            detail["artifacts_sha256"] = digest(manifest)
            detail["artifact_files"] = len(manifest["files"])
            health_path = directory / "checkpoint-status.json"
            if health_path.exists() and read_json(health_path).get("status") != "ok":
                status = "needs_attention"
                detail["reason"] = "execution_checkpoint_sealing_failed"
        except Exception as exc:
            status = "needs_attention"
            detail = {"reason": "artifact_sealing_failed", "error_type": type(exc).__name__}
        store.transition(job_id, status, detail, expected={"running"})


def make_server(node, port=0):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BenchmarkExecutionNode/1"

        def log_message(self, *_):
            pass  # No request headers, tokens, payloads or query paths in logs.

        def response(self, status, value, *, binary=False):
            payload = value if binary else canonical(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream" if binary else "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def dispatch(self):
            self.connection.settimeout(30)
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + node.token):
                self.response(401, {"error": "unauthorized"}); return
            route = urlsplit(self.path)
            path = route.path.strip("/").split("/")
            query = parse_qs(route.query)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= CHUNK_SIZE:
                raise ValueError("Request exceeds chunk limit")
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked request bodies are not supported")
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request")
            if path == ["health"] and self.command == "GET":
                return self.response(200, {"schema_version": 1, "node_id": node.config["node_id"], "status": "ok"})
            if path == ["jobs"]:
                if self.command == "GET":
                    return self.response(200, node.store.list())
                if self.command == "POST":
                    return self.response(200, node.submit(json.loads(body)))
            if len(path) >= 2 and path[0] == "jobs":
                job_id = path[1]
                if len(path) == 2 and self.command == "GET":
                    return self.response(200, node.store.get(job_id))
                if len(path) == 3 and path[2] == "events" and self.command == "GET":
                    return self.response(200, node.store.events(job_id, int(query.get("after", [0])[0])))
                if len(path) == 3 and path[2] == "progress" and self.command == "GET":
                    return self.response(200, node.progress(job_id))
                if len(path) == 3 and path[2] == "checkpoints" and self.command == "GET":
                    node.store.get(job_id)
                    directory = node.store.directory(job_id)
                    index = checkpoints.catalog(directory)
                    row = node.store.get(job_id)
                    config_path = directory / "node.json"
                    index["origin"] = {"spec": row["spec"], "generation": row["generation"],
                        "node_config": read_json(config_path) if config_path.is_file() else node.config,
                        "remote_job_root": str(directory)}
                    index["acknowledged"] = [u["checkpoint_id"] for u in index["checkpoints"]
                        if (directory / "checkpoint-acks" / (u["checkpoint_id"] + ".json")).is_file()]
                    return self.response(200, index)
                if len(path) == 3 and path[2] == "checkpoint" and self.command == "GET":
                    node.store.get(job_id)
                    return self.response(200, checkpoints.checkpoint_manifest(node.store.directory(job_id), query["id"][0]))
                if len(path) == 3 and path[2] == "checkpoint-ack" and self.command == "POST":
                    node.store.get(job_id)
                    value = json.loads(body)
                    return self.response(200, checkpoints.acknowledge(node.store.directory(job_id), value["checkpoint_id"], value))
                if len(path) == 3 and path[2] == "checkpoint-file" and self.command == "GET":
                    node.store.get(job_id)
                    checkpoint_id = sha256(query["id"][0])
                    directory = node.store.directory(job_id)
                    manifest = checkpoints.checkpoint_manifest(directory, checkpoint_id)
                    name = query["path"][0]; offset = int(query.get("offset", [0])[0])
                    if name not in manifest["files"] or not 0 <= offset <= manifest["files"][name]["size"]:
                        raise ValueError("Unknown checkpoint member/offset")
                    target = safe_path(directory / "checkpoints" / checkpoint_id, name)
                    with target.open("rb") as stream:
                        stream.seek(offset)
                        return self.response(200, stream.read(CHUNK_SIZE), binary=True)
                if len(path) == 3 and path[2] == "resume" and self.command == "POST":
                    value = json.loads(body); exact(value, {"reason", "generation"})
                    if type(value["generation"]) is not int:
                        raise ValueError("generation must be an integer")
                    return self.response(200, node.store.resume(job_id, value["reason"], value["generation"]))
                if len(path) == 3 and path[2] == "artifacts" and self.command == "GET":
                    return self.response(200, node.manifest(job_id, int(query["generation"][0])))
                if len(path) == 3 and path[2] == "file" and self.command == "GET":
                    return self.response(200, node.read_artifact(job_id, int(query["generation"][0]),
                        query["path"][0], int(query.get("offset", [0])[0])), binary=True)
            if len(path) == 2 and path[0] == "uploads":
                archive_hash = sha256(path[1])
                upload = node.store.root / "uploads" / (archive_hash + ".tar.gz")
                with lock(upload.with_suffix(".lock"), blocking=True):
                    size = upload.stat().st_size if upload.exists() else 0
                    if self.command == "PUT":
                        offset = int(query["offset"][0])
                        if size != offset or not body:
                            raise ValueError("Upload offset mismatch/empty chunk; query and resume")
                        if size + len(body) > node.config.get("max_bundle_bytes", 2 * 1024**3):
                            raise ValueError("Upload exceeds node limit")
                        with upload.open("ab") as output:
                            output.write(body); output.flush(); os.fsync(output.fileno())
                        size += len(body)
                    elif self.command != "GET":
                        raise ValueError("Unsupported upload operation")
                    return self.response(200, {"offset": size})
            if path == ["releases"] and self.command == "POST":
                value = json.loads(body); exact(value, {"archive_sha256", "release_id"})
                archive_hash = sha256(value["archive_sha256"])
                archive = node.store.root / "uploads" / (archive_hash + ".tar.gz")
                with lock(archive.with_suffix(".lock"), blocking=True):
                    if file_hash(archive) != archive_hash:
                        raise ValueError("Archive transfer checksum mismatch")
                    destination = bundle.install(archive, node.store.root / "releases", value["release_id"],
                        max_bytes=node.config.get("max_bundle_bytes", 2 * 1024**3))
                return self.response(200, {"release_id": destination.name})
            self.response(404, {"error": "unknown_route"})

        def handle_request(self):
            try:
                self.dispatch()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass  # Client loss never cancels a queued/running job.
            except (ValueError, KeyError, OSError, TypeError) as exc:
                try:
                    self.response(400, {"error": type(exc).__name__})
                except OSError:
                    pass

        do_GET = do_POST = do_PUT = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--execute", help=argparse.SUPPRESS)
    args = parser.parse_args()
    config = validate_node(read_json(args.config))
    if args.execute:
        execute(config, args.execute)
        return
    os.umask(0o077)
    node = Node(config)
    with lock(node.store.root / "worker.lock"):
        server = make_server(node, args.port)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        print(json.dumps({"node_id": config["node_id"], "port": server.server_port}), flush=True)
        try:
            while True:
                node.tick()
                time.sleep(0.5)
        finally:
            server.shutdown(); server.server_close()


if __name__ == "__main__":
    main()
