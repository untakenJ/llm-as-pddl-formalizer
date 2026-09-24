"""Content-addressed releases; no secrets, weights, outputs or runtime installs."""

from __future__ import annotations

import gzip
import io
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path

from .protocol import canonical, digest, exact, file_hash, private_json, read_json, relative, safe_path, sha256

EXCLUDED = {".git", ".venv", "_private", "output", ".cache", "__pycache__", "node_modules"}
LOCAL_ONLY = {"source/remote_execution/node.local.json", "source/remote_execution/vllm.local.json"}


def allowed(name):
    parts = Path(relative(name)).parts
    return (name not in LOCAL_ONLY and
            not any(part in EXCLUDED or part.startswith(".env") for part in parts) and
            not name.endswith((".pyc", ".safetensors", ".gguf")))


def inventory(root: Path, includes: list[str]):
    """Read-only inventory, using exactly the same input rules as packaging."""
    root = root.resolve(strict=True)
    rows = {}
    for name in includes:
        path = safe_path(root, name)
        if not allowed(name):
            raise ValueError(f"Excluded release input: {name}")
        if not path.exists():
            raise ValueError(f"Missing release input: {name}")
        candidates = path.rglob("*") if path.is_dir() else [path]
        for item in candidates:
            rel = item.relative_to(root).as_posix()
            if not allowed(rel):
                continue
            if item.is_symlink():
                raise ValueError(f"Release input is a symlink: {rel}")
            if item.is_dir():
                continue
            if not stat.S_ISREG(item.stat().st_mode):
                raise ValueError("Release inputs must be regular files")
            rows[rel] = {"sha256": file_hash(item), "size": item.stat().st_size,
                         "executable": bool(item.stat().st_mode & 0o111)}
    if not rows:
        raise ValueError("Empty release")
    return {"schema_version": 1, "files": dict(sorted(rows.items()))}


def build(root: Path, includes: list[str], destination: Path):
    """Explicit includes only. Destination is create-only, outside included trees."""
    root = root.resolve(strict=True)
    manifest = inventory(root, includes)
    if any((root / name).resolve() == destination.resolve() for name in manifest["files"]):
        raise ValueError("Archive cannot contain itself")
    release_id = digest(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as target, gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w|") as archive:
            payload = canonical(manifest)
            info = tarfile.TarInfo("manifest.json"); info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
            for name, row in manifest["files"].items():
                info = tarfile.TarInfo("workspace/" + name)
                info.size = row["size"]; info.mode = 0o755 if row["executable"] else 0o644
                with safe_path(root, name).open("rb") as stream:
                    archive.addfile(info, stream)
                if file_hash(root / name) != row["sha256"]:
                    raise ValueError("Release source changed during packaging; discard this archive")
    return {"release_id": release_id, "archive_sha256": file_hash(destination),
            "bytes": destination.stat().st_size, "files": len(manifest["files"])}


def verify(release: Path):
    manifest = read_json(release / "manifest.json")
    exact(manifest, {"schema_version", "files"})
    if manifest["schema_version"] != 1 or not isinstance(manifest["files"], dict):
        raise ValueError("Invalid release manifest")
    actual = set()
    for parent, directories, files in os.walk(release / "workspace", followlinks=False):
        directories[:] = [name for name in directories if name not in EXCLUDED]
        for name in directories:
            if (Path(parent) / name).is_symlink():
                raise ValueError("Unexpected release directory symlink")
        for name in files:
            relative_name = (Path(parent) / name).relative_to(release / "workspace").as_posix()
            if allowed(relative_name):
                actual.add(relative_name)
    if actual != set(manifest["files"]):
        raise ValueError("Release file inventory changed")
    for name, row in manifest["files"].items():
        if not allowed(name):
            raise ValueError("Excluded release member")
        exact(row, {"sha256", "size", "executable"})
        sha256(row["sha256"])
        path = safe_path(release / "workspace", name)
        if (not path.is_file() or path.stat().st_size != row["size"] or file_hash(path) != row["sha256"]
                or bool(path.stat().st_mode & 0o111) != row["executable"]):
            raise ValueError(f"Release hash mismatch: {name}")
    return manifest


def install(archive: Path, releases: Path, expected: str, *, max_bytes=2 * 1024**3):
    sha256(expected)
    releases.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = releases / expected
    if destination.exists():
        if digest(verify(destination)) != expected:
            raise ValueError("Existing release identity mismatch")
        return destination
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=releases))
    try:
        (staging / "workspace").mkdir()
        total = 0; members = set()
        with tarfile.open(archive, "r:gz") as stream:
            for member in stream:
                if not member.isfile() or member.name in members or len(members) >= 100000:
                    raise ValueError("Only unique regular archive members are accepted")
                if member.name != "manifest.json" and not member.name.startswith("workspace/"):
                    raise ValueError("Invalid release member root")
                target = safe_path(staging, member.name)
                total += member.size
                if total > max_bytes or (member.name == "manifest.json" and member.size > 16 * 1024**2):
                    raise ValueError("Expanded release exceeds node limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output, stream.extractfile(member) as source:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
                members.add(member.name)
        manifest = verify(staging)
        expected_members = {"manifest.json"} | {"workspace/" + p for p in manifest["files"]}
        if members != expected_members or digest(manifest) != expected:
            raise ValueError("Release contents/identity mismatch")
        try:
            os.rename(staging, destination)
        except OSError:
            if not destination.exists() or digest(verify(destination)) != expected:
                raise
        return destination
    finally:
        # Only this function's fresh staging tree; never follows archive links.
        if staging.exists():
            shutil.rmtree(staging)


def bind_runtime(release: Path, bindings: dict):
    """Node-owned paths only. Never change an existing binding on resume."""
    targets = {"harness_runtimes": "workspace/.cache/harness-runtimes",
               "zeroclaw_deadlines": "workspace/.cache/zeroclaw-deadlines",
               "val": "VAL", "secrets_env_file": "workspace/_private/.env"}
    for key, value in bindings.items():
        source = Path(value).resolve(strict=True)
        # These host binaries are passed through the validated execution-node
        # environment and bind-mounted by the existing OpenClaw adapter.
        if key in {"openclaw_node_bin", "openclaw_module_dir"}:
            continue
        link = release / targets[key]
        if link.is_symlink():
            if link.resolve(strict=True) != source:
                raise ValueError("Existing release runtime binding changed")
        elif link.exists():
            raise ValueError("Runtime binding would replace release content")
        else:
            link.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            link.symlink_to(source, target_is_directory=source.is_dir())
