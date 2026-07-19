"""NanoBot adapter with an ephemeral in-container config and session."""

from __future__ import annotations

import base64
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
from agent_formalizer.config import CONTAINER_WORKSPACE, NANOBOT_ENV_PATH
from agent_formalizer.result_types import AgentResult

NANOBOT_CONFIG_DIR = "/tmp/nanobot-pddl-benchmark"

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
        return {
            "agents": {
                "defaults": {
                    "workspace": CONTAINER_WORKSPACE,
                    "model": self.openai_compatible_model,
                    "provider": self.nanobot_provider,
                    "fallbackModels": [],
                    "maxToolIterations": self.max_turns or 200,
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
        return value

    def runtime_info(self) -> dict:
        return {
            **super().runtime_info(),
            **self.python_runtime_info("nanobot-ai"),
        }

    def skills_info(self) -> dict:
        from agent_formalizer.provenance import file_manifest

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
        encoded = base64.urlsafe_b64encode(cls._session_id(agent_id).encode()).decode()
        encoded = encoded.rstrip("=")
        return f"{CONTAINER_WORKSPACE}/sessions/{encoded}.jsonl"

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
            "nanobot",
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
        code = (
            "import sys; "
            f"sys.argv = {argv!r}; "
            "from nanobot.cli.commands import app; "
            "app()"
        )
        cmd = ["docker", "exec", "-w", CONTAINER_WORKSPACE]
        cmd.extend(
            self.docker_exec_env_args(
                {
                    "HOME": NANOBOT_CONFIG_DIR,
                    "NO_COLOR": "1",
                }
            )
        )
        cmd.extend([container_name, str(self.runtime_python), "-c", code])
        result = run_captured_agent(
            cmd,
            timeout=self.remaining_timeout(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            container_name=container_name,
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
    ) -> None:
        if not container_name:
            return
        output = dest / "sessions"
        output.mkdir(parents=True, exist_ok=True)
        source = session_file or self._session_path(agent_id)
        try:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{container_name}:{source}",
                    str(output / "nanobot.jsonl"),
                ],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return

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
