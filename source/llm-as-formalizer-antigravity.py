"""Formalizer pipeline via Google Antigravity (Interactions API).

Uses the managed Antigravity agent (``client.interactions.create``) on the
**Gemini Developer API** (``generativelanguage.googleapis.com``), including the
``environment=remote`` sandbox.

Authentication uses a Gemini Developer API key (no ADC / project scoping)::

    GOOGLE_CLOUD_API_KEY=your-gemini-api-key   # or GEMINI_API_KEY / GOOGLE_API_KEY

The key must be valid for the Generative Language API. The SDK serves the
Interactions API at ``v1beta/interactions`` and sends the key in the
``x-goog-api-key`` header.

Antigravity does not support JSON-schema structured output; this script asks for
JSON in the prompt and parses ``interaction.output_text``.

Example::

    python3 source/llm-as-formalizer-antigravity.py \\
        --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --indices 1,2,3

    python3 source/llm-as-formalizer-antigravity.py \\
        --domain blocksworld \\
        --data Heavily_Templated_BlocksWorld-100 \\
        --index_start 1 --index_end 11 \\
        --environment remote
"""

from __future__ import annotations

from env_loader import load_project_dotenv

load_project_dotenv()

import argparse
import json
import os
import re
import time

from batch_utils import format_problem_name, run_parallel
from api_providers import GEMINI_INTERACTIONS_BACKEND, Tracer, build_gemini_interactions_client

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_AGENT = "antigravity-preview-05-2026"
ANTIGRAVITY_AGENTS = [DEFAULT_AGENT]

PDDL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain file": {"type": "string", "description": "Full PDDL domain file contents."},
        "problem file": {"type": "string", "description": "Full PDDL problem file contents."},
    },
    "required": ["domain file", "problem file"],
    "additionalProperties": False,
}

POLL_STATUSES = frozenset({"in_progress", "requires_action"})


def _is_transient_setup_error(exc: BaseException) -> bool:
    """True for the Enterprise "Resource setup ... try again shortly" 400.

    The Antigravity remote sandbox is provisioned lazily; the first calls for a
    project can return this transient error while the resource comes up.
    """
    msg = str(exc).lower()
    return "resource setup" in msg and ("in progress" in msg or "just started" in msg)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """True for 429 / RESOURCE_EXHAUSTED (per-minute stateful interaction quota)."""
    text = str(exc)
    upper = text.upper()
    return (
        "429" in text
        or "RESOURCE_EXHAUSTED" in upper
        or "TOO_MANY_REQUESTS" in upper
        or "QUOTA EXCEEDED" in upper
    )


def _is_retriable_create_error(exc: BaseException) -> bool:
    return _is_transient_setup_error(exc) or _is_rate_limit_error(exc)


def _format_antigravity_api_error(exc: BaseException) -> str | None:
    text = str(exc)
    upper = text.upper()
    if "403" in text and "PERMISSION_DENIED" in upper:
        return (
            "Interactions API permission denied (403). Ensure the Gemini API key "
            "is valid for the Generative Language API "
            "(generativelanguage.googleapis.com) and that this API is enabled "
            "for the key's project."
        )
    if "401" in text and "UNAUTHENTICATED" in upper:
        return (
            "Interactions API authentication failed (401). Set a valid Gemini "
            "Developer API key via GOOGLE_CLOUD_API_KEY (or GEMINI_API_KEY / "
            "GOOGLE_API_KEY)."
        )
    if "400" in text and "API_KEY_INVALID" in upper:
        return (
            "Interactions API rejected the API key (400 API_KEY_INVALID). "
            "Provide a Gemini Developer API key valid for "
            "generativelanguage.googleapis.com."
        )
    if "404" in text:
        return (
            "Interactions API not found (404). The Developer API path serves the "
            "Antigravity agent at generativelanguage.googleapis.com/v1beta/"
            "interactions; do not pin api_version='v1' for this client."
        )
    if _is_rate_limit_error(exc):
        return (
            "Interactions API quota exhausted (429) on "
            "generativelanguage.googleapis.com. Retries within --timeout were "
            "not enough; raise --timeout, lower --workers, or request a quota "
            "increase for the Gemini API key's project."
        )
    return None


def _serialize_interaction(interaction) -> dict:
    if hasattr(interaction, "model_dump"):
        return interaction.model_dump(mode="json", exclude_none=True)
    if hasattr(interaction, "to_dict"):
        return interaction.to_dict()
    return {"_repr": repr(interaction)}


def _build_formalizer_prompt(domain_description: str, problem_description: str) -> str:
    schema_json = json.dumps(PDDL_OUTPUT_SCHEMA, indent=2)
    return (
        "You are a PDDL expert. Here is a game we are playing.\n"
        f"{domain_description}\n{problem_description}\n"
        "Write the domain and problem files in minimal PDDL.\n"
        "Please focus on the problem itself and do it independently. "
        "DO NOT reference any existing datasets.\n\n"
        "Return ONLY a single JSON object (no markdown fences) with exactly these keys:\n"
        '  "domain file": <full PDDL domain as one string>\n'
        '  "problem file": <full PDDL problem as one string>\n\n'
        f"The JSON must conform to this schema:\n{schema_json}"
    )


def _loads_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text, strict=False)


def _parse_pddl_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model output")

    try:
        data = _loads_json_object(text)
    except json.JSONDecodeError:
        fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if fence:
            data = _loads_json_object(fence.group(1))
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("no JSON object found in model output")
            data = _loads_json_object(text[start : end + 1])

    for key in ("domain file", "problem file"):
        if key not in data:
            raise ValueError(f"missing required key {key!r} in parsed JSON")
    return data


def _wait_for_interaction(client, interaction, poll_interval: float, timeout_s: float, tracer=None):
    deadline = time.monotonic() + timeout_s
    current = interaction
    while getattr(current, "status", None) in POLL_STATUSES:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Antigravity interaction {current.id} did not finish within {timeout_s}s "
                f"(last status={current.status})"
            )
        if getattr(current, "status", None) == "requires_action":
            raise RuntimeError(
                f"Antigravity interaction {current.id} requires_action; "
                "custom tool handling is not implemented in this formalizer script"
            )
        time.sleep(poll_interval)
        current = client.interactions.get(id=current.id)
        if tracer:
            tracer.emit("poll", interaction_id=current.id, status=current.status)
    return current


def run_antigravity_interaction(
    client,
    agent: str,
    prompt: str,
    *,
    environment: str | None,
    background: bool,
    timeout_s: float,
    poll_interval: float,
    tracer=None,
) -> str:
    create_kwargs: dict = {
        "agent": agent,
        "input": prompt,
        "background": background,
        "environment": environment if environment is not None else "remote",
    }

    if tracer:
        tracer.emit("request", provider="antigravity", kwargs=create_kwargs)

    t0 = time.monotonic()
    create_deadline = t0 + timeout_s
    attempt = 0
    while True:
        attempt += 1
        try:
            interaction = client.interactions.create(**create_kwargs, timeout=timeout_s)
            break
        except Exception as e:
            if _is_retriable_create_error(e) and time.monotonic() < create_deadline:
                # 429 is a per-minute project quota; back off longer than setup.
                delay = max(poll_interval, 30.0) if _is_rate_limit_error(e) else poll_interval
                if tracer:
                    tracer.emit(
                        "create_retry",
                        provider="antigravity",
                        attempt=attempt,
                        kind="rate_limit" if _is_rate_limit_error(e) else "setup",
                        delay_s=delay,
                        error_message=str(e),
                    )
                time.sleep(delay)
                continue
            hint = _format_antigravity_api_error(e)
            if tracer:
                tracer.emit(
                    "api_error",
                    provider="antigravity",
                    elapsed_ms=(time.monotonic() - t0) * 1000.0,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    hint=hint,
                )
            if hint:
                raise SystemExit(hint)
            raise

    if background or getattr(interaction, "status", None) in POLL_STATUSES:
        interaction = _wait_for_interaction(
            client, interaction, poll_interval, timeout_s, tracer=tracer
        )

    elapsed_ms = (time.monotonic() - t0) * 1000.0
    if tracer:
        tracer.emit(
            "response",
            provider="antigravity",
            elapsed_ms=elapsed_ms,
            status=getattr(interaction, "status", None),
            interaction_id=getattr(interaction, "id", None),
            response=_serialize_interaction(interaction),
        )

    status = getattr(interaction, "status", None)
    if status != "completed":
        raise RuntimeError(
            f"Antigravity interaction finished with status={status!r} "
            f"(interaction_id={getattr(interaction, 'id', None)})"
        )

    text = getattr(interaction, "output_text", None) or ""
    if not text:
        raise RuntimeError(
            "Antigravity returned no output_text "
            f"(interaction_id={getattr(interaction, 'id', None)})"
        )
    return text


def run_formalizer_antigravity(
    client,
    domain,
    data,
    problem,
    agent,
    *,
    environment=None,
    background=True,
    timeout_s=600.0,
    poll_interval=5.0,
    record_trace=True,
    out_dir_root=None,
):
    domain_description = open(
        f"{ROOT_DIR}/data/textual_{domain}/{data}/{problem}_domain.txt"
    ).read()
    problem_description = open(
        f"{ROOT_DIR}/data/textual_{domain}/{data}/{problem}_problem.txt"
    ).read()
    prompt = _build_formalizer_prompt(domain_description, problem_description)

    out_root = out_dir_root or f"{ROOT_DIR}/output"
    out_dir = f"{out_root}/llm-as-formalizer-antigravity/{domain}/{data}/{agent}/{problem}"
    os.makedirs(out_dir, exist_ok=True)
    trace_path = f"{out_dir}/{problem}_{agent}_trace.jsonl" if record_trace else None
    tracer = Tracer(trace_path)

    t_start = time.monotonic()
    try:
        tracer.emit(
            "start",
            pipeline="llm-as-formalizer-antigravity",
            provider="antigravity",
            backend=GEMINI_INTERACTIONS_BACKEND,
            agent=agent,
            domain=domain,
            data=data,
            problem=problem,
            environment=environment,
            background=background,
            timeout_s=timeout_s,
            prompt=prompt,
            domain_description=domain_description,
            problem_description=problem_description,
        )

        raw_text = run_antigravity_interaction(
            client,
            agent,
            prompt,
            environment=environment,
            background=background,
            timeout_s=timeout_s,
            poll_interval=poll_interval,
            tracer=tracer,
        )
        return_dict = _parse_pddl_json(raw_text)
        domain_file = return_dict["domain file"]
        problem_file = return_dict["problem file"]

        df_path = f"{out_dir}/{problem}_{agent}_df.pddl"
        pf_path = f"{out_dir}/{problem}_{agent}_pf.pddl"
        with open(df_path, "w") as df:
            df.write(domain_file)
        with open(pf_path, "w") as pf:
            pf.write(problem_file)

        tracer.emit(
            "final",
            status="ok",
            elapsed_s=time.monotonic() - t_start,
            raw_output_text=raw_text,
            domain_file_chars=len(domain_file),
            problem_file_chars=len(problem_file),
            output_paths={"df": df_path, "pf": pf_path},
        )
        return domain_file, problem_file
    except Exception as e:
        tracer.emit(
            "error",
            status="failed",
            elapsed_s=time.monotonic() - t_start,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise
    finally:
        tracer.close()


def run_batch(
    client,
    domain,
    agent,
    data,
    problem_numbers,
    *,
    environment=None,
    background=True,
    timeout_s=600.0,
    poll_interval=5.0,
    record_trace=True,
    out_dir_root=None,
    workers=1,
):
    def _run_one(problem_number):
        problem_name = format_problem_name(problem_number)
        print(f"Running {problem_name}", flush=True)
        try:
            run_formalizer_antigravity(
                client,
                domain,
                data,
                problem_name,
                agent,
                environment=environment,
                background=background,
                timeout_s=timeout_s,
                poll_interval=poll_interval,
                record_trace=record_trace,
                out_dir_root=out_dir_root,
            )
        except Exception as e:
            print(f"FAILED {problem_name}: {e}", flush=True)

    run_parallel(problem_numbers, _run_one, workers=workers)


def _resolve_problem_numbers(args):
    if args.indices:
        return [int(x.strip()) for x in args.indices.split(",") if x.strip()]
    if args.index_start is None or args.index_end is None:
        raise SystemExit("Must provide either --indices or both --index_start and --index_end.")
    return list(range(eval(args.index_start), eval(args.index_end)))


Parser = argparse.ArgumentParser(description="PDDL formalizer via Antigravity Interactions API")
Parser.add_argument(
    "--domain",
    choices=["blocksworld", "mystery_blocksworld", "barman", "logistics"],
    required=True,
)
Parser.add_argument(
    "--data",
    choices=[
        "Heavily_Templated_BlocksWorld-100",
        "Moderately_Templated_BlocksWorld-100",
        "Natural_BlocksWorld-100",
        "Heavily_Templated_Mystery_BlocksWorld-100",
        "Heavily_Templated_Barman-100",
        "Heavily_Templated_Logistics-100",
        "Moderately_Templated_Logistics-100",
        "Natural_Logistics-100",
    ],
    required=True,
)
Parser.add_argument(
    "--agent",
    default=DEFAULT_AGENT,
    choices=ANTIGRAVITY_AGENTS,
    help="Antigravity agent id (Interactions API)",
)
Parser.add_argument("--index_start", help="start index (inclusive)")
Parser.add_argument("--index_end", help="end index (exclusive)")
Parser.add_argument(
    "--indices",
    default=None,
    help="comma-separated problem numbers (overrides --index_start/--index_end)",
)
Parser.add_argument("--out_dir", default=None, help="base output directory")
Parser.add_argument(
    "--trace",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="write per-problem JSONL trace (default on)",
)
Parser.add_argument("--workers", type=int, default=1, help="parallel problem workers")
Parser.add_argument(
    "--environment",
    default="remote",
    help='Antigravity sandbox (default "remote"; API requires this for the agent)',
)
Parser.add_argument(
    "--background",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="run interaction in background and poll (default on)",
)
Parser.add_argument(
    "--timeout",
    type=float,
    default=600.0,
    help="max seconds to wait per problem (default 600)",
)
Parser.add_argument(
    "--poll-interval",
    type=float,
    default=5.0,
    help="seconds between status polls when --background (default 5)",
)


if __name__ == "__main__":
    args = Parser.parse_args()
    client = build_gemini_interactions_client()
    run_batch(
        client,
        domain=args.domain,
        agent=args.agent,
        data=args.data,
        problem_numbers=_resolve_problem_numbers(args),
        environment=args.environment,
        background=args.background,
        timeout_s=args.timeout,
        poll_interval=args.poll_interval,
        record_trace=args.trace,
        out_dir_root=args.out_dir,
        workers=args.workers,
    )
