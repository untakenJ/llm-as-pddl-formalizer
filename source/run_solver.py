import argparse
import json
import os
import time
import traceback

import requests

from batch_utils import format_problem_name, run_parallel

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLVER_BASE_URL = "https://solver.planning.domains:5001"
REQUEST_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.5

Parser = argparse.ArgumentParser()
Parser.add_argument("--domain", help="which domain to evaluate", choices=["blocksworld", "mystery_blocksworld", "barman", "logistics"])
Parser.add_argument("--model", help="model name (used only to locate output files; not validated)")
Parser.add_argument("--data", help="which data to formalize", choices=["Heavily_Templated_BlocksWorld-100", "Moderately_Templated_BlocksWorld-100", "Natural_BlocksWorld-100", "Heavily_Templated_Mystery_BlocksWorld-100", "Heavily_Templated_Barman-100", "Heavily_Templated_Logistics-100", "Moderately_Templated_Logistics-100", "Natural_Logistics-100"])
Parser.add_argument("--index_start", help="index to start generating result from (inclusive)")
Parser.add_argument("--index_end", help="index to end generating result from (exclusive)")
Parser.add_argument("--indices", default=None,
                    help="comma-separated problem numbers (e.g. '1,5,17'); overrides --index_start/--index_end when provided")
Parser.add_argument("--out_dir", default=None,
                    help="base output directory; defaults to {ROOT_DIR}/output")
Parser.add_argument("--solver", help="which solver to use", default="dual-bfws-ffparser")
Parser.add_argument("--prediction_type", help="which formalizer pipeline produced the PDDL", choices=["llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent"], default="llm-as-formalizer")
Parser.add_argument("--workers", type=int, default=1,
                    help="parallel worker threads for independent problems (default 1 = sequential)")


def _model_output_name(model):
    if "/" not in model:
        return model
    if "meta" in model or "google" in model or "deepseek-ai" in model:
        return model.split("/", 1)[1]
    return model


def _log_value(value, limit=16000):
    """Render remote data for a bounded, human-readable error record."""
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


def _solver_failure(stage, message, *, solver, task_url=None, response=None, payload=None):
    """Build a diagnostic that can be written directly to a per-problem file."""
    lines = [
        "solver request failed",
        f"stage: {stage}",
        f"solver: {solver}",
        f"message: {message}",
    ]
    if task_url:
        lines.append(f"task_url: {task_url}")
    if response is not None:
        status_code = getattr(response, "status_code", "unknown")
        lines.append(f"http_status: {status_code}")
    if payload is not None:
        lines.extend(("response_json:", _log_value(payload)))
    elif response is not None:
        response_text = getattr(response, "text", "")
        if response_text:
            lines.extend(("response_body:", _log_value(response_text)))
    return False, "\n".join(lines)


def _decode_solver_response(response, *, stage, solver, task_url=None):
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        return None, _solver_failure(
            stage,
            f"response was not valid JSON ({type(exc).__name__}: {exc})",
            solver=solver,
            task_url=task_url,
            response=response,
        )

    if not isinstance(payload, dict):
        return None, _solver_failure(
            stage,
            f"expected a JSON object, got {type(payload).__name__}",
            solver=solver,
            task_url=task_url,
            response=response,
            payload=payload,
        )

    status_code = getattr(response, "status_code", 200)
    if not 200 <= status_code < 300:
        return None, _solver_failure(
            stage,
            "remote service returned a non-success HTTP status",
            solver=solver,
            task_url=task_url,
            response=response,
            payload=payload,
        )
    return payload, None


def _remote_error(payload):
    if "error" in payload:
        return payload["error"]
    if "Error" in payload:
        return payload["Error"]
    return None


def _task_url(task_reference):
    if task_reference.startswith(("http://", "https://")):
        return task_reference
    return f"{SOLVER_BASE_URL}/{task_reference.lstrip('/')}"


def _plan_from_output(output):
    """Return a plan string from the generic Planutils output mapping."""
    if not isinstance(output, dict):
        return None
    if "plan" in output:
        return output["plan"] if isinstance(output["plan"], str) else None
    if len(output) == 1:
        only_value = next(iter(output.values()))
        return only_value if isinstance(only_value, str) else None
    return None


def run_solver(domain, data, problem, model, solver, prediction_type="llm-as-formalizer", out_dir_root=None):
    model_name = _model_output_name(model)

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    problem_dir = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem}'
    domain_path = f'{problem_dir}/{problem}_{model_name}_df.pddl'
    problem_path = f'{problem_dir}/{problem}_{model_name}_pf.pddl'
    missing = [path for path in (domain_path, problem_path) if not os.path.exists(path)]
    if missing:
        return False, "missing PDDL file(s):\n" + "\n".join(missing)

    with open(domain_path) as f:
        domain_file = f.read()
    with open(problem_path) as f:
        problem_file = f.read()

    req_body = {"domain" : domain_file, "problem" : problem_file}
    submit_url = f"{SOLVER_BASE_URL}/package/{solver}/solve"

    # Send job request to solve endpoint
    try:
        submit_response = requests.post(
            submit_url,
            json=req_body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return _solver_failure(
            "submit",
            f"request failed ({type(exc).__name__}: {exc})",
            solver=solver,
        )

    submit_payload, failure = _decode_solver_response(
        submit_response,
        stage="submit",
        solver=solver,
    )
    if failure:
        return failure

    task_reference = submit_payload.get("result")
    if not isinstance(task_reference, str) or not task_reference:
        remote_error = _remote_error(submit_payload)
        message = "submit response missing top-level 'result'"
        if remote_error is not None:
            message += f": {remote_error}"
        return _solver_failure(
            "submit",
            message,
            solver=solver,
            response=submit_response,
            payload=submit_payload,
        )
    task_url = _task_url(task_reference)

    # Query the result in the job
    while True:
        try:
            terminal_response = requests.post(
                task_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            return _solver_failure(
                "poll",
                f"request failed ({type(exc).__name__}: {exc})",
                solver=solver,
                task_url=task_url,
            )

        terminal_payload, failure = _decode_solver_response(
            terminal_response,
            stage="poll",
            solver=solver,
            task_url=task_url,
        )
        if failure:
            return failure
        if terminal_payload.get("status") != "PENDING":
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if "result" not in terminal_payload:
        remote_error = _remote_error(terminal_payload)
        message = "terminal response missing top-level 'result'"
        if remote_error is not None:
            message += f": {remote_error}"
        return _solver_failure(
            "terminal",
            message,
            solver=solver,
            task_url=task_url,
            response=terminal_response,
            payload=terminal_payload,
        )

    result = terminal_payload["result"]
    if not isinstance(result, dict):
        return _solver_failure(
            "terminal",
            f"top-level 'result' must be an object, got {type(result).__name__}",
            solver=solver,
            task_url=task_url,
            response=terminal_response,
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
        message = "dual-bfws-ffparser returned no plan without an empty-plan success marker"
    else:
        message = f"unsupported solver {solver!r}"

    if stderr:
        message += f"; stderr: {_log_value(stderr, limit=4000)}"
    elif stdout:
        message += f"; stdout: {_log_value(stdout, limit=4000)}"
    return _solver_failure(
        "solver-result",
        message,
        solver=solver,
        task_url=task_url,
        response=terminal_response,
        payload=terminal_payload,
    )


def _plan_text_from_solver_result(result) -> tuple[bool, str]:
    """Normalize dual-bfws-ffparser / lama-first payloads into plan text.

    ``run_solver`` may return either a structured ``{'plan': ...}`` dict or a raw
    stdout/stderr string. Missing or malformed plan payloads downgrade to an
    error message instead of raising in the batch worker.
    """
    if isinstance(result, dict):
        if "plan" in result:
            return True, result["plan"] or ""
        return False, f"solver returned dict without 'plan' key: {result!r}"
    if isinstance(result, str):
        if "Plan found with cost: 0" in result or "The empty plan solves it" in result:
            return True, ""
        return False, result
    return False, f"unexpected solver result type {type(result).__name__}: {result!r}"


def _run_solver_one(problem_number, domain, data, model, solver, prediction_type, out_root, model_name, attempts=3):
    problem_name = format_problem_name(problem_number)
    print(f"Running {problem_name}", flush=True)
    problem_dir = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}'
    os.makedirs(problem_dir, exist_ok=True)

    plan_found = False
    result = "solver did not run"
    attempt_errors = []
    for attempt in range(1, attempts + 1):
        try:
            plan_found, result = run_solver(domain, data, problem_name, model, solver, prediction_type, out_dir_root=out_root)
        except Exception as exc:
            attempt_errors.append(
                f"attempt {attempt}/{attempts}: {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc().rstrip()}"
            )
            if attempt < attempts:
                continue
            result = (
                f"solver raised an unexpected exception on all {attempts} attempt(s)\n\n"
                + "\n\n".join(attempt_errors)
            )
        break

    if plan_found:
        ok, plan_or_error = _plan_text_from_solver_result(result)
        if ok:
            plan_path = f'{problem_dir}/{problem_name}_{model_name}_plan.txt'
            with open(plan_path, 'w') as plan_file:
                plan_file.write(plan_or_error)
            return True
        plan_found = False
        result = plan_or_error

    error_path = f'{problem_dir}/{problem_name}_{model_name}_error.txt'
    with open(error_path, 'w') as error_file:
        error_file.write(
            "solver_status: failed\n"
            f"problem: {problem_name}\n"
            f"solver: {solver}\n"
            f"recorded_at_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
        )
        error_file.write(result if isinstance(result, str) else repr(result))
        error_file.write("\n")
    return False


def run_solver_batch(domain, model, data, problem_numbers, solver, prediction_type="llm-as-formalizer",
                     out_dir_root=None, workers=1):
    model_name = _model_output_name(model)
    out_root = out_dir_root or f'{ROOT_DIR}/output'

    def _worker(problem_number):
        _run_solver_one(problem_number, domain, data, model, solver, prediction_type, out_root, model_name)

    run_parallel(problem_numbers, _worker, workers=workers)


def _resolve_problem_numbers(args):
    if args.indices:
        return [int(x.strip()) for x in args.indices.split(',') if x.strip()]
    if args.index_start is None or args.index_end is None:
        raise SystemExit("Must provide either --indices or both --index_start and --index_end.")
    return list(range(eval(args.index_start), eval(args.index_end)))


if __name__=="__main__":
    args = Parser.parse_args()
    DOMAIN = args.domain
    MODEL = args.model
    DATA = args.data
    PROBLEM_NUMBERS = _resolve_problem_numbers(args)
    SOLVER = args.solver
    PREDICTION_TYPE = args.prediction_type
    OUT_DIR_ROOT = args.out_dir
    WORKERS = args.workers

    run_solver_batch(domain=DOMAIN, model=MODEL, data=DATA, problem_numbers=PROBLEM_NUMBERS, solver=SOLVER,
                     prediction_type=PREDICTION_TYPE, out_dir_root=OUT_DIR_ROOT, workers=WORKERS)
