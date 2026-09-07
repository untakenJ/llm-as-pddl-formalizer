"""End-to-end sweep over every (domain, dataset) pair in ./data/.

For each model in ``--model`` (default ``gpt-5.4-mini``; pass a comma-separated
list like ``gpt-5.4-mini,gpt-5.5`` to sweep several) and each (domain, dataset)
pair this runs both pipelines:

1. **llm-as-formalizer-api**: generate PDDL -> ``run_solver`` -> ``run_val``
2. **llm-as-planner-api**:    generate plan directly -> ``run_val``

Per-batch artefacts for each model land under their own ``.../<model>/`` folder
(the inner scripts already key paths on the model name), so multiple models in
one sweep never clobber each other.

Output layout:

By default this sweep creates a fresh timestamped run directory under
``output/`` (e.g. ``output/sweep_20260619-085530/``) and all per-batch artefacts
(generated PDDL/plans, traces, VAL CSVs) plus a single aggregated summary are
written inside it. The summary is ``sweep_<model>_summary.{md,csv}`` for a single
model and ``sweep_summary.{md,csv}`` when several models are swept; either way it
carries a ``model`` column so every batch is attributable. This keeps successive
sweeps from clobbering each other. Pass ``--tag`` to append a custom label after
the timestamp (e.g. ``--tag full`` -> ``output/sweep_20260619-085530_full/``) so
runs are easy to tell apart by purpose. Pass ``--out_dir`` to override the whole
path (in which case ``--tag`` is ignored).

Sampling:

By default every batch processes the full range ``[--index_start, --index_end)``
(default 1..101). Use ``--samples N`` to randomly pick N problem numbers from
that range for each batch; ``--sample_seed K`` (default 0) controls
reproducibility. The same ``--out_dir`` and indices are threaded through every
subprocess invocation.

Per-batch Solvability and Correctness are scraped from ``run_val``'s stdout.
Each batch is isolated via ``subprocess.run``; if one batch crashes the rest
still complete and the failure is recorded in the summary as ``Solvability=ERR``.

Within each batch, independent problems are processed in parallel when
``--workers`` > 1 (default 8). Stages inside a formalizer batch remain
sequential (formalize -> solve -> validate), but each stage parallelizes across
problems. Batch boundaries (model / domain / dataset / pipeline) stay sequential
so partial summaries stay coherent.

Example:
    python3 source/sweep_pipeline.py --model gpt-5.4-mini --index_start 1 --index_end 101 --tag full
    python3 source/sweep_pipeline.py --model gpt-5.4-mini,gpt-5.5 --samples 20 --tag compare --workers 8
    python3 source/sweep_pipeline.py --model gpt-5.4-mini --out_dir output/my_run/
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

from local_solver import (
    DEFAULT_SOLVER_BACKEND,
    SUPPORTED_BACKENDS,
    base_urls_for_backend,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# (domain, dataset) pairs that exist under ./data/textual_<domain>/<dataset>/
DOMAIN_DATA_PAIRS = [
    ("blocksworld",         "Heavily_Templated_BlocksWorld-100"),
    ("blocksworld",         "Moderately_Templated_BlocksWorld-100"),
    ("blocksworld",         "Natural_BlocksWorld-100"),
    ("mystery_blocksworld", "Heavily_Templated_Mystery_BlocksWorld-100"),
    ("barman",              "Heavily_Templated_Barman-100"),
    ("logistics",           "Heavily_Templated_Logistics-100"),
    ("logistics",           "Moderately_Templated_Logistics-100"),
    ("logistics",           "Natural_Logistics-100"),
]


@dataclass
class BatchResult:
    pipeline: str
    domain: str
    dataset: str
    model: str = ""
    solvability: str = "-"      # number or "-" or "ERR"
    correctness: str = "-"
    total: int = 0
    indices: list = field(default_factory=list)
    stages: dict = field(default_factory=dict)   # stage name -> "ok"|"FAIL"
    notes: str = ""


def _run(cmd: list, log_label: str) -> tuple:
    print(f"  $ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"    [{log_label}] returncode={proc.returncode}")
        if proc.stderr:
            print(f"    stderr (tail):\n      " + "\n      ".join(proc.stderr.strip().splitlines()[-10:]))
    return proc.returncode, proc.stdout, proc.stderr


_SOLV_RE = re.compile(r"Solvability:\s*(\S+)\s*/\s*(\d+)")
_CORR_RE = re.compile(r"Correctness:\s*(\S+)\s*/\s*(\d+)")


def _parse_val_stdout(stdout: str) -> tuple:
    s = _SOLV_RE.search(stdout)
    c = _CORR_RE.search(stdout)
    solvability = s.group(1) if s else "-"
    correctness = c.group(1) if c else "-"
    total = int(c.group(2)) if c else (int(s.group(2)) if s else 0)
    return solvability, correctness, total


def _build_index_flags(indices: list) -> list:
    """Inner scripts accept either --indices or --index_start/--index_end.

    We always send --indices when sampling and when the indices list is
    explicit, so the inner scripts see exactly the same subset.
    """
    return ["--indices", ",".join(str(i) for i in indices)]


def _common_flags(model: str, domain: str, dataset: str, indices: list, out_dir: str, workers: int) -> list:
    return [
        "--domain", domain,
        "--model", model,
        "--data", dataset,
        "--out_dir", out_dir,
        "--workers", str(workers),
        *_build_index_flags(indices),
    ]


def run_formalizer_pipeline(model: str, domain: str, dataset: str,
                            indices: list, out_dir: str, workers: int,
                            solver_backend: str = DEFAULT_SOLVER_BACKEND,
                            solver_base_url: str | None = None) -> BatchResult:
    res = BatchResult(pipeline="llm-as-formalizer-api", domain=domain, dataset=dataset,
                      model=model, indices=list(indices))
    common = _common_flags(model, domain, dataset, indices, out_dir, workers)

    rc, _, _ = _run([PYTHON, f"{SOURCE_DIR}/llm-as-formalizer-api.py", *common], "formalizer-api")
    res.stages["formalize"] = "ok" if rc == 0 else "FAIL"

    solver_command = [
        PYTHON,
        f"{SOURCE_DIR}/run_solver.py",
        "--prediction_type", "llm-as-formalizer-api",
        "--solver-backend", solver_backend,
    ]
    if solver_base_url:
        solver_command.extend(["--solver-base-url", solver_base_url])
    rc, _, _ = _run([*solver_command, *common], "run_solver")
    res.stages["solve"] = "ok" if rc == 0 else "FAIL"

    rc, stdout, _ = _run([PYTHON, f"{SOURCE_DIR}/run_val.py",
                          "--prediction_type", "llm-as-formalizer-api",
                          "--csv_result", *common], "run_val")
    res.stages["validate"] = "ok" if rc == 0 else "FAIL"
    if rc == 0:
        res.solvability, res.correctness, res.total = _parse_val_stdout(stdout)
    else:
        res.solvability = res.correctness = "ERR"
        res.notes = "run_val failed"
    return res


def run_planner_pipeline(model: str, domain: str, dataset: str,
                         indices: list, out_dir: str, workers: int) -> BatchResult:
    res = BatchResult(pipeline="llm-as-planner-api", domain=domain, dataset=dataset,
                      model=model, indices=list(indices))
    common = _common_flags(model, domain, dataset, indices, out_dir, workers)

    rc, _, _ = _run([PYTHON, f"{SOURCE_DIR}/llm-as-planner-api.py", *common], "planner-api")
    res.stages["plan"] = "ok" if rc == 0 else "FAIL"

    rc, stdout, _ = _run([PYTHON, f"{SOURCE_DIR}/run_val.py",
                          "--prediction_type", "llm-as-planner-api",
                          "--csv_result", *common], "run_val")
    res.stages["validate"] = "ok" if rc == 0 else "FAIL"
    if rc == 0:
        res.solvability, res.correctness, res.total = _parse_val_stdout(stdout)
    else:
        res.solvability = res.correctness = "ERR"
        res.notes = "run_val failed"
    return res


def write_summary(models: list, results: list, out_dir: str, run_meta: dict) -> tuple:
    """Write one aggregated summary covering every model in ``models``.

    The summary always carries a ``model`` column. For a single model the files
    keep the legacy name ``sweep_<model>_summary.{md,csv}``; for several models
    they collapse to ``sweep_summary.{md,csv}``.
    """
    if len(models) == 1:
        stem = f"sweep_{models[0].replace('/', '_')}_summary"
    else:
        stem = "sweep_summary"
    csv_path = os.path.join(out_dir, f"{stem}.csv")
    md_path = os.path.join(out_dir, f"{stem}.md")

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "pipeline", "domain", "dataset", "solvability", "correctness",
                    "total", "stage_status", "indices", "notes"])
        for r in results:
            stages = ", ".join(f"{k}={v}" for k, v in r.stages.items())
            w.writerow([r.model, r.pipeline, r.domain, r.dataset, r.solvability, r.correctness,
                        r.total, stages, ",".join(str(i) for i in r.indices), r.notes])

    by_pipeline: dict = {}
    for r in results:
        by_pipeline.setdefault(r.pipeline, []).append(r)

    model_label = (f"model `{models[0]}`" if len(models) == 1
                   else "models " + ", ".join(f"`{m}`" for m in models))
    lines = [f"# Sweep summary - {model_label}", "",
             f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Output dir: `{out_dir}`",
             f"Index range: `[{run_meta['index_start']}, {run_meta['index_end']})`"
             + (f" -- sampled {run_meta['samples']} per batch (seed={run_meta['sample_seed']})"
                if run_meta.get('samples') else " -- full")
             + f" -- workers={run_meta.get('workers', 1)}",
             f"Solver backend: `{run_meta.get('solver_backend', DEFAULT_SOLVER_BACKEND)}`"
             + (
                 f" (`{run_meta['solver_base_url']}`)"
                 if run_meta.get("solver_base_url")
                 else ""
             ),
             ""]
    for pipeline, batches in by_pipeline.items():
        lines += [f"## {pipeline}", "",
                  "| model | domain | dataset | solvability | correctness | total | stages | notes |",
                  "|---|---|---|---:|---:|---:|---|---|"]
        for r in batches:
            stages = "<br>".join(f"`{k}`={v}" for k, v in r.stages.items())
            lines.append(f"| {r.model} | {r.domain} | {r.dataset} | {r.solvability} | "
                         f"{r.correctness} | {r.total} | {stages} | {r.notes} |")
        lines.append("")
    md = "\n".join(lines)
    with open(md_path, "w") as f:
        f.write(md)
    return csv_path, md_path


def _sanitize_tag(tag: str) -> str:
    """Make a user-supplied tag safe to embed in a directory name.

    Whitespace collapses to ``_`` and any character outside ``[A-Za-z0-9._-]``
    is dropped, so e.g. ``"full run / v2"`` becomes ``"full_run_v2"``.
    """
    tag = re.sub(r"\s+", "_", tag.strip())
    return re.sub(r"[^0-9A-Za-z._-]", "", tag)


def _default_out_dir(tag: str = "") -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"sweep_{stamp}"
    safe_tag = _sanitize_tag(tag)
    if safe_tag:
        name = f"{name}_{safe_tag}"
    return os.path.join(ROOT_DIR, "output", name)


def _sample_indices(index_start: int, index_end: int, samples, sample_seed: int) -> list:
    full = list(range(index_start, index_end))
    if samples is None:
        return full
    if samples >= len(full):
        return full
    rng = random.Random(sample_seed)
    return sorted(rng.sample(full, samples))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gpt-5.4-mini",
                   help="model name(s) for both pipelines; comma-separate to sweep several "
                        "(e.g. gpt-5.4-mini,gpt-5.5). Each model's artefacts go under its own "
                        "<model>/ folder and the summary aggregates all models with a 'model' column")
    p.add_argument("--index_start", type=int, default=1)
    p.add_argument("--index_end", type=int, default=101)
    p.add_argument("--samples", type=int, default=None,
                   help="if set, randomly pick this many problem numbers from [index_start, index_end) "
                        "for each batch; if unset (default) the full range is used")
    p.add_argument("--sample_seed", type=int, default=0,
                   help="seed for the per-batch sample selection (default 0; ignored without --samples)")
    p.add_argument("--out_dir", default=None,
                   help="base output directory for this sweep; default 'output/sweep_<timestamp>/' so "
                        "successive sweeps do not clobber each other")
    p.add_argument("--tag", default="",
                   help="optional label appended after the timestamp in the default run dir name "
                        "(e.g. --tag full -> output/sweep_<timestamp>_full/) to mark a run's purpose; "
                        "ignored when --out_dir is given")
    p.add_argument("--pipelines", default="formalizer,planner",
                   help="comma-separated subset of {formalizer,planner}")
    p.add_argument("--pairs", default="",
                   help="optional 'domain:dataset,domain:dataset' subset; "
                        "default is all 8 (domain, dataset) pairs in ./data/")
    p.add_argument("--workers", type=int, default=8,
                   help="parallel worker threads per batch for independent problems "
                        "(passed through to formalizer/planner/solver/val; default 8; use 1 for sequential)")
    p.add_argument(
        "--solver-backend",
        choices=sorted(SUPPORTED_BACKENDS),
        default=DEFAULT_SOLVER_BACKEND,
        help="solver backend for the formalizer-api evaluation stage (default: local)",
    )
    p.add_argument(
        "--solver-base-url",
        default=None,
        help="explicit host-visible solver origin; defaults from --solver-backend",
    )
    args = p.parse_args()

    if args.pairs:
        pairs = [tuple(x.split(":", 1)) for x in args.pairs.split(",") if x.strip()]
    else:
        pairs = DOMAIN_DATA_PAIRS
    pipelines = {x.strip() for x in args.pipelines.split(",") if x.strip()}
    models = [m.strip() for m in args.model.split(",") if m.strip()]
    if not models:
        p.error("--model must name at least one model")

    if args.out_dir and args.tag:
        print("Note: --tag is ignored because --out_dir was given explicitly.")
    out_dir = args.out_dir or _default_out_dir(args.tag)
    os.makedirs(out_dir, exist_ok=True)
    default_solver_base_url, _ = base_urls_for_backend(args.solver_backend)
    solver_base_url = (args.solver_base_url or default_solver_base_url).rstrip("/")

    run_meta = {
        "index_start": args.index_start,
        "index_end": args.index_end,
        "samples": args.samples,
        "sample_seed": args.sample_seed,
        "workers": args.workers,
        "solver_backend": args.solver_backend,
        "solver_base_url": solver_base_url,
    }

    print(f"Out dir: {out_dir}")
    print(f"Models:  {', '.join(models)}")
    print(f"Workers: {args.workers} per batch")
    print(f"Index range: [{args.index_start}, {args.index_end})"
          + (f"  samples={args.samples} seed={args.sample_seed}" if args.samples else "  (full)"))

    results: list = []
    start_wall = time.time()
    for model in models:
        for domain, dataset in pairs:
            indices = _sample_indices(args.index_start, args.index_end, args.samples, args.sample_seed)

            if "formalizer" in pipelines:
                print(f"\n=== [formalizer-api] {model} | {domain} / {dataset}  ({len(indices)} problems) ===", flush=True)
                try:
                    results.append(
                        run_formalizer_pipeline(
                            model,
                            domain,
                            dataset,
                            indices,
                            out_dir,
                            args.workers,
                            args.solver_backend,
                            solver_base_url,
                        )
                    )
                except Exception as e:
                    print(f"!! batch crashed: {e}")
                    results.append(BatchResult(pipeline="llm-as-formalizer-api",
                                               domain=domain, dataset=dataset, model=model,
                                               solvability="ERR", correctness="ERR",
                                               indices=list(indices),
                                               notes=f"sweep exception: {e}"))
                _, md_p = write_summary(models, results, out_dir, run_meta)
                print(f"  partial summary written: {md_p}")

            if "planner" in pipelines:
                print(f"\n=== [planner-api]    {model} | {domain} / {dataset}  ({len(indices)} problems) ===", flush=True)
                try:
                    results.append(run_planner_pipeline(model, domain, dataset, indices, out_dir, args.workers))
                except Exception as e:
                    print(f"!! batch crashed: {e}")
                    results.append(BatchResult(pipeline="llm-as-planner-api",
                                               domain=domain, dataset=dataset, model=model,
                                               solvability="ERR", correctness="ERR",
                                               indices=list(indices),
                                               notes=f"sweep exception: {e}"))
                _, md_p = write_summary(models, results, out_dir, run_meta)
                print(f"  partial summary written: {md_p}")

    csv_p, md_p = write_summary(models, results, out_dir, run_meta)
    print(f"\nDone in {time.time() - start_wall:.1f}s")
    print(f"Summary: {md_p}")
    print(f"CSV:     {csv_p}")


if __name__ == "__main__":
    main()
