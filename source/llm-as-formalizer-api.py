"""Standalone API-only variant of llm-as-formalizer.py.

Supports:
- **OpenAI** Responses API (``client.responses.create``): structured JSON, optional
  hosted tools (``web_search``, ``code_interpreter``).
- **Gemini** via Google GenAI SDK on **Gemini Enterprise Agent Platform / Vertex**
  using ``GOOGLE_CLOUD_API_KEY``.
- **DeepSeek** via the OpenAI-compatible Chat Completions API using JSON mode.
- **Logits** via its public sampling REST API and an audited model-family chat
  convention (currently Qwen3.5).

Credentials in ``_private/.env`` (python-dotenv) or shell env:
- OpenAI: ``_private/key.txt``
- Gemini Vertex: ``GOOGLE_CLOUD_API_KEY``, ``GOOGLE_CLOUD_PROJECT``,
  ``GOOGLE_CLOUD_LOCATION``. This path does not use browser/ADC auth.
- DeepSeek: ``DEEPSEEK_API_KEY``.
- Logits: ``LOGITS_API_KEY``. Use an explicit dynamic model route such as
  ``logits/Qwen/Qwen3.5-4B``.

External provider transients use the standalone, bounded
``external-transient-v2`` retry policy. Each application-level attempt is
recorded in the per-problem trace.

Example:
    python3 source/llm-as-formalizer-api.py \\
        --domain blocksworld --model gpt-4o-mini \\
        --data Heavily_Templated_BlocksWorld-100 --index_start 1 --index_end 11

    python3 source/llm-as-formalizer-api.py \\
        --domain blocksworld --model gemini-2.5-flash \\
        --data Heavily_Templated_BlocksWorld-100 --indices 1,2,3

    python3 source/llm-as-formalizer-api.py \\
        --domain barman --model deepseek-v4-flash \\
        --data Heavily_Templated_Barman-100 --indices 1,2,3
"""

from env_loader import load_project_dotenv

load_project_dotenv()

import json
import os
import argparse
import time

from batch_utils import format_problem_name, run_parallel
from api_providers import (
    Tracer,
    build_provider_client,
    default_tools_for_model,
    direct_api_transient_policy,
    is_reasoning_model,
    respond_with_tools,
    sanitize_model_name,
    validate_api_model,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

Parser = argparse.ArgumentParser()
Parser.add_argument("--domain", help="which domain to evaluate", choices=["blocksworld", "mystery_blocksworld", "barman", "logistics"])
Parser.add_argument("--model", help="which API-served model to use", type=validate_api_model)
Parser.add_argument("--data", help="which data to formalize", choices=["Heavily_Templated_BlocksWorld-100", "Moderately_Templated_BlocksWorld-100", "Natural_BlocksWorld-100", "Heavily_Templated_Mystery_BlocksWorld-100", "Heavily_Templated_Barman-100", "Heavily_Templated_Logistics-100", "Moderately_Templated_Logistics-100", "Natural_Logistics-100"])
Parser.add_argument("--index_start", help="index to start generating result from (inclusive)")
Parser.add_argument("--index_end", help="index to end generating result from (exclusive)")
Parser.add_argument("--indices", default=None,
                    help="comma-separated problem numbers (e.g. '1,5,17'); overrides --index_start/--index_end when provided")
Parser.add_argument("--out_dir", default=None,
                    help="base output directory; defaults to {ROOT_DIR}/output")
Parser.add_argument("--trace", action=argparse.BooleanOptionalAction, default=True,
                    help="Record per-problem JSONL trace next to the .pddl outputs (default on; pass --no-trace to disable)")
Parser.add_argument("--workers", type=int, default=1,
                    help="parallel worker threads for independent problems (default 1 = sequential)")
Parser.add_argument("--resume", action="store_true",
                    help="skip a problem when both generated PDDL files already exist")


PDDL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain file": {"type": "string", "description": "Full PDDL domain file contents."},
        "problem file": {"type": "string", "description": "Full PDDL problem file contents."},
    },
    "required": ["domain file", "problem file"],
    "additionalProperties": False,
}


def run_formalizer_gpt(provider, client, domain, data, problem, model, tools=None,
                       tool_executors=None, record_trace=True, out_dir_root=None):
    domain_description = open(f'{ROOT_DIR}/data/textual_{domain}/{data}/{problem}_domain.txt').read()
    problem_description = open(f'{ROOT_DIR}/data/textual_{domain}/{data}/{problem}_problem.txt').read()

    prompt = (
        f"You are a PDDL expert. Here is a game we are playing.\n"
        f"{domain_description}\n{problem_description}\n"
        "Write the domain and problem files in minimal PDDL.\n"
        "Please focus on the problem itself and do it independently. DO NOT reference any existing datasets."
    )

    input_items = [{"role": "user", "content": prompt}]
    text_format = {
        "type": "json_schema",
        "name": "pddl_files",
        "schema": PDDL_OUTPUT_SCHEMA,
        "strict": True,
    }

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    model_label = sanitize_model_name(model)
    out_dir = f'{out_root}/llm-as-formalizer-api/{domain}/{data}/{model_label}/{problem}'
    os.makedirs(out_dir, exist_ok=True)
    trace_path = f'{out_dir}/{problem}_{model_label}_trace.jsonl' if record_trace else None
    tracer = Tracer(trace_path)

    t_start = time.monotonic()
    try:
        tracer.emit("start",
                    pipeline="llm-as-formalizer-api",
                    provider=provider,
                    domain=domain, data=data, problem=problem, model=model,
                    is_reasoning_model=is_reasoning_model(model),
                    tools=tools if provider == "openai" else [],
                    tool_executors=list(tool_executors.keys()) if tool_executors else [],
                    transient_error_policy=direct_api_transient_policy(),
                    text_format=text_format,
                    prompt=prompt,
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
        domain_file = return_dict["domain file"]
        problem_file = return_dict["problem file"]

        df_path = f'{out_dir}/{problem}_{model_label}_df.pddl'
        pf_path = f'{out_dir}/{problem}_{model_label}_pf.pddl'

        with open(df_path, 'w') as df:
            df.write(domain_file)
        with open(pf_path, 'w') as pf:
            pf.write(problem_file)

        tracer.emit("final", status="ok",
                    elapsed_s=time.monotonic() - t_start,
                    raw_output_text=return_string,
                    domain_file_chars=len(domain_file),
                    problem_file_chars=len(problem_file),
                    output_paths={"df": df_path, "pf": pf_path})

        return domain_file, problem_file
    except Exception as e:
        tracer.emit("error", status="failed",
                    elapsed_s=time.monotonic() - t_start,
                    error_type=type(e).__name__,
                    error_message=str(e))
        raise
    finally:
        tracer.close()


def run_gpt_batch(provider, client, domain, model, data, problem_numbers, tools=None,
                  tool_executors=None, record_trace=True, out_dir_root=None, workers=1,
                  resume=False):
    def _run_one(problem_number):
        problem_name = format_problem_name(problem_number)
        out_root = out_dir_root or f'{ROOT_DIR}/output'
        model_label = sanitize_model_name(model)
        problem_dir = f'{out_root}/llm-as-formalizer-api/{domain}/{data}/{model_label}/{problem_name}'
        df_path = f'{problem_dir}/{problem_name}_{model_label}_df.pddl'
        pf_path = f'{problem_dir}/{problem_name}_{model_label}_pf.pddl'
        if resume and os.path.isfile(df_path) and os.path.isfile(pf_path):
            print(f"Skipping {problem_name} (complete PDDL pair exists)", flush=True)
            return
        print(f"Running {problem_name}", flush=True)
        run_formalizer_gpt(
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
    RESUME = args.resume

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
        resume=RESUME,
    )
