#!/usr/bin/env python3
"""Small planning.domains-compatible HTTP front-end over local Planutils.

The server owns a fixed pool of long-lived Docker workers.  Each worker has an
independent cgroup memory/CPU/PID limit and executes at most one task at a time.
No Flask, Celery, Redis, MySQL, or Flower processes are required.
"""

from __future__ import annotations

import argparse
import atexit
import ipaddress
import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
RUNNER_CONTAINER_PATH = "/opt/pddl-local-solver/planutils_runner.py"
DEFAULT_IMAGE = "pddl-local-solver:planutils-v1"
DEFAULT_ALLOWED_SOLVERS = ("dual-bfws-ffparser",)
WORKER_SECURITY_MODES = frozenset({"restricted", "userns", "privileged"})
TASK_PATH = re.compile(r"^/check/([0-9a-f]{32})/?$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ServerConfig:
    listen_host: str = "0.0.0.0"
    port: int = 8769
    workers: int = 1
    queue_limit: int = 128
    memory: str = "4096m"
    memory_swap: str = "4096m"
    cpus: float = 1.0
    pids_limit: int = 256
    timeout_seconds: float = 90.0
    image: str = DEFAULT_IMAGE
    worker_security: str = "privileged"
    task_retention: int = 10000
    allowed_solvers: tuple[str, ...] = DEFAULT_ALLOWED_SOLVERS
    allowed_client_cidrs: tuple[str, ...] = (
        "127.0.0.0/8",
        "172.16.0.0/12",
        "::1/128",
    )

    def validate(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be in [0, 65535]")
        for name in ("workers", "queue_limit", "pids_limit", "task_retention"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.cpus <= 0 or self.timeout_seconds <= 0:
            raise ValueError("cpus and timeout_seconds must be positive")
        if not self.image:
            raise ValueError("image must be non-empty")
        if not self.allowed_solvers:
            raise ValueError("at least one solver package must be allowed")
        if self.worker_security not in WORKER_SECURITY_MODES:
            raise ValueError(
                "worker_security must be one of "
                + ", ".join(sorted(WORKER_SECURITY_MODES))
            )
        for cidr in self.allowed_client_cidrs:
            ipaddress.ip_network(cidr, strict=False)


class DockerWorkerPool:
    """Fixed-size pool of one-task-at-a-time Planutils containers."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.owner = f"{os.getpid()}-{uuid.uuid4().hex[:10]}"
        self._available: queue.Queue[str] = queue.Queue()
        self._names: list[str] = []
        self._lock = threading.Lock()
        self._closed = False
        self.image_id = ""

    @staticmethod
    def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(command, capture_output=True, text=True, **kwargs)

    def start(self) -> None:
        self.config.validate()
        inspected = self._run(
            ["docker", "image", "inspect", self.config.image, "--format", "{{.Id}}"]
        )
        if inspected.returncode != 0:
            raise RuntimeError(
                f"local solver image {self.config.image!r} is unavailable; build it "
                f"with: docker build -t {self.config.image} {HERE}\n"
                f"docker: {inspected.stderr.strip()}"
            )
        self.image_id = inspected.stdout.strip()
        try:
            for index in range(1, self.config.workers + 1):
                name = f"pddl-local-solver-{self.owner}-w{index:02d}"
                self._start_worker(name)
                self._names.append(name)
                self._verify_worker(name)
                self._available.put(name)
        except Exception:
            self.close()
            raise

    def _start_worker(self, name: str) -> None:
        command = [
            "docker", "run", "-d", "--pull", "never",
            "--name", name,
            "--label", f"pddl.local-solver.owner={self.owner}",
            "--network", "none",
            "--memory", self.config.memory,
            "--memory-swap", self.config.memory_swap,
            "--cpus", str(self.config.cpus),
            "--pids-limit", str(self.config.pids_limit),
        ]
        if self.config.worker_security == "restricted":
            command.extend(["--security-opt", "no-new-privileges"])
        elif self.config.worker_security == "userns":
            # Planutils' SIF packages use an unprivileged nested user namespace.
            # Docker's default seccomp profile blocks that clone flag. Keep all
            # capabilities at Docker defaults, retain no-new-privileges, and
            # open only the syscall filter rather than granting --privileged.
            command.extend(
                [
                    "--security-opt", "no-new-privileges",
                    "--security-opt", "seccomp=unconfined",
                ]
            )
        elif self.config.worker_security == "privileged":
            command.append("--privileged")
        command.extend([self.config.image, "tail", "-f", "/dev/null"])
        result = self._run(command)
        if result.returncode != 0:
            raise RuntimeError(
                f"failed to start local solver worker {name}: {result.stderr.strip()}"
            )

    def _inspect(self, name: str) -> dict[str, Any]:
        result = self._run(["docker", "inspect", name])
        if result.returncode != 0:
            return {"available": False, "error": result.stderr.strip()}
        try:
            value = json.loads(result.stdout)[0]
        except (json.JSONDecodeError, IndexError, TypeError):
            return {"available": False, "error": "docker inspect returned invalid JSON"}
        state = value.get("State", {})
        return {
            "available": True,
            "running": bool(state.get("Running")),
            "oom_killed": bool(state.get("OOMKilled")),
            "exit_code": state.get("ExitCode"),
            "status": state.get("Status"),
            "error": state.get("Error", ""),
        }

    def _verify_worker(self, name: str) -> None:
        result = self._run(
            [
                "docker", "exec", name,
                "python3", RUNNER_CONTAINER_PATH,
                "--describe",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"local solver worker {name} failed its package check: "
                f"{result.stderr.strip()}"
            )
        try:
            description = json.loads(result.stdout)
            installed = set(description["installed_solver_packages"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError(
                f"local solver worker {name} returned an invalid package check"
            ) from exc
        missing = sorted(set(self.config.allowed_solvers) - installed)
        if missing:
            raise RuntimeError(
                f"local solver image lacks allowed package(s): {', '.join(missing)}"
            )

    def _replace_worker(self, name: str) -> None:
        self._run(["docker", "rm", "-f", "-v", name])
        self._start_worker(name)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        name = self._available.get()
        started = time.monotonic()
        replace = False
        try:
            command = [
                "docker", "exec", "-i", name,
                "python3", RUNNER_CONTAINER_PATH,
            ]
            payload = dict(request)
            payload["timeout_seconds"] = self.config.timeout_seconds
            try:
                result = subprocess.run(
                    command,
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds + 15,
                )
            except subprocess.TimeoutExpired as exc:
                inspect = self._inspect(name)
                replace = True
                return {
                    "ok": False,
                    "error": {
                        "type": "worker_control_timeout",
                        "message": str(exc),
                    },
                    "worker": {**inspect, "name": name},
                }
            inspect = self._inspect(name)
            if not inspect.get("running", False):
                replace = True
            try:
                response = json.loads(result.stdout) if result.stdout else {}
            except json.JSONDecodeError:
                response = {}
            if not isinstance(response, dict) or "ok" not in response:
                return {
                    "ok": False,
                    "error": {
                        "type": "worker_protocol_error",
                        "message": "worker did not return a valid JSON result",
                        "docker_exec_returncode": result.returncode,
                        "stderr": result.stderr[-4000:],
                    },
                    "worker": {**inspect, "name": name},
                }
            response["worker"] = {
                **inspect,
                "name": name,
                "duration_seconds": round(time.monotonic() - started, 6),
                "memory_limit": self.config.memory,
                "memory_swap_limit": self.config.memory_swap,
                "cpus": self.config.cpus,
            }
            return response
        finally:
            if replace and not self._closed:
                try:
                    self._replace_worker(name)
                except Exception:
                    # A failed replacement is observable on the next request; do
                    # not hide the current task's already-recorded result.
                    pass
            if not self._closed:
                self._available.put(name)

    def snapshot(self) -> dict[str, Any]:
        workers = {
            name: self._inspect(name)
            for name in list(self._names)
        }
        return {
            "owner": self.owner,
            "image": self.config.image,
            "image_id": self.image_id,
            "workers": len(self._names),
            "idle_workers": self._available.qsize(),
            "worker_status": workers,
            "resource_limits": {
                "memory": self.config.memory,
                "memory_swap": self.config.memory_swap,
                "cpus": self.config.cpus,
                "pids": self.config.pids_limit,
                "timeout_seconds": self.config.timeout_seconds,
                "worker_security": self.config.worker_security,
            },
        }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            names = list(self._names)
        for name in names:
            self._run(["docker", "rm", "-f", "-v", name])


@dataclass
class TaskRecord:
    task_id: str
    solver: str
    submitted_at: str
    domain_bytes: int
    problem_bytes: int
    future: Future


class LocalSolverState:
    def __init__(self, config: ServerConfig, pool: DockerWorkerPool):
        self.config = config
        self.pool = pool
        self.executor = ThreadPoolExecutor(
            max_workers=config.workers,
            thread_name_prefix="local-planutils",
        )
        self.capacity = threading.BoundedSemaphore(config.workers + config.queue_limit)
        self.tasks: dict[str, TaskRecord] = {}
        self.task_order: list[str] = []
        self.lock = threading.Lock()
        self.submitted = 0
        self.completed = 0
        self.succeeded = 0
        self.failed = 0

    def submit(self, solver: str, domain: str, problem: str) -> str | None:
        if not self.capacity.acquire(blocking=False):
            return None
        task_id = uuid.uuid4().hex

        def work() -> dict[str, Any]:
            try:
                return self.pool.execute(
                    {"solver": solver, "domain": domain, "problem": problem}
                )
            finally:
                self.capacity.release()

        future = self.executor.submit(work)
        record = TaskRecord(
            task_id=task_id,
            solver=solver,
            submitted_at=_now(),
            domain_bytes=len(domain.encode()),
            problem_bytes=len(problem.encode()),
            future=future,
        )
        with self.lock:
            self.tasks[task_id] = record
            self.task_order.append(task_id)
            self.submitted += 1
            while len(self.task_order) > self.config.task_retention:
                oldest = self.task_order[0]
                old_record = self.tasks.get(oldest)
                if old_record is not None and not old_record.future.done():
                    break
                self.task_order.pop(0)
                self.tasks.pop(oldest, None)

        def count(done: Future) -> None:
            try:
                value = done.result()
                ok = bool(value.get("ok"))
            except Exception:
                ok = False
            with self.lock:
                self.completed += 1
                self.succeeded += int(ok)
                self.failed += int(not ok)

        future.add_done_callback(count)
        return task_id

    def terminal_payload(self, task_id: str) -> tuple[int, dict[str, Any]]:
        with self.lock:
            record = self.tasks.get(task_id)
        if record is None:
            return 404, {"error": "unknown local solver task", "status": "NOT_FOUND"}
        if not record.future.done():
            return 200, {"status": "PENDING"}
        try:
            value = record.future.result()
        except Exception as exc:
            return 200, {
                "status": "failed",
                "error": "local solver worker raised an unexpected exception",
                "local_backend": {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        if value.get("ok") and isinstance(value.get("result"), dict):
            result = value["result"]
            result["local_worker"] = value.get("worker", {})
            return 200, {"status": "ok", "result": result}
        return 200, {
            "status": "failed",
            "error": "local solver worker failed",
            "local_backend": value,
        }

    def status(self) -> dict[str, Any]:
        with self.lock:
            pending = self.submitted - self.completed
            counters = {
                "submitted": self.submitted,
                "pending": pending,
                "completed": self.completed,
                "succeeded": self.succeeded,
                "failed": self.failed,
            }
        return {**counters, "pool": self.pool.snapshot()}

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


def make_handler(state: LocalSolverState):
    allowed_networks = tuple(
        ipaddress.ip_network(value, strict=False)
        for value in state.config.allowed_client_cidrs
    )

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _client_allowed(self) -> bool:
            try:
                address = ipaddress.ip_address(self.client_address[0])
            except ValueError:
                return False
            return any(address in network for network in allowed_networks)

        def _authorize(self) -> bool:
            if self._client_allowed():
                return True
            self._json({"error": "client address is not allowed"}, status=403)
            return False

        def do_GET(self):
            if not self._authorize():
                return
            path = urlsplit(self.path).path
            if path == "/__benchmark__/health":
                pool = state.pool.snapshot()
                healthy = bool(pool["workers"]) and all(
                    value.get("running", False)
                    for value in pool["worker_status"].values()
                )
                self._json(
                    {
                        "status": "ok" if healthy else "unavailable",
                        "backend": "local-planutils",
                        "config": {
                            **asdict(state.config),
                            "allowed_client_cidrs": list(
                                state.config.allowed_client_cidrs
                            ),
                            "allowed_solvers": list(state.config.allowed_solvers),
                        },
                        "pool": pool,
                    },
                    status=200 if healthy else 503,
                )
                return
            if path == "/__benchmark__/status":
                self._json(state.status())
                return
            match = TASK_PATH.fullmatch(path)
            if match:
                status, payload = state.terminal_payload(match.group(1))
                self._json(payload, status=status)
                return
            self._json({"error": f"unknown path {path}"}, status=404)

        def do_POST(self):
            if not self._authorize():
                return
            path = urlsplit(self.path).path
            match = TASK_PATH.fullmatch(path)
            if match:
                status, payload = state.terminal_payload(match.group(1))
                self._json(payload, status=status)
                return
            parts = [part for part in path.split("/") if part]
            if len(parts) != 3 or parts[0] != "package" or parts[2] != "solve":
                self._json({"error": f"unknown path {path}"}, status=404)
                return
            solver = parts[1]
            if solver not in state.config.allowed_solvers:
                self._json({"Error": f"unsupported local solver package: {solver}"}, status=404)
                return
            try:
                length = int(self.headers.get("content-length", "0") or 0)
            except ValueError:
                self._json({"error": "invalid content-length"}, status=400)
                return
            if length <= 0 or length > 16 * 1024 * 1024:
                self._json({"error": "request body must be 1 byte to 16 MiB"}, status=413)
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._json({"error": f"invalid JSON: {exc}"}, status=400)
                return
            if not isinstance(payload, dict):
                self._json({"error": "request body must be a JSON object"}, status=400)
                return
            domain = payload.get("domain")
            problem = payload.get("problem")
            if not isinstance(domain, str) or not isinstance(problem, str):
                self._json({"error": "domain and problem must be strings"}, status=400)
                return
            task_id = state.submit(solver, domain, problem)
            if task_id is None:
                self._json(
                    {
                        "error": "local solver queue is full",
                        "retryable": True,
                    },
                    status=503,
                )
                return
            self._json({"result": f"/check/{task_id}"})

        def _json(self, value: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, format, *args):
            return

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a lightweight planning.domains-compatible local solver."
    )
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--queue-limit", type=int, default=128)
    parser.add_argument("--memory", default="4096m")
    parser.add_argument("--memory-swap", default="4096m")
    parser.add_argument("--cpus", type=float, default=1.0)
    parser.add_argument("--pids-limit", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=90.0, dest="timeout_seconds")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--worker-security",
        choices=sorted(WORKER_SECURITY_MODES),
        default="privileged",
        help=(
            "worker container security mode; privileged matches the official "
            "planning-as-a-service worker and reliably supports Planutils SIFs"
        ),
    )
    parser.add_argument("--task-retention", type=int, default=10000)
    parser.add_argument(
        "--solver",
        action="append",
        dest="allowed_solvers",
        help="allowed installed package (repeatable; default: dual-bfws-ffparser)",
    )
    parser.add_argument(
        "--allowed-client-cidr",
        action="append",
        dest="allowed_client_cidrs",
        help="allowed client network (repeatable; defaults to loopback and Docker-private)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ServerConfig(
        listen_host=args.listen_host,
        port=args.port,
        workers=args.workers,
        queue_limit=args.queue_limit,
        memory=args.memory,
        memory_swap=args.memory_swap,
        cpus=args.cpus,
        pids_limit=args.pids_limit,
        timeout_seconds=args.timeout_seconds,
        image=args.image,
        worker_security=args.worker_security,
        task_retention=args.task_retention,
        allowed_solvers=tuple(args.allowed_solvers or DEFAULT_ALLOWED_SOLVERS),
        allowed_client_cidrs=tuple(
            args.allowed_client_cidrs or ServerConfig.allowed_client_cidrs
        ),
    )
    config.validate()
    pool = DockerWorkerPool(config)
    pool.start()
    state = LocalSolverState(config, pool)
    server = ThreadingHTTPServer(
        (config.listen_host, config.port), make_handler(state)
    )
    actual_port = server.server_address[1]
    print(
        json.dumps(
            {
                "event": "local_solver_ready",
                "timestamp": _now(),
                "listen_host": config.listen_host,
                "port": actual_port,
                "workers": config.workers,
                "memory_per_worker": config.memory,
                "timeout_seconds": config.timeout_seconds,
                "worker_security": config.worker_security,
                "image": config.image,
                "image_id": pool.image_id,
            }
        ),
        flush=True,
    )

    closed = False

    def close() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        state.close()
        pool.close()

    atexit.register(close)

    def stop(_signum, _frame) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
