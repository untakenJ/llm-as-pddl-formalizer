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
import re
import shlex
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


_ENV_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$"
)


def _read_named_env_file_value(name: str, env_file: str | Path) -> str | None:
    """Read one dotenv assignment without evaluating or expanding the file."""
    path = Path(env_file).expanduser()
    if not path.is_file():
        return None
    selected = None
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        match = _ENV_ASSIGNMENT.match(line)
        if not match or match.group("name") != name:
            continue
        lexer = shlex.shlex(match.group("value"), posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            parts = list(lexer)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid dotenv value for {name!r} at {path}:{line_number}"
            ) from exc
        selected = " ".join(parts)
    return selected


def read_named_setting(name: str, env_file: str | Path | None = None) -> str:
    """Read one explicitly named runner input from a dotenv file or environment.

    The repository-local file has precedence. No other assignments are
    returned, exported, interpolated, or inherited by an agent process.
    """
    value = (
        _read_named_env_file_value(name, env_file)
        if env_file is not None
        else None
    )
    if value is None:
        value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required benchmark runner variable {name!r} is not set"
        )
    return value


def read_named_secret(name: str, env_file: str | Path | None = None) -> str:
    """Read exactly one credential without scanning personal harness config."""
    return read_named_setting(name, env_file)


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
