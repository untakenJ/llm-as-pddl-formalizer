"""Small, best-effort provenance helpers used by benchmark metadata."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from agent_formalizer.configuration.benchmark_profile import canonical_sha256


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode())


def file_manifest(paths: Iterable[Path], *, root: Path | None = None) -> list[dict]:
    rows: list[dict] = []
    for path in sorted({Path(p) for p in paths}, key=lambda p: str(p)):
        if not path.is_file():
            continue
        try:
            label = str(path.relative_to(root)) if root else str(path)
        except ValueError:
            label = str(path)
        data = path.read_bytes()
        rows.append({"path": label, "sha256": sha256_bytes(data), "bytes": len(data)})
    return rows


def run_text(argv: list[str], timeout: int = 20) -> str | None:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = (result.stdout or result.stderr or "").strip()
    return value if result.returncode == 0 and value else None


def git_info(path: Path) -> dict[str, Any]:
    commit = run_text(["git", "-C", str(path), "rev-parse", "HEAD"])
    try:
        status_result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        dirty = bool(status_result.stdout.strip()) if status_result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        dirty = None
    return {
        "path": str(path.resolve()),
        "commit": commit,
        "dirty": dirty,
    }


def docker_image_info(image: str) -> dict[str, Any]:
    raw = run_text(["docker", "image", "inspect", image], timeout=30)
    if not raw:
        return {"reference": image, "available": False}
    try:
        record = json.loads(raw)[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        return {"reference": image, "available": True, "inspect_sha256": sha256_text(raw)}
    return {
        "reference": image,
        "available": True,
        "id": record.get("Id"),
        "repo_digests": record.get("RepoDigests") or [],
        "created": record.get("Created"),
        "os": record.get("Os"),
        "architecture": record.get("Architecture"),
    }


def host_runtime_info(*, include_docker: bool = True) -> dict[str, Any]:
    value = {
        "python": sys.version.splitlines()[0],
        "platform": platform.platform(),
    }
    if include_docker:
        value["docker"] = run_text(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        )
    else:
        value["docker_required"] = False
    return value


def fingerprint(value: Any) -> dict[str, Any]:
    return {"sha256": canonical_sha256(value), "value": value}
