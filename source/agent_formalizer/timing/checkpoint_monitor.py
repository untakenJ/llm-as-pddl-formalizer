"""Checkpoint timing with native asynchronous work, not a serial-agent guard.

An isolated call escrows deadlines. Healthy overlap releases that escrow into
the ordinary wall clock, counting elapsed time once. Only an actual recovery
that cannot be isolated from concurrent observable work fails closed.
"""
from __future__ import annotations

import logging
import subprocess
import time

from .call_checkpoint import POLICY_ID, RecoveryUnsafe, NativeBudgetExpired, CheckpointClosed
from ..external_calls.control import read_json, write_json


def control_paths(bases):
    for base in bases:
        yield base  # legacy fixtures and the solver sidecar's idle marker
        yield from (base.parent / (base.stem + ".calls")).glob("*.json")


def monitor(workspace, clock, stop):
    broker = workspace._deadline_broker
    broker.attach(clock)
    bases = [workspace._gateway_control_dir / "model-timing.json"]
    if workspace._solver_control_monitor:
        bases.append(workspace._solver_control_monitor.path)
    completed, concurrent = set(), set()
    retired_paths = set()
    owner = None
    receipt = None
    release_started = None
    last_liveness = 0.0

    def ack(path, state, status, **values):
        value = {"call_id": state["call_id"], "status": status, **values}
        target = path.with_suffix(".ack.json")
        if read_json(target) != value:
            write_json(target, value)

    def invalidate(reason, evidence):
        terminal = {"reason": reason, "source": evidence.get("source", POLICY_ID), "evidence": evidence}
        if evidence.get("classification"):
            terminal["classification"] = evidence["classification"]
        workspace._gateway_terminal_error = terminal
        clock.cancel(reason)
        try:
            broker.record({"event": "invalidation", **terminal})
            cancel_path = getattr(workspace, "_gateway_cancel_path", None)
            if cancel_path is not None:
                cancel_path.write_text("infrastructure_invalidated\n")
        finally:
            subprocess.run(["docker", "kill", workspace.container_name], capture_output=True, timeout=5)

    try:
        while not stop.is_set() or receipt is not None:
            model = workspace._read_gateway_control() or {}
            if model.get("terminal_infra_error"):
                terminal = model["terminal_infra_error"]
                invalidate(terminal["reason"], terminal)
                return
            if model.get("action_step_limit_reached"):
                workspace._gateway_action_step_limit_reached = True
                subprocess.run(["docker", "kill", workspace.container_name], capture_output=True, timeout=5)
                return  # valid benchmark guard, not infra
            if broker.failure:
                raise RuntimeError(broker.failure)
            if model.get("active_committed_streams", 0) and time.monotonic() - last_liveness >= 1:
                last_liveness = time.monotonic()
                result = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}",
                                         workspace.gateway_name], capture_output=True, text=True, timeout=5)
                # An inspect failure is not evidence of a dead gateway. A
                # successful, explicit negative observation is required.
                if not stop.is_set() and result.returncode == 0 and result.stdout.strip() == "false":
                    invalidate("post_commit_stream_failure", {"stream_error_type": "GatewaySidecarExit"})
                    return
                model = workspace._read_gateway_control() or {}
            active = {}
            for path in control_paths(bases):
                if path.name.endswith(".ack.json") or path in retired_paths:
                    continue
                state = read_json(path) or {}
                key = state.get("call_id")
                if state.get("phase") == "invalid":
                    terminal = state["terminal_infra_error"]
                    invalidate(terminal["reason"], terminal)
                    return
                if not key or key in completed:
                    continue
                if state.get("phase") in {"running", "settle", "ready"}:
                    active[key] = (path, state)
                elif state.get("phase") in {"done", "cancelled", "native_done"}:
                    completed.add(key)
                    if path not in bases:
                        retired_paths.add(path)
                    if owner == key:
                        # Native cancellation/exit is not a missing-control
                        # invalidator. No candidate will be delivered.
                        if receipt is None:
                            broker.run_concurrently([key])
                        else:
                            broker.resume()
                        owner = receipt = release_started = None
            if not active:
                if owner is not None:
                    raise RuntimeError("checkpoint control disappeared without a terminal state")
                concurrent.clear()
                stop.wait(0.02)
                continue

            # Native cancellation can immediately advance the harness into
            # its next model call while this rejected candidate is still at
            # the delivery barrier. A settled timeout is irreversible: new
            # healthy work must not turn its verdict into `released` or replace
            # its truncated charge with the full physical solver duration.
            if owner in active and receipt and receipt['native_due']:
                previous_path, previous_state = active[owner]
                if previous_state['phase'] == 'settle':
                    ack(previous_path, previous_state, 'charged',
                        charged_seconds=receipt['charged_seconds'])
                elif previous_state['phase'] == 'ready':
                    if release_started is None:
                        release_started = time.monotonic()
                    if time.monotonic() - release_started < 0.15:
                        stop.wait(0.02)
                        continue
                    broker.resume()
                    ack(previous_path, previous_state, 'native_deadline',
                        charged_seconds=receipt['charged_seconds'])
                    # Native exit can immediately start evidence collection.
                    # Let the sidecar persist rejection before monitor shutdown
                    # is allowed to tear it down (same bound as the solo path).
                    until = time.monotonic() + 2
                    while time.monotonic() < until:
                        if (read_json(previous_path) or {}).get('phase') in {'native_done', 'cancelled'}:
                            break
                        time.sleep(0.01)
                    completed.add(owner)
                    if previous_path not in bases:
                        retired_paths.add(previous_path)
                    broker.record({'event': 'native_deadline_finalized', 'call_id': owner,
                                   'subsequent_native_calls': sorted(set(active) - {owner})})
                    owner = receipt = release_started = None
                else:
                    raise RuntimeError('settled native deadline moved backwards')
                stop.wait(0.02)
                continue

            # A stale stream snapshot can at most choose the ordinary clock;
            # it can never by itself invalidate a healthy execution.
            # Never retain a model snapshot across filesystem/Docker work.
            # This read influences clock mode only, not healthy validity.
            model = workspace._read_gateway_control() or {}
            overlap = len(active) > 1 or bool(model.get("active_committed_streams", 0))
            if concurrent or overlap:
                def progress():
                    for call_path, call_state in active.values():
                        ack(call_path, call_state, "controller_waiting", updated_monotonic=time.monotonic())
                broker.wait_progress = progress
                first_overlap = not concurrent
                concurrent.update(active)
                recovering = {key: state["rollback_count"] for key, (_, state) in active.items()
                              if state.get("rollback_count", 0)}
                if recovering:
                    invalidate("external_call_recovery_unsafe", {
                        "classification": "recovery_crossed_native_concurrency",
                        "recovering_calls": recovering, "concurrent_call_ids": sorted(concurrent)})
                    return
                if owner is not None:
                    if receipt is None:
                        broker.run_concurrently(concurrent)
                    else:
                        broker.resume()  # the prefix has already been charged
                    owner = receipt = release_started = None
                elif first_overlap:
                    broker.record({"event": "native_concurrency", "call_ids": sorted(concurrent),
                                   "timing_mode": "running_wall", "escrow_seconds_charged_once": 0.0})
                if clock.expired():
                    workspace.enforce_agent_deadline()
                    return
                for key, (path, state) in active.items():
                    phase = state["phase"]
                    if phase == "running":
                        ack(path, state, "paused", timing_mode="running_wall")
                    elif phase == "settle":
                        ack(path, state, "charged", charged_seconds=state["charged_seconds"],
                            timing_mode="running_wall")
                    elif phase == "ready":
                        ack(path, state, "released", charged_seconds=state["charged_seconds"],
                            timing_mode="running_wall")
                        completed.add(key)
                        if path not in bases:
                            retired_paths.add(path)
                stop.wait(0.02)
                continue

            key, (path, state) = next(iter(active.items()))
            broker.wait_progress = lambda: ack(path, state, "controller_waiting", updated_monotonic=time.monotonic())
            if owner is None:
                owner = key
                broker.freeze(key)
            if owner != key:
                raise RuntimeError("checkpoint control disappeared without a terminal state")
            if state["phase"] == "running":
                ack(path, state, "paused")
            elif state["phase"] == "settle":
                receipt = broker.settle(key, float(state["charged_seconds"]),
                                        rollback=bool(state.get("rollback_count")))
                if receipt["benchmark_due"]:
                    ack(path, state, "deadline", charged_seconds=receipt["charged_seconds"])
                    workspace.enforce_agent_deadline()
                    return
                ack(path, state, "charged", charged_seconds=receipt["charged_seconds"])
            elif state["phase"] == "ready":
                if receipt is None:
                    raise RuntimeError("checkpoint release without settlement")
                due = receipt["native_due"]
                if release_started is None:
                    release_started = time.monotonic()
                # Cancellation belongs to the native runtime. An agent's
                # cleanup handler need not exit or delete its timer lease.
                # Never relabel a long cleanup as an infrastructure failure.
                if due and time.monotonic() - release_started < 0.15:
                    stop.wait(0.02)
                    continue
                broker.resume()
                ack(path, state, "native_deadline" if due else "released",
                    charged_seconds=receipt["charged_seconds"])
                if due:
                    # Collection may start as soon as native cancellation exits
                    # the CLI. Give the gateway time to persist its receipt;
                    # absent optional acknowledgement is not an invalidator.
                    until = time.monotonic() + 2
                    while time.monotonic() < until:
                        final = read_json(path) or {}
                        if final.get("phase") in {"native_done", "cancelled"}:
                            break
                        time.sleep(0.01)
                completed.add(key)
                if path not in bases:
                    retired_paths.add(path)
                owner = receipt = release_started = None
            stop.wait(0.02)
    except CheckpointClosed:
        pass  # Owner cleanup, not a new infrastructure verdict.
    except NativeBudgetExpired:
        broker.record({"event": "native_busy_deadline", "outcome": "valid_benchmark_timeout"})
        if broker.paused:
            clock.charge_active(clock.remaining())
        owner = None  # the deadline is already charged; do not charge it twice
        workspace.enforce_agent_deadline()
    except RecoveryUnsafe as exc:
        invalidate("external_call_recovery_unsafe", {"classification": exc.classification,
                                                    "detail": str(exc)})
    except Exception as exc:
        if not stop.is_set():
            logging.getLogger(__name__).exception("Checkpoint controller failed")
            invalidate("external_call_control_failed", {"error_type": type(exc).__name__, "detail": str(exc)})
    finally:
        # Shutdown after an ordinary harness exit is not an unfinished-call
        # error. Avoid a new acknowledgement barrier to already exited peers.
        from .logical_time import DeadlineBroker
        if broker.paused and receipt is None and owner is not None:
            # A native exit while a healthy request is in flight must not make
            # its entire wait free. A recovery pause remains diagnostic escrow.
            owner_state = next((read_json(path) for path in control_paths(bases)
                                if not path.name.endswith(".ack.json") and
                                (read_json(path) or {}).get("call_id") == owner), {}) or {}
            if not owner_state.get("rollback_count"):
                with broker.lock:
                    elapsed = max(0, time.monotonic() - broker.anchor)
                    broker.logical += elapsed
                    clock.charge_active(elapsed)
        DeadlineBroker.resume(broker)
