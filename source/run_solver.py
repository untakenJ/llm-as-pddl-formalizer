import argparse
import os
import sys
import time
import traceback
from pathlib import Path

from batch_utils import format_problem_name, run_parallel

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

from agent_formalizer.tools.solver import (  # noqa: E402
    DEFAULT_SOLVER,
    SOLVER_BASE_URL,
    plan_text_from_solver_result,
    solve_pddl,
)
from local_solver import (  # noqa: E402
    DEFAULT_SOLVER_BACKEND,
    SUPPORTED_BACKENDS,
    base_urls_for_backend,
)
from agent_formalizer.execution_validity import (  # noqa: E402
    selected_artifact_paths_for_model_dir,
    validity_is_managed_for_model_dir,
)

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
Parser.add_argument("--solver", help="which solver to use", default=DEFAULT_SOLVER)
Parser.add_argument("--prediction_type", help="which formalizer pipeline produced the PDDL", choices=["llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent"], default="llm-as-formalizer")
Parser.add_argument("--workers", type=int, default=1,
                    help="parallel worker threads for independent problems (default 1 = sequential)")
Parser.add_argument(
    "--solver-backend",
    choices=sorted(SUPPORTED_BACKENDS),
    default=DEFAULT_SOLVER_BACKEND,
    help="solver service backend (default: local Planutils)",
)
Parser.add_argument(
    "--solver-base-url",
    default=None,
    help="explicit host-visible solver service origin; defaults from --solver-backend",
)


def _model_output_name(model):
    if model.startswith("logits/"):
        return model.replace("/", "__")
    if "/" not in model:
        return model
    if "meta" in model or "google" in model or "deepseek-ai" in model:
        return model.split("/", 1)[1]
    return model


def run_solver(
    domain,
    data,
    problem,
    model,
    solver,
    prediction_type="llm-as-formalizer",
    out_dir_root=None,
    solver_base_url=SOLVER_BASE_URL,
):
    """Load generated PDDL files and solve them on the selected backend."""
    model_name = _model_output_name(model)

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    model_dir = Path(out_root) / prediction_type / domain / data / model_name
    problem_dir = model_dir / problem
    if (
        prediction_type == "llm-as-formalizer-agent"
        and validity_is_managed_for_model_dir(model_dir, problem)
    ):
        selected = selected_artifact_paths_for_model_dir(model_dir, problem)
        if selected is None:
            return False, (
                "missing PDDL file(s): selected effective-valid execution did "
                "not produce both official PDDL artifacts"
            )
        domain_path, problem_path = selected
    else:
        domain_path = problem_dir / f'{problem}_{model_name}_df.pddl'
        problem_path = problem_dir / f'{problem}_{model_name}_pf.pddl'
    missing = [path for path in (domain_path, problem_path) if not os.path.exists(path)]
    if missing:
        return False, "missing PDDL file(s):\n" + "\n".join(map(str, missing))

    with open(domain_path) as f:
        domain_file = f.read()
    with open(problem_path) as f:
        problem_file = f.read()

    return solve_pddl(
        domain_file,
        problem_file,
        solver=solver,
        base_url=solver_base_url,
    )


def _plan_text_from_solver_result(result) -> tuple[bool, str]:
    """Normalize dual-bfws-ffparser / lama-first payloads into plan text."""
    return plan_text_from_solver_result(result)


def _run_solver_one(
    problem_number,
    domain,
    data,
    model,
    solver,
    prediction_type,
    out_root,
    model_name,
    attempts=3,
    solver_base_url=SOLVER_BASE_URL,
):
    problem_name = format_problem_name(problem_number)
    print(f"Running {problem_name}", flush=True)
    problem_dir = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}'
    os.makedirs(problem_dir, exist_ok=True)

    plan_found = False
    result = "solver did not run"
    attempt_errors = []
    for attempt in range(1, attempts + 1):
        try:
            plan_found, result = run_solver(
                domain,
                data,
                problem_name,
                model,
                solver,
                prediction_type,
                out_dir_root=out_root,
                solver_base_url=solver_base_url,
            )
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
            Path(f'{problem_dir}/{problem_name}_{model_name}_error.txt').unlink(
                missing_ok=True
            )
            return True
        plan_found = False
        result = plan_or_error

    error_path = f'{problem_dir}/{problem_name}_{model_name}_error.txt'
    Path(f'{problem_dir}/{problem_name}_{model_name}_plan.txt').unlink(
        missing_ok=True
    )
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
                     out_dir_root=None, workers=1, solver_base_url=SOLVER_BASE_URL):
    model_name = _model_output_name(model)
    out_root = out_dir_root or f'{ROOT_DIR}/output'

    def _worker(problem_number):
        _run_solver_one(
            problem_number,
            domain,
            data,
            model,
            solver,
            prediction_type,
            out_root,
            model_name,
            solver_base_url=solver_base_url,
        )

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
    DEFAULT_BASE_URL, _ = base_urls_for_backend(args.solver_backend)
    SOLVER_SERVICE_BASE_URL = (args.solver_base_url or DEFAULT_BASE_URL).rstrip("/")

    run_solver_batch(domain=DOMAIN, model=MODEL, data=DATA, problem_numbers=PROBLEM_NUMBERS, solver=SOLVER,
                     prediction_type=PREDICTION_TYPE, out_dir_root=OUT_DIR_ROOT, workers=WORKERS,
                     solver_base_url=SOLVER_SERVICE_BASE_URL)
