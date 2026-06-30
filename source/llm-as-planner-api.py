"""Standalone API-only variant of llm-as-planner.py.

Supports:
- **OpenAI** Responses API with structured JSON and optional hosted tools.
- **Gemini** via Google GenAI SDK on **Gemini Enterprise Agent Platform** (ADC).

Credentials in ``_private/.env`` (python-dotenv) or shell env:
- OpenAI: ``_private/key.txt``
- Gemini Enterprise: ``GOOGLE_GENAI_USE_ENTERPRISE=true``,
  ``GOOGLE_CLOUD_PROJECT``, ``GOOGLE_CLOUD_LOCATION``; ADC via
  ``gcloud auth application-default login``

Example:
    python3 source/llm-as-planner-api.py \\
        --domain blocksworld --model gpt-4o-mini \\
        --data Heavily_Templated_BlocksWorld-100 --index_start 1 --index_end 11

    python3 source/llm-as-planner-api.py \\
        --domain blocksworld --model gemini-2.5-flash \\
        --data Heavily_Templated_BlocksWorld-100 --indices 1,2,3
"""

from env_loader import load_project_dotenv

load_project_dotenv()

import json
import os
import argparse
import time

from batch_utils import format_problem_name, run_parallel
from api_providers import (
    API_MODELS,
    Tracer,
    build_provider_client,
    default_tools_for_model,
    is_reasoning_model,
    respond_with_tools,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

Parser = argparse.ArgumentParser()
Parser.add_argument("--domain", help="which domain to evaluate", choices=["blocksworld", "mystery_blocksworld", "barman", "logistics"])
Parser.add_argument("--model", help="which API-served model to use", choices=API_MODELS)
Parser.add_argument("--data", help="which data to formalize", choices=["Heavily_Templated_BlocksWorld-100", "Moderately_Templated_BlocksWorld-100", "Natural_BlocksWorld-100", "Heavily_Templated_Mystery_BlocksWorld-100", "Heavily_Templated_Barman-100", "Heavily_Templated_Logistics-100", "Moderately_Templated_Logistics-100", "Natural_Logistics-100"])
Parser.add_argument("--index_start", help="index to start generating result from (inclusive)")
Parser.add_argument("--index_end", help="index to end generating result from (exclusive)")
Parser.add_argument("--indices", default=None,
                    help="comma-separated problem numbers (e.g. '1,5,17'); overrides --index_start/--index_end when provided")
Parser.add_argument("--out_dir", default=None,
                    help="base output directory; defaults to {ROOT_DIR}/output")
Parser.add_argument("--trace", action=argparse.BooleanOptionalAction, default=True,
                    help="Record per-problem JSONL trace next to the plan files (default on; pass --no-trace to disable)")
Parser.add_argument("--workers", type=int, default=1,
                    help="parallel worker threads for independent problems (default 1 = sequential)")


PLAN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered list of grounded action calls, each formatted like '(ACTION arg1 arg2 ...)'.",
        },
    },
    "required": ["plan"],
    "additionalProperties": False,
}


DOMAIN_ACTION_SPECS = {
    "blocksworld": {
        "available_actions": (
            "(PICK-UP block): pick up a block from the table\n"
            "(PUT-DOWN block): put down a block on the table\n"
            "(STACK block1 block2): stack block1 onto block2\n"
            "(UNSTACK block1 block2): unstack block1 from block2"
        ),
        "example_answer": "(PICK-UP A)\n(STACK A B)\n(UNSTACK A B)\n(PUT-DOWN A)\n",
    },
    "mystery_blocksworld": {
        "available_actions": (
            "(ATTACK object): attack object\n"
            "(SUCCUMB object): succumb\n"
            "(OVERCOME object1 object2): overcome object1 from object2\n"
            "(FEAST object1 object2): feast object1 from object2"
        ),
        "example_answer": "(ATTACK A)\n(OVERCOME A B)\n(FEAST A B)\n(SUCCUMB A)\n",
    },
    "barman": {
        "available_actions": (
            "(GRASP hand container): grasp container with hand\n"
            "(LEAVE hand container): leave container with hand\n"
            "(FILL-SHOT shot ingredient hand1 hand2 dispenser): fill shot with ingredient from dispenser using hand1 and hand2\n"
            "(REFILL-SHOT shot ingredient hand1 hand2 dispenser): re-fill shot with ingredient from dispenser using hand1 and hand2\n"
            "(EMPTY-SHOT hand shot beverage): empty shot containing beverage with hand\n"
            "(CLEAN-SHOT shot beverage hand1 hand2): clean shot containing beverage using hand1 and hand2\n"
            "(POUR-SHOT-TO-CLEAN-SHAKER shot ingredient shaker hand level level1): pour shot into clean shaker\n"
            "(POUR-SHOT-TO-USED-SHAKER shot ingredient shaker hand level level1): pour shot into used shaker\n"
            "(EMPTY-SHAKER hand shaker cocktail level level1): empty shaker containing cocktail\n"
            "(CLEAN-SHAKER hand1 hand2 shaker): clean shaker\n"
            "(SHAKE cocktail ingredient1 ingredient2 shaker hand1 hand2): shake shaker containing cocktail\n"
            "(POUR-SHAKER-TO-SHOT beverage shot hand shaker level level1): pour shaker into shot"
        ),
        "example_answer": (
            "(GRASP right shot1)\n(FILL-SHOT shot1 ingredient10 right left dispenser10)\n"
            "(POUR-SHOT-TO-CLEAN-SHAKER shot1 ingredient10 shaker1 right l0 l1)\n"
            "(CLEAN-SHOT shot1 ingredient10 right left)\n(FILL-SHOT shot1 ingredient5 right left dispenser5)\n"
            "(GRASP left shaker1)\n(POUR-SHOT-TO-USED-SHAKER shot1 ingredient5 shaker1 right l1 l2)\n"
            "(LEAVE right shot1)\n(SHAKE cocktail1 ingredient5 ingredient10 shaker1 left right)\n"
            "(LEAVE left shaker1)\n(GRASP left shot1)\n(CLEAN-SHOT shot1 ingredient5 left right)\n"
            "(GRASP right shaker1)\n(POUR-SHAKER-TO-SHOT cocktail1 shot1 right shaker1 l2 l1)"
        ),
    },
    "logistics": {
        "available_actions": (
            "(load-truck package truck location): load a package onto a truck at a location\n"
            "(load-airplane object airplane location): load a package onto an airplane at a location\n"
            "(unload-truck package truck location): unload a package from a truck at a location\n"
            "(unload-airplane package airplane location): unload a package from an airplan at a location\n"
            "(drive-truck truck location1 location2 city): drive a truck from location1 to location2 in a city\n"
            "(fly-airplane airplane location1 location2): fly an airplane from location1 to location2"
        ),
        "example_answer": (
            "(load-truck package truck city1-1)\n(drive-truck truck city1-1 city1-2 city1)\n"
            "(unload-truck package truck city1-2)\n(load-airplane package plane city1-2)\n"
            "(fly-airplane plane city1-2 city2-1)\n(unload-airplane package plane city2-1)"
        ),
    },
}


def run_planner_gpt(provider, client, domain, data, problem, model, tools=None,
                    tool_executors=None, record_trace=True, out_dir_root=None):
    spec = DOMAIN_ACTION_SPECS[domain]
    available_actions = spec["available_actions"]
    example_answer = spec["example_answer"]

    domain_description = open(f'{ROOT_DIR}/data/textual_{domain}/{data}/{problem}_domain.txt').read()
    problem_description = open(f'{ROOT_DIR}/data/textual_{domain}/{data}/{problem}_problem.txt').read()

    prompt = (
        f"Here is a game we are playing.\n\n{domain_description}\n\n{problem_description}\n\n"
        f"Write the plan that would solve this problem.\n\n"
        f"These are the available actions:\n{available_actions}\n\n"
        f"Here is what each step in the plan should look like (one action call per item):\n{example_answer}\n"
    )

    input_items = [{"role": "user", "content": prompt}]
    text_format = {
        "type": "json_schema",
        "name": "pddl_plan",
        "schema": PLAN_OUTPUT_SCHEMA,
        "strict": True,
    }

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    out_dir = f'{out_root}/llm-as-planner-api/{domain}/{data}/{model}'
    os.makedirs(out_dir, exist_ok=True)
    plan_path = f'{out_dir}/{problem}_{model}_plan.txt'
    trace_path = f'{out_dir}/{problem}_{model}_trace.jsonl' if record_trace else None
    tracer = Tracer(trace_path)

    t_start = time.monotonic()
    try:
        tracer.emit("start",
                    pipeline="llm-as-planner-api",
                    provider=provider,
                    domain=domain, data=data, problem=problem, model=model,
                    is_reasoning_model=is_reasoning_model(model),
                    tools=tools if provider == "openai" else [],
                    tool_executors=list(tool_executors.keys()) if tool_executors else [],
                    text_format=text_format,
                    prompt=prompt,
                    available_actions=available_actions,
                    example_answer=example_answer,
                    domain_description=domain_description,
                    problem_description=problem_description)

        return_string = respond_with_tools(
            provider=provider,
            client=client,
            model=model,
            input_items=input_items,
            text_format=text_format,
            tools=tools,
            tool_executors=tool_executors,
            tracer=tracer,
        )

        return_dict = json.loads(return_string)
        plan = return_dict["plan"]

        with open(plan_path, 'w') as file:
            for line in plan:
                file.write(f"{line}\n")

        tracer.emit("final", status="ok",
                    elapsed_s=time.monotonic() - t_start,
                    raw_output_text=return_string,
                    plan_length=len(plan),
                    output_paths={"plan": plan_path})

        return plan
    except Exception as e:
        tracer.emit("error", status="failed",
                    elapsed_s=time.monotonic() - t_start,
                    error_type=type(e).__name__,
                    error_message=str(e))
        raise
    finally:
        tracer.close()


def run_gpt_batch(provider, client, domain, model, data, problem_numbers, tools=None,
                  tool_executors=None, record_trace=True, out_dir_root=None, workers=1):
    def _run_one(problem_number):
        problem_name = format_problem_name(problem_number)
        print(f"Running {problem_name}", flush=True)
        run_planner_gpt(
            provider=provider,
            client=client,
            domain=domain,
            data=data,
            problem=problem_name,
            model=model,
            tools=tools,
            tool_executors=tool_executors,
            record_trace=record_trace,
            out_dir_root=out_dir_root,
        )

    run_parallel(problem_numbers, _run_one, workers=workers)


def _resolve_problem_numbers(args):
    if args.indices:
        return [int(x.strip()) for x in args.indices.split(',') if x.strip()]
    if args.index_start is None or args.index_end is None:
        raise SystemExit("Must provide either --indices or both --index_start and --index_end.")
    return list(range(eval(args.index_start), eval(args.index_end)))


if __name__ == "__main__":
    args = Parser.parse_args()
    DOMAIN = args.domain
    MODEL = args.model
    DATA = args.data
    PROBLEM_NUMBERS = _resolve_problem_numbers(args)
    RECORD_TRACE = args.trace
    OUT_DIR_ROOT = args.out_dir
    WORKERS = args.workers

    provider, client = build_provider_client(MODEL)
    tools, tool_executors = default_tools_for_model(MODEL)

    run_gpt_batch(
        provider=provider,
        client=client,
        domain=DOMAIN,
        model=MODEL,
        data=DATA,
        problem_numbers=PROBLEM_NUMBERS,
        tools=tools,
        tool_executors=tool_executors,
        record_trace=RECORD_TRACE,
        out_dir_root=OUT_DIR_ROOT,
        workers=WORKERS,
    )
