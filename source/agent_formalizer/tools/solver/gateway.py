"""Fixed-route gateway from the agent to a selected compatible solver backend.

The agent container stays on the internal Docker network. This sidecar has
bridge egress and forwards domain/problem PDDL to the same public or local
planning.domains-compatible service used by ``source/run_solver.py``.
"""

from __future__ import annotations

import json
import hashlib
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from contextlib import nullcontext

# Allow ``python3 /opt/.../gateway.py`` with the sibling module mounted
# next to this file inside the sidecar.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
# The same package is mounted beside model_gateway.py, never in the agent.
sys.path.insert(0, str(_HERE.parent.parent))
try:
    from agent_formalizer.external_calls import ExternalCallInvalid
    from agent_formalizer.external_calls.control import ToolControl, write_json, NativeDeadlineExpired
    from agent_formalizer.external_calls.solver import POLICY_ID
    from agent_formalizer.external_calls.checkpoint import RequestCheckpoint
    from agent_formalizer.external_calls.solver_fallback import validate_local_health
except ModuleNotFoundError:
    from external_calls import ExternalCallInvalid
    from external_calls.control import ToolControl, write_json, NativeDeadlineExpired
    from external_calls.solver import POLICY_ID
    from external_calls.checkpoint import RequestCheckpoint
    from external_calls.solver_fallback import validate_local_health

from remote_client import (  # noqa: E402
    DEFAULT_SOLVER,
    SUPPORTED_SOLVERS,
    plan_text_from_solver_result,
    solve_pddl,
)


LISTEN_PORT = int(os.environ.get("PDDL_SOLVER_GATEWAY_PORT", "8768"))
LISTEN_HOST = os.environ.get("PDDL_SOLVER_GATEWAY_LISTEN_HOST", "0.0.0.0")
UPSTREAM_BASE = os.environ.get(
    "PDDL_SOLVER_UPSTREAM_BASE", "http://host.docker.internal:8769"
).rstrip("/")
DEFAULT_PACKAGE = os.environ.get("PDDL_SOLVER_DEFAULT_PACKAGE", DEFAULT_SOLVER)
REQUIRE_UPSTREAM_HEALTH = os.environ.get(
    "PDDL_SOLVER_UPSTREAM_HEALTH_REQUIRED", "0"
) == "1"
RECOVERY_POLICY = os.environ.get("PDDL_SOLVER_ERROR_ROUTING") or None
BACKEND = os.environ.get("PDDL_SOLVER_BACKEND", "single")
FALLBACK_BASE = os.environ.get("PDDL_SOLVER_FALLBACK_BASE") or None
if BACKEND not in {"single", "public_then_local"} or (
    (BACKEND == "public_then_local") != bool(FALLBACK_BASE)
):
    raise RuntimeError("invalid explicit solver fallback configuration")
if FALLBACK_BASE and not RECOVERY_POLICY:
    raise RuntimeError("solver fallback requires recovery and timing control")
CONTROL_FILE = os.environ.get("PDDL_SOLVER_CONTROL_FILE")
CANCEL_FILE = os.environ.get("PDDL_SOLVER_CANCEL_FILE")
EVIDENCE_DIR = os.environ.get("PDDL_SOLVER_EVIDENCE_DIR")
if RECOVERY_POLICY and (
    RECOVERY_POLICY != POLICY_ID or not CONTROL_FILE or not CANCEL_FILE or not EVIDENCE_DIR
):
    raise RuntimeError("solver recovery requires a supported policy, control, cancellation and evidence paths")


def _cancelled():
    return bool(CANCEL_FILE and Path(CANCEL_FILE).exists())


CONTROL = ToolControl(CONTROL_FILE, cancelled=_cancelled) if RECOVERY_POLICY else None
if RECOVERY_POLICY:
    Path(EVIDENCE_DIR).mkdir(parents=True, mode=0o700, exist_ok=True)
    Path(EVIDENCE_DIR).chmod(0o700)


def _upstream_health() -> tuple[bool, dict | str]:
    if not REQUIRE_UPSTREAM_HEALTH and not FALLBACK_BASE:
        return True, {"required": False}
    url = f"{(FALLBACK_BASE or UPSTREAM_BASE).rstrip('/')}/__benchmark__/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            raw = response.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return False, {"url": url, "response": payload}
        if FALLBACK_BASE:
            validate_local_health(payload, solver=DEFAULT_PACKAGE)
        return True, {"url": url, "response": payload}
    except Exception as exc:  # noqa: BLE001 - health boundary diagnostic
        return False, f"{type(exc).__name__}: {exc}"


class State:
    lock = threading.Lock()
    call_lock = threading.Lock()
    request_attempts = 0
    solved_ok = 0
    solved_fail = 0
    ledger: list[dict] = []


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class SolverGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/__benchmark__/health":
            healthy, detail = _upstream_health()
            self._json(
                {
                    "status": "ok" if healthy else "unavailable",
                    "upstream": UPSTREAM_BASE,
                    "upstream_health": detail,
                },
                status=200 if healthy else 503,
            )
            return
        if self.path == "/__benchmark__/status":
            with State.lock:
                self._json(
                    {
                        "request_attempts": State.request_attempts,
                        "solved_ok": State.solved_ok,
                        "solved_fail": State.solved_fail,
                        "upstream": UPSTREAM_BASE,
                        "default_solver": DEFAULT_PACKAGE,
                    }
                )
            return
        if self.path == "/__benchmark__/ledger":
            with State.lock:
                self._json({"ledger": list(State.ledger)})
            return
        self._json(
            {"error": {"type": "not_found", "message": f"unknown path {self.path}"}},
            status=404,
        )

    def do_POST(self):
        if self.path.rstrip("/") != "/solve":
            self._json(
                {"error": {"type": "not_found", "message": f"unknown path {self.path}"}},
                status=404,
            )
            return
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        started = time.monotonic()
        try:
            payload = json.loads(raw.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(
                {
                    "error": {
                        "type": "invalid_json",
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                },
                status=400,
            )
            return
        if not isinstance(payload, dict):
            self._json(
                {
                    "error": {
                        "type": "invalid_body",
                        "message": "request body must be a JSON object",
                    }
                },
                status=400,
            )
            return

        domain = payload.get("domain")
        problem = payload.get("problem")
        solver = payload.get("solver") or DEFAULT_PACKAGE
        if not isinstance(domain, str) or not isinstance(problem, str):
            self._json(
                {
                    "error": {
                        "type": "invalid_body",
                        "message": "domain and problem must be PDDL strings",
                    }
                },
                status=400,
            )
            return
        if solver not in SUPPORTED_SOLVERS:
            self._json(
                {
                    "error": {
                        "type": "unsupported_solver",
                        "message": f"unsupported solver {solver!r}",
                    }
                },
                status=400,
            )
            return

        with State.lock:
            State.request_attempts += 1
            index = State.request_attempts

        if CONTROL is None:
            ok, result = solve_pddl(domain, problem, solver=solver, base_url=UPSTREAM_BASE)
        else:
            independent = os.environ.get("PDDL_SOLVER_EXTERNAL_CALL_TIMING") == "call-checkpoint-v1"
            # Legacy escrow has one owner; checkpoints use per-request state.
            # Do not serialize the native harness's legitimate background work.
            with (nullcontext() if independent else State.call_lock):
                control = ToolControl(CONTROL_FILE, cancelled=_cancelled, independent=True) if independent else CONTROL
                if _cancelled() or control.state.get("phase") == "invalid":
                    self.close_connection = True
                    return
                evidence = Path(EVIDENCE_DIR) / f"call-{index:04d}"
                try:
                    evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
                    for name, contents in (("domain.pddl", domain), ("problem.pddl", problem)):
                        target = evidence / name
                        target.write_text(contents, encoding="utf-8")
                        target.chmod(0o600)
                    request_record = {
                        "index": index, "policy": RECOVERY_POLICY, "solver": solver,
                        "upstream": UPSTREAM_BASE, "timestamp": _now(),
                        "domain_sha256": hashlib.sha256(domain.encode()).hexdigest(),
                        "problem_sha256": hashlib.sha256(problem.encode()).hexdigest(),
                    }
                    if FALLBACK_BASE:
                        request_record.update(backend=BACKEND, fallback_upstream=FALLBACK_BASE)
                    write_json(evidence / "request.json", request_record)

                    def event(value):
                        path = evidence / "events.jsonl"
                        with open(path, "a", encoding="utf-8") as handle:
                            os.chmod(path, 0o600)
                            handle.write(json.dumps({"timestamp": _now(), **value}, ensure_ascii=False) + "\n")
                        if value.get("action") in {"retry", "fallback"} and checkpoint is not None:
                            checkpoint.discard(value["reason"])
                            control.publish(rollback_count=checkpoint.discarded)

                    checkpoint = None
                    if os.environ.get("PDDL_SOLVER_EXTERNAL_CALL_TIMING") == "call-checkpoint-v1":
                        checkpoint_request = {"domain": domain, "problem": problem,
                                              "solver": solver, "upstream": UPSTREAM_BASE}
                        if FALLBACK_BASE:
                            checkpoint_request["fallback_upstream"] = FALLBACK_BASE
                        checkpoint = RequestCheckpoint(json.dumps(checkpoint_request,
                            sort_keys=True).encode(), event=event)
                    control.begin()
                    request_record["timing_control_call_id"] = control.state["call_id"]
                    write_json(evidence / "request.json", request_record)
                    charges = []
                    ok, result = solve_pddl(
                        domain, problem, solver=solver, base_url=UPSTREAM_BASE,
                        recovery_policy=RECOVERY_POLICY, event=event,
                        cancelled=_cancelled, charge=charges.append,
                        **({"fallback_base_url": FALLBACK_BASE} if FALLBACK_BASE else {}),
                    )
                    charged = charges[0] if charges else 0.0  # local argument rejection
                    write_json(evidence / "outcome.json", {
                        "action": "return_candidate", "ok": ok, "charged_seconds": charged,
                        "policy": RECOVERY_POLICY,
                    })
                    receipt = control.finish(charged)
                    if checkpoint is not None:
                        checkpoint.commit()
                    write_json(evidence / "outcome.json", {
                        "action": "return", "ok": ok, "charged_seconds": charged,
                        "policy": RECOVERY_POLICY, "host_release_acknowledged": True,
                        "timing_mode": receipt.get("timing_mode", "isolated_escrow"),
                    })
                except NativeDeadlineExpired:
                    write_json(evidence / "outcome.json", {
                        "action": "native_deadline", "candidate_discarded": True,
                        "accepted_seconds": charged, "policy": RECOVERY_POLICY,
                    })
                    control.publish(phase="native_done")
                    self.close_connection = True
                    return
                except ExternalCallInvalid as exc:
                    if exc.reason != "external_call_cancelled":
                        reason = (exc.reason if exc.reason.startswith("external_call_")
                                  else "external_call_unrecoverable")
                        control.invalidate(reason, classification=exc.reason)
                        write_json(evidence / "outcome.json", {
                            "action": "invalidate", "reason": reason, "classification": exc.reason,
                            "diagnostic": exc.diagnostic, "evidence": exc.evidence,
                        })
                    else:
                        write_json(evidence / "outcome.json", {
                            "action": "cancelled", "reason": exc.reason,
                            "phase": control.state.get("phase"),
                            "charged_seconds": control.state.get("charged_seconds", 0),
                        })
                    # Do not publish a synthetic service error into agent context.
                    self.close_connection = True
                    return
                except Exception as exc:
                    control.invalidate("external_call_control_failed", classification=type(exc).__name__)
                    self.close_connection = True
                    return
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        entry = {
            "index": index,
            "timestamp": _now(),
            "solver": solver,
            "ok": ok,
            "duration_ms": duration_ms,
            "domain_bytes": len(domain.encode()),
            "problem_bytes": len(problem.encode()),
        }
        with State.lock:
            if ok:
                State.solved_ok += 1
            else:
                State.solved_fail += 1
            State.ledger.append(entry)

        if ok:
            plan_ok, plan_text = plan_text_from_solver_result(result)
            self._json(
                {
                    "ok": True,
                    "solver": solver,
                    "plan": plan_text if plan_ok else "",
                    "result": result if isinstance(result, dict) else {"raw": result},
                }
            )
            return
        self._json(
            {
                "ok": False,
                "solver": solver,
                "error": result if isinstance(result, str) else repr(result),
            },
            status=422,
        )

    def _json(self, value: dict, status: int = 200) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), SolverGatewayHandler).serve_forever()
