"""NanoBot adapter with an ephemeral in-container config and session."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable

from agent_formalizer.claws.common import (
    INTERNAL_API_KEY_ENV,
    EnvConfiguredAdapter,
    PythonRuntimeMixin,
    jsonl_steps,
    run_captured_agent,
    tool_records,
)
from agent_formalizer.configuration.config import CONTAINER_WORKSPACE, NANOBOT_ENV_PATH
from agent_formalizer.timing.deadline_integration import ENVIRONMENT_KEYS, selected as logical_deadlines_selected
from agent_formalizer.results.optional_evidence import inspect_json_analysis_fields
from agent_formalizer.result_types import AgentResult

NANOBOT_CONFIG_DIR = "/tmp/nanobot-pddl-benchmark"
NANOBOT_USAGE_PATH = f"{NANOBOT_CONFIG_DIR}/usage.json"
NANOBOT_CAPTURE_SCRIPT = f"{NANOBOT_CONFIG_DIR}/benchmark_agent.py"

NANOBOT_USAGE_CAPTURE_SOURCE = f'''\
"""Benchmark wrapper around Nanobot's native CLI.

The wrapper changes no prompt, tools, or loop settings.  It only attaches a
run-level hook and writes Nanobot's own aggregate AgentRunResult.usage after
the native run ends.
"""

import json
from pathlib import Path

from nanobot.agent.hook import AgentHook
from nanobot.agent.loop import AgentLoop


_USAGE_PATH = Path({NANOBOT_USAGE_PATH!r})
_ORIGINAL_PROCESS_DIRECT = AgentLoop.process_direct


def _clean_usage(value):
    if not isinstance(value, dict):
        return {{}}
    cleaned = {{}}
    for key, item in value.items():
        try:
            cleaned[str(key)] = int(item or 0)
        except (TypeError, ValueError):
            continue
    return cleaned


class _BenchmarkUsageHook(AgentHook):
    def __init__(self):
        super().__init__()
        self.finished = False

    def _write(self, capture_status, context):
        report = {{
            "schema_version": 1,
            "source": "nanobot-agent-run-result",
            "capture_status": capture_status,
            "stop_reason": context.stop_reason,
            "error": context.error,
            "raw_usage": _clean_usage(context.usage),
        }}
        temporary = _USAGE_PATH.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\\n",
                encoding="utf-8",
            )
            temporary.replace(_USAGE_PATH)
        except OSError:
            temporary.unlink(missing_ok=True)

    async def after_run(self, context):
        self._write("complete", context)
        self.finished = True

    async def on_error(self, context):
        self._write("error", context)

    async def on_finally(self, context):
        if not self.finished:
            self._write("partial", context)


async def _process_direct_with_usage(self, *args, **kwargs):
    hooks = list(kwargs.get("hooks") or [])
    kwargs["hooks"] = [*hooks, _BenchmarkUsageHook()]
    return await _ORIGINAL_PROCESS_DIRECT(self, *args, **kwargs)


_USAGE_PATH.unlink(missing_ok=True)
AgentLoop.process_direct = _process_direct_with_usage

from nanobot.cli.commands import app

app()
'''

NANOBOT_DISABLED_SKILLS = [
    "clawhub",
    "cron",
    "github",
    "image-generation",
    "long-goal",
    "memory",
    "my",
    "skill-creator",
    "summarize",
    "tmux",
    "update-setup",
    "weather",
]

NANOBOT_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "gemini": "gemini",
    "google-vertex": "openai",
    "deepseek": "deepseek",
    "logits": "custom",
    "dashscope": "dashscope",
}


class NanoBotAdapter(PythonRuntimeMixin, EnvConfiguredAdapter):
    """Run NanoBot with only shell/file tools and repository-scoped data."""

    name = "nanobot"
    runtime_env = NANOBOT_ENV_PATH
    install_target = "nanobot"

    @property
    def nanobot_provider(self) -> str:
        try:
            return NANOBOT_PROVIDER_MAP[self.provider]
        except KeyError as exc:
            raise ValueError(
                f"NanoBot has no provider mapping for '{self.raw_provider}'."
            ) from exc

    def validate_runtime(self) -> None:
        super().validate_runtime()
        self.validate_python_runtime()
        self.nanobot_provider

    def container_run_args(self, instance_id: str) -> list[str]:
        return self.python_runtime_mount_args()

    def post_container_start(self, workspace) -> None:
        result = workspace.run_in_container(
            f"mkdir -p {NANOBOT_CONFIG_DIR} {CONTAINER_WORKSPACE}/memory"
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create NanoBot config dir: {result.stderr}")
        config = json.dumps(self._benchmark_config(), indent=2) + "\n"
        if not workspace.write_text_file(f"{NANOBOT_CONFIG_DIR}/config.json", config):
            raise RuntimeError("Failed to provision isolated NanoBot config")
        if not workspace.write_text_file(
            NANOBOT_CAPTURE_SCRIPT, NANOBOT_USAGE_CAPTURE_SOURCE
        ):
            raise RuntimeError("Failed to provision NanoBot usage capture wrapper")
        # Reproduce a clean official onboarding baseline from the pinned
        # package, never from a host user's NanoBot workspace.
        bootstrap = self._official_bootstrap_files() if self.skills_mode == "official" else {}
        bootstrap["memory/MEMORY.md"] = ""
        for relative in ("AGENTS.md", "SOUL.md", "USER.md", "memory/MEMORY.md"):
            content = bootstrap.get(relative, "")
            if not workspace.write_text_file(f"{CONTAINER_WORKSPACE}/{relative}", content):
                raise RuntimeError(f"Failed to isolate NanoBot bootstrap file {relative}")

    def _nanobot_package_dir(self) -> Path | None:
        candidates = sorted(
            (self.runtime_env / "lib").glob("python*/site-packages/nanobot")
        )
        return candidates[0] if candidates else None

    def _official_bootstrap_files(self) -> dict[str, str]:
        package = self._nanobot_package_dir()
        if not package:
            return {}
        result: dict[str, str] = {}
        for name in ("AGENTS.md", "SOUL.md", "USER.md"):
            path = package / "templates" / name
            if path.is_file():
                result[name] = path.read_text()
        return result

    def _benchmark_config(self) -> dict:
        provider_config = {
            "apiKey": (
                "vertex-auth-via-x-goog-api-key"
                if self.is_google_vertex
                else f"${{{INTERNAL_API_KEY_ENV}}}"
            ),
            "apiBase": self.api_base,
        }
        if self.is_google_vertex:
            provider_config.update(
                {
                    "apiType": "chat_completions",
                    "extraHeaders": {
                        "Authorization": "",
                        "x-goog-api-key": f"${{{INTERNAL_API_KEY_ENV}}}",
                    },
                }
            )
        config = {
            "agents": {
                "defaults": {
                    "workspace": CONTAINER_WORKSPACE,
                    "model": self.openai_compatible_model,
                    "provider": self.nanobot_provider,
                    "fallbackModels": [],
                    "maxConcurrentSubagents": 1,
                    "disabledSkills": (
                        [] if self.skills_mode == "official" else NANOBOT_DISABLED_SKILLS
                    ),
                    "timezone": "UTC",
                }
            },
            "providers": {
                self.nanobot_provider: provider_config
            },
            "tools": {
                # Keep the pinned clean-install registry.  model_only is an
                # egress boundary, not a web-tool ablation: native web tools
                # remain visible and fail at the network boundary.
                "web": {"enable": True},
                "exec": {"enable": True, "timeout": 60},
                "file": {"enable": True},
                "cliApps": {
                    "enable": True,
                    "installTimeout": 300,
                    "runTimeout": 60,
                    "catalogTtlSeconds": 3600,
                },
                "my": {"enable": True, "allowSet": False},
                "imageGeneration": {"enabled": False},
                "restrictToWorkspace": False,
                "mcpServers": {},
            },
            "channels": {},
        }
        if self.output_token_policy():
            defaults = config["agents"]["defaults"]
            defaults["maxTokens"] = self.native_max_output_tokens()
            # The true model context, not output+old context fabricated to
            # compensate for a large completion reservation.
            defaults["contextWindowTokens"] = self.output_token_policy()["context_window_tokens"]
        if logical_deadlines_selected(self):
            # Native allowlist surface: propagate only the non-secret timing
            # runtime, never the model credential or host environment.
            config["tools"]["exec"]["allowedEnvKeys"] = list(ENVIRONMENT_KEYS)
        return config

    def tool_policy(self) -> dict:
        return {
            "registry": "pinned-clean-install-defaults",
            "native_web_tools_visible": True,
            "network_effect_boundary": self.network_mode,
            "mcp_servers": "official-clean-empty",
            "restrict_to_workspace": False,
            "cli_apps": True,
            "self_inspection": True,
            "skills": self.skills_mode,
            "bootstrap_files": "official-clean" if self.skills_mode == "official" else "empty",
            "state": "throwaway-container",
        }

    def effective_config(self) -> dict:
        value = super().effective_config()
        value["harness_config"] = self._benchmark_config()
        value["optional_diagnostics"] = {
            "token_usage": {
                "source": "nanobot AgentRunResult.usage via run-level hook",
                "raw_artifact": NANOBOT_USAGE_PATH,
                "prompt_or_tool_changes": False,
            }
        }
        return value

    def runtime_info(self) -> dict:
        return {
            **super().runtime_info(),
            **self.python_runtime_info("nanobot-ai"),
        }

    def skills_info(self) -> dict:
        from agent_formalizer.results.provenance import file_manifest

        package = self._nanobot_package_dir()
        paths = [] if not package else [
            path for path in (package / "skills").glob("**/*")
            if "__pycache__" not in path.parts and path.suffix != ".pyc"
        ]
        paths += [] if not package else list((package / "templates").glob("*.md"))
        return {
            "mode": self.skills_mode,
            "baseline": "pinned-package-bundled-skills-and-bootstrap",
            "manifest": file_manifest(paths, root=package) if package else [],
        }

    @staticmethod
    def _session_id(agent_id: str) -> str:
        return f"benchmark:{agent_id}"

    @classmethod
    def _session_path(cls, agent_id: str) -> str:
        # Nanobot 0.2.2 SessionManager.safe_key replaces filesystem-unsafe
        # characters (including the session-id colon) with underscores.
        unsafe = set('<>:"/\\|?*')
        stem = "".join(
            "_" if char in unsafe else char for char in cls._session_id(agent_id)
        ).strip()
        return f"{CONTAINER_WORKSPACE}/sessions/{stem}.jsonl"

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent_stdout.log" if artifact_dir else None
        stderr_path = artifact_dir / "agent_stderr.log" if artifact_dir else None

        argv = [
            "agent",
            "--message",
            prompt,
            "--session",
            self._session_id(agent_id),
            "--config",
            f"{NANOBOT_CONFIG_DIR}/config.json",
            "--workspace",
            CONTAINER_WORKSPACE,
            "--no-markdown",
            "--no-logs",
        ]
        cmd = ["docker", "exec", "-w", CONTAINER_WORKSPACE]
        cmd.extend(
            self.docker_exec_env_args(
                {
                    "HOME": NANOBOT_CONFIG_DIR,
                    "NO_COLOR": "1",
                }
            )
        )
        cmd.extend(
            [container_name, str(self.runtime_python), NANOBOT_CAPTURE_SCRIPT, *argv]
        )
        result = run_captured_agent(
            cmd,
            timeout=self.remaining_timeout(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            container_name=container_name,
            attempt_clock=self.current_attempt_clock(),
        )
        result.session_id = self._session_id(agent_id)
        result.session_file = self._session_path(agent_id)
        return result

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> dict:
        if not container_name:
            return {
                "status": "failed",
                "collector": "nanobot-docker-copy",
                "reason": "container_name_unavailable",
                "files_copied": 0,
            }
        output = dest / "sessions"
        output.mkdir(parents=True, exist_ok=True)
        source = session_file or self._session_path(agent_id)
        destination = output / "nanobot.jsonl"
        try:
            result = subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{container_name}:{source}",
                    str(destination),
                ],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "status": "failed",
                "collector": "nanobot-docker-copy",
                "error_type": type(exc).__name__,
                "files_copied": 0,
            }
        if result.returncode != 0:
            return {
                "status": "failed",
                "collector": "nanobot-docker-copy",
                "copy_exit_code": result.returncode,
                "files_copied": 0,
            }
        if not destination.is_file():
            return {
                "status": "missing",
                "collector": "nanobot-docker-copy",
                "copy_exit_code": result.returncode,
                "files_copied": 0,
            }
        return {
            "status": "persisted" if destination.stat().st_size else "empty",
            "collector": "nanobot-docker-copy",
            "copy_exit_code": result.returncode,
            "files_copied": 1,
        }

    def analysis_evidence_spec(self) -> dict:
        return {
            "schema_version": 1,
            "analysis_source": {
                "kind": "native_session_message_fields",
                "native_harness_exposure": "structured",
                "absence_is_model_attributable": False,
                "text_fields": ["reasoning_content", "thinking"],
                "opaque_fields": [],
            },
            "raw_session": {
                "adapter_persistence": "implemented",
                "collector": "nanobot-docker-copy",
            },
            "normalized_analysis": {
                "status": "not_implemented",
                "known_loss_modes": [
                    "reasoning_content_and_thinking_blocks_are_not_projected"
                ],
            },
        }

    def inspect_analysis_evidence(self, artifact_dir: Path) -> dict:
        return inspect_json_analysis_fields(
            sorted((artifact_dir / "sessions").glob("*.jsonl")),
            artifact_dir=artifact_dir,
            text_fields={"reasoning_content", "thinking"},
        )

    def collect_usage(self, workspace, artifact_dir: Path) -> dict:
        """Copy and normalize Nanobot's own per-run token accounting."""
        sessions = artifact_dir / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        usage_path = sessions / "usage.json"
        usage_path.unlink(missing_ok=True)

        if not workspace.copy_from_container(NANOBOT_USAGE_PATH, str(usage_path)):
            report = {
                "schema_version": 1,
                "source": "nanobot-agent-run-result",
                "capture_status": "missing",
                "usage": {},
            }
            usage_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n"
            )
            return {}

        try:
            report = json.loads(usage_path.read_text(errors="replace"))
            if not isinstance(report, dict):
                raise TypeError("usage report is not a JSON object")
            raw_usage = report.get("raw_usage", {})
            usage = _normalize_nanobot_usage(raw_usage)
            report["measurement"] = _nanobot_usage_measurement(raw_usage)
            report["usage"] = usage
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            report = {
                "schema_version": 1,
                "source": "nanobot-agent-run-result",
                "capture_status": "error",
                "error": str(exc),
                "usage": {},
            }
            usage = {}

        usage_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        return usage

    @staticmethod
    def _artifact_sessions(artifact_dir: Path) -> list[Path]:
        return sorted((artifact_dir / "sessions").glob("*.jsonl"))

    def iter_agent_steps(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        return jsonl_steps(self._artifact_sessions(artifact_dir))

    def iter_tool_calls(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        return tool_records(jsonl_steps(self._artifact_sessions(artifact_dir)))


def _normalize_nanobot_usage(raw_usage: object) -> dict:
    """Map Nanobot/OpenAI token fields to the benchmark's usage vocabulary.

    OpenAI-compatible ``prompt_tokens`` includes cached prompt tokens, whereas
    the benchmark's ``input`` field represents non-cached input.  The raw
    provider values remain available in ``sessions/usage.json``.
    """
    if not isinstance(raw_usage, dict):
        return {}

    def token(name: str) -> int:
        try:
            return max(0, int(raw_usage.get(name, 0) or 0))
        except (TypeError, ValueError):
            return 0

    prompt = token("prompt_tokens")
    output = token("completion_tokens")
    cache_read = min(prompt, token("cached_tokens"))
    total = token("total_tokens") or prompt + output
    if not any((prompt, output, cache_read, total)):
        return {}
    return {
        "input": prompt - cache_read,
        "output": output,
        "cacheRead": cache_read,
        "cacheWrite": 0,
        "total": total,
        "providerTokens": token("provider_tokens"),
        "estimatedTokens": token("estimated_tokens"),
    }


def _nanobot_usage_measurement(raw_usage: object) -> str:
    """Describe whether Nanobot used provider usage, estimates, or both."""
    if not isinstance(raw_usage, dict):
        return "unavailable"

    def positive(name: str) -> bool:
        try:
            return int(raw_usage.get(name, 0) or 0) > 0
        except (TypeError, ValueError):
            return False

    provider = positive("provider_tokens")
    estimated = positive("estimated_tokens")
    if provider and estimated:
        return "mixed"
    if provider:
        return "provider-reported"
    if estimated:
        return "nanobot-estimated"
    if _normalize_nanobot_usage(raw_usage):
        return "unclassified"
    return "unavailable"
