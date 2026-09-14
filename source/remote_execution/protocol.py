"""Small, strict, secret-free wire contracts shared by controller and node."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

VERSION = 1
CHUNK_SIZE = 4 * 1024 * 1024
TERMINAL = {"completed", "failed", "needs_attention"}


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exact(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f"Expected fields {sorted(required)}; optional {sorted(optional)}")
    return value


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise ValueError("Invalid identifier")
    return value


def sha256(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected SHA-256")
    return value


def positive(value, maximum=100000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"Expected integer in 1..{maximum}")
    return value


def relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("Invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")):
        raise ValueError("Path must be normalized and relative")
    return value


def safe_path(root: Path, name: str) -> Path:
    """Never follow artifact or archive links, including intermediate components."""
    relative(name)
    root = root.resolve(strict=True)
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not transportable")
    return current


def private_json(path: Path, value, *, replace=True):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".json-", dir=path.parent)
    tmp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)  # Atomic create-only, never overwrite old evidence.
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path):
    return json.loads(path.read_bytes())


def endpoint(value: str, *, loopback=False) -> str:
    if not isinstance(value, str):
        raise ValueError("Endpoint must be a URL")
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Endpoint must be an HTTP(S) URL without credentials/query/fragment")
    if loopback and url.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Control endpoint must be loopback; use an SSH tunnel")
    return value.rstrip("/")


def secret_file(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Token must be an owner-only regular file")
    value = path.read_text().strip()
    if len(value) < 32 or any(c.isspace() for c in value):
        raise ValueError("Token must contain at least 32 non-whitespace characters")
    return value


def validate_job(raw):
    exact(raw, {"schema_version", "job_id", "release_id", "kind", "parameters"})
    if type(raw["schema_version"]) is not int or raw["schema_version"] != VERSION:
        raise ValueError("Unsupported job schema")
    identifier(raw["job_id"])
    sha256(raw["release_id"])
    p = raw["parameters"]
    if raw["kind"] == "probe":
        exact(p, set(), {"delay_seconds"})
        delay = p.get("delay_seconds", 0)
        if type(delay) not in {int, float} or not 0 <= delay <= 10:
            raise ValueError("Probe delay must be 0..10 seconds")
    elif raw["kind"] == "agent_cell":
        exact(p, {"harness", "domain", "dataset", "indices", "benchmark_profile",
                  "operational_config", "resolved_config_sha256", "services"})
        if p["harness"] not in {"openclaw", "hermes", "nanobot", "generic", "zeroclaw", "minimum"}:
            raise ValueError("Unknown harness")
        identifier(p["domain"])
        identifier(p["dataset"])
        for key in ("benchmark_profile", "operational_config"):
            relative(p[key])
        sha256(p["resolved_config_sha256"])
        indices = p["indices"]
        if not isinstance(indices, list) or not indices or len(indices) > 100000:
            raise ValueError("Nonempty fixed indices required")
        for index in indices:
            positive(index)
        if indices != sorted(set(indices)):
            raise ValueError("Indices must be sorted and unique")
        if not isinstance(p["services"], list) or len(p["services"]) != len(set(p["services"])):
            raise ValueError("Services must be a unique list")
        for name in p["services"]:
            identifier(name)
    else:
        raise ValueError("Unsupported job kind")
    return raw


def validate_node(raw):
    exact(raw, {"schema_version", "node_id", "state_dir", "python", "token_file"},
          {"max_jobs", "max_formalizer_workers", "allow_probe", "bindings", "services", "max_bundle_bytes"})
    if raw["schema_version"] != VERSION or type(raw["schema_version"]) is not int:
        raise ValueError("Unsupported node schema")
    identifier(raw["node_id"])
    for key in ("state_dir", "python", "token_file"):
        if not isinstance(raw[key], str) or not Path(raw[key]).is_absolute():
            raise ValueError(f"{key} must be absolute")
    positive(raw.get("max_jobs", 1), 64)
    positive(raw.get("max_formalizer_workers", 4), 256)
    positive(raw.get("max_bundle_bytes", 2 * 1024**3), 32 * 1024**3)
    if type(raw.get("allow_probe", False)) is not bool:
        raise ValueError("allow_probe must be boolean")
    bindings = raw.get("bindings", {})
    exact(bindings, set(), {"harness_runtimes", "zeroclaw_deadlines", "val", "secrets_env_file"})
    for value in bindings.values():
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("Bindings must be absolute node-local paths")
    services = raw.get("services", {})
    if not isinstance(services, dict):
        raise ValueError("services must be an object")
    for name, service in services.items():
        identifier(name)
        exact(service, {"health_url", "expected", "systemd_unit"}, {"provenance", "api_key_env"})
        if "api_key_env" in service and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", service["api_key_env"]):
            raise ValueError("Service API key must be an environment-variable reference")
        endpoint(service["health_url"])
        if not isinstance(service["expected"], dict) or not isinstance(service.get("provenance", {}), dict):
            raise ValueError("Service expected/provenance must be objects")
        if not isinstance(service["systemd_unit"], str) or not re.fullmatch(r"[A-Za-z0-9_.@-]+\.service", service["systemd_unit"]):
            raise ValueError("A supervised service unit is required")
    return raw
