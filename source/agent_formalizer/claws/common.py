"""Shared runtime, authentication, subprocess, and transcript helpers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from agent_formalizer.claws.base import (
    AttemptClock,
    BaseClawAdapter,
    decode_output,
    run_process_with_attempt_clock,
)
from agent_formalizer.configuration.config import (
    MODEL_GATEWAY_HOST,
    MODEL_GATEWAY_PORT,
    PROVIDER_API_BASE,
    PROVIDER_API_KEY_ENV,
    api_key_env_for_model,
    provider_for_model,
)
from agent_formalizer.result_types import AgentResult

INTERNAL_API_KEY_ENV = "PDDL_BENCHMARK_API_KEY"
GOOGLE_VERTEX_PROVIDER = "google-vertex"


@dataclass(frozen=True)
class ProviderSpec:
    """Normalized provider details shared by the Python harnesses."""

    name: str
    key_env: str
    api_base: str
    gateway_auth_mode: str = "bearer"


_PROVIDER_ALIASES = {
    "qwen": "dashscope",
    "google": "gemini",
}


def normalized_provider(provider: str) -> str:
    return _PROVIDER_ALIASES.get(provider, provider)


def split_model_id(model: str) -> tuple[str, str]:
    """Split ``provider/model`` once, preserving nested gateway model ids."""
    provider, sep, runtime_model = model.partition("/")
    if not sep or not provider or not runtime_model:
        raise ValueError(
            f"Model '{model}' must use provider/model form, for example "
            "openai/gpt-5.4-mini."
        )
    return provider, runtime_model


def provider_spec(model: str) -> ProviderSpec:
    raw_provider, _ = split_model_id(model)
    provider = normalized_provider(raw_provider)
    key_env = PROVIDER_API_KEY_ENV.get(raw_provider) or PROVIDER_API_KEY_ENV.get(provider)
    api_base = PROVIDER_API_BASE.get(raw_provider) or PROVIDER_API_BASE.get(provider)
    if not key_env or not api_base:
        supported = ", ".join(sorted(PROVIDER_API_BASE))
        raise ValueError(
            f"Provider '{raw_provider}' is not configured for isolated harness runs. "
            f"Supported provider prefixes: {supported}."
        )
    if raw_provider in {"google", "gemini", "google-vertex"}:
        auth_mode = "x_goog_api_key"
    elif raw_provider == "anthropic":
        auth_mode = "x_api_key"
    else:
        auth_mode = "bearer"
    return ProviderSpec(provider, key_env, api_base, auth_mode)


def google_vertex_settings(provider_options: dict | None = None) -> tuple[str, str, str]:
    """Return the Vertex project, location, and regional API origin."""
    options = dict((provider_options or {}).get("google_vertex", {}))
    project = options.get("project")
    if not project:
        raise RuntimeError(
            "google-vertex requires a project in the selected credential profile "
            "(or the legacy benchmark/--vertex-project compatibility path)."
        )
    location = options.get("location") or "global"
    origin = options.get("origin")
    if not origin:
        origin = (
            "https://aiplatform.googleapis.com"
            if location == "global"
            else f"https://{location}-aiplatform.googleapis.com"
        )
    return project, location, origin


def google_vertex_openai_base(provider_options: dict | None = None) -> str:
    """Build the project-qualified Vertex Chat Completions base URL."""
    project, location, origin = google_vertex_settings(provider_options)
    return (
        f"{origin}/v1/projects/{project}/locations/{location}"
        "/endpoints/openapi"
    )


def safe_component(value: str) -> str:
    """Return a conservative, collision-resistant filesystem component.

    Runtime ids occur near the end of long benchmark instance ids. Truncating
    only the readable prefix could therefore map concurrent executions to the
    same host state directory. Preserve a readable prefix and always retain a
    digest of the complete value.
    """
    cleaned = "".join(c if c.isalnum() or c in "._-" else "-" for c in value)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    prefix = (cleaned or "run")[:143].rstrip(".-") or "run"
    return f"{prefix}-{digest}"


class EnvConfiguredAdapter(BaseClawAdapter):
    """Base for harnesses configured only from repo state and environment keys."""

    def __init__(
        self,
        model: str,
        timeout: int,
        max_action_steps: int = 200,
        *,
        model_api_keys: dict[str, str] | None = None,
        api_key: str | None = None,
        api_key_name: str | None = None,
        credential_metadata: dict | None = None,
        provider_options: dict | None = None,
        max_model_calls: int = 50,
        allow_network: bool = False,
        network_mode: str | None = None,
        skills_mode: str = "official",
        benchmark_profile=None,
        resolved_config=None,
    ):
        super().__init__(
            model,
            timeout,
            max_action_steps,
            max_model_calls=max_model_calls,
            allow_network=allow_network,
            network_mode=network_mode,
            skills_mode=skills_mode,
            benchmark_profile=benchmark_profile,
            resolved_config=resolved_config,
        )
        self.model_api_keys = dict(model_api_keys or {})
        self._api_key = api_key
        self._api_key_name = api_key_name
        self.credential_metadata = dict(credential_metadata or {})
        self.provider_options = dict(provider_options or {})

    @property
    def raw_provider(self) -> str:
        return provider_for_model(self.model)

    @property
    def provider(self) -> str:
        return provider_spec(self.model).name

    @property
    def runtime_model(self) -> str:
        return split_model_id(self.model)[1]

    @property
    def is_google_vertex(self) -> bool:
        return self.raw_provider == GOOGLE_VERTEX_PROVIDER

    @property
    def openai_compatible_model(self) -> str:
        """Model id expected by OpenAI-compatible provider transports."""
        if self.is_google_vertex:
            return f"google/{self.runtime_model}"
        return self.runtime_model

    @property
    def direct_api_base(self) -> str:
        if self.is_google_vertex:
            return google_vertex_openai_base(self.provider_options)
        return provider_spec(self.model).api_base

    @property
    def api_base(self) -> str:
        """Provider base routed through the per-task model gateway."""
        from urllib.parse import urlsplit

        direct = urlsplit(self.direct_api_base)
        suffix = direct.path.rstrip("/")
        if self.raw_provider == "logits" and not suffix:
            suffix = "/v1"
        return f"http://{MODEL_GATEWAY_HOST}:{MODEL_GATEWAY_PORT}{suffix}"

    def upstream_api_base(self) -> str:
        return self.direct_api_base

    def model_gateway(self) -> dict:
        value = super().model_gateway()
        spec = provider_spec(self.model)
        value["auth_mode"] = spec.gateway_auth_mode
        value["allowed_models"] = sorted(
            {
                self.model,
                self.runtime_model,
                self.openai_compatible_model,
            }
        )
        from urllib.parse import urlsplit

        path = urlsplit(self.direct_api_base).path.rstrip("/")
        if not path:
            path = "/v1/projects" if self.is_google_vertex else "/v1"
        value["allowed_path_prefixes"] = [path]
        if self.raw_provider == "logits":
            # The public Logits endpoint is a token-level sampling API.  A
            # provider-specific component in the same sidecar translates the
            # harness's OpenAI-compatible requests before egress.
            value.update(
                {
                    "transport": "logits-rest-openai-v1",
                    "upstream_model": self.runtime_model,
                    "allowed_path_prefixes": ["/v1"],
                }
            )
        return value

    def model_gateway_secret(self) -> str | None:
        return self.resolved_api_key()

    def api_key_env(self) -> str | None:
        return self._api_key_name or api_key_env_for_model(self.model, self.model_api_keys)

    def resolved_api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        name = self.api_key_env()
        return os.environ.get(name) if name else None

    def model_auth(self) -> dict:
        value = {
            "model": self.model,
            "provider": self.raw_provider,
            "normalized_provider": self.provider,
            "runtime_model": self.runtime_model,
            "api_base": self.api_base,
            "upstream_api_base": self.direct_api_base,
            "api_key_env": self.api_key_env(),
            "api_key_present": bool(self.resolved_api_key()),
        }
        if self.credential_metadata:
            value["credential"] = dict(self.credential_metadata)
        return value

    def validate_runtime(self) -> None:
        # Resolve the provider first so unsupported or malformed model ids fail
        # before Docker is started.
        provider_spec(self.model)
        if self.is_google_vertex:
            google_vertex_settings(self.provider_options)
        if not self.resolved_api_key():
            env_name = self.api_key_env()
            hint = (
                f"pass the key explicitly or set only {env_name} for the runner"
                if env_name
                else "pass --api-key-env NAME and define only that runner variable"
            )
            raise RuntimeError(f"No API key for {self.model}. {hint}.")

    def auth_env(self) -> dict[str, str]:
        """Placeholder auth aliases; real credentials remain gateway-only."""
        value = "benchmark-gateway-placeholder"
        spec = provider_spec(self.model)
        result = {
            INTERNAL_API_KEY_ENV: value,
            spec.key_env: value,
        }
        if self.provider == "gemini":
            result["GOOGLE_API_KEY"] = value
            result["GEMINI_API_KEY"] = value
        return result

    def docker_exec_env_args(self, extra: dict[str, str] | None = None) -> list[str]:
        env = self.auth_env()
        if self.resolved_config is not None:
            env.update(self.resolved_config.raw["resolved"]["environment"]["fixed"])
        env.update(extra or {})
        from agent_formalizer.timing.deadline_integration import policy
        if policy(self) == 'call-checkpoint-v1' and 'PYTHONPATH' in env:
            from agent_formalizer.timing.logical_time import RUNTIME_DIR
            env['PYTHONPATH'] = RUNTIME_DIR + os.pathsep + env['PYTHONPATH']
        args: list[str] = []
        for name, value in env.items():
            args.extend(["-e", f"{name}={value}"])
        return args

class PythonRuntimeMixin:
    """Bind-mount an isolated venv and its uv-managed base interpreter."""

    runtime_env: Path
    install_target: str

    @property
    def runtime_python(self) -> Path:
        return self.runtime_env / "bin" / "python"

    def validate_python_runtime(self) -> None:
        if not self.runtime_python.is_file():
            raise RuntimeError(
                f"{self.install_target} runtime not found at {self.runtime_python}. "
                "Run: bash source/agent_formalizer/runtime/install_harnesses.sh "
                f"{self.install_target}"
            )

    def python_runtime_mount_args(self) -> list[str]:
        self.validate_python_runtime()
        sources = self.python_runtime_mount_sources()
        resolved_python = self.runtime_python.resolve()
        if self.runtime_python.is_symlink():
            link_target = Path(os.readlink(self.runtime_python))
            if not link_target.is_absolute():
                link_target = self.runtime_python.parent / link_target
            target_home = link_target.parent.parent
        else:
            target_home = sources[0]
        mounts = ["-v", f"{sources[0]}:{self.runtime_env}:ro"]
        if len(sources) > 1:
            # uv's venv symlink normally points through an unversioned Python
            # home symlink. Docker resolves mount sources, so explicitly mount
            # the resolved source at the exact path embedded in the venv link.
            mounts.extend(["-v", f"{sources[1]}:{target_home}:ro"])
        return mounts

    def python_runtime_mount_sources(self) -> list[Path]:
        self.validate_python_runtime()
        resolved_python = self.runtime_python.resolve()
        sources = [self.runtime_env]
        try:
            resolved_python.relative_to(self.runtime_env)
        except ValueError:
            sources.append(resolved_python.parent.parent)
        return sources

    def state_isolation_spec(self, instance_id: str) -> dict:
        spec = super().state_isolation_spec(instance_id)
        spec["shared_readonly_bind_sources"] = [
            *spec.get("shared_readonly_bind_sources", []),
            *(str(path) for path in self.python_runtime_mount_sources()),
        ]
        return spec

    def python_runtime_info(self, distribution: str | None = None) -> dict:
        from agent_formalizer.results.provenance import run_text

        info = {
            "python_executable": str(self.runtime_python),
            "python_version": run_text([str(self.runtime_python), "--version"]),
            "runtime_env": str(self.runtime_env),
        }
        if distribution:
            code = (
                "import importlib.metadata as m; "
                f"print(m.version({distribution!r}))"
            )
            info["distribution"] = distribution
            info["distribution_version"] = run_text(
                [str(self.runtime_python), "-c", code]
            )
        return info


def run_captured_agent(
    cmd: list[str],
    *,
    timeout: float,
    stdout_path: Path | None,
    stderr_path: Path | None,
    final_text: str | None = None,
    container_name: str | None = None,
    attempt_clock: AttemptClock | None = None,
    env: dict[str, str] | None = None,
) -> AgentResult:
    """Run a non-interactive harness command and normalize its result."""
    started = time.monotonic()
    timed_out = False
    try:
        result = (
            run_process_with_attempt_clock(
                cmd,
                clock=attempt_clock,
                capture_output=True,
                text=True,
                env=env,
            )
            if attempt_clock is not None
            else subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = decode_output(exc.stdout)
        stderr = decode_output(exc.stderr)
        if container_name:
            subprocess.run(
                ["docker", "kill", container_name], capture_output=True, timeout=30
            )

    if stdout_path:
        stdout_path.write_text(stdout or "", errors="replace")
    if stderr_path:
        stderr_path.write_text(stderr or "", errors="replace")

    if timed_out:
        finish_reason = "timeout"
    elif exit_code != 0:
        finish_reason = "error"
    elif not (stdout or "").strip():
        finish_reason = "empty"
    else:
        finish_reason = "stop"

    return AgentResult(
        success=finish_reason == "stop",
        timeout=timed_out,
        exit_code=exit_code,
        finish_reason=finish_reason,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        duration_seconds=round(time.monotonic() - started, 1),
        usage={},
        final_text=final_text if final_text is not None else (stdout or "").strip() or None,
    )


def jsonl_steps(paths: Iterable[Path]) -> Iterator[dict]:
    """Normalize OpenAI-style JSONL messages into diagnostic session records."""
    step = 0
    for path in paths:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(message, dict) or message.get("_type") == "metadata":
                continue
            role = message.get("role")
            content = _content_text(message.get("content"))
            if role in {"user", "assistant", "system"}:
                yield {
                    "step": step,
                    "event": "message",
                    "role": role,
                    "content": content,
                    "session_file": path.name,
                }
                step += 1
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or call
                args = function.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        pass
                yield {
                    "step": step,
                    "event": "tool_call",
                    "tool": function.get("name"),
                    "arguments": args,
                    "tool_call_id": call.get("id"),
                    "session_file": path.name,
                }
                step += 1
            if role == "tool":
                yield {
                    "step": step,
                    "event": "tool_result",
                    "tool": message.get("name"),
                    "tool_call_id": message.get("tool_call_id"),
                    "output": content,
                    "ok": not content.lower().startswith(("error", "failed")),
                    "session_file": path.name,
                }
                step += 1


def tool_records(steps: Iterable[dict]) -> Iterator[dict]:
    index = 0
    for record in steps:
        event = record.get("event")
        if event not in {"tool_call", "tool_result"}:
            continue
        yield {
            "index": index,
            "kind": "call" if event == "tool_call" else "result",
            "name": record.get("tool"),
            "arguments": record.get("arguments"),
            "result": record.get("output"),
            "ok": record.get("ok"),
            "session_file": record.get("session_file"),
            "step": record.get("step"),
        }
        index += 1


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return "" if content is None else str(content)
