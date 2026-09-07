"""Out-of-band, acknowledged timing escrow. No Docker/harness dependencies."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .retry import ExternalCallInvalid


class NativeDeadlineExpired(Exception):
    """A native/benchmark deadline won delivery: valid cancellation, not infra."""
    def __init__(self, receipt=None):
        super().__init__("native deadline expired before result delivery")
        self.receipt = receipt or {}


def read_json(path):
    if path is None:
        return None
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, sort_keys=True, allow_nan=False)
    os.replace(temporary, path)


class ToolControl:
    """Gateway side. Serialize calls using the caller's lock before entering."""

    def __init__(self, path, *, cancelled=lambda: False):
        self.path = Path(path)
        self.ack_path = self.path.with_suffix(".ack.json")
        self.cancelled = cancelled
        self.state = {"phase": "idle", "pause_requested": False}
        write_json(self.path, self.state)

    def publish(self, **values):
        self.state.update(values)
        write_json(self.path, self.state)

    def wait_ack(self, status):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.cancelled():
                raise ExternalCallInvalid("external_call_cancelled")
            ack = read_json(self.ack_path) or {}
            if ack.get("call_id") == self.state["call_id"]:
                if ack.get("status") == "native_deadline":
                    raise NativeDeadlineExpired(ack)
                if ack.get("status") == "deadline":
                    raise ExternalCallInvalid("external_call_cancelled")
                if ack.get("status") == status:
                    return ack
            time.sleep(0.01)
        self.invalidate("external_call_control_failed")
        raise ExternalCallInvalid("external_call_control_failed")

    def begin(self):
        self.publish(call_id=uuid.uuid4().hex, phase="running", pause_requested=True,
                     pause_started_unix=time.time(), charged_seconds=0.0,
                     terminal_infra_error=None, rollback_count=0)
        self.wait_ack("paused")

    def finish(self, charged_seconds):
        self.publish(phase="settle", charged_seconds=charged_seconds)
        self.wait_ack("charged")
        self.publish(phase="ready", pause_requested=False)
        return self.wait_ack("released")

    def invalidate(self, reason, *, classification=None):
        self.publish(phase="invalid", pause_requested=True,
                    terminal_infra_error={"reason": reason, "source": "external_calls",
                                           "classification": classification or reason,
                                           "call_id": self.state.get("call_id")})


class ToolControlMonitor:
    """Host side. The workspace owns process freeze/kill and acknowledgement."""

    def __init__(self, path):
        self.path = Path(path)
        self.ack_path = self.path.with_suffix(".ack.json")
        self.charged = set()
        self.state = {}

    def merge(self, model_control, clock):
        state = read_json(self.path)
        if state is None:
            # Before the sidecar starts there is no tool call to recover.
            if self.state.get("pause_requested"):
                return {**model_control, "terminal_infra_error": {
                    "reason": "external_call_control_failed", "source": "external_calls"}}
            return model_control
        self.state = state
        merged = dict(model_control)
        if state.get("phase") == "settle" and state.get("call_id") not in self.charged:
            clock.charge_active(state["charged_seconds"])
            self.charged.add(state["call_id"])
        if state.get("pause_requested"):
            merged["pause_requested"] = True
            starts = [x for x in (state.get("pause_started_unix"), model_control.get("pause_started_unix"))
                      if isinstance(x, (float, int))]
            merged["pause_started_unix"] = min(starts) if starts else time.time()
        if state.get("terminal_infra_error") and not merged.get("terminal_infra_error"):
            merged["terminal_infra_error"] = state["terminal_infra_error"]
        # Freezing a concurrently committed model stream is not transparent.
        if not merged.get("terminal_infra_error") and state.get("pause_requested") and model_control.get("active_committed_streams", 0):
            merged["terminal_infra_error"] = {
                "reason": "external_call_stream_overlap", "source": "external_calls"}
        if state.get("pause_requested") and time.time() - state.get("pause_started_unix", time.time()) > 600:
            merged["terminal_infra_error"] = {
                "reason": "external_call_control_failed", "source": "external_calls"}
        return merged

    def acknowledge(self, *, paused, clock):
        state = self.state
        if not state.get("call_id"):
            return False
        phase = state.get("phase")
        if phase == "settle" and clock.expired():
            status = "deadline"
        elif phase == "running" and paused:
            status = "paused"
        elif phase == "settle" and paused:
            status = "charged"
        elif phase == "ready" and not paused:
            status = "released"
        else:
            return False
        value = {"call_id": state["call_id"], "status": status}
        if read_json(self.ack_path) != value:
            write_json(self.ack_path, value)
        return status == "deadline"
