import os
import subprocess
import pandas as pd
import re
import argparse
from pathlib import Path

from batch_utils import format_problem_name, run_parallel
from agent_formalizer.results.execution_validity import (
    cell_dir_for_model_dir,
    refresh_cell_state,
    selected_attempt,
    selected_execution_record,
    validity_is_managed_for_model_dir,
    validity_metadata,
)

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
Parser.add_argument("--prediction_type", help="which pipeline produced the plan", choices=["llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent", "llm-as-planner", "llm-as-planner-api"])
Parser.add_argument("--csv_result", help="get full output as csv file", action='store_true')
Parser.add_argument("--workers", type=int, default=1,
                    help="parallel worker threads for independent problems (default 1 = sequential)")

def _model_output_name(model):
    if model.startswith("logits/"):
        return model.replace("/", "__")
    if "/" not in model:
        return model
    if "meta" in model or "google" in model or "deepseek-ai" in model:
        return model.split("/", 1)[1]
    return model

def standardize_blocks(plan):
    new_plan = re.sub(
            r'\b(?:b|block)?\s*(\d+)\b',  
            r' block\1',                  
            plan,
            flags=re.IGNORECASE
        )
    return new_plan

def plan_to_path(domain, plan, plan_filepath):
    if domain not in ["barman", "logistics"]:
        plan = plan.strip().lower().replace('-', '').replace('_', '')
    else:
        plan = plan.strip().lower()
    if domain == "blocksworld":
        plan = standardize_blocks(plan)
    with open(plan_filepath, 'w') as plan_file:
        plan_file.write(plan)

    return plan, plan_filepath

def validate_plan(domain, problem_file_path, plan_filepath):
    validate_executable = f"{os.path.dirname(ROOT_DIR)}/VAL/build/linux64/Release/bin/Validate"
    if domain == "blocksworld":
        domain_path = f'{ROOT_DIR}/data/textual_blocksworld/BlocksWorld-100_PDDL/domain.pddl'
    elif domain == "mystery_blocksworld":
        domain_path = f'{ROOT_DIR}/data/textual_mystery_blocksworld/Mystery_BlocksWorld-100_PDDL/domain.pddl'
    elif domain == "barman":
        domain_path = f'{ROOT_DIR}/data/textual_barman/Barman-100_PDDL/domain.pddl'
    elif domain == "logistics":
        domain_path = f'{ROOT_DIR}/data/textual_logistics/Logistics-100_PDDL/domain.pddl'
    
    command = [validate_executable, "-v", domain_path, problem_file_path, plan_filepath]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return f"Validation Output:\n{result.stdout}"
        
    except subprocess.CalledProcessError as e:
        return f"Error:\n{e.output}"

    
def _problem_file_path(domain, problem_name):
    if domain == "blocksworld":
        return f'{ROOT_DIR}/data/textual_blocksworld/BlocksWorld-100_PDDL/{problem_name}.pddl'
    if domain == "mystery_blocksworld":
        return f'{ROOT_DIR}/data/textual_mystery_blocksworld/Mystery_BlocksWorld-100_PDDL/{problem_name}.pddl'
    if domain == "barman":
        return f'{ROOT_DIR}/data/textual_barman/Barman-100_PDDL/{problem_name}.pddl'
    return f'{ROOT_DIR}/data/textual_logistics/Logistics-100_PDDL/{problem_name}.pddl'


def _validate_one_problem(
    problem_number,
    domain,
    data,
    model_name,
    prediction_type,
    out_root,
    validity_state=None,
    validity_attempt_index=1,
):
    problem_name = format_problem_name(problem_number)
    print(f"Running {problem_name}", flush=True)

    if validity_state is not None:
        attempt = selected_attempt(
            validity_state, problem_name, validity_attempt_index
        )
        execution = selected_execution_record(
            validity_state, problem_name, validity_attempt_index
        )
        if (
            attempt is None
            or execution is None
            or execution.get("generation_success") is not True
        ):
            return {
                "problem_name": problem_name,
                "plan_found": "no",
                "pddl_error": (
                    "no selected effective-valid execution with complete PDDL artifacts"
                ),
                "plan": "",
                "val_result": "",
                "is_plan_correct": "",
                "solv_inc": 0,
                "correct_inc": 0,
            }

    if prediction_type in ("llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent"):
        plan_file = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}/{problem_name}_{model_name}_plan.txt'
    else:
        plan_file = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}_{model_name}_plan.txt'

    if os.path.exists(plan_file):
        problem_file = _problem_file_path(domain, problem_name)
        plan = open(plan_file).read()

        if prediction_type in ("llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent"):
            new_plan_file = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}/{problem_name}_{model_name}_plan_VAL.txt'
        else:
            new_plan_file = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}_{model_name}_plan_VAL.txt'

        standard_plan, _ = plan_to_path(domain, plan, new_plan_file)
        val_result = validate_plan(domain, problem_file, new_plan_file)
        is_correct = "yes" if ("Error" not in val_result and "Failed" not in val_result) else "no"
        return {
            "problem_name": problem_name,
            "plan_found": "yes",
            "pddl_error": "",
            "plan": standard_plan,
            "val_result": val_result,
            "is_plan_correct": is_correct,
            "solv_inc": 1,
            "correct_inc": 1 if is_correct == "yes" else 0,
        }

    if prediction_type in ("llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent"):
        error_path = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}/{problem_name}_{model_name}_error.txt'
    else:
        error_path = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{problem_name}_{model_name}_error.txt'
    error = open(error_path).read() if os.path.exists(error_path) else "(no plan file and no error file)"
    return {
        "problem_name": problem_name,
        "plan_found": "no",
        "pddl_error": error,
        "plan": "",
        "val_result": "",
        "is_plan_correct": "",
        "solv_inc": 0,
        "correct_inc": 0,
    }


def validate_plan_batch(domain, data, model, problem_numbers, prediction_type, csv_result, out_dir_root=None,
                        workers=1):
    model_name = _model_output_name(model)

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    total = len(problem_numbers)
    validity_state = None
    validity_attempt_index = 1
    validity_summary = None
    if prediction_type == "llm-as-formalizer-agent":
        model_dir = Path(out_root) / prediction_type / domain / data / model_name
        if any(
            validity_is_managed_for_model_dir(
                model_dir, format_problem_name(problem_number)
            )
            for problem_number in problem_numbers
        ):
            cell_dir, validity_attempt_index = cell_dir_for_model_dir(model_dir)
            validity_state = refresh_cell_state(cell_dir)
            validity_summary = validity_metadata(validity_state)

    def _worker(problem_number):
        return _validate_one_problem(
            problem_number,
            domain,
            data,
            model_name,
            prediction_type,
            out_root,
            validity_state,
            validity_attempt_index,
        )

    rows = run_parallel(problem_numbers, _worker, workers=workers)

    problem_names = [r["problem_name"] for r in rows]
    plan_found = [r["plan_found"] for r in rows]
    pddl_errors = [r["pddl_error"] for r in rows]
    plans = [r["plan"] for r in rows]
    val_results = [r["val_result"] for r in rows]
    is_plan_correct = [r["is_plan_correct"] for r in rows]
    solvability = sum(r["solv_inc"] for r in rows)
    correctness = sum(r["correct_inc"] for r in rows)

    if csv_result:
        all_results_dict = {"problem_number": problem_names, "plan_found": plan_found, "error, if not found": pddl_errors, "plan, if found": plans, "val_result": val_results, "is_plan_correct": is_plan_correct}
        if validity_summary is not None:
            all_results_dict.update(
                {
                    "execution_validity_revision": [
                        validity_summary["revision"]
                    ] * len(rows),
                    "execution_validity_state_sha256": [
                        validity_summary["state_sha256"]
                    ] * len(rows),
                    "execution_validity_complete": [
                        validity_summary["complete"]
                    ] * len(rows),
                }
            )
        all_results = pd.DataFrame(all_results_dict)
        result_path = f'{out_root}/{prediction_type}/{domain}/{data}/{model_name}/{prediction_type}_{domain}_{data}_{model_name}_results.csv'
        os.makedirs(os.path.dirname(result_path), exist_ok=True)
        all_results.to_csv(result_path)

    is_formalizer = prediction_type in ("llm-as-formalizer", "llm-as-formalizer-api", "llm-as-formalizer-antigravity", "llm-as-formalizer-agent")
    print(f"Solvability: {solvability if is_formalizer else '---'}/{total}")
    print(f"Correctness: {correctness}/{total}")


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
    PREDICTION_TYPE = args.prediction_type
    CSV_RESULT = args.csv_result
    OUT_DIR_ROOT = args.out_dir
    WORKERS = args.workers

    validate_plan_batch(domain=DOMAIN, data=DATA, model=MODEL, problem_numbers=PROBLEM_NUMBERS,
                        prediction_type=PREDICTION_TYPE, csv_result=CSV_RESULT, out_dir_root=OUT_DIR_ROOT,
                        workers=WORKERS)
