"""Standalone API-only variant of llm-as-formalizer.py.

Supports:
- **OpenAI** Responses API (``client.responses.create``): structured JSON, optional
  hosted tools (``web_search``, ``code_interpreter``).
- **Gemini** via Google GenAI SDK on **Gemini Enterprise Agent Platform / Vertex**
  using ``GOOGLE_CLOUD_API_KEY``.
- **DeepSeek** via the OpenAI-compatible Chat Completions API using JSON mode.
- **Alibaba Model Studio** via its Singapore OpenAI-compatible endpoint using
  the explicit ``alibaba/qwen3.8-27b`` model route.
- **Logits** via its public sampling REST API and an audited model-family chat
  convention (currently Qwen3.5).
- **Self-hosted** via OpenAI-compatible Chat Completions, including local vLLM.
  Use ``self-hosted/SERVED_MODEL_ID``, ``SELF_HOSTED_BASE_URL`` (ending in /v1)
  and ``SELF_HOSTED_API_KEY``. No hosted tools are enabled on this route.

Credentials in ``_private/.env`` (python-dotenv) or shell env:
- OpenAI: ``_private/key.txt``
- Gemini Vertex: ``GOOGLE_CLOUD_API_KEY``, ``GOOGLE_CLOUD_PROJECT``,
  ``GOOGLE_CLOUD_LOCATION``. This path does not use browser/ADC auth.
- DeepSeek: ``DEEPSEEK_API_KEY``.
- Alibaba Model Studio: ``ALIBABA_API_KEY`` (Singapore-region key).
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
import hashlib
from pathlib import Path
import uuid

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
Parser.add_argument("--stream", action=argparse.BooleanOptionalAction, default=True,
                    help="Stream model responses (default on; --no-stream buffers at the provider)")
Parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=None,
                    help="Alibaba thinking mode; omitted uses the API default, --no-thinking disables it")
Parser.add_argument("--trace", action=argparse.BooleanOptionalAction, default=True,
                    help="Record per-problem JSONL trace next to the .pddl outputs (default on; pass --no-trace to disable)")
Parser.add_argument("--workers", type=int, default=1,
                    help="parallel worker threads for independent problems (default 1 = sequential)")
Parser.add_argument("--resume", action="store_true",
                    help="skip verified completed outcomes, including valid generation failures")
Parser.add_argument("--max-output-tokens", default=None,
                    help="model_max, native, or positive integer; defaults to the canonical benchmark profile")
Parser.add_argument("--model-capabilities", default=None, help="Optional model-capability registry JSON")


PDDL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain file": {"type": "string", "description": "Full PDDL domain file contents."},
        "problem file": {"type": "string", "description": "Full PDDL problem file contents."},
    },
    "required": ["domain file", "problem file"],
    "additionalProperties": False,
}



class InvalidModelOutput(ValueError):
    """A complete response failed the output contract; never resample it."""


def _task_prompt(domain, data, problem):
    folder = Path(ROOT_DIR) / 'data' / f'textual_{domain}' / data
    domain_description = (folder / f'{problem}_domain.txt').read_text()
    problem_description = (folder / f'{problem}_problem.txt').read_text()
    prompt = (
        f"You are a PDDL expert. Here is a game we are playing.\n"
        f"{domain_description}\n{problem_description}\n"
        "Write the domain and problem files in minimal PDDL.\n"
        "Please focus on the problem itself and do it independently. DO NOT reference any existing datasets."
    )
    return prompt, domain_description, problem_description


def _save_completion(out_dir, trace_path, model, prompt, output_token_policy, stream,
                     outputs=(), *, failure=None, enable_thinking=None):
    completion = {"schema_version": 2, "status": "invalid_model_output" if failure else "ok",
                  "attempt_valid": True, "generation_success": failure is None,
                  "model": model, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                  "outputs": {Path(path).name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                              for path in outputs},
                  "trace_sha256": hashlib.sha256(Path(trace_path).read_bytes()).hexdigest() if trace_path else None,
                  "stream": stream}
    if enable_thinking is not None:
        completion['enable_thinking'] = enable_thinking
    if failure:
        completion['failure'] = failure
    if output_token_policy is not None:
        completion['output_token_policy'] = output_token_policy
    temporary = Path(out_dir) / 'api_completion.json.tmp'
    temporary.write_text(json.dumps(completion, indent=2) + '\n')
    temporary.replace(Path(out_dir) / 'api_completion.json')


def run_formalizer_gpt(provider, client, domain, data, problem, model, tools=None,
                       tool_executors=None, record_trace=True, out_dir_root=None,
                       output_directory=None, output_token_policy=None, stream=True,
                       enable_thinking=None):
    if enable_thinking is not None and (provider != 'alibaba' or not isinstance(enable_thinking, bool)):
        raise ValueError('Explicit thinking mode requires Alibaba and a boolean')
    prompt, domain_description, problem_description = _task_prompt(domain, data, problem)

    input_items = [{"role": "user", "content": prompt}]
    text_format = {
        "type": "json_schema",
        "name": "pddl_files",
        "schema": PDDL_OUTPUT_SCHEMA,
        "strict": True,
    }

    out_root = out_dir_root or f'{ROOT_DIR}/output'
    model_label = sanitize_model_name(model)
    out_dir = str(output_directory) if output_directory is not None else f'{out_root}/llm-as-formalizer-api/{domain}/{data}/{model_label}/{problem}'
    os.makedirs(out_dir, exist_ok=True)
    trace_path = f'{out_dir}/{problem}_{model_label}_trace.jsonl' if record_trace else None
    # Preserve interrupted or explicitly repeated API executions. The ordinary
    # resume path below still skips a complete pair; never truncate old traces.
    prior_paths = [Path(out_dir) / f'{problem}_{model_label}_{suffix}'
                   for suffix in ('trace.jsonl', 'df.pddl', 'pf.pddl')]
    prior_paths.append(Path(out_dir) / 'api_completion.json')
    prior_paths = [path for path in prior_paths if path.exists()]
    if prior_paths:
        if any(path.is_symlink() or not path.is_file() for path in prior_paths):
            raise RuntimeError('Unexpected API evidence path type; refusing overwrite')
        history = Path(out_dir) / 'execution_history' / (str(time.time_ns()) + '-' + uuid.uuid4().hex[:8])
        history.mkdir(parents=True)
        for path in prior_paths:
            path.rename(history / path.name)
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
                    output_token_policy=output_token_policy, stream=stream,
                    enable_thinking=enable_thinking,
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
            output_token_policy=output_token_policy, stream=stream,
            **({'enable_thinking': enable_thinking} if enable_thinking is not None else {}),
        )

        tracer.emit("model_output", raw_output_text=return_string)
        try:
            return_dict = json.loads(return_string)
            if not isinstance(return_dict, dict):
                raise TypeError("PDDL output must be a JSON object")
            domain_file = return_dict["domain file"]
            problem_file = return_dict["problem file"]
            if not isinstance(domain_file, str) or not isinstance(problem_file, str):
                raise TypeError("PDDL output fields must be strings")
        except (ValueError, KeyError, TypeError) as exc:
            failure = {"reason": "invalid_model_output", "error_type": type(exc).__name__,
                       "error_message": str(exc)}
            tracer.emit("final", status="invalid_model_output", attempt_valid=True,
                        generation_success=False, elapsed_s=time.monotonic() - t_start,
                        failure=failure)
            tracer.close()
            _save_completion(out_dir, trace_path, model, prompt, output_token_policy, stream,
                             failure=failure, enable_thinking=enable_thinking)
            raise InvalidModelOutput(str(exc)) from exc

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
        tracer.close()
        _save_completion(out_dir, trace_path, model, prompt, output_token_policy, stream,
                         outputs=(df_path, pf_path), enable_thinking=enable_thinking)

        return domain_file, problem_file
    except Exception as e:
        tracer.emit("error", status="failed",
                    elapsed_s=time.monotonic() - t_start,
                    error_type=type(e).__name__,
                    error_message=str(e))
        raise
    finally:
        tracer.close()


def _api_cell_path(out_dir_root, domain, data, model):
    return Path(out_dir_root or f'{ROOT_DIR}/output') / 'llm-as-formalizer-api' / domain / data / sanitize_model_name(model)


def _freeze_api_output_policy(cell, policy):
    """An incomplete API cell must also retain its original output condition."""
    path = cell / 'api_output_policy.json'
    if path.exists():
        if json.loads(path.read_text()) != policy:
            raise ValueError('API output-token policy changed; use a new output directory')
        return
    if policy is None:
        return  # Legacy callers/outputs remain byte-compatible.
    from agent_formalizer.configuration.model_capabilities import validate_policy
    validate_policy(policy)
    if cell.exists() and any(cell.iterdir()):
        raise ValueError('Existing API cell has no frozen output policy; use a new output directory')
    cell.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(policy, stream, indent=2, sort_keys=True)
        stream.write('\n')


def _freeze_api_thinking(cell, provider, enable_thinking):
    if enable_thinking is not None and (provider != 'alibaba' or not isinstance(enable_thinking, bool)):
        raise ValueError('Explicit thinking mode requires Alibaba and a boolean')
    path = cell / 'api_generation_options.json'
    options = {'enable_thinking': enable_thinking}
    if path.exists():
        if json.loads(path.read_text()) != options:
            raise ValueError('API thinking mode changed; use a new output directory')
    elif enable_thinking is not None:
        if cell.exists() and any(p.name != 'api_output_policy.json' for p in cell.iterdir()):
            raise ValueError('Existing API cell has no frozen thinking mode; use a new output directory')
        cell.mkdir(parents=True, exist_ok=True)
        with path.open('x') as stream:
            json.dump(options, stream, indent=2)
            stream.write('\n')


def run_gpt_batch(provider, client, domain, model, data, problem_numbers, tools=None,
                  tool_executors=None, record_trace=True, out_dir_root=None, workers=1,
                  resume=False, output_token_policy=None, stream=True, enable_thinking=None):
    cell = _api_cell_path(out_dir_root, domain, data, model)
    _freeze_api_output_policy(cell, output_token_policy)
    _freeze_api_thinking(cell, provider, enable_thinking)
    def _run_one(problem_number):
        problem_name = format_problem_name(problem_number)
        out_root = out_dir_root or f'{ROOT_DIR}/output'
        model_label = sanitize_model_name(model)
        problem_dir = f'{out_root}/llm-as-formalizer-api/{domain}/{data}/{model_label}/{problem_name}'
        df_path = f'{problem_dir}/{problem_name}_{model_label}_df.pddl'
        pf_path = f'{problem_dir}/{problem_name}_{model_label}_pf.pddl'
        complete = os.path.isfile(df_path) and os.path.isfile(pf_path)
        completion_path = Path(problem_dir) / 'api_completion.json'
        if completion_path.exists():
            saved = json.loads(completion_path.read_text())
            if saved.get("stream", False) != stream:
                raise ValueError("Direct API resume transport differs from saved completion")
            if saved.get('enable_thinking') != enable_thinking:
                raise ValueError('Direct API resume thinking mode differs from saved completion')
            if saved.get("output_token_policy") != output_token_policy:
                raise ValueError("API output-token policy changed; use a new output directory")
            expected_prompt = hashlib.sha256(_task_prompt(domain, data, problem_name)[0].encode()).hexdigest()
            if saved.get('model') != model or saved.get('prompt_sha256') != expected_prompt:
                raise ValueError("API completion model/input identity changed; refusing resample")
            failed = (saved.get('status') == 'invalid_model_output'
                      and saved.get('attempt_valid') is True
                      and saved.get('generation_success') is False
                      and saved.get('outputs') == {})
            if failed:
                if os.path.exists(df_path) or os.path.exists(pf_path):
                    raise ValueError("Failed API outcome has unselected PDDL artifacts")
            elif saved.get('status') == 'ok':
                for path in (df_path, pf_path):
                    if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != saved.get('outputs', {}).get(Path(path).name):
                        raise ValueError("API completion artifact changed; refusing resample")
            else:
                raise ValueError("Unknown API completion status; refusing resample")
            if record_trace or saved.get('trace_sha256'):
                trace = Path(problem_dir) / f'{problem_name}_{model_label}_trace.jsonl'
                if not trace.is_file() or hashlib.sha256(trace.read_bytes()).hexdigest() != saved.get('trace_sha256'):
                    raise ValueError("API completion trace changed; refusing resample")
            complete = True
        elif complete:
            if output_token_policy is not None:
                raise ValueError("Legacy API results cannot resume under a new output-token policy")
        if complete and not completion_path.exists() and record_trace:
            # Legacy complete pairs are reusable only with a finished trace.
            trace = Path(problem_dir) / f'{problem_name}_{model_label}_trace.jsonl'
            try:
                last = json.loads(trace.read_text().splitlines()[-1])
                complete = last.get('event') == 'final' and last.get('status') == 'ok'
            except (OSError, ValueError, IndexError):
                complete = False
        if resume and complete:
            print(f"Skipping {problem_name} (verified terminal outcome)", flush=True)
            return
        print(f"Running {problem_name}", flush=True)
        try:
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
                output_token_policy=output_token_policy, stream=stream,
                enable_thinking=enable_thinking,
            )
        except InvalidModelOutput as exc:
            print(f"Completed {problem_name} without PDDL: {exc}", flush=True)


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

    from agent_formalizer.configuration.benchmark_profile import DEFAULT_BENCHMARK_PROFILE
    from agent_formalizer.configuration.model_capabilities import load_registry, resolve_output_policy, validate_policy
    selected_limit = args.max_output_tokens
    if selected_limit is None:
        selected_limit = DEFAULT_BENCHMARK_PROFILE.raw["condition_profile"]["overrides"].get("generation", {}).get("max_output_tokens", "native")
    elif selected_limit.isdigit():
        selected_limit = int(selected_limit)
    from api_providers import model_capability_route
    frozen_policy = _api_cell_path(OUT_DIR_ROOT, DOMAIN, DATA, MODEL) / 'api_output_policy.json'
    if RESUME and frozen_policy.is_file() and args.model_capabilities is None:
        output_token_policy = validate_policy(json.loads(frozen_policy.read_text()))
        if output_token_policy['model'] != model_capability_route(MODEL):
            raise ValueError('Frozen API policy is for a different model')
        if args.max_output_tokens is not None and selected_limit != output_token_policy['selection']:
            raise ValueError('Requested output budget differs from the frozen API policy')
    else:
        output_token_policy = resolve_output_policy(model_capability_route(MODEL), selected_limit,
            load_registry(args.model_capabilities) if args.model_capabilities else None)

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
        output_token_policy=output_token_policy, stream=args.stream,
        enable_thinking=args.thinking,
    )
