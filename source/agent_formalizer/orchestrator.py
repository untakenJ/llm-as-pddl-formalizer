"""Orchestrator: run an agent harness on PDDL formalization problems.

This is the agentic analogue of ``run_formalizer_gpt`` /
``run_gpt_batch`` in ``source/llm-as-formalizer-api.py``. For each problem it:

1. Creates the per-problem output dir (solver/val-compatible layout).
2. Creates an isolated agent (claw-specific; no-op for stateless claws).
3. Starts a Docker container and seeds the workspace with the descriptions.
4. Builds the prompt and runs the agent inside the container.
5. Reads the agent-authored ``domain.pddl`` / ``problem.pddl`` back out
   (falling back to parsing the final message if the files are absent).
6. Writes ``<problem>_<model>_df.pddl`` / ``_pf.pddl`` so run_solver.py and
   run_val.py can consume them unchanged.
7. Records a JSONL trace (orchestration events) plus a sibling
   ``<problem>_<model>_agent_steps.jsonl`` with per-step agent loop records
   (user/assistant messages, tool calls/results), raw session logs under
   ``sessions/``, and a metadata.json.

The orchestrator is claw-agnostic: everything claw-specific is reached through
the :class:`BaseClawAdapter` interface.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from agent_formalizer.config import (
    OUTPUT_DIR,
    agent_model_label,
    container_name as make_container_name,
    domain_dir,
    problem_output_dir,
)
from agent_formalizer.prompt import build_prompt, extract_pddl_from_text
from agent_formalizer.result_types import AgentResult, FormalizerResult
from agent_formalizer.util import Tracer, format_problem_name, run_parallel
from agent_formalizer.workspace import AgentWorkspace

logger = logging.getLogger(__name__)


def _read_descriptions(domain: str, data: str, problem: str) -> tuple[str, str]:
    d = domain_dir(domain, data)
    domain_description = (d / f"{problem}_domain.txt").read_text()
    problem_description = (d / f"{problem}_problem.txt").read_text()
    return domain_description, problem_description


def _record_tool_calls(
    adapter,
    agent_id: str,
    artifact_dir: Path,
    tracer: Tracer,
    *,
    session_id: str | None = None,
    session_file: str | None = None,
) -> int:
    """Emit one ``tool_exec`` trace event per tool call; return the count."""
    count = 0
    try:
        for rec in adapter.iter_tool_calls(
            agent_id,
            artifact_dir,
            session_id=session_id,
            session_file=session_file,
        ):
            tracer.emit(
                "tool_exec",
                provider=adapter.name,
                index=rec.get("index"),
                kind=rec.get("kind"),
                name=rec.get("name"),
                arguments=rec.get("arguments"),
                result=rec.get("result"),
                ok=rec.get("ok"),
                session_file=rec.get("session_file"),
            )
            count += 1
    except Exception as e:  # never let trace extraction break a run
        logger.warning("Tool-call trace extraction failed: %s", e)
        tracer.emit("tool_trace_error", provider=adapter.name,
                    error_type=type(e).__name__, error_message=str(e))
    return count


def _record_agent_steps(
    adapter,
    agent_id: str,
    artifact_dir: Path,
    problem: str,
    model_label: str,
    tracer: Tracer,
    *,
    session_id: str | None = None,
    session_file: str | None = None,
) -> tuple[int, str | None]:
    """Write per-step agent loop records to a sibling JSONL file."""
    steps_path = artifact_dir / f"{problem}_{model_label}_agent_steps.jsonl"
    count = 0
    try:
        with open(steps_path, "w", buffering=1) as fp:
            for rec in adapter.iter_agent_steps(
                agent_id,
                artifact_dir,
                session_id=session_id,
                session_file=session_file,
            ):
                fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                count += 1
        tracer.emit(
            "agent_steps",
            provider=adapter.name,
            path=str(steps_path),
            step_count=count,
            session_id=session_id,
            session_file=session_file,
        )
        return count, str(steps_path)
    except Exception as e:
        logger.warning("Agent step trace extraction failed: %s", e)
        tracer.emit(
            "agent_steps_error",
            provider=adapter.name,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        return 0, None


def _save_metadata(out_dir: Path, result: FormalizerResult, model_label: str,
                   domain: str, data: str, tool_call_count: int,
                   step_count: int = 0, agent_steps_path: str | None = None,
                   tool_policy: dict | None = None,
                   model_auth: dict | None = None) -> None:
    ar = result.agent_result
    data_out = {
        "pipeline": "llm-as-formalizer-agent",
        "problem": result.problem,
        "domain": domain,
        "data": data,
        "model": model_label,
        "status": result.status,
        "extraction_source": result.extraction_source,
        "tool_call_count": tool_call_count,
        "step_count": step_count,
        "agent_steps_path": agent_steps_path,
        "tool_policy": tool_policy,
        "model_auth": model_auth,
        "error": result.error,
    }
    if ar is not None:
        data_out["agent"] = {
            "success": ar.success,
            "finish_reason": ar.finish_reason,
            "exit_code": ar.exit_code,
            "timeout": ar.timeout,
            "duration_seconds": ar.duration_seconds,
            "session_id": ar.session_id,
            "session_file": ar.session_file,
            "openclaw_agent_id": ar.openclaw_agent_id,
            "usage": ar.usage,
        }
    (out_dir / "metadata.json").write_text(
        json.dumps(data_out, indent=2, ensure_ascii=False)
    )


def run_one_problem(
    adapter,
    domain: str,
    data: str,
    problem: str,
    *,
    model_label: str | None = None,
    record_trace: bool = True,
    out_dir_root: Path | None = None,
    image: str | None = None,
) -> FormalizerResult:
    """Formalize one problem with the agent harness; return a FormalizerResult."""
    model_label = model_label or agent_model_label(adapter.name, adapter.model)
    out_root = Path(out_dir_root) if out_dir_root else OUTPUT_DIR
    out_dir = problem_output_dir(out_root, domain, data, model_label, problem)
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_path = str(out_dir / f"{problem}_{model_label}_trace.jsonl") if record_trace else None
    tracer = Tracer(trace_path)

    domain_description, problem_description = _read_descriptions(domain, data, problem)
    prompt = build_prompt(domain_description, problem_description,
                          template_path=adapter.prompt_template())
    (out_dir / "prompt.txt").write_text(prompt)

    instance_id = f"{domain}-{data}-{problem}"
    agent_id = f"pddl-{instance_id}-{model_label}".replace(".", "-").replace("/", "-")
    cname = make_container_name(adapter.name, domain, data, model_label, problem)

    workspace = AgentWorkspace(instance_id, cname, adapter, image=image)
    agent_result: AgentResult | None = None
    result = FormalizerResult(problem=problem, status="failed")
    t_start = time.monotonic()
    tool_policy: dict = {}
    model_auth: dict = {}

    try:
        adapter.validate_runtime()
        tool_policy = adapter.tool_policy()
        model_auth = adapter.model_auth()
        tracer.emit(
            "start",
            pipeline="llm-as-formalizer-agent",
            provider=adapter.name,
            claw=adapter.name,
            model=adapter.model,
            model_label=model_label,
            domain=domain, data=data, problem=problem,
            timeout=adapter.timeout,
            max_turns=adapter.max_turns,
            container=cname,
            image=workspace.image_name,
            tool_policy=tool_policy,
            model_auth=model_auth,
            prompt=prompt,
            domain_description=domain_description,
            problem_description=problem_description,
        )

        # 1. Isolated agent (own workspace / sessions / memory).
        adapter.create_agent(agent_id)

        # 2. Container + seeded workspace.
        workspace.start()
        workspace.seed_workspace(domain_description, problem_description)
        tracer.emit("container_started", container=cname, image=workspace.image_name)

        # 3. Run the agent.
        logger.info("Sending task to %s for %s (agent=%s)", adapter.name, problem, agent_id)
        tracer.emit("request", provider=adapter.name, agent_id=agent_id,
                    container=cname, timeout=adapter.timeout)
        agent_result = adapter.send_task(
            prompt,
            agent_id=agent_id,
            container_name=cname,
            artifact_dir=out_dir,
            instance_id=instance_id,
        )
        result.agent_result = agent_result
        tracer.emit(
            "agent_result",
            provider=adapter.name,
            success=agent_result.success,
            finish_reason=agent_result.finish_reason,
            exit_code=agent_result.exit_code,
            timeout=agent_result.timeout,
            duration_seconds=agent_result.duration_seconds,
            session_id=agent_result.session_id,
            usage=agent_result.usage,
        )

        # 4. Collect claw-specific usage while the container is alive.
        extra_usage = adapter.collect_usage(workspace, out_dir) or {}
        if extra_usage:
            agent_result.usage = {**agent_result.usage, **extra_usage}
            tracer.emit("usage", provider=adapter.name, usage=extra_usage)

        # 5. Read the authored PDDL files out of the container.
        domain_file, problem_file = workspace.read_pddl_outputs()
        extraction_source = "file"

        # Fallback: recover PDDL from the agent's final message.
        if not (domain_file and problem_file) and agent_result.final_text:
            rec_d, rec_p = extract_pddl_from_text(agent_result.final_text)
            domain_file = domain_file or rec_d
            problem_file = problem_file or rec_p
            if rec_d or rec_p:
                extraction_source = "parsed"

        # 6. Back up session transcript, record per-step agent loop, fold tools into trace.
        session_agent_id = (
            (agent_result.openclaw_agent_id if agent_result else None) or agent_id
        )
        session_id = agent_result.session_id if agent_result else None
        session_file = agent_result.session_file if agent_result else None
        adapter.backup_session(
            session_agent_id,
            out_dir,
            session_id=session_id,
            session_file=session_file,
            container_name=cname,
        )
        step_count, agent_steps_path = _record_agent_steps(
            adapter,
            session_agent_id,
            out_dir,
            problem,
            model_label,
            tracer,
            session_id=session_id,
            session_file=session_file,
        )
        tool_call_count = _record_tool_calls(
            adapter,
            session_agent_id,
            out_dir,
            tracer,
            session_id=session_id,
            session_file=session_file,
        )

        if domain_file and problem_file:
            df_path = out_dir / f"{problem}_{model_label}_df.pddl"
            pf_path = out_dir / f"{problem}_{model_label}_pf.pddl"
            df_path.write_text(domain_file)
            pf_path.write_text(problem_file)
            result.status = "ok"
            result.domain_file = domain_file
            result.problem_file = problem_file
            result.extraction_source = extraction_source
            tracer.emit(
                "final", status="ok",
                elapsed_s=time.monotonic() - t_start,
                extraction_source=extraction_source,
                tool_call_count=tool_call_count,
                step_count=step_count,
                agent_steps_path=agent_steps_path,
                domain_file_chars=len(domain_file),
                problem_file_chars=len(problem_file),
                output_paths={"df": str(df_path), "pf": str(pf_path)},
            )
        else:
            missing = []
            if not domain_file:
                missing.append("domain")
            if not problem_file:
                missing.append("problem")
            result.error = (
                f"agent did not produce PDDL ({'+'.join(missing)} missing); "
                f"finish_reason={agent_result.finish_reason}"
            )
            tracer.emit("final", status="failed",
                        elapsed_s=time.monotonic() - t_start,
                        tool_call_count=tool_call_count,
                        step_count=step_count,
                        agent_steps_path=agent_steps_path,
                        error_message=result.error)

        _save_metadata(
            out_dir, result, model_label, domain, data, tool_call_count,
            step_count=step_count, agent_steps_path=agent_steps_path,
            tool_policy=tool_policy, model_auth=model_auth,
        )
        return result

    except Exception as e:
        result.error = str(e)
        tracer.emit("error", status="failed",
                    elapsed_s=time.monotonic() - t_start,
                    error_type=type(e).__name__, error_message=str(e))
        _save_metadata(out_dir, result, model_label, domain, data, 0,
                       tool_policy=tool_policy, model_auth=model_auth)
        raise
    finally:
        # Unmount runtime/state paths before deleting host-side agent state.
        try:
            workspace.cleanup()
        finally:
            try:
                adapter.delete_agent(agent_id)
            finally:
                tracer.close()


def run_batch(
    adapter,
    domain: str,
    data: str,
    problem_numbers,
    *,
    model_label: str | None = None,
    record_trace: bool = True,
    out_dir_root: Path | None = None,
    image: str | None = None,
    workers: int = 1,
) -> list[FormalizerResult]:
    """Run the agent over a batch of problems (sequential or thread-pooled)."""
    results: list[FormalizerResult] = []

    def _run_one(problem_number):
        problem_name = format_problem_name(problem_number)
        print(f"Running {problem_name}", flush=True)
        try:
            return run_one_problem(
                adapter, domain, data, problem_name,
                model_label=model_label,
                record_trace=record_trace,
                out_dir_root=out_dir_root,
                image=image,
            )
        except Exception as e:
            print(f"FAILED {problem_name}: {e}", flush=True)
            return FormalizerResult(problem=problem_name, status="failed", error=str(e))

    results = run_parallel(problem_numbers, _run_one, workers=workers)
    ok = sum(1 for r in results if r and r.status == "ok")
    print(f"Done: {ok}/{len(results)} problems produced PDDL.", flush=True)
    return results
