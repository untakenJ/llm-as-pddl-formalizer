"""Standalone API-only variant of llm-as-planner.py.

Uses OpenAI's Responses API (``client.responses.create``) instead of the older
Chat Completions endpoint. Mirrors ``llm-as-formalizer-api.py``:
- structured output via ``json_schema``
- tool-calling loop driven by ``previous_response_id`` chaining
- OpenAI-hosted tools (``web_search`` and ``code_interpreter`` enabled by
  default; ``file_search``, ``image_generation``, ``mcp`` plug in the same way)
- ``TOOL_EXECUTORS`` left empty but the loop is in place for future custom
  ``function`` tools
- optional per-problem JSONL trace file capturing every request, response,
  hosted-tool event (web_search/code_interpreter/reasoning) and local
  ``function`` execution; written to the same directory as the plan text file

Note: DeepSeek's API only exposes a Chat Completions-compatible endpoint, so
``deepseek-reasoner`` is intentionally not supported here -- use the original
``llm-as-planner.py`` for that model.

Example:
    python3 source/llm-as-planner-api.py \
        --domain blocksworld \
        --model gpt-4o-mini \
        --data Heavily_Templated_BlocksWorld-100 \
        --index_start 1 --index_end 11
        # --no-trace to disable trace recording (default is on)
"""

from openai import OpenAI
import json
import os
import argparse
import datetime
import time

from batch_utils import format_problem_name, run_parallel

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_MODELS = [
    "gpt-3.5-turbo",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.1",
    "gpt-5.1-mini",
    "gpt-5.2",
    "gpt-5.2-mini",
    "gpt-5.3",
    "gpt-5.3-mini",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-5.5-mini",
]

REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


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


def build_client():
    api_key = open(f'{ROOT_DIR}/_private/key.txt').read().strip()
    return OpenAI(api_key=api_key)


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in REASONING_PREFIXES)


def _serialize_response(resp):
    """Convert the OpenAI Responses object (a pydantic model) into a JSON-friendly dict."""
    if hasattr(resp, "model_dump"):
        return resp.model_dump(mode="json", exclude_none=True)
    if hasattr(resp, "to_dict"):
        return resp.to_dict()
    return {"_repr": repr(resp)}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class _Tracer:
    """Append-only JSONL writer. No-ops when ``path`` is None."""

    def __init__(self, path):
        self.path = path
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._fp = open(path, "w", buffering=1)
        else:
            self._fp = None

    def emit(self, event: str, **fields):
        if self._fp is None:
            return
        rec = {"event": event, "ts": _now(), **fields}
        self._fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def close(self):
        if self._fp is not None:
            self._fp.close()
            self._fp = None


def _respond_with_tools(client, model, input_items, text_format, tools=None, tool_executors=None, tool_choice="auto", max_tool_rounds=8, tracer=None):
    """Drive a Responses API call, looping until the model stops calling tools.

    Only ``function`` tool calls require local execution; hosted tools
    (``web_search``, ``file_search``, ``code_interpreter`` etc.) are resolved
    server-side and never surface as ``function_call`` items.

    When ``tracer`` is provided, every request, response, and local tool
    execution is appended as a JSONL event so the full conversation -- including
    OpenAI-internal reasoning summaries, web_search queries and
    code_interpreter code/outputs -- is replayable offline.
    """

    def _create(input_payload, round_idx, previous_response_id=None):
        kwargs = {
            "model": model,
            "input": input_payload,
            "text": {"format": text_format},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id
        if _is_reasoning_model(model):
            kwargs["reasoning"] = {"summary": "auto"}

        if tracer:
            tracer.emit("request", round=round_idx, kwargs=kwargs)
        t0 = time.monotonic()
        try:
            resp = client.responses.create(**kwargs)
        except Exception as e:
            if tracer:
                tracer.emit("api_error", round=round_idx,
                            elapsed_ms=(time.monotonic() - t0) * 1000.0,
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        if tracer:
            tracer.emit("response", round=round_idx,
                        elapsed_ms=elapsed_ms,
                        response=_serialize_response(resp))
        return resp

    response = _create(input_items, round_idx=0)

    for round_idx in range(1, max_tool_rounds + 1):
        function_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]

        if not function_calls:
            return response.output_text

        followup_input = []
        for fc in function_calls:
            fn_name = fc.name
            args_for_log = fc.arguments
            duration_ms = 0.0
            try:
                fn_args = json.loads(fc.arguments or "{}")
                args_for_log = fn_args
            except json.JSONDecodeError as e:
                tool_result = {"error": f"Invalid JSON arguments: {e}"}
            else:
                if tool_executors and fn_name in tool_executors:
                    t0 = time.monotonic()
                    try:
                        tool_result = tool_executors[fn_name](**fn_args)
                    except Exception as e:
                        tool_result = {"error": f"Tool '{fn_name}' raised: {e}"}
                    duration_ms = (time.monotonic() - t0) * 1000.0
                else:
                    tool_result = {"error": f"No executor registered for tool '{fn_name}'"}

            if tracer:
                tracer.emit("tool_exec", round=round_idx,
                            name=fn_name, arguments=args_for_log,
                            result=tool_result, duration_ms=duration_ms,
                            call_id=fc.call_id)

            followup_input.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": tool_result if isinstance(tool_result, str) else json.dumps(tool_result),
            })

        response = _create(followup_input, round_idx=round_idx, previous_response_id=response.id)

    raise RuntimeError(f"Tool-calling loop exceeded max_tool_rounds={max_tool_rounds}")


def run_planner_gpt(client, domain, data, problem, model, tools=None, tool_executors=None, record_trace=True, out_dir_root=None):
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
    tracer = _Tracer(trace_path)

    t_start = time.monotonic()
    try:
        tracer.emit("start",
                    pipeline="llm-as-planner-api",
                    domain=domain, data=data, problem=problem, model=model,
                    is_reasoning_model=_is_reasoning_model(model),
                    tools=tools,
                    tool_executors=list(tool_executors.keys()) if tool_executors else [],
                    text_format=text_format,
                    prompt=prompt,
                    available_actions=available_actions,
                    example_answer=example_answer,
                    domain_description=domain_description,
                    problem_description=problem_description)

        return_string = _respond_with_tools(
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


def run_gpt_batch(client, domain, model, data, problem_numbers, tools=None, tool_executors=None,
                  record_trace=True, out_dir_root=None, workers=1):
    def _run_one(problem_number):
        problem_name = format_problem_name(problem_number)
        print(f"Running {problem_name}", flush=True)
        run_planner_gpt(
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


TOOLS = [
    {"type": "web_search"},
    {"type": "code_interpreter", "container": {"type": "auto"}},
]


TOOL_EXECUTORS = {}


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

    client = build_client()
    run_gpt_batch(
        client=client,
        domain=DOMAIN,
        model=MODEL,
        data=DATA,
        problem_numbers=PROBLEM_NUMBERS,
        tools=TOOLS or None,
        tool_executors=TOOL_EXECUTORS or None,
        record_trace=RECORD_TRACE,
        out_dir_root=OUT_DIR_ROOT,
        workers=WORKERS,
    )
