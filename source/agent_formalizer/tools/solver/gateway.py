"""Fixed-route solver gateway: agent-facing solve API over the shared remote backend.

The agent container stays on the internal Docker network. This sidecar has
bridge egress and forwards domain/problem PDDL to the same planning.domains
service used by ``source/run_solver.py``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

# Allow ``python3 /opt/.../gateway.py`` with the sibling module mounted
# next to this file inside the sidecar.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from remote_client import (  # noqa: E402
    DEFAULT_SOLVER,
    SOLVER_BASE_URL,
    SUPPORTED_SOLVERS,
    plan_text_from_solver_result,
    solve_pddl,
)


LISTEN_PORT = int(os.environ.get("PDDL_SOLVER_GATEWAY_PORT", "8768"))
UPSTREAM_BASE = os.environ.get("PDDL_SOLVER_UPSTREAM_BASE", SOLVER_BASE_URL).rstrip("/")
DEFAULT_PACKAGE = os.environ.get("PDDL_SOLVER_DEFAULT_PACKAGE", DEFAULT_SOLVER)


class State:
    lock = threading.Lock()
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
            self._json({"status": "ok", "upstream": UPSTREAM_BASE})
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

        ok, result = solve_pddl(
            domain,
            problem,
            solver=solver,
            base_url=UPSTREAM_BASE,
        )
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
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), SolverGatewayHandler).serve_forever()
