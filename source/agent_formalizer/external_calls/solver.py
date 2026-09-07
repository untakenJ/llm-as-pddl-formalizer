"""Versioned planning.domains-compatible solver policy, independent of harnesses."""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .retry import Action, Decision, ExternalCallInvalid, RetryController, RetryPolicy

POLICY_ID = "solver-transient-v1"
DEFAULT_POLICY = RetryPolicy(2, (5.0, 15.0), 60.0, 300.0)
TASK_WAIT_SECONDS = 180.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward submitted PDDL to an unconfigured origin.


@dataclass
class Response:
    payload: dict | None = None
    status: int | None = None
    body: str = ""
    error: str = ""
    error_type: str = ""
    headers: dict = field(default_factory=dict)


def request_json(method, url, *, body=None, timeout=30.0) -> Response:
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers)
    try:
        try:
            result = urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            result = exc
        with result:
            response = Response(status=result.code, headers=dict(result.headers.items()),
                                body=result.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        cause = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        return Response(error=str(cause), error_type=type(cause).__name__)
    try:
        value = json.loads(response.body)
        if not isinstance(value, dict):
            raise ValueError("response must be a JSON object")
        response.payload = value
    except (ValueError, TypeError) as exc:
        response.error = str(exc)
        response.error_type = "InvalidResponse"
    return response


def retry(reason: str, *, ambiguous=False) -> Decision:
    return Decision(Action.RETRY, reason,
                    Action.RETURN if ambiguous else Action.INVALIDATE,
                    replay="new_task" if ambiguous else "same_request")


def classify_response(response: Response, *, stage: str) -> Decision:
    """Classify only the envelope and planner diagnostics, never PDDL arguments."""
    status = response.status
    if response.error_type in {"SSLCertVerificationError", "CertificateError"}:
        return Decision(Action.INVALIDATE, "solver_certificate_error")
    if status == 429:
        return retry("solver_rate_limited")
    if status in {408, 502, 503, 504, 520, 521, 522, 523, 524, 525, 529}:
        return retry("solver_service_unavailable")
    if status in {401, 403}:
        return Decision(Action.INVALIDATE, "solver_authentication_error")
    if status is not None and 300 <= status < 400:
        return Decision(Action.INVALIDATE, "solver_untrusted_redirect")
    if status == 413:
        return Decision(Action.RETURN, "solver_request_size_limit")
    if status in {400, 404, 405, 415, 422}:
        return Decision(Action.INVALIDATE, "solver_protocol_configuration_error")
    if response.error:
        return retry("solver_transport_error" if response.error_type != "InvalidResponse"
                     else "solver_response_protocol_error")
    payload = response.payload or {}
    local = payload.get("local_backend")
    if isinstance(local, dict):
        worker = local.get("worker") or {}
        error = local.get("error") or {}
        kind = error.get("type") if isinstance(error, dict) else None
        if isinstance(worker, dict) and worker.get("oom_killed"):
            return retry("solver_worker_oom", ambiguous=True)
        if kind in {"FileNotFoundError", "PermissionError", "ValueError", "KeyError"}:
            return Decision(Action.INVALIDATE, "solver_runtime_configuration_error")
        if kind == "worker_control_timeout":
            return retry("solver_worker_control_timeout", ambiguous=True)
        return retry("solver_worker_service_error")
    envelope_error = payload.get("error", payload.get("Error"))
    if envelope_error:
        error = envelope_error if isinstance(envelope_error, str) else json.dumps(envelope_error)
        if any(part in error for part in (
            "Required argument", "does not exist", "does not contain", "is not installed",
            "not configured correctly", "Adaptor Not Found", "unsupported local solver package",
        )):
            return Decision(Action.INVALIDATE, "solver_protocol_configuration_error")
        if "server-side error trying to run a planutils package" in error:
            return retry("solver_server_side_error", ambiguous=stage == "poll")
        # A structured local compatible service may also report worker failures.
        if "queue is full" in error:
            return retry("solver_service_unavailable")
        return retry("solver_unexplained_service_error", ambiguous=stage == "poll")
    if status is not None and not 200 <= status < 300:
        return retry("solver_http_error", ambiguous=stage == "poll" and status == 500)
    if stage == "submit":
        if isinstance(payload.get("result"), str) and payload["result"]:
            return Decision(Action.RETURN, "solver_submitted")
        return retry("solver_response_protocol_error")
    if payload.get("status") == "PENDING":
        return Decision(Action.RETURN, "solver_pending")
    result = payload.get("result")
    if not isinstance(result, dict):
        return retry("solver_response_protocol_error")
    stdout, stderr = result.get("stdout", ""), result.get("stderr", "")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        return retry("solver_response_protocol_error")
    text = stdout + "\n" + stderr
    backend = result.get("local_backend") or {}
    if not isinstance(backend, dict):
        return retry("solver_response_protocol_error")
    plan = extract_plan(result.get("output"))
    if plan and any(line.strip() and not line.lstrip().startswith(";") for line in plan.splitlines()):
        # A solver (especially an anytime planner) may leave a plan before a
        # later timeout. Preserve that actual artifact; VAL decides validity.
        # Zero cost alone does not mean zero actions in cost-based planners.
        return Decision(Action.RETURN, "solver_plan")
    if backend.get("timed_out") or re.search(r"(?im)^\s*(?:Request Time Out|.*time limit exceeded)\s*$", text):
        return retry("solver_execution_timeout", ambiguous=True)
    if re.search(r"(?im)^.*(?:can't find (?:operator|fact) file|Package \S+ (?:not found|is not installed|is not executable)|singularity: command not found).*$", text):
        return Decision(Action.INVALIDATE, "solver_runtime_configuration_error")
    if re.search(r"(?im)^.*(?:Segmentation fault|std::bad_alloc|Assertion.*failed|wrong specifier|debug me|Exception of unknown type).*$", text) or re.search(
        r"(?im)^\s*MemoryError(?:\s*:.*)?\s*$|^\s*Killed(?:\s*\([^\n]*\))?\s*$|^.*:\s*line \d+:\s*\d+\s+Killed\b", text
    ):
        return retry("solver_internal_failure", ambiguous=True)
    if re.search(r"(?im)^.*syntax error in line \d+", text) or re.search(
        r"(?im)^\s*(?:undeclared (?:predicate|function|variable)|unknown constant|type mismatch|type of var .*does not match|(?:predicate|function) .* (?:declared twice|is declared to have)|double metric specification)", text
    ):
        return Decision(Action.RETURN, "solver_input_error")
    if re.search(r"(?im)^.*(?:increase MAX_[A-Z_]+|too many axioms|not an ADL problem|not a linear task|requirement .*not supported)", text):
        return Decision(Action.RETURN, "solver_input_capability_limit")
    if re.search(r"(?im)^\s*(?:illegal initial state|illegal goal formula|op .* has illegal (?:precondition|effects)|equality in (?:initial state|effect)|unknown optimization method)", text):
        return Decision(Action.RETURN, "solver_input_error")
    if "The empty plan solves it" in stdout or re.search(r"(?m)^Plan found with cost: 0(?:\.0*)?\s*$", stdout):
        return Decision(Action.RETURN, "solver_empty_plan")
    if re.search(r"(?im)^\s*ff:.*(?:No plan will solve it|Problem unsolvable)", stdout):
        return Decision(Action.RETURN, "solver_unsolvable")
    # A first-stage NOTFOUND alone is not the terminal result of Dual BFWS.
    if re.search(r"Plan found with cost: NOTFOUND\s*\nBFS search completed in [^\n]+\s*$", stdout):
        return Decision(Action.RETURN, "solver_search_exhausted")
    return retry("solver_missing_terminal_result", ambiguous=True)


def extract_plan(output):
    if not isinstance(output, dict):
        return None
    value = output.get("plan") if "plan" in output else next(iter(output.values()), None) if len(output) == 1 else None
    return value if isinstance(value, str) else None


def solve(domain: str, problem: str, *, solver: str, base_url: str,
          format_failure, timeout_seconds=30.0, poll_interval_seconds=0.5,
          policy=DEFAULT_POLICY, request=request_json, event=lambda value: None,
          cancelled=lambda: False, monotonic=time.monotonic, sleep=time.sleep):
    """Return (ok, legacy result, charged seconds) or raise ExternalCallInvalid.

    One bounded controller spans submit, poll and re-solve failures. Poll errors
    preserve task identity. A PENDING task is never duplicated. Callers escrow
    active time and commit only charged_seconds before releasing a tool result.
    """
    recovery = RetryController(policy, monotonic=monotonic)
    stage, task_url = "submit", None
    solve_started, discarded_transport = monotonic(), 0.0
    task_started = None
    physical = submissions = ambiguous_failures = 0
    while True:
        if cancelled():
            raise ExternalCallInvalid("external_call_cancelled")
        remaining = recovery.remaining()
        if remaining is not None and remaining <= 0:
            raise ExternalCallInvalid("solver_recovery_deadline", evidence={"submissions": submissions})
        url = f"{base_url.rstrip('/')}/package/{solver}/solve" if stage == "submit" else task_url
        if stage == "submit":
            submissions += 1
            solve_started, discarded_transport = monotonic(), 0.0
        started = monotonic()
        limit = timeout_seconds if remaining is None else min(timeout_seconds, remaining)
        if task_started is not None:
            limit = min(limit, max(0.001, TASK_WAIT_SECONDS - (started - task_started)))
        response = request("POST", url,
            body={"domain": domain, "problem": problem} if stage == "submit" else None,
            timeout=max(0.001, limit))
        duration = monotonic() - started
        physical += 1
        decision = classify_response(response, stage=stage)
        record = {"physical_attempt": physical, "submission": submissions, "stage": stage,
                  "task_url": task_url, "http_status": response.status, "reason": decision.reason,
                  "duration_seconds": duration, "policy": POLICY_ID}
        # Domain-specific restricted evidence, not a generic model/raw ledger.
        event({**record, "response": response.payload, "response_body": response.body,
               "transport_error": response.error, "error_type": response.error_type})
        if decision.reason == "solver_submitted":
            task_url = urllib.parse.urljoin(base_url.rstrip('/') + '/', response.payload["result"])
            origin = urllib.parse.urlsplit(base_url)
            target = urllib.parse.urlsplit(task_url)
            if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
                raise ExternalCallInvalid("solver_untrusted_task_url")
            stage, task_started = "poll", monotonic()
            continue
        if decision.reason == "solver_pending":
            if monotonic() - task_started >= TASK_WAIT_SECONDS:
                raise ExternalCallInvalid("solver_task_wait_exhausted", evidence={"task_url": task_url})
            recovery.wait(min(poll_interval_seconds, max(0.0, TASK_WAIT_SECONDS - (monotonic() - task_started))),
                          cancelled=cancelled, sleep=sleep)
            continue
        if decision.action == Action.RETRY and decision.exhausted == Action.RETURN:
            ambiguous_failures += 1
        action, delay = recovery.decide(decision, headers=response.headers)
        if action == Action.RETURN and decision.action == Action.RETRY and ambiguous_failures < policy.max_retries + 1:
            # Transport failures cannot count as evidence of repeated PDDL-
            # dependent failure. A mixed exhausted budget fails closed.
            action = Action.INVALIDATE
        if action == Action.RETRY:
            event({**record, "action": "retry", "delay_seconds": delay, "retry": recovery.retries})
            recovery.wait(delay, cancelled=cancelled, sleep=sleep)
            if stage == "poll" and decision.replay == "new_task":
                # The service returned an execution failure; start a fresh solve.
                stage, task_url, task_started = "submit", None, None
            else:
                discarded_transport += duration + delay
            continue
        diagnostic = format_failure(stage, response.error or decision.reason, solver=solver,
                                    task_url=task_url, http_status=response.status,
                                    payload=response.payload, response_body=response.body)[1]
        if action == Action.INVALIDATE:
            raise ExternalCallInvalid(decision.reason, diagnostic=diagnostic,
                                      evidence={"submissions": submissions, "physical_attempts": physical})
        charged = max(0.0, monotonic() - solve_started - discarded_transport)
        event({"action": "return", "reason": decision.reason, "charged_seconds": charged,
               "submissions": submissions, "physical_attempts": physical})
        if decision.reason == "solver_empty_plan":
            return True, {"plan": ""}, charged
        if decision.reason == "solver_plan":
            return True, {"plan": extract_plan(response.payload["result"]["output"])}, charged
        return False, diagnostic, charged
