"""Logical *deadlines*, not a replacement for any OS or language clock.

The host owns settlement. Container clients can only create/read/close their
own deadline leases. No retry diagnostics or writable clock enter the agent.
This module is also mounted alone as ``benchmark_logical_time`` in containers.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import socket
import socketserver
import struct
import threading
import time
import uuid
from pathlib import Path

POLICY_ID = "logical-deadline-v1"
CONTAINER_DIR = "/run/benchmark-deadlines"
RUNTIME_DIR = "/opt/benchmark-deadlines"


def _atomic(path, value):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    tmp.chmod(0o644)
    tmp.replace(path)


def enabled():
    return bool(os.environ.get("BENCHMARK_DEADLINE_DIR"))


def logical_now():
    directory = os.environ.get("BENCHMARK_DEADLINE_DIR")
    if not directory:
        return time.monotonic()
    state = json.loads((Path(directory) / "clock.json").read_text())
    if state["policy"] != POLICY_ID:
        raise RuntimeError("logical deadline policy mismatch")
    return state["logical"] + (0.0 if state["paused"] else
                                max(0.0, time.monotonic() - state["anchor"]))


def _rpc(message):
    directory = os.environ["BENCHMARK_DEADLINE_DIR"]
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.connect(str(Path(directory) / "broker.sock"))
        sock.sendall((json.dumps(message) + "\n").encode())
        with sock.makefile("rb") as reader:
            result = json.loads(reader.readline(4096))
    if "error" in result:
        raise RuntimeError("logical deadline control rejected: " + result["error"])
    return result


class Deadline:
    """One native deadline. Keep this alive until native timeout cleanup ends."""
    def __init__(self, seconds):
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("deadline must be finite and nonnegative")
        self.key = None
        self.target = logical_now() + seconds
        if enabled():
            value = _rpc({"op": "register", "seconds": seconds})
            self.key, self.target = value["id"], value["target"]

    def remaining(self):
        return max(0.0, self.target - logical_now())

    def expired(self):
        return self.remaining() <= 0

    def close(self):
        if self.key is not None:
            key, self.key = self.key, None
            _rpc({"op": "close", "id": key})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


async def wait_for(awaitable, timeout):
    """Targeted alternative to asyncio.wait_for; no global event-loop patch."""
    if timeout is None or not enabled():
        return await asyncio.wait_for(awaitable, timeout)
    task = asyncio.ensure_future(awaitable)
    with Deadline(max(0, timeout)) as deadline:
        try:
            while not task.done():
                if deadline.expired():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        raise TimeoutError() from None
                    return task.result()  # Native cancellation suppression.
                await asyncio.wait({task}, timeout=min(0.05, deadline.remaining()))
            return task.result()
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


class DeadlineBroker:
    """Per-execution host service. The public socket cannot pause or charge."""
    def __init__(self, directory, evidence=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.evidence = Path(evidence) if evidence else None
        self.lock = threading.RLock()
        self.clock = None
        self.leases = {}
        self.settled = {}
        self.logical = 0.0
        self.anchor = time.monotonic()
        self.paused = False
        self._publish()
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    self.connection.settimeout(3)
                    pid, _, _ = struct.unpack("3i", self.connection.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    msg = json.loads(self.rfile.readline(4096))
                    with owner.lock:
                        if msg["op"] == "register":
                            seconds = float(msg["seconds"])
                            if not math.isfinite(seconds) or not 0 <= seconds <= 1e9:
                                raise ValueError("invalid duration")
                            owner._prune()
                            if len(owner.leases) >= 4096:
                                raise ValueError("deadline lease limit")
                            key = uuid.uuid4().hex
                            target = owner.now() + seconds
                            owner.leases[key] = {"pid": pid, "target": target}
                            result = {"id": key, "target": target}
                        elif msg["op"] == "close":
                            lease = owner.leases.get(msg["id"])
                            if lease and lease["pid"] != pid:
                                raise ValueError("deadline owner mismatch")
                            owner.leases.pop(msg["id"], None)
                            result = {"ok": True}
                        else:
                            raise ValueError("unsupported operation")
                    self.wfile.write((json.dumps(result) + "\n").encode())
                except Exception as exc:
                    self.wfile.write((json.dumps({"error": type(exc).__name__}) + "\n").encode())

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True
        # A proc-fd pathname avoids AF_UNIX's 108-byte limit for output paths.
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.server = Server(f"/proc/self/fd/{fd}/broker.sock", Handler)
        finally:
            os.close(fd)
        (self.directory / "broker.sock").chmod(0o666)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def now(self):
        return self.logical + (0 if self.paused else max(0, time.monotonic() - self.anchor))

    def _publish(self):
        _atomic(self.directory / "clock.json", {
            "policy": POLICY_ID, "logical": self.logical, "anchor": self.anchor,
            "paused": self.paused,
        })

    def attach(self, clock):
        with self.lock:
            self.clock = clock
            self.logical = clock.snapshot()["active_duration_seconds"]
            self.anchor = time.monotonic()
            self._publish()

    def freeze(self):
        with self.lock:
            if not self.paused:
                self.logical = self.now()
                self.anchor = time.monotonic()
                self.paused = True
                self.clock.pause()
                self._publish()

    def _prune(self):
        for key, lease in list(self.leases.items()):
            try:
                status = Path(f"/proc/{lease['pid']}/stat").read_text().rsplit(")", 1)[1].split()[0]
                alive = status not in {"Z", "X"}
            except (OSError, IndexError):
                alive = False
            if not alive:
                self.leases.pop(key, None)

    def settle(self, call_id, seconds):
        with self.lock:
            if call_id in self.settled:
                return self.settled[call_id]
            if not self.paused or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("invalid logical-time settlement")
            self._prune()
            available = min([self.clock.remaining(), *(
                max(0, item["target"] - self.logical) for item in self.leases.values())])
            spent = min(seconds, available)
            self.logical += spent
            self.clock.charge_active(spent)
            due = [key for key, item in self.leases.items() if item["target"] <= self.logical + 1e-8]
            result = {"call_id": call_id, "accepted_seconds": seconds,
                      "charged_seconds": spent, "native_due": due,
                      "benchmark_due": self.clock.expired()}
            self.settled[call_id] = result
            self._publish()
            if self.evidence:
                self.evidence.parent.mkdir(parents=True, exist_ok=True)
                with self.evidence.open("a") as stream:
                    os.chmod(self.evidence, 0o600)
                    stream.write(json.dumps(result) + "\n")
            return result

    def pending(self, due):
        with self.lock:
            self._prune()
            return any(key in self.leases for key in due)

    def resume(self):
        with self.lock:
            if self.paused:
                self.anchor = time.monotonic()
                self.paused = False
                self.clock.resume()
                self._publish()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
