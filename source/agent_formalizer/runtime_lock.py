"""Validation of the pinned, user-space harness runtime closure."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from agent_formalizer.benchmark_profile import canonical_sha256
from agent_formalizer.config import (
    OPENCLAW_MODULE_DIR,
    OPENCLAW_NODE_BIN,
    ZEROCLAW_BIN,
    ZEROCLAW_SOURCE_PATH,
    ZEROCLAW_VERSION_NOTE_PATH,
)
from agent_formalizer.provenance import sha256_bytes


LOCK_PATH = Path(__file__).with_name("runtime_lock.json")


class RuntimeLockMismatch(RuntimeError):
    """Raised before an attempt when the installed closure does not match."""


def load_runtime_lock() -> dict[str, Any]:
    return json.loads(LOCK_PATH.read_text())


def _file_sha256(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def _python_manifest(python: Path) -> tuple[str | None, int | None]:
    code = (
        "import hashlib,importlib.metadata as m,json;"
        "r=sorted(f'{d.metadata.get(chr(78)+chr(97)+chr(109)+chr(101),d.name).lower()}=={d.version}' "
        "for d in m.distributions());"
        "b=json.dumps(r,separators=(\",\",\":\"),ensure_ascii=False).encode();"
        "print(hashlib.sha256(b).hexdigest(),len(r))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code], capture_output=True, text=True, timeout=60
        )
        digest, count = result.stdout.strip().split()
        if result.returncode == 0:
            return digest, int(count)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None, None


def _python_distribution_payload(
    runtime_env: Path, distribution: str
) -> tuple[str | None, int | None]:
    """Hash actual installed files belonging to the harness distribution."""
    sites = sorted((runtime_env / "lib").glob("python*/site-packages"))
    if not sites:
        return None, None
    site = sites[0]
    normalized = distribution.lower().replace("_", "-")
    for info in sorted(site.glob("*.dist-info")):
        metadata = info / "METADATA"
        record = info / "RECORD"
        if not metadata.is_file() or not record.is_file():
            continue
        name = None
        for line in metadata.read_text(errors="replace").splitlines():
            if line.lower().startswith("name:"):
                name = line.split(":", 1)[1].strip().lower().replace("_", "-")
                break
        if name != normalized:
            continue
        rows: list[dict[str, Any]] = []
        with record.open(newline="") as stream:
            for row in csv.reader(stream):
                if not row:
                    continue
                relative = row[0]
                path = site / relative
                if not path.is_file():
                    continue
                payload = path.read_bytes()
                rows.append({
                    "path": relative,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                })
        return canonical_sha256(rows), len(rows)
    return None, None


def _git_tracked_payload(root: Path) -> tuple[str | None, int | None]:
    raw = _run_text(["git", "-C", str(root), "ls-files", "-z"])
    if raw is None:
        return None, None
    paths = [root / value for value in raw.split("\0") if value]
    rows = [
        {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in paths
        if path.is_file()
    ]
    return canonical_sha256(rows), len(rows)


def _tree_payload(root: Path, paths: list[Path]) -> tuple[str, int]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                candidate for candidate in path.glob("**/*") if candidate.is_file()
            )
    rows = [
        {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(set(files), key=lambda item: str(item))
        if "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    return canonical_sha256(rows), len(rows)


def _node_manifest(root: Path) -> tuple[str, int]:
    rows: list[str] = []
    for path in root.glob("**/package.json"):
        try:
            package = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if package.get("name") and package.get("version"):
            rows.append(f"{package['name']}=={package['version']}")
    rows.sort()
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest(), len(rows)


def _run_text(argv: list[str]) -> str | None:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def observe_runtime(adapter) -> dict[str, Any]:
    name = adapter.name
    assets = adapter.skills_info().get("manifest", [])
    asset_identity = {
        "native_assets_manifest_sha256": canonical_sha256(assets),
        "native_assets_count": len(assets),
    }
    if name in {"hermes", "nanobot", "generic"}:
        digest, count = _python_manifest(adapter.runtime_python)
        observed: dict[str, Any] = {
            "python_version": _run_text([str(adapter.runtime_python), "--version"]),
            "python_executable_sha256": _file_sha256(
                adapter.runtime_python.resolve()
            ),
            "python_distribution_manifest_sha256": digest,
            "python_distribution_count": count,
        }
        if name != "generic":
            distribution = "hermes-agent" if name == "hermes" else "nanobot-ai"
            payload_digest, payload_count = _python_distribution_payload(
                adapter.runtime_env, distribution
            )
            code = (
                "import importlib.metadata as m;"
                f"print(m.version({distribution!r}))"
            )
            observed["distribution"] = distribution
            observed["version"] = _run_text([str(adapter.runtime_python), "-c", code])
            observed["harness_payload_manifest_sha256"] = payload_digest
            observed["harness_payload_count"] = payload_count
        else:
            payload_digest, payload_count = _git_tracked_payload(adapter.runtime_repo)
            observed["source_commit"] = _run_text(
                ["git", "-C", str(adapter.runtime_repo), "rev-parse", "HEAD"]
            )
            observed["pyproject_sha256"] = _file_sha256(
                adapter.runtime_repo / "pyproject.toml"
            )
            observed["source_payload_manifest_sha256"] = payload_digest
            observed["source_payload_count"] = payload_count
        return {**observed, **asset_identity}
    if name == "minimum":
        runtime = Path(__file__).with_name("minimum_agent_runtime.py")
        return {
            "runtime_kind": "benchmark-owned-python-stdlib",
            "runtime_entrypoint_sha256": _file_sha256(runtime),
            **asset_identity,
        }
    if name == "openclaw":
        root = Path(OPENCLAW_MODULE_DIR)
        digest, count = _node_manifest(root)
        payload_digest, payload_count = _tree_payload(
            root,
            [root / "openclaw.mjs", root / "package.json", root / "dist"],
        )
        return {
            "version": _run_text(
                [str(OPENCLAW_NODE_BIN), str(root / "openclaw.mjs"), "--version"]
            ),
            "node_version": _run_text([str(OPENCLAW_NODE_BIN), "--version"]),
            "node_binary_sha256": _file_sha256(Path(OPENCLAW_NODE_BIN).resolve()),
            "package_json_sha256": _file_sha256(root / "package.json"),
            "node_distribution_manifest_sha256": digest,
            "node_distribution_count": count,
            "runtime_payload_manifest_sha256": payload_digest,
            "runtime_payload_count": payload_count,
            **asset_identity,
        }
    if name == "zeroclaw":
        version = _run_text([str(ZEROCLAW_BIN), "--version"])
        if ZEROCLAW_VERSION_NOTE_PATH.is_file():
            note = ZEROCLAW_VERSION_NOTE_PATH.read_text(encoding="utf-8").strip()
            if note:
                version = f"{version} ({note})"
        return {
            "version": version,
            "binary_sha256": _file_sha256(ZEROCLAW_BIN),
            "source_commit": _run_text(
                ["git", "-C", str(ZEROCLAW_SOURCE_PATH), "rev-parse", "HEAD"]
            ),
            "cargo_lock_sha256": _file_sha256(ZEROCLAW_SOURCE_PATH / "Cargo.lock"),
            **asset_identity,
        }
    raise ValueError(f"No runtime-lock observer for {name}")


def validate_runtime_lock(
    adapter, *, container_image_id: str | None = None
) -> dict[str, Any]:
    lock = load_runtime_lock()
    expected = lock["harnesses"][adapter.name]
    observed = observe_runtime(adapter)
    mismatches = {
        key: {"expected": value, "observed": observed.get(key)}
        for key, value in expected.items()
        if observed.get(key) != value
    }
    container_expected = lock["container"]
    container_mismatches = {}
    dockerfile = Path(__file__).with_name("docker") / "Dockerfile"
    container_required = adapter.name != "minimum"
    observed_dockerfile_sha256 = (
        _file_sha256(dockerfile) if container_required else None
    )
    if (
        container_required
        and observed_dockerfile_sha256 != container_expected["dockerfile_sha256"]
    ):
        container_mismatches["dockerfile_sha256"] = {
            "expected": container_expected["dockerfile_sha256"],
            "observed": observed_dockerfile_sha256,
        }
    if (
        container_required
        and container_image_id is not None
        and container_image_id != container_expected["image_id"]
    ):
        container_mismatches["image_id"] = {
            "expected": container_expected["image_id"],
            "observed": container_image_id,
        }
    evidence = {
        "preset": "runtime-lock",
        "version": 1,
        "status": "pass" if not mismatches and not container_mismatches else "fail",
        "lock_id": lock["lock_id"],
        "lock_sha256": canonical_sha256(lock),
        "expected": expected,
        "observed": observed,
        "mismatches": mismatches,
        "container": {
            "required": container_required,
            "expected": container_expected,
            "observed": {
                "image_id": container_image_id,
                "dockerfile_sha256": observed_dockerfile_sha256,
            },
            "mismatches": container_mismatches,
        },
    }
    if mismatches or container_mismatches:
        raise RuntimeLockMismatch(
            f"{adapter.name} runtime closure does not match {lock['lock_id']}: "
            + ", ".join(sorted([*mismatches, *container_mismatches]))
        )
    return evidence
