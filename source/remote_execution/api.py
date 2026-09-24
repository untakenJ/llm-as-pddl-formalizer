"""Node-side API-only orchestration, reusing the standalone formalizer and eval.

One valid generation per problem, including valid failures. A transport retry
is owned by api_providers; explicit job resume only fills missing valid slots.
Terminal generation directories are immutable and can be checkpointed before
the cell's deterministic evaluation finishes. No harness loop is introduced.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json

from .checkpoints import copy_file
from .protocol import digest, file_hash, private_json, read_json, safe_path

PIPELINE = "llm-as-formalizer-api"


def load_formalizer(workspace):
    spec = importlib.util.spec_from_file_location("remote_direct_formalizer", workspace / "source/llm-as-formalizer-api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model_route(model):
    """Map standalone CLI names to credential-registry routes, not new models."""
    from api_providers import is_deepseek_model, is_gemini_model, validate_api_model
    validate_api_model(model)
    if "/" in model:
        return model
    provider = "google-vertex" if is_gemini_model(model) else "deepseek" if is_deepseek_model(model) else "openai"
    return provider + "/" + model


def case_directory(output, parameters, problem):
    from api_providers import sanitize_model_name
    return output / PIPELINE / parameters["domain"] / parameters["dataset"] / sanitize_model_name(parameters["model"]) / problem


def case_identity(spec, workspace, problem):
    p = spec["parameters"]
    folder = workspace / "data" / ("textual_" + p["domain"]) / p["dataset"]
    return {"request_sha256": digest(spec), "problem": problem,
            "input_sha256": {suffix: file_hash(folder / f"{problem}_{suffix}.txt") for suffix in ("domain", "problem")}}


def selected_case(directory, identity=None, *, verify_files=True):
    """Select first valid outcome, never best outcome; verify immutable evidence."""
    for execution in sorted((directory / "executions").glob("execution-*")):
        safe_path(directory, execution.relative_to(directory).as_posix())
        request = execution / "api_request.json"
        if request.exists() and identity is not None and read_json(request) != identity:
            raise ValueError("API resume identity/input mismatch")
        terminal = execution / "execution_result.json"
        if not terminal.is_file():
            continue
        record = read_json(terminal)
        if record.get("complete") is not True or record.get("attempt_valid") is not True:
            raise ValueError("Malformed API terminal record")
        if not request.is_file() or record.get("identity") != read_json(request):
            raise ValueError("API terminal identity mismatch")
        if verify_files:
            for name, expected in record["files"].items():
                if file_hash(safe_path(execution, name)) != expected:
                    raise ValueError("API execution evidence changed; refusing resample")
        return execution, record
    return None


def run_case(formalizer, provider, client, spec, workspace, output, problem):
    p = spec["parameters"]
    directory = case_directory(output, p, problem)
    identity = case_identity(spec, workspace, problem)
    selected = selected_case(directory, identity) if directory.exists() else None
    if selected is not None:
        return selected
    executions = directory / "executions"
    executions.mkdir(parents=True, exist_ok=True)
    previous = list(executions.glob("execution-*"))
    number = max((int(path.name.split("-", 1)[1]) for path in previous), default=0) + 1
    execution = executions / f"execution-{number:06d}"
    execution.mkdir()  # Single job owner + disjoint problem workers, no overwrite.
    private_json(execution / "api_request.json", identity, replace=False)
    record = {"schema_version": 1, "complete": True, "attempt_valid": True,
              "generation_success": False, "identity": identity, "execution": execution.name}
    try:
        formalizer.run_formalizer_gpt(provider, client, p["domain"], p["dataset"], problem,
            p["model"], tools=None, tool_executors=None, record_trace=True, output_directory=execution,
            **({"output_token_policy": p["output_token_policy"]} if "output_token_policy" in p else {}))
        record["generation_success"] = True
        record["reason"] = "generated"
    except Exception as exc:
        from api_providers import classify_direct_api_error
        # A delivered malformed JSON/PDDL response is a model outcome, not an
        # excuse to obtain another sample. Unknown runner/provider errors fail
        # closed and retain their full per-call trace for manual diagnosis.
        events = []
        for trace in execution.glob("*_trace.jsonl"):
            events.extend(json.loads(line) for line in trace.read_text().splitlines() if line.strip())
        delivered = any(row.get("event") == "model_output" for row in events)
        responses = [row.get("response", {}) for row in events if row.get("event") == "response"]
        choices = responses[-1].get("choices", []) if responses else []
        # Missing choices/message is an uncertain provider-protocol failure,
        # distinct from a real assistant message with empty/truncated content.
        empty = (isinstance(exc, RuntimeError) and "returned empty JSON content" in str(exc)
                 and bool(choices) and isinstance(choices[0].get("message"), dict)
                 and choices[0]["message"].get("role") == "assistant")
        # Explicit provider termination/refusal is also an outcome, not a
        # transient to resample. Unexplained missing candidates fail closed.
        gemini_outcome = any(row.get("event") == "gemini_rejection" and (
            row.get("finish_reason") in {"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
            or isinstance(row.get("prompt_feedback"), dict) and row["prompt_feedback"].get("block_reason") in {
                "SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT"}) for row in events)
        from agent_formalizer.configuration.model_capabilities import OutputBudgetInputError
        model_failure = (delivered and isinstance(exc, (ValueError, KeyError, TypeError))) or empty or gemini_outcome or isinstance(exc, OutputBudgetInputError)
        record.update({"attempt_valid": bool(model_failure), "error_type": type(exc).__name__,
                       "error_classification": classify_direct_api_error(exc),
                       "reason": "invalid_model_output" if model_failure else "api_or_runner_infrastructure_error"})
    record["files"] = {path.name: file_hash(path) for path in execution.iterdir() if path.is_file()}
    terminal = "execution_result.json" if record["attempt_valid"] else "infra_invalid.json"
    private_json(execution / terminal, record, replace=False)
    return (execution, record) if record["attempt_valid"] else None


def evaluate(spec, output, selected, generation, scheduling):
    """Fresh eval generation; never overwrite prior solver/VAL evidence."""
    from api_providers import sanitize_model_name
    from run_solver import DEFAULT_SOLVER, run_solver_batch
    from run_val import validate_plan_batch

    p = spec["parameters"]
    evaluation = output / f"evaluation-{generation}"
    evaluation.mkdir()
    indices = []
    for problem, (execution, record) in selected.items():
        target = case_directory(evaluation, p, problem)
        target.mkdir(parents=True)
        indices.append(int(problem[1:]))
        if record["generation_success"]:
            label = sanitize_model_name(p["model"])
            for suffix in ("df.pddl", "pf.pddl"):
                name = f"{problem}_{label}_{suffix}"
                source = safe_path(execution, name)
                if record["files"].get(name) != file_hash(source):
                    raise ValueError("Selected PDDL changed before evaluation")
                copy_file(source, target / name)
    if indices:
        run_solver_batch(p["domain"], p["model"], p["dataset"], sorted(indices), DEFAULT_SOLVER,
                         prediction_type=PIPELINE, out_dir_root=str(evaluation),
                         workers=scheduling["solver_workers"], solver_backend=p["solver_backend"])
        validate_plan_batch(p["domain"], p["dataset"], p["model"], sorted(indices), PIPELINE, True,
                            out_dir_root=str(evaluation), workers=scheduling["val_workers"])
    return evaluation


def run(spec, node, workspace, directory, generation):
    from api_providers import build_provider_client
    from batch_utils import format_problem_name
    from agent_formalizer.configuration.credentials import load_credential_registry
    from .benchmark import prepare, required_service_preflight

    p = spec["parameters"]
    _, _, op, _ = prepare(spec, node, workspace, directory, generation)
    required_service_preflight(p["model"], p["solver_backend"], spec, node, op, directory, generation,
                               output_token_policy=p.get("output_token_policy"))
    registry = load_credential_registry(op["credential"]["registry_file"])
    credential = registry.resolve(model_route(p["model"]), env_file=op["credential"]["secrets_env_file"])
    provider, client = build_provider_client(p["model"], api_key=credential.api_key,
        provider_options=credential.provider_options.get("self_hosted", {}))
    formalizer = load_formalizer(workspace)
    output = directory / "output"
    problems = [format_problem_name(number) for number in p["indices"]]
    try:
        with ThreadPoolExecutor(max_workers=op["scheduling"]["formalizer_workers"]) as pool:
            results = list(pool.map(lambda problem: run_case(formalizer, provider, client, spec,
                                                           workspace, output, problem), problems))
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()
    selected = {problem: result for problem, result in zip(problems, results) if result is not None}
    evaluation = evaluate(spec, output, selected, generation, op["scheduling"])
    private_json(output / f"cell-summary-{generation}.json", {
        "kind": "api_cell", "request_sha256": digest(spec), "requested": len(problems),
        "valid_attempts": len(selected), "missing_valid_problems": sorted(set(problems) - selected.keys()),
        "generated_pddl_pairs": sum(record["generation_success"] for _, record in selected.values()),
        "selected_executions": {problem: execution.relative_to(output).as_posix()
                                for problem, (execution, _) in selected.items()},
        "evaluation_root": evaluation.relative_to(directory).as_posix(),
        "credential": credential.metadata()}, replace=False)
    return 0 if len(selected) == len(problems) else 2
