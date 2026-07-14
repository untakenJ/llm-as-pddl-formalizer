"""Shared runtime, authentication, subprocess, and transcript helpers."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from agent_formalizer.claws.base import BaseClawAdapter, decode_output
from agent_formalizer.config import (
    PROVIDER_API_BASE,
    PROVIDER_API_BASE_ENV,
    PROVIDER_API_KEY_ENV,
    api_key_env_for_model,
    provider_for_model,
)
from agent_formalizer.result_types import AgentResult

SUBPROCESS_TIMEOUT_BUFFER = 60
INTERNAL_API_KEY_ENV = "PDDL_BENCHMARK_API_KEY"
GOOGLE_VERTEX_PROVIDER = "google-vertex"
VERTEX_PROXY_PORT = 8765
VERTEX_PROXY_CONTAINER_PATH = "/opt/pddl-benchmark/vertex_openai_proxy.py"
VERTEX_PROXY_SCRIPT = Path(__file__).resolve().parent.parent / "vertex_openai_proxy.py"


@dataclass(frozen=True)
class ProviderSpec:
    """Normalized provider details shared by the Python harnesses."""

    name: str
    key_env: str
    api_base: str
    api_base_env: str | None = None


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
    base_env = PROVIDER_API_BASE_ENV.get(raw_provider) or PROVIDER_API_BASE_ENV.get(provider)
    if not key_env or not api_base:
        supported = ", ".join(sorted(PROVIDER_API_BASE))
        raise ValueError(
            f"Provider '{raw_provider}' is not configured for isolated harness runs. "
            f"Supported provider prefixes: {supported}."
        )
    return ProviderSpec(provider, key_env, api_base, base_env)


def google_vertex_settings() -> tuple[str, str, str]:
    """Return the Vertex project, location, and regional API origin."""
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    )
    if not project:
        raise RuntimeError(
            "google-vertex requires GOOGLE_CLOUD_PROJECT in _private/.env."
        )
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    configured_origin = os.environ.get("GOOGLE_VERTEX_BASE_URL")
    if configured_origin:
        origin = configured_origin.rstrip("/")
    elif location == "global":
        origin = "https://aiplatform.googleapis.com"
    else:
        origin = f"https://{location}-aiplatform.googleapis.com"
    return project, location, origin


def google_vertex_openai_base(*, proxy: bool = False) -> str:
    """Build the project-qualified Vertex Chat Completions base URL."""
    project, location, origin = google_vertex_settings()
    if proxy:
        origin = f"http://127.0.0.1:{VERTEX_PROXY_PORT}"
    return (
        f"{origin}/v1/projects/{project}/locations/{location}"
        "/endpoints/openapi"
    )


def safe_component(value: str) -> str:
    """Return a conservative filesystem component."""
    cleaned = "".join(c if c.isalnum() or c in "._-" else "-" for c in value)
    return cleaned[:160] or "run"


class EnvConfiguredAdapter(BaseClawAdapter):
    """Base for harnesses configured only from repo state and environment keys."""

    def __init__(
        self,
        model: str,
        timeout: int,
        max_turns: int | None = None,
        *,
        model_api_keys: dict[str, str] | None = None,
    ):
        super().__init__(model, timeout, max_turns)
        self.model_api_keys = dict(model_api_keys or {})

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
    def api_base(self) -> str:
        if self.is_google_vertex:
            return google_vertex_openai_base()
        spec = provider_spec(self.model)
        if spec.api_base_env and os.environ.get(spec.api_base_env):
            return os.environ[spec.api_base_env]
        return spec.api_base

    def api_key_env(self) -> str | None:
        return api_key_env_for_model(self.model, self.model_api_keys)

    def resolved_api_key(self) -> str | None:
        name = self.api_key_env()
        return os.environ.get(name) if name else None

    def model_auth(self) -> dict:
        return {
            "model": self.model,
            "provider": self.raw_provider,
            "normalized_provider": self.provider,
            "runtime_model": self.runtime_model,
            "api_base": self.api_base,
            "api_key_env": self.api_key_env(),
            "api_key_present": bool(self.resolved_api_key()),
        }

    def validate_runtime(self) -> None:
        # Resolve the provider first so unsupported or malformed model ids fail
        # before Docker is started.
        provider_spec(self.model)
        if self.is_google_vertex:
            google_vertex_settings()
        if not self.resolved_api_key():
            env_name = self.api_key_env()
            hint = (
                f"Set {env_name} in _private/.env"
                if env_name
                else "pass --api-key-env NAME and define NAME in _private/.env"
            )
            raise RuntimeError(f"No API key for {self.model}. {hint}.")

    def auth_env(self) -> dict[str, str]:
        """Container env aliases for the selected key, without host config files."""
        value = self.resolved_api_key()
        if not value:
            return {}
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
        env.update(extra or {})
        args: list[str] = []
        for name, value in env.items():
            args.extend(["-e", f"{name}={value}"])
        return args

    def vertex_proxy_container_args(self) -> list[str]:
        """Mount and configure the loopback Vertex auth proxy when required."""
        if not self.is_google_vertex:
            return []
        if not VERTEX_PROXY_SCRIPT.is_file():
            raise RuntimeError(f"Vertex proxy script missing: {VERTEX_PROXY_SCRIPT}")
        project, location, origin = google_vertex_settings()
        args = [
            "-v",
            f"{VERTEX_PROXY_SCRIPT}:{VERTEX_PROXY_CONTAINER_PATH}:ro",
        ]
        args.extend(
            self.docker_exec_env_args(
                {
                    "GOOGLE_CLOUD_PROJECT": project,
                    "GOOGLE_CLOUD_LOCATION": location,
                    "GOOGLE_VERTEX_BASE_URL": origin,
                }
            )
        )
        return args

    def start_vertex_proxy(self, workspace) -> None:
        """Start a per-container proxy that replaces Bearer auth with API-key auth."""
        if not self.is_google_vertex:
            return
        start = workspace.run_in_container(
            f"python3 {VERTEX_PROXY_CONTAINER_PATH} "
            ">/tmp/pddl-vertex-proxy.log 2>&1 </dev/null &"
        )
        if start.exit_code != 0:
            raise RuntimeError(f"Failed to start Vertex proxy: {start.stderr}")
        health = workspace.run_in_container(
            f"for i in $(seq 1 50); do "
            f"curl -fsS http://127.0.0.1:{VERTEX_PROXY_PORT}/health >/dev/null "
            "&& exit 0; sleep 0.1; done; "
            "cat /tmp/pddl-vertex-proxy.log >&2; exit 1"
        )
        if health.exit_code != 0:
            raise RuntimeError(f"Vertex proxy did not become ready: {health.stderr}")


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
                "Run: bash source/agent_formalizer/install_harnesses.sh "
                f"{self.install_target}"
            )

    def python_runtime_mount_args(self) -> list[str]:
        self.validate_python_runtime()
        resolved_python = self.runtime_python.resolve()
        source_home = resolved_python.parent.parent
        if self.runtime_python.is_symlink():
            link_target = Path(os.readlink(self.runtime_python))
            if not link_target.is_absolute():
                link_target = self.runtime_python.parent / link_target
            target_home = link_target.parent.parent
        else:
            target_home = source_home
        mounts = ["-v", f"{self.runtime_env}:{self.runtime_env}:ro"]
        try:
            resolved_python.relative_to(self.runtime_env)
        except ValueError:
            # uv's venv symlink normally points through an unversioned Python
            # home symlink. Docker resolves mount sources, so explicitly mount
            # the resolved source at the exact path embedded in the venv link.
            mounts.extend(["-v", f"{source_home}:{target_home}:ro"])
        return mounts


def run_captured_agent(
    cmd: list[str],
    *,
    timeout: int,
    stdout_path: Path | None,
    stderr_path: Path | None,
    final_text: str | None = None,
) -> AgentResult:
    """Run a non-interactive harness command and normalize its result."""
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + SUBPROCESS_TIMEOUT_BUFFER,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = decode_output(exc.stdout)
        stderr = decode_output(exc.stderr)

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
    """Normalize OpenAI-style JSONL messages into agent-step records."""
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
