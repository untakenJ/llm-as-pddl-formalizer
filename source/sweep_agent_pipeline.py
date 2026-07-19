"""End-to-end sweep for agent-backed PDDL formalization.

This is the agent-harness counterpart to ``sweep_pipeline.py``.  It runs:

1. ``agent_formalizer/run_formalizer_agent.py`` to produce PDDL
2. ``run_solver.py`` with ``--prediction_type llm-as-formalizer-agent``
3. ``run_val.py`` with ``--prediction_type llm-as-formalizer-agent``

The script is intentionally claw-agnostic: it shells out through
``run_formalizer_agent.py --claw ...`` instead of depending on OpenClaw classes
directly.  Registering a future harness in ``agent_formalizer.claws`` makes it
usable here via ``--claw <name>``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_formalizer.claws import CLAWS
from agent_formalizer.benchmark_profile import (
    load_benchmark_profile,
    with_google_vertex_project,
)
from agent_formalizer.config import (
    CLAW_DEFAULTS,
    DEFAULT_SECRETS_ENV_FILE,
    PREDICTION_TYPE,
    agent_model_label,
    sanitize_model_name,
)
from agent_formalizer.util import read_named_setting
from batch_utils import format_problem_name

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable

DOMAIN_DATA_PAIRS = [
    ("blocksworld", "Heavily_Templated_BlocksWorld-100"),
    ("blocksworld", "Moderately_Templated_BlocksWorld-100"),
    ("blocksworld", "Natural_BlocksWorld-100"),
    ("mystery_blocksworld", "Heavily_Templated_Mystery_BlocksWorld-100"),
    ("barman", "Heavily_Templated_Barman-100"),
    ("logistics", "Heavily_Templated_Logistics-100"),
    ("logistics", "Moderately_Templated_Logistics-100"),
    ("logistics", "Natural_Logistics-100"),
]


@dataclass
class AgentBatchResult:
    claw: str
    model: str
    model_label: str
    domain: str
    dataset: str
    pddl_completed: int = 0
    solvability: str = "-"
    correctness: str = "-"
    total: int = 0
    indices: list[int] = field(default_factory=list)
    stages: dict[str, str] = field(default_factory=dict)
    durations: dict[str, float] = field(default_factory=dict)
    logs: dict[str, str] = field(default_factory=dict)
    notes: str = ""


_SOLV_RE = re.compile(r"Solvability:\s*(\S+)\s*/\s*(\d+)")
_CORR_RE = re.compile(r"Correctness:\s*(\S+)\s*/\s*(\d+)")

def _parse_val_stdout(stdout: str) -> tuple[str, str, int]:
    s = _SOLV_RE.search(stdout)
    c = _CORR_RE.search(stdout)
    solvability = s.group(1) if s else "-"
    correctness = c.group(1) if c else "-"
    total = int(c.group(2)) if c else (int(s.group(2)) if s else 0)
    return solvability, correctness, total


def _format_cmd(cmd: list[str]) -> str:
    return " ".join(cmd)


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_") or "run"


def _run(cmd: list[str], log_label: str, log_dir: Path) -> tuple[int, str, str, float, dict[str, str]]:
    print(f"  $ {_format_cmd(cmd)}", flush=True)
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0

    log_dir.mkdir(parents=True, exist_ok=True)
    safe_label = _safe_name(log_label)
    stdout_path = log_dir / f"{safe_label}.stdout.log"
    stderr_path = log_dir / f"{safe_label}.stderr.log"
    stdout_path.write_text(proc.stdout)
    stderr_path.write_text(proc.stderr)

    if proc.returncode != 0:
        print(f"    [{log_label}] returncode={proc.returncode}")
        if proc.stderr:
            tail = "\n      ".join(proc.stderr.strip().splitlines()[-10:])
            print(f"    stderr (tail):\n      {tail}")

    return (
        proc.returncode,
        proc.stdout,
        proc.stderr,
        elapsed,
        {"stdout": str(stdout_path), "stderr": str(stderr_path)},
    )


def _build_index_flags(indices: list[int]) -> list[str]:
    return ["--indices", ",".join(str(i) for i in indices)]


def _common_eval_flags(
    model_label: str,
    domain: str,
    dataset: str,
    indices: list[int],
    out_dir: Path,
    workers: int,
) -> list[str]:
    return [
        "--domain", domain,
        "--model", model_label,
        "--data", dataset,
        "--out_dir", str(out_dir),
        "--workers", str(workers),
        *_build_index_flags(indices),
    ]


def _agent_output_dir(out_dir: Path, domain: str, dataset: str, model_label: str, problem: str) -> Path:
    return out_dir / PREDICTION_TYPE / domain / dataset / model_label / problem


def _count_pddl_outputs(out_dir: Path, domain: str, dataset: str, model_label: str, indices: list[int]) -> int:
    count = 0
    for index in indices:
        problem = format_problem_name(index)
        problem_dir = _agent_output_dir(out_dir, domain, dataset, model_label, problem)
        df = problem_dir / f"{problem}_{model_label}_df.pddl"
        pf = problem_dir / f"{problem}_{model_label}_pf.pddl"
        if df.is_file() and pf.is_file():
            count += 1
    return count


def _formalize_indices_for_resume(
    out_dir: Path,
    domain: str,
    dataset: str,
    model_label: str,
    indices: list[int],
) -> list[int]:
    """Compatibility helper: only atomic valid completion records are resumable."""
    pending: list[int] = []
    for index in indices:
        problem = format_problem_name(index)
        problem_dir = _agent_output_dir(out_dir, domain, dataset, model_label, problem)
        metadata_path = problem_dir / "completion.json"
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError, TypeError):
            pending.append(index)
            continue

        if not (metadata.get("complete") is True and metadata.get("attempt_valid") is True):
            pending.append(index)
    return pending


def _resolve_model_label(
    claw: str, model: str, explicit_label: str | None, job_count: int
) -> str:
    if explicit_label:
        if job_count != 1:
            raise ValueError("--model-label can only be used with one claw/model job")
        return explicit_label
    return agent_model_label(claw, model)


def _qualify_model_label(model_label: str, config_label: str) -> str:
    suffix = f"__{config_label}"
    return model_label if model_label.endswith(suffix) else model_label + suffix


def run_agent_pipeline(
    *,
    claw: str,
    model: str,
    model_label: str,
    domain: str,
    dataset: str,
    indices: list[int],
    out_dir: Path,
    log_dir: Path,
    stages: set[str],
    formalizer_workers: int,
    solver_workers: int,
    val_workers: int,
    timeout: int | None,
    max_turns: int | None,
    max_model_calls: int | None,
    network_mode: str | None,
    attempts_per_case: int | None,
    max_execution_tries: int | None,
    allow_final_message_recovery: bool | None,
    benchmark_config: str | None,
    api_key_env: str | None,
    secrets_env_file: str,
    vertex_project_env: str,
    image: str | None,
    trace: bool,
    tools_profile: str | None,
    tools_allow: str | None,
    tools_deny: str | None,
    resume: bool,
) -> AgentBatchResult:
    harness_overrides = None
    if claw == "openclaw" and any((tools_profile, tools_allow, tools_deny)):
        harness_overrides = {}
        if tools_profile:
            harness_overrides["tools_profile"] = tools_profile
        if tools_allow:
            harness_overrides["tools_allow"] = _split_csv(tools_allow)
        if tools_deny:
            harness_overrides["tools_deny"] = _split_csv(tools_deny)
    resolved = load_benchmark_profile(benchmark_config).resolve(
        claw,
        model=model,
        timeout=timeout,
        max_turns=max_turns,
        max_model_calls=max_model_calls,
        network_mode=network_mode,
        attempts_per_case=attempts_per_case,
        max_execution_tries=max_execution_tries,
        allow_final_message_recovery=allow_final_message_recovery,
        harness_overrides=harness_overrides,
    )
    model_label = _qualify_model_label(model_label, resolved.label)
    attempt_count = resolved.attempts_per_case
    evaluation_labels = (
        [model_label]
        if attempt_count == 1
        else [
            f"{model_label}__attempt_{index:03d}"
            for index in range(1, attempt_count + 1)
        ]
    )
    res = AgentBatchResult(
        claw=claw,
        model=model,
        model_label=model_label,
        domain=domain,
        dataset=dataset,
        indices=list(indices),
    )

    batch_log_dir = log_dir / _safe_name(f"{claw}_{model_label}_{domain}_{dataset}")

    # Always submit the fixed study set. The runner itself reuses only atomic
    # completion records whose config/task hashes match; outcomes never decide
    # whether another attempt is created.
    formalize_indices = indices

    if "formalize" in stages and formalize_indices:
        cmd = [
            PYTHON,
            str(SOURCE_DIR / "agent_formalizer" / "run_formalizer_agent.py"),
            "--claw", claw,
            "--domain", domain,
            "--data", dataset,
            "--model", model,
            "--model_label", model_label,
            "--out_dir", str(out_dir),
            "--workers", str(formalizer_workers),
            *_build_index_flags(formalize_indices),
        ]
        if timeout is not None:
            cmd.extend(["--timeout", str(timeout)])
        if max_turns is not None:
            cmd.extend(["--max_turns", str(max_turns)])
        if max_model_calls is not None:
            cmd.extend(["--max-model-calls", str(max_model_calls)])
        if network_mode is not None:
            cmd.extend(["--network-mode", network_mode])
        if attempts_per_case is not None:
            cmd.extend(["--attempts-per-case", str(attempts_per_case)])
        if max_execution_tries is not None:
            cmd.extend(["--max-execution-tries", str(max_execution_tries)])
        if allow_final_message_recovery is not None:
            cmd.append(
                "--allow-final-message-recovery"
                if allow_final_message_recovery
                else "--no-allow-final-message-recovery"
            )
        if benchmark_config:
            cmd.extend(["--benchmark-config", benchmark_config])
        if api_key_env:
            cmd.extend(["--api-key-env", api_key_env])
        cmd.extend(["--secrets-env-file", secrets_env_file])
        cmd.extend(["--vertex-project-env", vertex_project_env])
        if image:
            cmd.extend(["--image", image])
        if not trace:
            cmd.append("--no-trace")
        if tools_profile:
            cmd.extend(["--tools-profile", tools_profile])
        if tools_allow:
            cmd.extend(["--tools-allow", tools_allow])
        if tools_deny:
            cmd.extend(["--tools-deny", tools_deny])

        rc, _, _, elapsed, logs = _run(cmd, "formalize", batch_log_dir)
        res.stages["formalize"] = "ok" if rc == 0 else "FAIL"
        res.durations["formalize"] = elapsed
        res.logs["formalize"] = logs["stderr"]
    elif "formalize" in stages:
        res.stages["formalize"] = "ok"
        res.durations["formalize"] = 0.0

    res.pddl_completed = sum(
        _count_pddl_outputs(out_dir, domain, dataset, label, indices)
        for label in evaluation_labels
    )
    expected_attempts = len(indices) * attempt_count
    if "formalize" in stages and res.pddl_completed != expected_attempts:
        missing = expected_attempts - res.pddl_completed
        res.notes = f"{missing} valid attempt(s) did not generate delivery files"

    if "solve" in stages:
        solve_rc = 0
        solve_elapsed = 0.0
        for label in evaluation_labels:
            common = _common_eval_flags(
                label, domain, dataset, indices, out_dir, solver_workers
            )
            cmd = [
                PYTHON,
                str(SOURCE_DIR / "run_solver.py"),
                "--prediction_type", PREDICTION_TYPE,
                *common,
            ]
            rc, _, _, elapsed, logs = _run(
                cmd, f"solve-{label}", batch_log_dir
            )
            solve_rc = solve_rc or rc
            solve_elapsed += elapsed
            res.logs[f"solve:{label}"] = logs["stderr"]
        res.stages["solve"] = "ok" if solve_rc == 0 else "FAIL"
        res.durations["solve"] = solve_elapsed

    if "val" in stages:
        val_rc = 0
        val_elapsed = 0.0
        solvability = 0
        correctness = 0
        total = 0
        for label in evaluation_labels:
            common = _common_eval_flags(
                label, domain, dataset, indices, out_dir, val_workers
            )
            cmd = [
                PYTHON,
                str(SOURCE_DIR / "run_val.py"),
                "--prediction_type", PREDICTION_TYPE,
                "--csv_result",
                *common,
            ]
            rc, stdout, _, elapsed, logs = _run(
                cmd, f"val-{label}", batch_log_dir
            )
            val_rc = val_rc or rc
            val_elapsed += elapsed
            res.logs[f"val:{label}"] = logs["stderr"]
            if rc == 0:
                solv, corr, row_total = _parse_val_stdout(stdout)
                solvability += int(solv) if solv.isdigit() else 0
                correctness += int(corr) if corr.isdigit() else 0
                total += row_total
        res.stages["val"] = "ok" if val_rc == 0 else "FAIL"
        res.durations["val"] = val_elapsed
        if val_rc == 0:
            res.solvability = str(solvability)
            res.correctness = str(correctness)
            res.total = total
        else:
            res.solvability = res.correctness = "ERR"
            res.notes = "; ".join(filter(None, (res.notes, "run_val failed")))

    return res


def write_summary(results: list[AgentBatchResult], out_dir: Path, run_meta: dict) -> tuple[Path, Path]:
    claws = sorted({r.claw for r in results}) or run_meta["claws"]
    models = sorted({r.model for r in results}) or run_meta["models"]
    if len(claws) == 1 and len(models) == 1:
        stem = f"agent_sweep_{_safe_name(claws[0])}_{_safe_name(sanitize_model_name(models[0]))}_summary"
    else:
        stem = "agent_sweep_summary"

    csv_path = out_dir / f"{stem}.csv"
    md_path = out_dir / f"{stem}.md"

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "claw", "model", "model_label", "domain", "dataset",
            "pddl_completed", "solvability", "correctness", "total",
            "stage_status", "durations_sec", "indices", "notes",
        ])
        for r in results:
            stages = ", ".join(f"{k}={v}" for k, v in r.stages.items())
            durations = ", ".join(f"{k}={v:.1f}" for k, v in r.durations.items())
            w.writerow([
                r.claw, r.model, r.model_label, r.domain, r.dataset,
                r.pddl_completed, r.solvability, r.correctness, r.total,
                stages, durations, ",".join(str(i) for i in r.indices), r.notes,
            ])

    lines = [
        "# Agent sweep summary",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Output dir: `{out_dir}`",
        f"Claws: {', '.join(f'`{c}`' for c in run_meta['claws'])}",
        f"Models: {', '.join(f'`{m}`' for m in run_meta['models'])}",
        f"Stages: `{','.join(run_meta['stages'])}`",
        f"Index range: `[{run_meta['index_start']}, {run_meta['index_end']})`"
        + (f" -- sampled {run_meta['samples']} per batch (seed={run_meta['sample_seed']})"
           if run_meta.get("samples") else " -- full"),
        (
            f"Workers: formalizer={run_meta['formalizer_workers']}, "
            f"solver={run_meta['solver_workers']}, val={run_meta['val_workers']}"
        ),
        "",
        "| claw | model | label | domain | dataset | PDDL | solvability | correctness | total | stages | durations | notes |",
        "|---|---|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for r in results:
        stages = "<br>".join(f"`{k}`={v}" for k, v in r.stages.items())
        durations = "<br>".join(f"`{k}`={v:.1f}s" for k, v in r.durations.items())
        lines.append(
            f"| {r.claw} | {r.model} | {r.model_label} | {r.domain} | {r.dataset} | "
            f"{r.pddl_completed}/{len(r.indices)} | {r.solvability} | {r.correctness} | "
            f"{r.total} | {stages} | {durations} | {r.notes} |"
        )
    lines.append("")
    md_path.write_text("\n".join(lines))
    return csv_path, md_path


def _sanitize_tag(tag: str) -> str:
    tag = re.sub(r"\s+", "_", tag.strip())
    return re.sub(r"[^0-9A-Za-z._-]", "", tag)


def _default_out_dir(tag: str = "") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"agent_sweep_{stamp}"
    safe_tag = _sanitize_tag(tag)
    if safe_tag:
        name = f"{name}_{safe_tag}"
    return ROOT_DIR / "output" / name


def _freeze_study_profile(profile, out_dir: Path):
    """Persist one immutable profile snapshot before the first study case."""
    path = out_dir / "study_benchmark_profile.json"
    payload = json.dumps(profile.raw, indent=2, ensure_ascii=False) + "\n"
    try:
        with path.open("x") as stream:
            stream.write(payload)
    except FileExistsError:
        try:
            existing = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"existing frozen study profile is unreadable: {path}") from exc
        if existing != profile.raw:
            raise ValueError(
                "output directory already contains a different frozen benchmark "
                f"profile: {path}"
            )
    return load_benchmark_profile(path)


def _sample_indices(index_start: int, index_end: int, samples: int | None, sample_seed: int) -> list[int]:
    full = list(range(index_start, index_end))
    if samples is None:
        return full
    if samples >= len(full):
        return full
    rng = random.Random(sample_seed)
    return sorted(rng.sample(full, samples))


def _parse_pairs(raw: str) -> list[tuple[str, str]]:
    if not raw:
        return DOMAIN_DATA_PAIRS
    pairs: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Invalid pair '{item}', expected domain:dataset")
        domain, dataset = item.split(":", 1)
        pairs.append((domain.strip(), dataset.strip()))
    return pairs


def _split_csv(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _claw_model_jobs_for_args(args, claws: list[str]) -> list[tuple[str, str]]:
    explicit_models = _split_csv(args.model)
    if explicit_models:
        return [(claw, model) for claw in claws for model in explicit_models]

    jobs = []
    for claw in claws:
        if claw not in CLAW_DEFAULTS:
            raise ValueError(f"No defaults registered for claw '{claw}'")
        jobs.append((claw, args._benchmark_profile.default_model))
    return jobs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run agent formalization, solver, and VAL over one or more batches."
    )
    p.add_argument("--claw", default="openclaw",
                   help=f"agent harness name(s), comma-separated; available: {', '.join(sorted(CLAWS))}")
    p.add_argument("--model", default=None,
                   help="model id(s), comma-separated; default is the benchmark profile model")
    p.add_argument("--benchmark-config", default=None,
                   help="JSON benchmark profile passed to every formalizer job")
    p.add_argument("--model-label", default=None,
                   help="base filesystem label for one claw/model job; the "
                        "resolved config name/hash is always appended")
    p.add_argument("--domain", default=None,
                   help="shortcut for a single pair; must be used with --data")
    p.add_argument("--data", default=None,
                   help="shortcut for a single pair; must be used with --domain")
    p.add_argument("--pairs", default="",
                   help="optional 'domain:dataset,domain:dataset' subset; default is all known pairs")
    p.add_argument("--index_start", type=int, default=1)
    p.add_argument("--index_end", type=int, default=101)
    p.add_argument("--samples", type=int, default=None,
                   help="randomly sample this many problem numbers from the index range")
    p.add_argument("--sample_seed", type=int, default=0)
    p.add_argument("--out_dir", default=None,
                   help="base output directory; default output/agent_sweep_<timestamp>/")
    p.add_argument("--tag", default="",
                   help="optional label appended to the default output directory name")
    p.add_argument("--stages", default="formalize,solve,val",
                   help="comma-separated subset of {formalize,solve,val}; useful for resuming")
    p.add_argument("--workers", type=int, default=1,
                   help="default workers for all stages unless a stage-specific value is set")
    p.add_argument("--formalizer-workers", type=int, default=None)
    p.add_argument("--solver-workers", type=int, default=None)
    p.add_argument("--val-workers", type=int, default=None)
    p.add_argument("--timeout", type=int, default=None,
                   help="agent timeout in seconds; omitted means claw default")
    p.add_argument("--max_turns", type=int, default=None,
                   help="agent max turns; omitted means claw default")
    p.add_argument("--max-model-calls", type=int, default=None,
                   help="maximum model API calls per problem; omitted means profile default")
    p.add_argument("--network-mode", choices=("model_only", "controlled_web"),
                   default=None)
    p.add_argument("--attempts-per-case", type=int, default=None)
    p.add_argument("--max-execution-tries", type=int, default=None)
    p.add_argument("--allow-final-message-recovery",
                   action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--api-key-env", default=None,
                   help="the one runner environment variable holding the model key")
    p.add_argument("--secrets-env-file", default=str(DEFAULT_SECRETS_ENV_FILE),
                   help="runner-only dotenv source for explicitly named provider inputs")
    p.add_argument("--vertex-project-env", default="GOOGLE_CLOUD_PROJECT",
                   help="dotenv/process variable used if a Vertex project is absent")
    p.add_argument("--image", default=None,
                   help="Docker image for the agent container")
    p.add_argument("--trace", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--resume", action="store_true",
                   help="reuse hash-matching atomic completion records")
    p.add_argument("--tools-profile", default=None,
                   help="claw-specific tool profile passed through to run_formalizer_agent.py")
    p.add_argument("--tools-allow", default=None,
                   help="claw-specific comma-separated allow list")
    p.add_argument("--tools-deny", default=None,
                   help="claw-specific comma-separated deny list")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args._benchmark_profile = load_benchmark_profile(args.benchmark_config)

    claws = _split_csv(args.claw)
    if not claws:
        parser.error("--claw must name at least one harness")
    unknown = [claw for claw in claws if claw not in CLAWS]
    if unknown:
        parser.error(f"unknown claw(s): {', '.join(unknown)}; available: {', '.join(sorted(CLAWS))}")

    jobs = _claw_model_jobs_for_args(args, claws)
    if not jobs:
        parser.error("--model must name at least one model when no claw default is available")
    models = sorted({model for _, model in jobs})
    if (
        any(model.startswith("google-vertex/") for model in models)
        and args._benchmark_profile.raw["providers"]["google_vertex"]["project"] is None
    ):
        try:
            vertex_project = read_named_setting(
                args.vertex_project_env, args.secrets_env_file
            )
        except RuntimeError as exc:
            parser.error(str(exc))
        args._benchmark_profile = with_google_vertex_project(
            args._benchmark_profile, vertex_project
        )

    if args.domain or args.data:
        if not (args.domain and args.data):
            parser.error("--domain and --data must be provided together")
        if args.pairs:
            parser.error("use either --domain/--data or --pairs, not both")
        pairs = [(args.domain, args.data)]
    else:
        try:
            pairs = _parse_pairs(args.pairs)
        except ValueError as exc:
            parser.error(str(exc))

    stages = set(_split_csv(args.stages))
    valid_stages = {"formalize", "solve", "val"}
    bad_stages = stages - valid_stages
    if bad_stages:
        parser.error(f"unknown stage(s): {', '.join(sorted(bad_stages))}")

    formalizer_workers = args.formalizer_workers or args.workers
    solver_workers = args.solver_workers or args.workers
    val_workers = args.val_workers or args.workers

    if args.out_dir and args.tag:
        print("Note: --tag is ignored because --out_dir was given explicitly.")
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(args.tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        args._benchmark_profile = _freeze_study_profile(
            args._benchmark_profile, out_dir
        )
    except ValueError as exc:
        parser.error(str(exc))
    frozen_benchmark_config = str(args._benchmark_profile.path)
    log_dir = out_dir / "sweep_logs"

    indices = _sample_indices(args.index_start, args.index_end, args.samples, args.sample_seed)
    run_meta = {
        "claws": claws,
        "models": models,
        "stages": [stage for stage in ("formalize", "solve", "val") if stage in stages],
        "index_start": args.index_start,
        "index_end": args.index_end,
        "samples": args.samples,
        "sample_seed": args.sample_seed,
        "formalizer_workers": formalizer_workers,
        "solver_workers": solver_workers,
        "val_workers": val_workers,
        "resume": args.resume,
        "benchmark_profile": args._benchmark_profile.metadata(),
        "budget_overrides": {
            "timeout_seconds": args.timeout,
            "max_turns": args.max_turns,
            "max_model_calls": args.max_model_calls,
        },
        "network_mode_override": args.network_mode,
    }

    print(f"Out dir: {out_dir}")
    print(f"Claws:   {', '.join(claws)}")
    print(f"Models:  {', '.join(models)}")
    print(f"Pairs:   {', '.join(f'{d}:{ds}' for d, ds in pairs)}")
    print(
        f"Workers: formalizer={formalizer_workers}, "
        f"solver={solver_workers}, val={val_workers}"
    )
    print(
        f"Index range: [{args.index_start}, {args.index_end})"
        + (f"  samples={args.samples} seed={args.sample_seed}" if args.samples else "  (full)")
    )

    results: list[AgentBatchResult] = []
    start_wall = time.time()
    job_count = len(jobs)
    for claw, model in jobs:
        try:
            model_label = _resolve_model_label(
                claw, model, args.model_label, job_count
            )
        except ValueError as exc:
            parser.error(str(exc))

        for domain, dataset in pairs:
            print(
                f"\n=== [agent:{claw}] {model} | {domain} / {dataset} "
                f"({len(indices)} problems) ===",
                flush=True,
            )
            try:
                result = run_agent_pipeline(
                    claw=claw,
                    model=model,
                    model_label=model_label,
                    domain=domain,
                    dataset=dataset,
                    indices=indices,
                    out_dir=out_dir,
                    log_dir=log_dir,
                    stages=stages,
                    formalizer_workers=formalizer_workers,
                    solver_workers=solver_workers,
                    val_workers=val_workers,
                    timeout=args.timeout,
                    max_turns=args.max_turns,
                    max_model_calls=args.max_model_calls,
                    network_mode=args.network_mode,
                    attempts_per_case=args.attempts_per_case,
                    max_execution_tries=args.max_execution_tries,
                    allow_final_message_recovery=args.allow_final_message_recovery,
                    benchmark_config=frozen_benchmark_config,
                    api_key_env=args.api_key_env,
                    secrets_env_file=args.secrets_env_file,
                    vertex_project_env=args.vertex_project_env,
                    image=args.image,
                    trace=args.trace,
                    tools_profile=args.tools_profile,
                    tools_allow=args.tools_allow,
                    tools_deny=args.tools_deny,
                    resume=args.resume,
                )
            except Exception as exc:
                print(f"!! batch crashed: {exc}", flush=True)
                result = AgentBatchResult(
                    claw=claw,
                    model=model,
                    model_label=model_label,
                    domain=domain,
                    dataset=dataset,
                    indices=list(indices),
                    solvability="ERR",
                    correctness="ERR",
                    notes=f"sweep exception: {exc}",
                )
            results.append(result)
            _, md_path = write_summary(results, out_dir, run_meta)
            print(f"  partial summary written: {md_path}")

    csv_path, md_path = write_summary(results, out_dir, run_meta)
    print(f"\nDone in {time.time() - start_wall:.1f}s")
    print(f"Summary: {md_path}")
    print(f"CSV:     {csv_path}")


if __name__ == "__main__":
    main()
