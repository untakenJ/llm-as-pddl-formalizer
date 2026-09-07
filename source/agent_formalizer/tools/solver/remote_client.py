"""Shared compatible planner client for evaluation and the agent solver tool.

Both the offline evaluation pipeline and the in-container ``pddl-solver`` CLI
talk to the same selected planning.domains-compatible package service. The
gateway sidecar is the only solver path from a ``model_only`` attempt network.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

# Host-side callers default to the repository's local Planutils service.
# Containerized solver gateways always pass their selected upstream explicitly.
SOLVER_BASE_URL = "http://127.0.0.1:8769"
DEFAULT_SOLVER = "dual-bfws-ffparser"
REQUEST_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.5
SUPPORTED_SOLVERS = frozenset({"dual-bfws-ffparser", "lama-first"})


def _log_value(value: Any, limit: int = 16000) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        try:
            rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + f"\n... truncated {len(rendered) - limit} characters"


def solver_failure(
    stage: str,
    message: str,
    *,
    solver: str,
    task_url: str | None = None,
    http_status: Any = None,
    payload: Any = None,
    response_body: str | None = None,
) -> tuple[bool, str]:
    lines = [
        "solver request failed",
        f"stage: {stage}",
        f"solver: {solver}",
        f"message: {message}",
    ]
    if task_url:
        lines.append(f"task_url: {task_url}")
    if http_status is not None:
        lines.append(f"http_status: {http_status}")
    if payload is not None:
        lines.extend(("response_json:", _log_value(payload)))
    elif response_body:
        lines.extend(("response_body:", _log_value(response_body)))
    return False, "\n".join(lines)


def _http_json(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> tuple[dict | None, str | None, int | None, str | None]:
    """Return ``(payload, error_message, http_status, response_body)``.

    ``response_body`` is populated only when the response cannot be represented
    as a JSON object.  This preserves upstream diagnostics without duplicating
    successful or structured error payloads in the caller's audit record.
    """
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return None, f"HTTP {status} with non-JSON body", status, raw
        if isinstance(payload, dict):
            return payload, None, status, None
        return (
            None,
            f"expected a JSON object, got {type(payload).__name__}",
            status,
            raw,
        )
    except urllib.error.URLError as exc:
        return None, f"request failed ({type(exc).__name__}: {exc})", None, None
    except TimeoutError as exc:
        return None, f"request failed (TimeoutError: {exc})", None, None

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        return (
            None,
            f"response was not valid JSON ({type(exc).__name__}: {exc})",
            status,
            raw,
        )
    if not isinstance(payload, dict):
        return (
            None,
            f"expected a JSON object, got {type(payload).__name__}",
            status,
            raw,
        )
    return payload, None, status, None


def _task_url(task_reference: str, base_url: str) -> str:
    if task_reference.startswith(("http://", "https://")):
        return task_reference
    return f"{base_url.rstrip('/')}/{task_reference.lstrip('/')}"


def _remote_error(payload: dict) -> Any:
    if "error" in payload:
        return payload["error"]
    if "Error" in payload:
        return payload["Error"]
    return None


def _plan_from_output(output: Any) -> str | None:
    if not isinstance(output, dict):
        return None
    if "plan" in output:
        return output["plan"] if isinstance(output["plan"], str) else None
    if len(output) == 1:
        only_value = next(iter(output.values()))
        return only_value if isinstance(only_value, str) else None
    return None


def solve_pddl(
    domain_file: str,
    problem_file: str,
    *,
    solver: str = DEFAULT_SOLVER,
    base_url: str = SOLVER_BASE_URL,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    recovery_policy: str | None = None,
    event=None,
    cancelled=None,
    charge=None,
) -> tuple[bool, dict | str]:
    """Submit domain/problem PDDL to a planning.domains-compatible service.

    Returns ``(True, {"plan": ...})`` on success, or ``(False, diagnostic)``.
    """
    if solver not in SUPPORTED_SOLVERS:
        return solver_failure(
            "validate",
            f"unsupported solver {solver!r}",
            solver=solver,
        )
    if not isinstance(domain_file, str) or not domain_file.strip():
        return solver_failure("validate", "domain PDDL is empty", solver=solver)
    if not isinstance(problem_file, str) or not problem_file.strip():
        return solver_failure("validate", "problem PDDL is empty", solver=solver)

    if recovery_policy is not None:
        try:
            from agent_formalizer.external_calls.solver import POLICY_ID, solve
        except ModuleNotFoundError:
            from external_calls.solver import POLICY_ID, solve
        if recovery_policy != POLICY_ID:
            raise ValueError(f"unsupported solver recovery policy {recovery_policy!r}")
        ok, result, charged = solve(
            domain_file, problem_file, solver=solver, base_url=base_url,
            format_failure=solver_failure, timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            event=event or (lambda value: None),
            cancelled=cancelled or (lambda: False),
        )
        if charge is not None:
            charge(charged)
        return ok, result

    submit_url = f"{base_url.rstrip('/')}/package/{solver}/solve"
    submit_payload, error, status, response_body = _http_json(
        "POST",
        submit_url,
        body={"domain": domain_file, "problem": problem_file},
        timeout=timeout_seconds,
    )
    if error:
        return solver_failure(
            "submit",
            error,
            solver=solver,
            http_status=status,
            payload=submit_payload,
            response_body=response_body,
        )
    assert submit_payload is not None
    if status is not None and not 200 <= status < 300:
        return solver_failure(
            "submit",
            "remote service returned a non-success HTTP status",
            solver=solver,
            http_status=status,
            payload=submit_payload,
        )

    task_reference = submit_payload.get("result")
    if not isinstance(task_reference, str) or not task_reference:
        remote_error = _remote_error(submit_payload)
        message = "submit response missing top-level 'result'"
        if remote_error is not None:
            message += f": {remote_error}"
        return solver_failure(
            "submit",
            message,
            solver=solver,
            http_status=status,
            payload=submit_payload,
        )
    task_url = _task_url(task_reference, base_url)

    while True:
        terminal_payload, error, status, response_body = _http_json(
            "POST",
            task_url,
            timeout=timeout_seconds,
        )
        if error:
            return solver_failure(
                "poll",
                error,
                solver=solver,
                task_url=task_url,
                http_status=status,
                payload=terminal_payload,
                response_body=response_body,
            )
        assert terminal_payload is not None
        if status is not None and not 200 <= status < 300:
            return solver_failure(
                "poll",
                "remote service returned a non-success HTTP status",
                solver=solver,
                task_url=task_url,
                http_status=status,
                payload=terminal_payload,
            )
        if terminal_payload.get("status") != "PENDING":
            break
        time.sleep(poll_interval_seconds)

    if "result" not in terminal_payload:
        remote_error = _remote_error(terminal_payload)
        message = "terminal response missing top-level 'result'"
        if remote_error is not None:
            message += f": {remote_error}"
        return solver_failure(
            "terminal",
            message,
            solver=solver,
            task_url=task_url,
            http_status=status,
            payload=terminal_payload,
        )

    result = terminal_payload["result"]
    if not isinstance(result, dict):
        return solver_failure(
            "terminal",
            f"top-level 'result' must be an object, got {type(result).__name__}",
            solver=solver,
            task_url=task_url,
            http_status=status,
            payload=terminal_payload,
        )

    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    output = result.get("output")
    plan = _plan_from_output(output)

    if solver == "lama-first":
        if plan:
            return True, {"plan": plan}
        message = "lama-first returned no non-empty plan"
    elif solver == "dual-bfws-ffparser":
        if plan:
            return True, {"plan": plan}
        if isinstance(stdout, str) and (
            "Plan found with cost: 0" in stdout
            or "The empty plan solves it" in stdout
        ):
            return True, {"plan": ""}
        message = (
            "dual-bfws-ffparser returned no plan without an empty-plan success marker"
        )
    else:
        message = f"unsupported solver {solver!r}"

    if stderr:
        message += f"; stderr: {_log_value(stderr, limit=4000)}"
    elif stdout:
        message += f"; stdout: {_log_value(stdout, limit=4000)}"
    return solver_failure(
        "solver-result",
        message,
        solver=solver,
        task_url=task_url,
        http_status=status,
        payload=terminal_payload,
    )


def plan_text_from_solver_result(result: Any) -> tuple[bool, str]:
    """Normalize dual-bfws-ffparser / lama-first payloads into plan text."""
    if isinstance(result, dict):
        if "plan" in result:
            return True, result["plan"] or ""
        return False, f"solver returned dict without 'plan' key: {result!r}"
    if isinstance(result, str):
        if "Plan found with cost: 0" in result or "The empty plan solves it" in result:
            return True, ""
        return False, result
    return False, f"unexpected solver result type {type(result).__name__}: {result!r}"
