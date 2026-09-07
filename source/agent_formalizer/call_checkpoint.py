"""Call-boundary budget checkpoints; native continuation stays behind delivery.

Unlike v1, Node watchdogs live in process and never register per stream event.
Only call boundaries exchange snapshots. Physical time and retry evidence are
not restored. The existing broker still serves Python/GNU timeout leases.
"""
from __future__ import annotations

import json
import math
import os
import socket
import socketserver
import struct
import threading
import time
import uuid

from . import logical_time

POLICY_ID = "call-checkpoint-v1"


class CheckpointBroker(logical_time.DeadlineBroker):
    """Trusted host coordinates a bounded, acknowledged native commit barrier."""

    def __init__(self, directory, evidence=None):
        self.clients = {}
        self.clients_lock = threading.RLock()
        self.barrier_lock = threading.Lock()
        self.failure = None
        self.closed = False
        super().__init__(directory, evidence)
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                key = "node:" + uuid.uuid4().hex
                client = {"socket": self.connection, "event": threading.Event(),
                          "sequence": None, "reply": None}
                pid, _, _ = struct.unpack("3i", self.connection.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                client["pid"] = pid
                try:
                    with owner.clients_lock:
                        if len(owner.clients) >= 128:
                            raise RuntimeError("checkpoint participant limit")
                        owner.clients[key] = client
                        owner._send(client, {"op": "hello", **owner.state()})
                    while line := self.rfile.readline(8193):
                        if len(line) > 8192:
                            raise ValueError("checkpoint reply too large")
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError("checkpoint reply must be an object")
                        if value.get("sequence") != client["sequence"]:
                            raise ValueError("checkpoint acknowledgement mismatch")
                        client["reply"] = value
                        client["event"].set()
                except (OSError, ValueError, RuntimeError, TypeError):
                    if not owner.closed:
                        owner.failure = "call_checkpoint_control_failed"
                finally:
                    with owner.clients_lock:
                        owner.clients.pop(key, None)
                    with owner.lock:
                        owner.leases.pop(key, None)
                    # A process exiting after its ordinary native timeout is
                    # expected. Exiting mid-barrier without ACK is not success.
                    client["event"].set()

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.checkpoint_server = Server(f"/proc/self/fd/{fd}/checkpoint.sock", Handler)
        finally:
            os.close(fd)
        (self.directory / "checkpoint.sock").chmod(0o666)
        self.checkpoint_thread = threading.Thread(
            target=self.checkpoint_server.serve_forever,
            kwargs={"poll_interval": 0.05}, daemon=True)
        self.checkpoint_thread.start()

    def state(self):
        with self.lock:
            return {"logical": self.logical, "anchor": self.anchor, "paused": self.paused}

    @staticmethod
    def _send(client, message):
        client["socket"].sendall((json.dumps(message, allow_nan=False) + "\n").encode())

    def barrier(self, operation, *, rollback=False):
        # No lock needed by reply handlers is held while waiting for replies.
        with self.barrier_lock:
            if self.failure:
                raise RuntimeError(self.failure)
            sequence = uuid.uuid4().hex
            with self.clients_lock:
                participants = list(self.clients.items())
                for _, client in participants:
                    client.update(sequence=sequence, reply=None)
                    client["event"].clear()
                    self._send(client, {"op": operation, "sequence": sequence,
                                        "rollback": rollback, **self.state()})
            deadline = time.monotonic() + 3
            for key, client in participants:
                if not client["event"].wait(max(0, deadline - time.monotonic())):
                    raise RuntimeError("checkpoint acknowledgement timeout")
                reply = client["reply"]
                if reply is None or reply.get("error"):
                    reason = reply.get("error") if reply else "checkpoint_participant_disconnected"
                    self.record({"event": "checkpoint_rejected", "reason": reason,
                                 "operation": operation})
                    raise RuntimeError(f"checkpoint participant failed: {reason}")
                target = reply.get("target")
                if target is not None and (not isinstance(target, (int, float)) or
                                           not math.isfinite(target) or target < 0):
                    raise ValueError("invalid checkpoint deadline")
                with self.lock:
                    if target is None:
                        self.leases.pop(key, None)
                    else:
                        self.leases[key] = {"pid": client["pid"], "target": target}
            return len(participants)

    def record(self, value):
        if self.evidence:
            self.evidence.parent.mkdir(parents=True, exist_ok=True)
            with self.evidence.open("a") as stream:
                os.chmod(self.evidence, 0o600)
                stream.write(json.dumps({"policy": POLICY_ID, "physical_unix": time.time(), **value}) + "\n")

    def freeze(self, call_id=None):
        super().freeze()
        count = self.barrier("checkpoint")
        self.record({"event": "checkpoint", "call_id": call_id,
                     "participants": count, "remaining_seconds": self.clock.remaining()})

    def settle(self, call_id, seconds, *, rollback=False):
        if call_id in self.settled:
            return self.settled[call_id]
        # Timers cancelled during the await must not become phantom deadlines.
        self.barrier("prepare", rollback=rollback)
        result = super().settle(call_id, seconds)
        # Execute actual native cancellation before releasing any candidate.
        self.barrier("settle")
        self.record({"event": "settlement", "rollback": rollback, **result})
        return result

    def pending(self, due):
        with self.lock:
            self._prune()
            # A Node participant reports its *next* earliest watchdog after
            # firing. The participant ID itself persists across call boundaries.
            return any(key in self.leases and (not key.startswith("node:") or
                       self.leases[key]["target"] <= self.logical + 1e-8) for key in due)

    def resume(self):
        if self.paused:
            super().resume()
            self.barrier("resume")

    def close(self):
        self.closed = True
        with self.clients_lock:
            for client in self.clients.values():
                try:
                    client["socket"].shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.checkpoint_server.shutdown()
        self.checkpoint_server.server_close()
        self.checkpoint_thread.join(timeout=3)
        super().close()
