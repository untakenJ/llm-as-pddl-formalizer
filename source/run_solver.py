import requests
import time
import pandas as pd
import os
import argparse

from batch_utils import format_problem_name, run_parallel

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

def run_solver(domain, data, problem, model, solver, prediction_type="llm-as-formalizer", out_dir_root=None):
    if "meta" in model or "google" in model or "deepseek-ai" in model:
        _, model_name = model.split("/")
    else:
        model_name = model

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    domain_file = open(f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem}/{problem}_{model_name}_df.pddl').read()
    problem_file = open(f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem}/{problem}_{model_name}_pf.pddl').read()


    plan_found = None


    req_body = {"domain" : domain_file, "problem" : problem_file}

    # Send job request to solve endpoint
    solve_request_url=requests.post(f"https://solver.planning.domains:5001/package/{solver}/solve", json=req_body).json()

    # Query the result in the job
    celery_result=requests.post('https://solver.planning.domains:5001' + solve_request_url['result'])

    while celery_result.json().get("status","")== 'PENDING':
        # Query the result every 0.5 seconds while the job is executing
        celery_result=requests.post('https://solver.planning.domains:5001' + solve_request_url['result'])
        time.sleep(0.5)
    

    result = celery_result.json()['result']

    if "Error" in celery_result.json().keys():
        return False, "timeout"
    
    if solver == "lama-first":
        if not result['output']:
            if not result['stderr']:
                return False, result['stdout']
            else:
                return False, result['stderr']
        else:
            return True, result['output']
    elif solver == "dual-bfws-ffparser":
        if result['output'] == {'plan': ''}:
            if not result['stderr']:
                if "NOTFOUND" in result['stdout'] or "No plan" in result['stdout'] or "unknown" in result['stdout'] or "undeclared" in result['stdout'] or "declared twice" in result['stdout'] or "check input files" in result['stdout'] or "does not match" in result['stdout'] or "timeout" in result['call']:
                    if "Plan found with cost: 0" in result['stdout']:
                        plan_found = True
                    else:
                        plan_found = False
                else:
                    plan_found = True
                return plan_found, result['stdout']
            else:
                plan_found = False
                return plan_found, result['stderr']
        else:
            plan_found = True
            return plan_found, result['output']
        
def _run_solver_one(problem_number, domain, data, model, solver, prediction_type, out_root, model_name, attempts=3):
    problem_name = format_problem_name(problem_number)
    print(f"Running {problem_name}", flush=True)
    for i in range(attempts):
        try:
            plan_found, result = run_solver(domain, data, problem_name, model, solver, prediction_type, out_dir_root=out_root)
        except Exception:
            if i < attempts - 1:
                continue
            raise
        break

    if plan_found:
        plan_path = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}/{problem_name}_{model_name}_plan.txt'
        if not os.path.exists(os.path.dirname(plan_path)):
            os.makedirs(os.path.dirname(plan_path))
        if "Plan found with cost: 0" in result or "The empty plan solves it" in result:
            plan = ''
        else:
            plan = result['plan']
        with open(plan_path, 'w') as plan_file:
            plan_file.write(plan)
    else:
        error_path = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}/{problem_name}_{model_name}_error.txt'
        if not os.path.exists(os.path.dirname(error_path)):
            os.makedirs(os.path.dirname(error_path))
        with open(error_path, 'w') as error_file:
            error_file.write(result)


def run_solver_batch(domain, model, data, problem_numbers, solver, prediction_type="llm-as-formalizer",
                     out_dir_root=None, workers=1):
    if '/' in model:
        _, model_name = model.split('/')
    else:
        model_name = model
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

