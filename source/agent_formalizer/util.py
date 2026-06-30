"""Small self-contained utilities for the agentic formalizer package.

We deliberately keep a local copy of the ``Tracer`` (same JSONL format as
``source/api_providers.py``) and the batch helpers (same semantics as
``source/batch_utils.py``) so this package has no import-time dependency on the
other ``source/`` modules (which pull in heavy SDKs like ``openai``).
"""

from __future__ import annotations

import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def now_iso() -> str:
    """UTC timestamp, matching api_providers._now()."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def format_problem_name(problem_number: int) -> str:
    return f"p0{problem_number}" if problem_number < 10 else f"p{problem_number}"


def run_parallel(items, worker, workers: int = 1):
    """Run ``worker(item)`` over ``items``; use a thread pool when workers > 1."""
    if workers <= 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(worker, items))


def load_private_secrets(root: Path | None = None) -> dict[str, str]:
    """Load ``_private/.env`` into the environment as the highest-priority source.

    ``_private/.env`` is the single, explicit credential source for benchmark
    runs. Values here OVERRIDE any pre-existing environment variables (so a run
    never silently uses a stale shell value or the operator's personal harness
    config). Returns the dict of keys that were applied.
    """
    from agent_formalizer.config import ROOT_DIR

    base = Path(root) if root is not None else ROOT_DIR
    env_file = base / "_private" / ".env"
    applied: dict[str, str] = {}
    if not env_file.is_file():
        return applied
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value  # .env wins over the inherited environment
            applied[key] = value
    return applied


class Tracer:
    """Append-only JSONL writer. No-ops when ``path`` is None.

    Identical on-disk format to ``api_providers.Tracer`` so downstream trace
    tooling treats agent traces and API traces the same way.
    """

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
        rec = {"event": event, "ts": now_iso(), **fields}
        self._fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def close(self):
        if self._fp is not None:
            self._fp.close()
            self._fp = None
