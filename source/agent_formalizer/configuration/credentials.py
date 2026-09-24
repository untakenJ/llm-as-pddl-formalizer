"""Named, runner-owned credential profiles for model gateway access.

The registry is deliberately secret-free: it contains only environment-variable
references and non-secret provider settings.  Values are resolved one at a time
from the runner-only dotenv file (or the process environment) and the API key is
never included in metadata, hashes, or adapter/container configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_formalizer.configuration.config import provider_for_model
from agent_formalizer.util import read_named_secret, read_named_setting
from . import CONFIGS_DIR


DEFAULT_CREDENTIAL_PROFILES_PATH = CONFIGS_DIR / "credential_profiles.json"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _exact_keys(
    value: dict[str, Any],
    *,
    required: set[str] = frozenset(),
    optional: set[str] = frozenset(),
    path: str,
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ValueError(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{path} has unknown fields: {', '.join(unknown)}")


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _env_name(value: Any, path: str) -> str:
    name = _nonempty_string(value, path)
    if not _ENV_NAME.fullmatch(name):
        raise ValueError(f"{path} must be an environment-variable name")
    return name


def _model_matches(pattern: str, model: str) -> bool:
    if pattern.endswith("/*"):
        return model.startswith(pattern[:-1])
    return pattern == model


def _validate_source_tree(value: Any, path: str) -> None:
    row = _object(value, path)
    if set(row) in ({"env"}, {"value"}):
        if "env" in row:
            _env_name(row["env"], f"{path}.env")
        else:
            _nonempty_string(row["value"], f"{path}.value")
        return
    if not row:
        raise ValueError(f"{path} must not be empty")
    for key, child in row.items():
        _nonempty_string(key, f"{path} key")
        _validate_source_tree(child, f"{path}.{key}")


def _resolve_source_tree(value: dict[str, Any], env_file: str | Path | None) -> Any:
    if set(value) == {"env"}:
        return read_named_setting(value["env"], env_file)
    if set(value) == {"value"}:
        return value["value"]
    return {key: _resolve_source_tree(child, env_file) for key, child in value.items()}


@dataclass(frozen=True)
class ResolvedCredential:
    """One selected profile, with its secret deliberately hidden from repr."""

    profile_name: str
    provider: str
    api_key_env: str
    api_key: str = field(repr=False)
    provider_options: dict[str, Any] = field(default_factory=dict)
    registry_sha256: str = ""
    source_descriptor: dict[str, Any] = field(default_factory=dict)

    def metadata(self) -> dict[str, Any]:
        """Return operational provenance containing references, never values."""
        return {
            "profile": self.profile_name,
            "provider": self.provider,
            "api_key_env": self.api_key_env,
            "api_key_present": bool(self.api_key),
            "provider_option_sources": deepcopy(
                self.source_descriptor.get("provider_options", {})
            ),
            "registry_sha256": self.registry_sha256,
            "experiment_identity": "excluded",
        }


@dataclass(frozen=True)
class CredentialRegistry:
    """Validated secret-free profile registry."""

    path: Path
    raw: dict[str, Any]

    @property
    def sha256(self) -> str:
        canonical = json.dumps(
            self.raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def default_profile_name(self, model: str) -> str:
        defaults = self.raw["defaults"]
        name = defaults["models"].get(model)
        if name is None:
            name = defaults["providers"].get(provider_for_model(model))
        if name is None:
            raise ValueError(
                f"No default credential profile for model {model!r}; "
                "pass --credential-profile NAME or add a model/provider default"
            )
        return name

    def profile(self, model: str, name: str | None = None) -> tuple[str, dict[str, Any]]:
        selected = name or self.default_profile_name(model)
        try:
            row = self.raw["profiles"][selected]
        except KeyError as exc:
            raise ValueError(f"Unknown credential profile {selected!r}") from exc
        provider = provider_for_model(model)
        if row["provider"] != provider:
            raise ValueError(
                f"Credential profile {selected!r} belongs to provider "
                f"{row['provider']!r}, not model {model!r}"
            )
        patterns = row.get("models", [])
        if patterns and not any(_model_matches(pattern, model) for pattern in patterns):
            raise ValueError(
                f"Credential profile {selected!r} is not in the pool for model {model!r}"
            )
        return selected, deepcopy(row)

    def resolve(
        self,
        model: str,
        *,
        name: str | None = None,
        env_file: str | Path | None = None,
        api_key_env_override: str | None = None,
    ) -> ResolvedCredential:
        selected, row = self.profile(model, name)
        key_name = (
            _env_name(api_key_env_override, "api_key_env_override")
            if api_key_env_override
            else row["api_key_env"]
        )
        api_key = read_named_secret(key_name, env_file)
        option_sources = row.get("provider_options", {})
        provider_options = (
            _resolve_source_tree(option_sources, env_file) if option_sources else {}
        )
        descriptor = deepcopy(row)
        descriptor["api_key_env"] = key_name
        return ResolvedCredential(
            profile_name=selected,
            provider=row["provider"],
            api_key_env=key_name,
            api_key=api_key,
            provider_options=provider_options,
            registry_sha256=self.sha256,
            source_descriptor=descriptor,
        )


def _validate_registry(raw: dict[str, Any], path: Path) -> None:
    _exact_keys(
        raw,
        required={"schema_version", "defaults", "profiles"},
        path=str(path),
    )
    if raw["schema_version"] != 1:
        raise ValueError(
            f"Unsupported credential profile schema: {raw['schema_version']}"
        )
    defaults = _object(raw["defaults"], "defaults")
    _exact_keys(defaults, required={"models", "providers"}, path="defaults")
    models = _object(defaults["models"], "defaults.models")
    providers = _object(defaults["providers"], "defaults.providers")
    profiles = _object(raw["profiles"], "profiles")
    if not profiles:
        raise ValueError("profiles must not be empty")

    for name, value in profiles.items():
        _nonempty_string(name, "profile name")
        row = _object(value, f"profiles.{name}")
        _exact_keys(
            row,
            required={"provider", "api_key_env"},
            optional={"models", "provider_options"},
            path=f"profiles.{name}",
        )
        provider = _nonempty_string(row["provider"], f"profiles.{name}.provider")
        _env_name(row["api_key_env"], f"profiles.{name}.api_key_env")
        patterns = row.get("models", [])
        if not isinstance(patterns, list) or not all(
            isinstance(pattern, str) and "/" in pattern for pattern in patterns
        ):
            raise ValueError(f"profiles.{name}.models must be model patterns")
        if any(pattern.split("/", 1)[0] != provider for pattern in patterns):
            raise ValueError(
                f"profiles.{name}.models must use provider prefix {provider!r}"
            )
        if provider in {"google-vertex", "self-hosted"} and "provider_options" not in row:
            raise ValueError(
                f"profiles.{name} must bind its provider route in provider_options"
            )
        if "provider_options" in row:
            options = _object(
                row["provider_options"], f"profiles.{name}.provider_options"
            )
            if provider not in {"google-vertex", "self-hosted"}:
                raise ValueError(
                    f"profiles.{name}.provider_options are not supported for "
                    f"provider {provider!r}"
                )
            if provider == "self-hosted":
                _exact_keys(options, required={"self_hosted"}, path=f"profiles.{name}.provider_options")
                route = _object(options["self_hosted"], f"profiles.{name}.provider_options.self_hosted")
                _exact_keys(route, required={"base_url"}, path=f"profiles.{name}.provider_options.self_hosted")
            else:
                _exact_keys(
                    options,
                    required={"google_vertex"},
                    path=f"profiles.{name}.provider_options",
                )
                vertex = _object(
                    options["google_vertex"],
                    f"profiles.{name}.provider_options.google_vertex",
                )
                _exact_keys(
                    vertex,
                    required={"project"},
                    optional={"location", "origin"},
                    path=f"profiles.{name}.provider_options.google_vertex",
                )
            _validate_source_tree(options, f"profiles.{name}.provider_options")

    for model, name in models.items():
        _nonempty_string(model, "defaults.models key")
        selected = _nonempty_string(name, f"defaults.models.{model}")
        if selected not in profiles:
            raise ValueError(f"defaults.models.{model} names unknown profile {selected!r}")
        row = profiles[selected]
        if row["provider"] != provider_for_model(model):
            raise ValueError(f"defaults.models.{model} selects a different provider")
        patterns = row.get("models", [])
        if patterns and not any(_model_matches(pattern, model) for pattern in patterns):
            raise ValueError(f"defaults.models.{model} selects an incompatible profile")

    for provider, name in providers.items():
        _nonempty_string(provider, "defaults.providers key")
        selected = _nonempty_string(name, f"defaults.providers.{provider}")
        if selected not in profiles:
            raise ValueError(
                f"defaults.providers.{provider} names unknown profile {selected!r}"
            )
        if profiles[selected]["provider"] != provider:
            raise ValueError(
                f"defaults.providers.{provider} selects a different provider"
            )


def load_credential_registry(
    path: str | Path | None = None,
) -> CredentialRegistry:
    registry_path = (
        Path(path).expanduser().resolve()
        if path
        else DEFAULT_CREDENTIAL_PROFILES_PATH.resolve()
    )
    try:
        raw = json.loads(registry_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load credential profiles {registry_path}: {exc}") from exc
    raw = _object(raw, str(registry_path))
    _validate_registry(raw, registry_path)
    return CredentialRegistry(registry_path, raw)
