"""Explicit public-then-local policy; no services, adapters or campaign state.

One caller checkpoint spans both backends. Backend failures stay in private
evidence; only the selected backend's final solve is charged and delivered.
"""

from __future__ import annotations

import hashlib
import time
from urllib.parse import urlsplit

from . import solver as single
from .retry import Action, ExternalCallInvalid

POLICY_ID = "solver-public-then-local-v1"
BACKEND = "public_then_local"
# Leave room beneath the existing 600-second tool transport/control guard.
BACKEND_WALL_SECONDS = {"public": 210.0, "local": 360.0}
LOCAL_PLANNER_SECONDS = 90.0


def validate_local_health(payload, *, solver=None):
    """Do not silently run the fallback on a legacy 60-second service."""
    config = payload.get("config", {}) if isinstance(payload, dict) else {}
    if (not isinstance(payload, dict) or payload.get("status") != "ok"
            or payload.get("backend") != "local-planutils"
            or not isinstance(config, dict)
            or config.get("timeout_seconds") != LOCAL_PLANNER_SECONDS
            or (solver is not None and (not isinstance(config.get("allowed_solvers"), list)
                                        or solver not in config["allowed_solvers"]))):
        raise ExternalCallInvalid("solver_fallback_configuration_error",
            diagnostic="public_then_local requires a healthy local Planutils service with "
                       "--timeout 90 and the requested package installed",
            evidence={"expected_timeout_seconds": LOCAL_PLANNER_SECONDS, "health": payload})


def solve(domain, problem, *, solver, base_url, fallback_base_url,
          format_failure, timeout_seconds=30.0, poll_interval_seconds=0.5,
          event=lambda value: None, cancelled=lambda: False,
          request=None, monotonic=time.monotonic, sleep=time.sleep):
    """Return (ok, diagnostic/plan, charged seconds), or an infra invalidator.

    Each backend owns one v1 retry budget; no outer retry multiplies it.
    Confirmed input/capability/no-plan results never cause fallback. Cancel,
    certificate, authentication, fixed-route and control failures fail closed.
    A pending task's wait cap may cause fallback, never a duplicate public job.
    """
    for origin in (base_url, fallback_base_url):
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("solver backends must be explicit HTTP(S) origins without credentials")
    if base_url.rstrip("/") == fallback_base_url.rstrip("/"):
        raise ValueError("public and local solver origins must be different")
    request = request or single.request_json
    identity = {"domain_sha256": hashlib.sha256(domain.encode()).hexdigest(),
                "problem_sha256": hashlib.sha256(problem.encode()).hexdigest()}
    event({"action": "wrapper_start", "wrapper_policy": POLICY_ID, **identity})

    for backend, origin in (("public", base_url), ("local", fallback_base_url)):
        started = monotonic()
        last_decision = None
        terminal = None
        failure = None
        health_verified = False
        physical_source = "solver"
        wall_limit = BACKEND_WALL_SECONDS[backend]

        def check():
            if cancelled():
                raise ExternalCallInvalid("external_call_cancelled")
            remaining = wall_limit - (monotonic() - started)
            if remaining <= 0:
                raise ExternalCallInvalid("solver_backend_deadline",
                    diagnostic=f"{backend} solver recovery exceeded {wall_limit:g}s",
                    evidence={"backend": backend, "wall_limit_seconds": wall_limit})
            return remaining

        def bounded_request(method, url, **kwargs):
            nonlocal health_verified, physical_source
            kwargs["timeout"] = min(kwargs["timeout"], check())
            if backend == "local" and not health_verified:
                physical_source = "local_health"
                health = request("GET", origin.rstrip("/") + "/__benchmark__/health",
                                 timeout=kwargs["timeout"])
                event({"action": "backend_health", "backend": backend,
                       "wrapper_policy": POLICY_ID, "http_status": health.status,
                       "response": health.payload, "transport_error": health.error})
                check()
                if health.error or health.status != 200:
                    # Let the SAME backend retry controller handle this failure;
                    # no nested health retry loop multiplies its budget.
                    if single.classify_response(health, stage="submit").action == Action.RETURN:
                        raise ExternalCallInvalid("solver_fallback_configuration_error",
                            diagnostic=f"local health endpoint rejected its fixed probe: HTTP {health.status}",
                            evidence={"http_status": health.status, "health": health.payload})
                    return health
                if isinstance(health.payload, dict) and health.payload.get("status") == "unavailable":
                    return single.Response(status=503, payload=health.payload)
                validate_local_health(health.payload, solver=solver)
                health_verified = True
                kwargs["timeout"] = min(kwargs["timeout"], check())
            physical_source = "solver"
            # Check the guard only after backend_event has saved the physical
            # response, including a slow final response that must be discarded.
            return request(method, url, **kwargs)

        def bounded_sleep(seconds):
            sleep(min(seconds, check()))
            check()

        def backend_event(value):
            nonlocal last_decision, terminal
            if "physical_attempt" in value and "action" not in value:
                value = {**value, "request_source": physical_source}
                last_decision = single.classify_response(single.Response(
                    payload=value.get("response"), status=value.get("http_status"),
                    body=value.get("response_body", ""), error=value.get("transport_error", ""),
                    error_type=value.get("error_type", "")), stage=value["stage"])
            if value.get("action") == "return":
                terminal = value
                value = {**value, "action": "backend_return"}
            event({**value, "backend": backend, "upstream": origin, "wrapper_policy": POLICY_ID})
            if "physical_attempt" in value and "action" not in value:
                check()

        event({"action": "backend_start", "backend": backend, "upstream": origin,
               "wrapper_policy": POLICY_ID, "wall_limit_seconds": wall_limit,
               "planner_timeout_seconds": 30.0 if backend == "public" else LOCAL_PLANNER_SECONDS})
        try:
            result = single.solve(domain, problem, solver=solver, base_url=origin,
                format_failure=format_failure, timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds, request=bounded_request,
                event=backend_event, cancelled=cancelled, monotonic=monotonic, sleep=bounded_sleep)
        except ExternalCallInvalid as exc:
            failure = exc
            eligible = exc.reason in {"solver_backend_deadline", "solver_task_wait_exhausted",
                                      "solver_recovery_deadline"} or (
                last_decision is not None and last_decision.action == Action.RETRY
                and exc.reason == last_decision.reason)
            if backend == "local" or not eligible:
                event({"action": "wrapper_invalid", "backend": backend, "reason": exc.reason,
                       "wrapper_policy": POLICY_ID, "diagnostic": exc.diagnostic,
                       "evidence": exc.evidence})
                raise
        else:
            eligible = (not result[0] and last_decision is not None
                        and last_decision.action == Action.RETRY)
            if backend == "local" or not eligible:
                event({**(terminal or {}), "action": "return", "backend": backend,
                       "wrapper_policy": POLICY_ID, "charged_seconds": result[2]})
                return result

        # A fallback is itself hidden recovery. The caller must roll back its
        # checkpoint here too, including when remote exhaustion raised rather
        # than returning an ambiguous failure. Never charge the remote candidate.
        if cancelled():
            raise ExternalCallInvalid("external_call_cancelled")
        event({"action": "fallback", "reason": failure.reason if failure else terminal["reason"],
               "from_backend": "public", "to_backend": "local", "wrapper_policy": POLICY_ID,
               "discarded_backend_seconds": monotonic() - started, **identity})

    raise AssertionError("unreachable backend routing state")
