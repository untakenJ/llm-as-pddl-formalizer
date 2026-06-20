"""Shared helpers for parallel per-problem batch execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def format_problem_name(problem_number: int) -> str:
    return f"p0{problem_number}" if problem_number < 10 else f"p{problem_number}"


def run_parallel(items, worker, workers: int = 1):
    """Run ``worker(item)`` over ``items``; use a thread pool when ``workers > 1``."""
    if workers <= 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(worker, items))
