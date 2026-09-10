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
from pathlib import Path

from . import logical_time

POLICY_ID = "call-checkpoint-v1"
IMPLEMENTATION_REVISION = "native-concurrency-v5-native-exit"


class RecoveryUnsafe(RuntimeError):
    """An actual discarded external request crossed observable native work."""

    def __init__(self, message, *, classification="checkpoint_business_state_changed"):
        super().__init__(message)
        self.classification = classification


class NativeBudgetExpired(RuntimeError):
    """A live native participant used its budget while busy; not infra."""


class CheckpointClosed(RuntimeError):
    """The owner is shutting down; do not create a new invalidation."""


def _process_identity(pid):
    """Three-valued liveness plus Linux start time; read errors are not exits."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return ("exited" if fields[0] in {"Z", "X"} else "alive", int(fields[19]))
    except FileNotFoundError:
        return "exited", None
    except (OSError, IndexError, ValueError):
        return "unknown", None


def _participant_status(client):
    status, start = _process_identity(client["pid"])
    if status != "alive":
        return status
    original = client["start_time"]
    if original is None:
        return "unknown"
    return "alive" if start == original else "exited"  # PID reused, not our peer.


class CheckpointBroker(logical_time.DeadlineBroker):
    """Trusted host coordinates a bounded, acknowledged native commit barrier."""

    def __init__(self, directory, evidence=None):
        self.clients = {}
        self.clients_lock = threading.RLock()
        self.barrier_lock = threading.Lock()
        self.checkpoint_participants = {}
        self.failure = None
        self.wait_progress = lambda: None
        self.barrier_seconds = 0.0
        self.closed = False
        super().__init__(directory, evidence)
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                key = "node:" + uuid.uuid4().hex
                client = {"socket": self.connection, "event": threading.Event(),
                          "sequence": None, "operation": "hello", "reply": None, "key": key,
                          "lock": threading.RLock(), "disconnect_lock": threading.Lock(),
                          "state": "active", "disposition": None, "protocol_error": False,
                          "exit_notice": None}
                pid, _, _ = struct.unpack("3i", self.connection.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                client["pid"] = pid
                _, client["start_time"] = _process_identity(pid)
                try:
                    # Per-connection ordering keeps hello before the first
                    # command, without holding the registry lock during I/O.
                    with client["lock"]:
                        with owner.clients_lock:
                            if owner.closed:
                                return
                            owner.clients[key] = client
                        owner._send(client, {"op": "hello", "participant": key, **owner.state()})
                    while line := self.rfile.readline(8193):
                        if len(line) > 8192:
                            raise ValueError("checkpoint reply too large")
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError("checkpoint reply must be an object")
                        if value.get("event") == "participant_exit":
                            owner._native_exit(client, value)
                            continue
                        with client["lock"]:
                            if client["exit_notice"] is not None:
                                raise ValueError("checkpoint acknowledgement after exit notice")
                            if value.get("sequence") != client["sequence"]:
                                raise ValueError("checkpoint acknowledgement mismatch")
                            client["reply"] = value
                            client["event"].set()
                except OSError as exc:
                    owner._disconnect(client, "receive", exc)
                except (ValueError, RuntimeError, TypeError) as exc:
                    owner._disconnect(client, "protocol", exc, protocol=True)
                finally:
                    owner._disconnect(client, "eof")

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

    def _check_open(self):
        if self.closed:
            raise CheckpointClosed("checkpoint broker closed")
        if self.failure:
            raise RuntimeError(self.failure)

    def _native_exit(self, client, value):
        """An in-band terminal record, not an ACK or a successful agent result.

        The locked Node runtime emits this at irreversible exit, before native
        handle cleanup. SO_PEERCRED/start time bind it to this connection, not
        a container-supplied PID. Keep checkpoint tombstones for real rollback.
        """
        with client["lock"]:
            if (type(value.get("version")) is not int or value["version"] != 1 or
                    value.get("participant") != client["key"] or
                    value.get("origin") not in {"native_exit", "control_failure"} or
                    type(value.get("exit_code")) is not int or
                    client["exit_notice"] is not None or
                    client["start_time"] is None):
                raise ValueError("invalid checkpoint exit notice")
            client["exit_notice"] = value
            if value["origin"] == "control_failure":
                client["protocol_error"] = True
                if not self.closed:
                    self.failure = "call_checkpoint_control_failed"
            client["state"] = "exiting"
            # An exit cannot stand in for a business-state validation ACK.
            client["reply"] = None
            self.record({"event": "checkpoint_participant_exit_notice",
                         "participant": client["key"], "pid": client["pid"],
                         "process_start_time": client["start_time"],
                         "origin": value["origin"], "exit_code": value["exit_code"],
                         "sequence": client["sequence"], "operation": client["operation"]})
            client["event"].set()

    def _disconnect(self, client, source, error=None, *, protocol=False):
        """Resolve each lost connection once, outside registry/ACK locks.

        A disconnected-but-unresolved peer stays in the registry so a barrier
        cannot silently omit it while the receive thread checks its identity.
        Socket loss alone is not an exit, nor permission to restore state.
        """
        with client["lock"]:
            client["state"] = "disconnected"
            client["event"].set()
            if protocol:
                client["protocol_error"] = True
                if not self.closed:
                    self.failure = "call_checkpoint_control_failed"
        with client["disconnect_lock"]:
            if client["disposition"] is not None:
                return client["disposition"]
            status = _participant_status(client)
            initial_status = status
            # Without a terminal notice, EOF alone still needs OS exit proof.
            # A native exit notice accounts for Node closing handles before
            # C++/isolate teardown finishes, even if that takes >0.5 seconds.
            confirmation_started = time.monotonic()
            until = confirmation_started + 0.5
            # /proc can also become briefly unreadable during teardown. An
            # unknown sample is never itself proof of exit; recheck within the
            # same bound and require positive exit/participant identity evidence.
            while (status != "exited" and not self.closed and
                   not client["protocol_error"] and time.monotonic() < until):
                with client["lock"]:
                    if status == "alive" and client["exit_notice"] is not None:
                        break
                time.sleep(0.01)
                status = _participant_status(client)
            with client["lock"]:
                disposition = ("shutdown" if self.closed else
                               "exited" if status == "exited" and not client["protocol_error"] else
                               "native_exiting" if status == "alive" and client["exit_notice"] is not None
                               and not client["protocol_error"] else
                               "control_failed")
                if disposition == "control_failed":
                    self.failure = "call_checkpoint_control_failed"
                client["disposition"] = disposition
                with self.clients_lock:
                    if self.clients.get(client["key"]) is client:
                        self.clients.pop(client["key"])
                with self.lock:
                    self.leases.pop(client["key"], None)
            if not self.closed:
                self.record({"event": "checkpoint_participant_disconnected",
                             "participant": client["key"], "pid": client["pid"],
                             "process_start_time": client["start_time"],
                             "sequence": client["sequence"], "operation": client["operation"],
                             "source": source,
                             "error_type": type(error).__name__ if error else None,
                             "exit_origin": (client["exit_notice"] or {}).get("origin"),
                             "native_exit_code": (client["exit_notice"] or {}).get("exit_code"),
                             "initial_process_status": initial_status,
                             "exit_confirmation_seconds": time.monotonic() - confirmation_started,
                             "process_status": status, "disposition": disposition})
            return disposition

    def barrier(self, operation, *, rollback=False):
        # No lock needed by reply handlers is held while waiting for replies.
        with self.barrier_lock:
            self._check_open()
            sequence = uuid.uuid4().hex
            with self.clients_lock:
                participants = dict(self.clients)
            if operation == "checkpoint":
                self.checkpoint_participants = {}
            elif rollback:
                # Retain tombstones until this call ends: retirement must not
                # erase a missing business-state check during real recovery.
                participants.update(self.checkpoint_participants)
            started = time.monotonic()
            for client in participants.values():
                self._check_open()
                try:
                    with client["lock"]:
                        client.update(sequence=sequence, operation=operation, reply=None)
                        if client["state"] != "active":
                            continue
                        client["event"].clear()
                        self._send(client, {"op": operation, "sequence": sequence,
                                            "rollback": rollback, **self.state()})
                except OSError as exc:
                    self._disconnect(client, "send", exc)
                    self._check_open()
            # A native JS event loop can legitimately be busy for >3 seconds.
            # Lack of an immediate ACK is not evidence of broken transport.
            deadline = started + (max(0, self.clock.remaining() - self.barrier_seconds) if self.clock else 1800)
            for key, client in participants.items():
                while not client["event"].wait(0.05):
                    self._check_open()
                    self.wait_progress()
                    if _participant_status(client) == "exited":
                        break
                    if time.monotonic() >= deadline:
                        raise NativeBudgetExpired("native participant busy through benchmark deadline")
                self._check_open()
                with client["lock"]:
                    reply = client["reply"]
                    disconnected = client["state"] != "active"
                if disconnected:
                    # An ACK does not excuse a subsequently observed live
                    # control failure. Finish its classification before release.
                    self._disconnect(client, "ack")
                    self._check_open()
                if reply is None or reply.get("error"):
                    if reply is None:
                        self._disconnect(client, "ack")
                        self._check_open()
                        if rollback and key in self.checkpoint_participants:
                            self.record({"event": "checkpoint_rejected",
                                         "reason": "checkpoint_participant_lost_during_recovery",
                                         "participant": key, "pid": client["pid"],
                                         "operation": operation})
                            raise RecoveryUnsafe(
                                "checkpoint participant lost during recovery",
                                classification="checkpoint_participant_lost_during_recovery")
                        continue
                    reason = reply.get("error") if reply else "checkpoint_participant_disconnected"
                    self.record({"event": "checkpoint_rejected", "reason": reason,
                                 "operation": operation})
                    if rollback and reason == "checkpoint_business_state_changed":
                        raise RecoveryUnsafe(f"checkpoint participant failed: {reason}")
                    raise RuntimeError(f"checkpoint participant failed: {reason}")
                target = reply.get("target")
                if target is not None and (not isinstance(target, (int, float)) or
                                           not math.isfinite(target) or target < 0):
                    raise ValueError("invalid checkpoint deadline")
                if operation == "checkpoint":
                    self.checkpoint_participants[key] = client
                with client["lock"]:
                    with self.lock:
                        if target is None or client["state"] != "active":
                            self.leases.pop(key, None)
                        else:
                            self.leases[key] = {"pid": client["pid"], "target": target}
            self._check_open()
            if operation == "resume":
                self.checkpoint_participants = {}
            self.barrier_seconds += time.monotonic() - started
            return len(participants)

    def record(self, value):
        if self.evidence:
            self.evidence.parent.mkdir(parents=True, exist_ok=True)
            with self.evidence.open("a") as stream:
                os.chmod(self.evidence, 0o600)
                stream.write(json.dumps({"policy": POLICY_ID, "physical_unix": time.time(), **value}) + "\n")

    def freeze(self, call_id=None):
        self._check_open()
        super().freeze()
        count = self.barrier("checkpoint")
        self.record({"event": "checkpoint", "call_id": call_id,
                     "participants": count, "remaining_seconds": self.clock.remaining()})

    def settle(self, call_id, seconds, *, rollback=False):
        if call_id in self.settled:
            return self.settled[call_id]
        # Timers cancelled during the await must not become phantom deadlines.
        self.barrier("prepare", rollback=rollback)
        # Native CPU/scheduling spent handling checkpoints is agent active
        # time, not a transparent external-retry credit.
        overhead, self.barrier_seconds = self.barrier_seconds, 0.0
        result = super().settle(call_id, seconds + overhead)
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

    def run_concurrently(self, call_ids):
        """Release healthy escrow into the ordinary running wall clock.

        Charge the elapsed interval ONCE, never sum overlapping call durations.
        No recovery has occurred on this path. A later discarded physical
        request requires separate recovery-safety adjudication by the monitor.
        """
        if self.paused:
            self.barrier("prepare")
            with self.lock:
                elapsed = max(0.0, time.monotonic() - self.anchor)
                self.logical += elapsed
                self.clock.charge_active(elapsed)
                self._publish()
                self.barrier_seconds = 0.0  # included in the elapsed interval
            self.barrier("settle")
            self.resume()
        else:
            elapsed = 0.0
        self.record({"event": "native_concurrency", "call_ids": sorted(call_ids),
                     "timing_mode": "running_wall", "escrow_seconds_charged_once": elapsed})

    def resume(self):
        if self.paused:
            with self.lock:
                self.logical += self.barrier_seconds
                self.clock.charge_active(self.barrier_seconds)
                self.barrier_seconds = 0.0
            super().resume()
            self.barrier("resume")
            self.barrier_seconds = 0.0  # running clock already counted this

    def close(self):
        self.closed = True
        with self.clients_lock:
            clients = list(self.clients.values())
        for client in clients:
            try:
                client["socket"].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._disconnect(client, "shutdown")
        self.checkpoint_server.shutdown()
        self.checkpoint_server.server_close()
        self.checkpoint_thread.join(timeout=3)
        super().close()
