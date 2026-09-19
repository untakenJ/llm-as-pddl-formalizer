"""Validation of the pinned, user-space harness runtime closure."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from agent_formalizer.configuration.benchmark_profile import canonical_sha256
from agent_formalizer.configuration.config import (
    PACKAGE_DIR,
    LOGITS_BRIDGE_ENV_PATH,
    LOGITS_BRIDGE_SCRIPT,
    LOGITS_GATEWAY_SCRIPT,
    LOGITS_MODEL_ASSETS_ROOT,
    OPENCLAW_MODULE_DIR,
    OPENCLAW_NODE_BIN,
    ZEROCLAW_BIN,
    ZEROCLAW_SOURCE_PATH,
    ZEROCLAW_VERSION_NOTE_PATH,
)
from agent_formalizer.results.provenance import sha256_bytes


LOCK_PATH = Path(__file__).with_name("runtime_lock.json")
TEXT_LOCK_PATH = Path(__file__).with_name("runtime_lock_text_v1.json")
TEXT_POLICY = "remote-text-v1"


class RuntimeLockMismatch(RuntimeError):
    """Raised before an attempt when the installed closure does not match."""


def load_runtime_lock(path: Path | str | None = None) -> dict[str, Any]:
    # The local default remains the original, byte-strict lock. Remote releases
    # explicitly select the separate text policy; no ambient env override.
    return json.loads((Path(path) if path is not None else LOCK_PATH).read_text())


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
        runtime = PACKAGE_DIR / "claws" / "minimum" / "runtime.py"
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


def observe_logits_transport() -> dict[str, Any]:
    python = LOGITS_BRIDGE_ENV_PATH / "bin" / "python"
    digest, count = _python_manifest(python)
    asset_files = [
        path
        for path in LOGITS_MODEL_ASSETS_ROOT.glob("**/*")
        if path.is_file()
        and ".cache" not in path.relative_to(LOGITS_MODEL_ASSETS_ROOT).parts
    ]
    assets_digest, assets_count = _tree_payload(
        LOGITS_MODEL_ASSETS_ROOT, asset_files
    )
    return {
        "python_version": _run_text([str(python), "--version"]),
        "python_executable_sha256": _file_sha256(python.resolve()),
        "python_distribution_manifest_sha256": digest,
        "python_distribution_count": count,
        "bridge_entrypoint_sha256": _file_sha256(LOGITS_BRIDGE_SCRIPT),
        "gateway_entrypoint_sha256": _file_sha256(LOGITS_GATEWAY_SCRIPT),
        "model_assets_manifest_sha256": assets_digest,
        "model_assets_count": assets_count,
    }


# A deliberately enumerated contract, not "compare whatever happens to be in
# the observed manifest". Binary identities remain in the observation/audit.
_ASSETS = {"native_assets_manifest_sha256"}
_PYTHON = {"python_runtime", "python_distribution_manifest_sha256"}
_TEXT_FIELDS = {
    "hermes": _ASSETS | _PYTHON | {"distribution", "version", "harness_text_manifest_sha256"},
    "nanobot": _ASSETS | _PYTHON | {"distribution", "version", "harness_text_manifest_sha256"},
    "generic": _ASSETS | _PYTHON | {"source_commit", "source_worktree_clean"},
    "openclaw": _ASSETS | {"version", "node_runtime", "node_distribution_manifest_sha256",
                            "runtime_text_manifest_sha256"},
    "zeroclaw": _ASSETS | {"version", "source_commit", "source_worktree_clean", "cargo_lock_sha256"},
    "minimum": _ASSETS | {"runtime_kind", "runtime_entrypoint_sha256"},
}
_LOGITS_TEXT_FIELDS = {
    "python_runtime", "python_distribution_manifest_sha256", "bridge_entrypoint_sha256",
    "gateway_entrypoint_sha256", "model_assets_manifest_sha256",
}
_TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".json", ".jsonl", ".toml", ".yaml", ".yml",
    ".md", ".txt", ".jinja", ".jinja2", ".j2", ".sh", ".bash", ".ini", ".cfg",
    ".html", ".css", ".sql", ".xml", ".svg",
}
_CONTAINER_COMMANDS = sorted({
    "sh", "bash", "python3", "git", "curl", "timeout", "grep", "sed", "awk", "find", "head", "tail",
})


def _python_runtime(python: Path) -> str | None:
    return _run_text([str(python), "-B", "-c",
                      "import sys; print(sys.implementation.name+'-'+'.'.join(map(str,sys.version_info[:2])))"])


def _text_tree_payload(root: Path, paths: list[Path]) -> str:
    """Hash runtime text, not generated bytecode, binaries or install metadata.

    No whitespace/AST/path rewriting: text handed to a harness may be a prompt.
    The manifest uses relative names and deterministic ordering. Missing declared
    inputs and escaping links fail closed rather than shrinking the inventory.
    """
    root = root.resolve()
    files: set[Path] = set()
    for path in paths:
        if not path.exists():
            raise RuntimeLockMismatch(f"missing runtime text input: {path}")
        candidates = path.rglob("*") if path.is_dir() else [path]
        for item in candidates:
            relative = item.relative_to(root)
            if "__pycache__" in relative.parts or item.suffix not in _TEXT_SUFFIXES:
                continue
            if not item.resolve().is_relative_to(root):
                raise RuntimeLockMismatch(f"runtime text link escapes package: {relative}")
            if item.is_file():
                files.add(item)
    rows = []
    for path in sorted(files):
        data = path.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeLockMismatch(f"runtime text is not UTF-8: {path.relative_to(root)}") from exc
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_bytes(data)})
    if not rows:
        raise RuntimeLockMismatch("runtime text inventory is empty")
    return canonical_sha256(rows)


def _python_text_payload(runtime_env: Path, distribution: str) -> str:
    runtime_env = runtime_env.resolve()
    sites = sorted((runtime_env / "lib").glob("python*/site-packages"))
    if not sites:
        raise RuntimeLockMismatch("Python site-packages is missing")
    site = sites[0].resolve()
    normalized = distribution.lower().replace("_", "-")
    for info in sorted(site.glob("*.dist-info")):
        metadata = info / "METADATA"
        if not metadata.is_file():
            continue
        names = [line[5:].strip().lower().replace("_", "-")
                 for line in metadata.read_text().splitlines() if line.lower().startswith("name:")]
        if names != [normalized]:
            continue
        record = info / "RECORD"
        if not record.is_file():
            raise RuntimeLockMismatch(f"missing distribution RECORD: {distribution}")
        roots: set[Path] = set()
        with record.open(newline="") as stream:
            for row in csv.reader(stream):
                if not row:
                    continue
                relative = Path(row[0])
                # These adapters import the CLI using their selected Python;
                # pip/uv's bin launchers (absolute shebang) are never executed.
                if relative.parts[:3] == ("..", "..", "..") and relative.parts[3:4] == ("bin",):
                    continue
                if relative.is_absolute() or not relative.parts:
                    raise RuntimeLockMismatch("unsafe Python RECORD path")
                installed = (site / relative).resolve()
                if not installed.is_relative_to(runtime_env):
                    raise RuntimeLockMismatch("Python RECORD escapes runtime environment")
                if any(part.endswith(".dist-info") for part in relative.parts):
                    continue
                if relative.suffix in _TEXT_SUFFIXES and "__pycache__" not in relative.parts:
                    if not installed.is_file():
                        raise RuntimeLockMismatch(f"missing installed runtime text: {relative}")
                    # Wheel data such as Hermes locales/templates can live at
                    # the venv root rather than inside site-packages.
                    base = site if installed.is_relative_to(site) else runtime_env
                    roots.add(base / installed.relative_to(base).parts[0])
        # Scan actual package roots, not only RECORD entries: added Python files
        # must also change the identity. Plugin entry point declarations matter.
        if (info / "entry_points.txt").is_file():
            roots.add(info / "entry_points.txt")
        return _text_tree_payload(runtime_env, sorted(roots))
    raise RuntimeLockMismatch(f"distribution metadata not found: {distribution}")


def observe_text_runtime(adapter) -> dict[str, Any]:
    """Retain exact artifact observations, adding portable comparison fields."""
    observed = observe_runtime(adapter)
    if adapter.name in {"hermes", "nanobot", "generic"}:
        observed["python_runtime"] = _python_runtime(adapter.runtime_python)
        if adapter.name != "generic":
            observed["harness_text_manifest_sha256"] = _python_text_payload(
                adapter.runtime_env, observed["distribution"])
    if adapter.name in {"generic", "zeroclaw"}:
        repo = adapter.runtime_repo if adapter.name == "generic" else ZEROCLAW_SOURCE_PATH
        observed["source_worktree_clean"] = _run_text(
            ["git", "-C", str(repo), "diff", "--no-ext-diff", "HEAD", "--name-only", "--"]) == ""
    if adapter.name == "openclaw":
        match = re.fullmatch(r"v(\d+)\.\d+\.\d+", observed["node_version"] or "")
        observed["node_runtime"] = f"node-{match[1]}" if match else None
        root = Path(OPENCLAW_MODULE_DIR).resolve()
        observed["runtime_text_manifest_sha256"] = _text_tree_payload(
            root, [root / "openclaw.mjs", root / "package.json", root / "dist"])
    if adapter.name == "zeroclaw":
        observed["version_note"] = observed["version"]
        observed["version"] = _run_text([str(ZEROCLAW_BIN), "--version"])
    return observed


def observe_container_capabilities(image_id: str) -> dict[str, Any]:
    """One bounded, network-free preflight, never a case/model/solver run."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeLockMismatch("container preflight requires a frozen image ID")
    name = "pddl-runtime-preflight-" + uuid.uuid4().hex
    script = (
        "import json,sys,shutil; print(json.dumps({"
        "'os':sys.platform,'python_runtime':sys.implementation.name+'-'+'.'.join(map(str,sys.version_info[:2])),"
        f"'commands':[name for name in {_CONTAINER_COMMANDS!r} if shutil.which(name)]}}))"
    )
    try:
        result = subprocess.run([
            "docker", "run", "--rm", "--pull", "never", "--name", name,
            "--network", "none", "--read-only", "--pids-limit", "64", "--memory", "128m",
            "--cpus", "1", "--entrypoint", "python3", image_id, "-B", "-c", script,
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeLockMismatch("container runtime capability probe failed: " + result.stderr[:500])
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError("container capability response must be an object")
        return value
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeLockMismatch(f"container capability probe failed: {type(exc).__name__}") from exc
    finally:
        # This UUID names only our own probe. A client timeout must not strand it.
        try:
            cleanup = subprocess.run(["docker", "rm", "--force", name],
                                     capture_output=True, text=True, timeout=15)
            if cleanup.returncode and "No such container" not in cleanup.stderr:
                raise RuntimeLockMismatch("container capability probe cleanup failed: " + name)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeLockMismatch("container capability probe cleanup failed: " + name) from exc


def observe_zeroclaw_container_runtime(adapter, image_id: str) -> dict[str, str]:
    """Test the selected binary's ABI, not merely the host installation.

    A source-identical Rust build can need a newer glibc than the task image.
    This zero-model probe also covers the derived checkpoint overlay. It does
    not change the image, executable, profile, or byte-strict local policy.
    """
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeLockMismatch("ZeroClaw startup probe requires a frozen image ID")
    binary = Path(adapter.execution_binary()).resolve(strict=True)
    if not binary.is_file() or "," in str(binary):
        raise RuntimeLockMismatch("invalid ZeroClaw startup probe executable")
    name = "pddl-runtime-preflight-" + uuid.uuid4().hex
    try:
        result = subprocess.run([
            "docker", "run", "--rm", "--pull", "never", "--name", name,
            "--network", "none", "--read-only", "--pids-limit", "64", "--memory", "128m",
            "--cpus", "1", "--mount", f"type=bind,source={binary},target=/usr/local/bin/zeroclaw,readonly",
            "--entrypoint", "/usr/local/bin/zeroclaw", image_id, "--version",
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeLockMismatch("ZeroClaw cannot start in the task image: " + result.stderr[:500])
        return {"version": result.stdout.strip(), "binary_sha256": _file_sha256(binary)}
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeLockMismatch(f"ZeroClaw container startup probe failed: {type(exc).__name__}") from exc
    finally:
        try:
            cleanup = subprocess.run(["docker", "rm", "--force", name],
                                     capture_output=True, text=True, timeout=15)
            if cleanup.returncode and "No such container" not in cleanup.stderr:
                raise RuntimeLockMismatch("ZeroClaw startup probe cleanup failed: " + name)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeLockMismatch("ZeroClaw startup probe cleanup failed: " + name) from exc


def _validate_text_lock_schema(lock: dict) -> None:
    if (set(lock) != {"schema_version", "policy", "lock_id", "container", "harnesses", "provider_transports"}
            or type(lock["schema_version"]) is not int or lock["schema_version"] != 2
            or lock["policy"] != TEXT_POLICY or not isinstance(lock["lock_id"], str) or not lock["lock_id"]):
        raise ValueError("invalid remote text runtime lock")
    scopes = {name: (lock["harnesses"].get(name), fields) for name, fields in _TEXT_FIELDS.items()}
    if set(lock["harnesses"]) != set(_TEXT_FIELDS) or set(lock["provider_transports"]) != {"logits"}:
        raise ValueError("remote text lock must enumerate every supported runtime")
    scopes["logits"] = (lock["provider_transports"]["logits"], _LOGITS_TEXT_FIELDS)
    for name, (expected, fields) in scopes.items():
        if not isinstance(expected, dict) or set(expected) != fields:
            raise ValueError(f"incorrect required text checks for {name}")
        for key, value in expected.items():
            if key == "source_worktree_clean":
                valid = value is True
            elif key.endswith("sha256"):
                valid = isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            else:
                valid = isinstance(value, str) and bool(value)
            if not valid:
                raise ValueError(f"invalid expected text check: {name}.{key}")
    container = lock["container"]
    capabilities = {"os": "linux", "python_runtime": "cpython-3.12", "commands": _CONTAINER_COMMANDS}
    if (set(container) != {"dockerfile_sha256", "runtime_capabilities"}
            or container["runtime_capabilities"] != capabilities
            or not isinstance(container["dockerfile_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", container["dockerfile_sha256"])):
        raise ValueError("invalid container text/capability contract")


def _differences(expected: dict, observed: dict) -> dict:
    return {key: {"expected": value, "observed": observed.get(key)}
            for key, value in expected.items()
            if type(observed.get(key)) is not type(value) or observed.get(key) != value}


def _validate_text_runtime_lock(adapter, lock: dict, image_id: str | None) -> dict:
    _validate_text_lock_schema(lock)
    expected = lock["harnesses"][adapter.name]
    observed = observe_text_runtime(adapter)
    mismatches = _differences(expected, observed)
    container = {"required": adapter.name != "minimum", "expected": lock["container"],
                 "observed": {"image_id": image_id}, "mismatches": {}}
    if container["required"]:
        if image_id is None:
            raise RuntimeLockMismatch("remote text validation requires the frozen container image")
        container["observed"].update({
            "dockerfile_sha256": _file_sha256(PACKAGE_DIR / "docker/Dockerfile"),
            "runtime_capabilities": observe_container_capabilities(image_id),
        })
        container["mismatches"] = _differences(container["expected"], container["observed"])
    provider = None
    if getattr(adapter, "raw_provider", getattr(adapter, "provider", None)) == "logits":
        actual = observe_logits_transport()
        actual["python_runtime"] = _python_runtime(LOGITS_BRIDGE_ENV_PATH / "bin/python")
        target = lock["provider_transports"]["logits"]
        provider = {"name": "logits", "expected": target, "observed": actual,
                    "mismatches": _differences(target, actual)}
    failures = sorted([*mismatches, *container["mismatches"], *(provider or {}).get("mismatches", {})])
    if failures:
        raise RuntimeLockMismatch(f"{adapter.name} does not match {lock['lock_id']}: " + ", ".join(failures))
    if adapter.name == "zeroclaw":
        startup = observe_zeroclaw_container_runtime(adapter, image_id)
        if startup["version"] != expected["version"]:
            raise RuntimeLockMismatch("ZeroClaw task-container version does not match the pinned runtime")
        container["observed"]["harness_startup"] = startup
    # Only the selected checks enter comparability/resume identity. The full
    # observed binary/image hashes remain in evidence, never in this projection.
    comparison = {"policy": TEXT_POLICY, "lock_id": lock["lock_id"],
                  "harness": adapter.name, "checks": {key: observed[key] for key in expected},
                  "container": container["expected"] if container["required"] else None,
                  "provider_transport": provider["expected"] if provider else None}
    return {"preset": "runtime-lock", "version": 1, "policy": TEXT_POLICY,
            "status": "pass", "lock_id": lock["lock_id"], "lock_sha256": canonical_sha256(lock),
            "expected": expected, "observed": observed, "mismatches": mismatches,
            "container": container, "provider_transport": provider, "comparison_identity": comparison}


def execution_runtime_identity(runtime_lock: dict, image_id: str | None, code_hash: str,
                               *, host_only: bool = False) -> dict:
    if runtime_lock.get("policy") == TEXT_POLICY:
        identity = {"runtime_lock": runtime_lock["comparison_identity"], "adapter_code_sha256": code_hash}
    else:
        # Preserve the old byte-strict identity structure exactly.
        identity = {"runtime_lock": runtime_lock, "container_image_id": image_id,
                    "adapter_code_sha256": code_hash}
    if host_only:
        identity["execution_backend"] = "host"
    return identity


def validate_runtime_lock(
    adapter, *, container_image_id: str | None = None, lock_path: Path | str | None = None
) -> dict[str, Any]:
    lock = load_runtime_lock(lock_path) if lock_path is not None else load_runtime_lock()
    if lock.get("schema_version") == 2:
        return _validate_text_runtime_lock(adapter, lock, container_image_id)
    if type(lock.get("schema_version")) is not int or lock["schema_version"] != 1:
        raise ValueError("unsupported runtime lock schema")
    expected = lock["harnesses"][adapter.name]
    observed = observe_runtime(adapter)
    mismatches = {
        key: {"expected": value, "observed": observed.get(key)}
        for key, value in expected.items()
        if observed.get(key) != value
    }
    container_expected = lock["container"]
    container_mismatches = {}
    provider_transport = None
    provider_mismatches = {}
    if getattr(adapter, "raw_provider", getattr(adapter, "provider", None)) == "logits":
        provider_observed = observe_logits_transport()
        provider_expected = lock["provider_transports"]["logits"]
        provider_mismatches = {
            key: {"expected": value, "observed": provider_observed.get(key)}
            for key, value in provider_expected.items()
            if provider_observed.get(key) != value
        }
        provider_transport = {
            "name": "logits",
            "expected": provider_expected,
            "observed": provider_observed,
            "mismatches": provider_mismatches,
        }
    dockerfile = PACKAGE_DIR / "docker" / "Dockerfile"
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
        "status": (
            "pass"
            if not mismatches and not container_mismatches and not provider_mismatches
            else "fail"
        ),
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
        "provider_transport": provider_transport,
    }
    if mismatches or container_mismatches or provider_mismatches:
        raise RuntimeLockMismatch(
            f"{adapter.name} runtime closure does not match {lock['lock_id']}: "
            + ", ".join(
                sorted([*mismatches, *container_mismatches, *provider_mismatches])
            )
        )
    return evidence
