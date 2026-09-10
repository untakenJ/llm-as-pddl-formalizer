"""Strict, secret-free operational configuration for benchmark runs.

Operational settings describe how an already-defined study is realized: the
credential profile, worker scheduling, optional evidence, infrastructure
diagnostics, and output locations.  They are intentionally excluded from the
resolved experimental configuration identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_formalizer.configuration.benchmark_profile import canonical_sha256
from agent_formalizer.docker.network_resources import DEFAULT_OPTIONS, validate_options
from . import CONFIGS_DIR, PACKAGE_DIR


ROOT_DIR = PACKAGE_DIR.parent.parent
DEFAULT_OPERATIONAL_CONFIG_PATH = (
    CONFIGS_DIR / "operational_configs" / "standard.json"
)

_ROOT_KEYS = {
    "schema_version",
    "config_id",
    "credential",
    "scheduling",
    "evidence_collection",
    "infra_diagnostics",
    "results",
    "network_resources",
}
_HANDLER_ID = re.compile(r"^builtin:[a-z][a-z0-9_-]*@[1-9][0-9]*$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]*$")


def _default_raw() -> dict[str, Any]:
    """Compatibility defaults matching the pre-operational-config CLI."""
    return {
        "schema_version": 1,
        "config_id": "legacy-cli-defaults-v1",
        "credential": {
            "registry_file": "source/agent_formalizer/configs/credential_profiles.json",
            "secrets_env_file": "_private/.env",
        },
        "scheduling": {
            "formalizer_workers": 1,
            "solver_workers": 1,
            "val_workers": 1,
            "resume": False,
        },
        "evidence_collection": {"agent_trace": True},
        "infra_diagnostics": {
            "enabled": False,
            "capture": {
                "transport_errors": True,
                "gateway_internal_errors": True,
            },
            "provider_diagnostics": {
                "mode": "off",
                "capture_success_metadata": False,
                "handlers": {},
            },
            "storage": {
                "root": ".cache/infra-diagnostics",
                "retention_days": 7,
                "max_event_bytes": 65536,
                "max_run_bytes": 268435456,
            },
        },
        "results": {"root": "output"},
        "network_resources": dict(DEFAULT_OPTIONS),
    }


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _strict_keys(
    value: dict[str, Any],
    *,
    path: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> None:
    unknown = set(value) - required - optional
    missing = required - set(value)
    if unknown:
        raise ValueError(f"{path} has unknown field(s): {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{path} is missing field(s): {', '.join(sorted(missing))}")


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _require_positive_int(value: Any, path: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()


def _validate(raw: dict[str, Any]) -> None:
    _strict_keys(raw, path="operational_config", required=_ROOT_KEYS)
    validate_options(raw["network_resources"])
    if raw["schema_version"] != 1:
        raise ValueError("operational_config.schema_version must be 1")
    config_id = _require_string(raw["config_id"], "operational_config.config_id")
    if not _NAME.fullmatch(config_id):
        raise ValueError("operational_config.config_id contains unsupported characters")

    credential = _require_object(raw["credential"], "credential")
    _strict_keys(
        credential,
        path="credential",
        required={"registry_file", "secrets_env_file"},
        optional={"profile"},
    )
    _require_string(credential["registry_file"], "credential.registry_file")
    _require_string(credential["secrets_env_file"], "credential.secrets_env_file")
    if "profile" in credential:
        _require_string(credential["profile"], "credential.profile")

    scheduling = _require_object(raw["scheduling"], "scheduling")
    _strict_keys(
        scheduling,
        path="scheduling",
        required={
            "formalizer_workers",
            "solver_workers",
            "val_workers",
            "resume",
        },
    )
    for field in ("formalizer_workers", "solver_workers", "val_workers"):
        _require_positive_int(scheduling[field], f"scheduling.{field}")
    _require_bool(scheduling["resume"], "scheduling.resume")

    evidence = _require_object(raw["evidence_collection"], "evidence_collection")
    _strict_keys(evidence, path="evidence_collection", required={"agent_trace"})
    _require_bool(evidence["agent_trace"], "evidence_collection.agent_trace")

    diagnostics = _require_object(raw["infra_diagnostics"], "infra_diagnostics")
    _strict_keys(
        diagnostics,
        path="infra_diagnostics",
        required={"enabled", "capture", "provider_diagnostics", "storage"},
    )
    _require_bool(diagnostics["enabled"], "infra_diagnostics.enabled")

    capture = _require_object(diagnostics["capture"], "infra_diagnostics.capture")
    _strict_keys(
        capture,
        path="infra_diagnostics.capture",
        required={"transport_errors", "gateway_internal_errors"},
    )
    _require_bool(capture["transport_errors"], "infra_diagnostics.capture.transport_errors")
    _require_bool(
        capture["gateway_internal_errors"],
        "infra_diagnostics.capture.gateway_internal_errors",
    )

    provider = _require_object(
        diagnostics["provider_diagnostics"],
        "infra_diagnostics.provider_diagnostics",
    )
    _strict_keys(
        provider,
        path="infra_diagnostics.provider_diagnostics",
        required={"mode", "capture_success_metadata"},
        optional={"handlers"},
    )
    if provider["mode"] not in {"off", "metadata", "structured", "raw"}:
        raise ValueError(
            "infra_diagnostics.provider_diagnostics.mode must be one of "
            "off, metadata, structured, raw"
        )
    _require_bool(
        provider["capture_success_metadata"],
        "infra_diagnostics.provider_diagnostics.capture_success_metadata",
    )
    handlers = provider.setdefault("handlers", {})
    _require_object(handlers, "infra_diagnostics.provider_diagnostics.handlers")
    from agent_formalizer.infra_diagnostics.registry import (
        HANDLER_FACTORIES,
        canonical_provider_id,
    )

    normalized_handlers: dict[str, str] = {}
    for provider_name, handler_id in handlers.items():
        if not isinstance(provider_name, str) or not _PROVIDER.fullmatch(provider_name):
            raise ValueError(f"invalid provider diagnostic key: {provider_name!r}")
        if not isinstance(handler_id, str) or not _HANDLER_ID.fullmatch(handler_id):
            raise ValueError(f"invalid provider diagnostic handler id: {handler_id!r}")
        if handler_id not in HANDLER_FACTORIES:
            raise ValueError(f"unknown provider diagnostic handler: {handler_id}")
        canonical_name = canonical_provider_id(provider_name)
        existing = normalized_handlers.get(canonical_name)
        if existing is not None and existing != handler_id:
            raise ValueError(
                "conflicting provider diagnostic handlers for canonical provider "
                f"{canonical_name}"
            )
        normalized_handlers[canonical_name] = handler_id
    provider["handlers"] = normalized_handlers

    storage = _require_object(diagnostics["storage"], "infra_diagnostics.storage")
    _strict_keys(
        storage,
        path="infra_diagnostics.storage",
        required={"root", "retention_days", "max_event_bytes", "max_run_bytes"},
    )
    _require_string(storage["root"], "infra_diagnostics.storage.root")
    _require_positive_int(storage["retention_days"], "infra_diagnostics.storage.retention_days")
    event_limit = _require_positive_int(
        storage["max_event_bytes"],
        "infra_diagnostics.storage.max_event_bytes",
        minimum=1024,
    )
    run_limit = _require_positive_int(
        storage["max_run_bytes"],
        "infra_diagnostics.storage.max_run_bytes",
        minimum=1024,
    )
    if run_limit < event_limit:
        raise ValueError("infra diagnostics max_run_bytes must be >= max_event_bytes")

    results = _require_object(raw["results"], "results")
    _strict_keys(results, path="results", required={"root"})
    _require_string(results["root"], "results.root")
    if _resolve_path(results["root"]) == _resolve_path(storage["root"]):
        raise ValueError("results.root and infra diagnostics storage.root must differ")


@dataclass(frozen=True)
class ResolvedOperationalConfig:
    raw: dict[str, Any]
    sha256: str
    source_path: Path | None
    source_sha256: str | None

    @property
    def config_id(self) -> str:
        return self.raw["config_id"]

    @property
    def credential_registry_path(self) -> Path:
        return _resolve_path(self.raw["credential"]["registry_file"])

    @property
    def credential_profile(self) -> str | None:
        return self.raw["credential"].get("profile")

    @property
    def secrets_env_path(self) -> Path:
        return _resolve_path(self.raw["credential"]["secrets_env_file"])

    @property
    def results_root(self) -> Path:
        return _resolve_path(self.raw["results"]["root"])

    @property
    def diagnostics_root(self) -> Path:
        return _resolve_path(self.raw["infra_diagnostics"]["storage"]["root"])

    @property
    def diagnostics_enabled(self) -> bool:
        return bool(self.raw["infra_diagnostics"]["enabled"])

    def metadata(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "config_id": self.config_id,
            "operational_config_sha256": self.sha256,
            "source_path": str(self.source_path) if self.source_path else None,
            "source_sha256": self.source_sha256,
            "experiment_identity": "excluded",
            "resolved": deepcopy(self.raw),
        }

    def execution_diagnostics_plan(
        self,
        *,
        provider: str,
        run_id: str,
        domain: str,
        data: str,
        problem: str,
        model_label: str,
        attempt_index: int,
        execution_try: int,
        runtime_id: str,
    ) -> "ExecutionDiagnosticsPlan | None":
        if not self.diagnostics_enabled:
            return None
        from agent_formalizer.infra_diagnostics.registry import (
            canonical_provider_id,
            resolve_handler_id,
        )

        diagnostics = self.raw["infra_diagnostics"]
        provider_config = diagnostics["provider_diagnostics"]
        canonical_provider = canonical_provider_id(provider)
        configured_handler = provider_config["handlers"].get(canonical_provider)
        handler_id = resolve_handler_id(canonical_provider, configured_handler)
        run_component = safe_operational_component(run_id)
        run_root = self.diagnostics_root / run_component
        execution_dir = (
            run_root
            / safe_operational_component(domain)
            / safe_operational_component(data)
            / safe_operational_component(model_label)
            / safe_operational_component(problem)
            / f"attempt-{attempt_index:03d}"
            / f"execution-{execution_try:03d}"
            / f"runtime-{safe_operational_component(runtime_id)}"
        )
        return ExecutionDiagnosticsPlan(
            run_root=run_root,
            execution_dir=execution_dir,
            runtime_config={
                "schema_version": 1,
                "enabled": True,
                "provider": canonical_provider,
                "mode": provider_config["mode"],
                "capture_success_metadata": provider_config[
                    "capture_success_metadata"
                ],
                "capture_transport_errors": diagnostics["capture"][
                    "transport_errors"
                ],
                "capture_gateway_internal_errors": diagnostics["capture"][
                    "gateway_internal_errors"
                ],
                "handler": handler_id,
                "max_event_bytes": diagnostics["storage"]["max_event_bytes"],
                "max_run_bytes": diagnostics["storage"]["max_run_bytes"],
                "operational_config_sha256": self.sha256,
                "correlation": {
                    "run_id": run_id,
                    "domain": domain,
                    "data": data,
                    "problem": problem,
                    "model_label": model_label,
                    "attempt_index": attempt_index,
                    "execution_try": execution_try,
                    "runtime_id": runtime_id,
                },
            },
        )


@dataclass(frozen=True)
class ExecutionDiagnosticsPlan:
    run_root: Path
    execution_dir: Path
    runtime_config: dict[str, Any]


def safe_operational_component(value: str, *, limit: int = 96) -> str:
    """Return a collision-resistant, traversal-safe operational path segment."""
    original = str(value)
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", original).strip("._-")
    cleaned = cleaned or "unnamed"
    if cleaned == original and len(cleaned) <= limit:
        return cleaned
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
    return f"{cleaned[: limit - 14]}__{digest}"


def load_operational_config(
    path: str | Path | None = None,
    *,
    credential_profiles_file: str | Path | None = None,
    credential_profile: str | None = None,
    secrets_env_file: str | Path | None = None,
    formalizer_workers: int | None = None,
    solver_workers: int | None = None,
    val_workers: int | None = None,
    resume: bool | None = None,
    agent_trace: bool | None = None,
    results_root: str | Path | None = None,
) -> ResolvedOperationalConfig:
    """Load a full v1 file and apply explicit, recorded CLI overrides."""
    source_path: Path | None = None
    source_sha256: str | None = None
    if path is None:
        raw = _default_raw()
    else:
        source_path = Path(path).expanduser().resolve()
        try:
            source_bytes = source_path.read_bytes()
            raw = json.loads(source_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load operational config {source_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("operational config root must be an object")
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    raw = deepcopy(raw)
    # Old operational files remain readable; new defaults are explicit in the
    # resolved operational provenance, never in the experimental profile.
    raw.setdefault("network_resources", dict(DEFAULT_OPTIONS))
    credential = raw.setdefault("credential", {})
    scheduling = raw.setdefault("scheduling", {})
    evidence = raw.setdefault("evidence_collection", {})
    results = raw.setdefault("results", {})

    if credential_profiles_file is not None:
        credential["registry_file"] = str(credential_profiles_file)
    if credential_profile is not None:
        credential["profile"] = credential_profile
    if secrets_env_file is not None:
        credential["secrets_env_file"] = str(secrets_env_file)
    if formalizer_workers is not None:
        scheduling["formalizer_workers"] = formalizer_workers
    if solver_workers is not None:
        scheduling["solver_workers"] = solver_workers
    if val_workers is not None:
        scheduling["val_workers"] = val_workers
    if resume is not None:
        scheduling["resume"] = resume
    if agent_trace is not None:
        evidence["agent_trace"] = agent_trace
    if results_root is not None:
        results["root"] = str(results_root)

    _validate(raw)
    return ResolvedOperationalConfig(
        raw=raw,
        sha256=canonical_sha256(raw),
        source_path=source_path,
        source_sha256=source_sha256,
    )
