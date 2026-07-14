"""ZeroClaw adapter for the current V3 multi-agent configuration schema."""

from __future__ import annotations

import json
from pathlib import Path

from agent_formalizer.claws.common import (
    EnvConfiguredAdapter,
    google_vertex_openai_base,
    run_captured_agent,
)
from agent_formalizer.config import CONTAINER_WORKSPACE, ZEROCLAW_BIN
from agent_formalizer.result_types import AgentResult

ZEROCLAW_CONFIG_DIR = "/tmp/zeroclaw-pddl-benchmark"
ZEROCLAW_AGENT_ALIAS = "benchmark"

ZEROCLAW_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "gemini": "gemini",
    # Custom routes through ZeroClaw's OpenAI-compatible transport, which
    # preserves Gemini extra_content/thought signatures across tool turns.
    "google-vertex": "custom",
    "deepseek": "deepseek",
    "dashscope": "qwen",
}

ZEROCLAW_ALLOWED_TOOLS = [
    "shell",
    "file_read",
    "file_write",
    "file_edit",
    "glob_search",
    "content_search",
]


class ZeroClawAdapter(EnvConfiguredAdapter):
    """Run the ZeroClaw binary with no dependency on ``~/.zeroclaw``."""

    name = "zeroclaw"

    @property
    def zeroclaw_provider(self) -> str:
        try:
            return ZEROCLAW_PROVIDER_MAP[self.provider]
        except KeyError as exc:
            raise ValueError(
                f"ZeroClaw has no provider mapping for '{self.raw_provider}'."
            ) from exc

    @property
    def zeroclaw_api_base(self) -> str:
        if self.is_google_vertex:
            return google_vertex_openai_base(proxy=True)
        base = self.api_base.rstrip("/")
        if self.provider == "gemini" and base.endswith("/openai"):
            # ZeroClaw's typed Gemini provider speaks generateContent, unlike
            # NanoBot/GenericAgent's OpenAI-compatible Gemini transport.
            base = base.removesuffix("/openai")
        return base

    def model_auth(self) -> dict:
        auth = super().model_auth()
        auth["api_base"] = self.zeroclaw_api_base
        return auth

    def validate_runtime(self) -> None:
        super().validate_runtime()
        self.zeroclaw_provider
        if not ZEROCLAW_BIN.is_file():
            raise RuntimeError(
                f"ZeroClaw binary not found at {ZEROCLAW_BIN}. Run: "
                "bash source/agent_formalizer/install_harnesses.sh zeroclaw"
            )

    def container_run_args(self, instance_id: str) -> list[str]:
        args = ["-v", f"{ZEROCLAW_BIN}:/usr/local/bin/zeroclaw:ro"]
        args.extend(self.vertex_proxy_container_args())
        return args

    def post_container_start(self, workspace) -> None:
        self.start_vertex_proxy(workspace)
        result = workspace.run_in_container(f"mkdir -p {ZEROCLAW_CONFIG_DIR}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create ZeroClaw config dir: {result.stderr}")
        if not workspace.write_text_file(
            f"{ZEROCLAW_CONFIG_DIR}/config.toml", self._benchmark_config_toml()
        ):
            raise RuntimeError("Failed to provision isolated ZeroClaw config")

    def _benchmark_config_toml(self) -> str:
        family = self.zeroclaw_provider
        max_turns = self.max_turns or 200
        q = json.dumps
        tools = ", ".join(q(tool) for tool in ZEROCLAW_ALLOWED_TOOLS)
        return f"""schema_version = 3

[providers.models.{family}.benchmark]
model = {q(self.openai_compatible_model)}
uri = {q(self.zeroclaw_api_base)}
timeout_secs = {int(self.timeout)}
wire_api = "chat_completions"

[agents.{ZEROCLAW_AGENT_ALIAS}]
model_provider = "{family}.benchmark"
risk_profile = "benchmark"
runtime_profile = "benchmark"

[agents.{ZEROCLAW_AGENT_ALIAS}.workspace]
path = {q(CONTAINER_WORKSPACE)}

[risk_profiles.benchmark]
level = "supervised"
workspace_only = true
allowed_commands = ["*"]
require_approval_for_medium_risk = false
block_high_risk_commands = false
auto_approve = [{tools}]
always_ask = []
allowed_tools = [{tools}]
excluded_tools = ["web_search", "web_fetch", "memory_recall", "memory_store", "spawn_subagent", "delegate", "session_status"]

[runtime_profiles.benchmark]
agentic = true
max_tool_iterations = {int(max_turns)}
max_actions_per_hour = 10000
max_cost_per_day_cents = 100000
shell_timeout_secs = {min(int(self.timeout), 600)}
parallel_tools = false
strict_tool_parsing = true

[memory]
backend = "none"
auto_save = false
"""

    def tool_policy(self) -> dict:
        return {
            "allowed": ZEROCLAW_ALLOWED_TOOLS,
            "workspace_only": True,
            "web": False,
            "memory": False,
            "delegation": False,
            "schema_version": 3,
            "state": "throwaway-container",
        }

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

        secret_env = (
            "ZEROCLAW_providers__models__"
            f"{self.zeroclaw_provider}__benchmark__api_key"
        )
        provider_key = (
            "vertex-auth-via-x-goog-api-key"
            if self.is_google_vertex
            else self.resolved_api_key() or ""
        )
        cmd = ["docker", "exec", "-w", CONTAINER_WORKSPACE]
        cmd.extend(
            self.docker_exec_env_args(
                {
                    "ZEROCLAW_CONFIG_DIR": ZEROCLAW_CONFIG_DIR,
                    "HOME": ZEROCLAW_CONFIG_DIR,
                    secret_env: provider_key,
                }
            )
        )
        cmd.extend(
            [
                container_name,
                "/usr/local/bin/zeroclaw",
                "--config-dir",
                ZEROCLAW_CONFIG_DIR,
                "agent",
                "--agent",
                ZEROCLAW_AGENT_ALIAS,
                "--message",
                prompt,
            ]
        )
        return run_captured_agent(
            cmd,
            timeout=self.timeout,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def collect_usage(self, workspace, artifact_dir: Path) -> dict:
        costs_path = artifact_dir / "costs.jsonl"
        candidates = [
            f"{CONTAINER_WORKSPACE}/state/costs.jsonl",
            f"{ZEROCLAW_CONFIG_DIR}/data/state/costs.jsonl",
        ]
        for candidate in candidates:
            if workspace.copy_from_container(candidate, str(costs_path)):
                break
        return _parse_costs(costs_path)


def _parse_costs(path: Path) -> dict:
    """Sum token usage from ZeroClaw's per-turn cost records."""
    if not path.is_file():
        return {}
    totals = {
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "reasoning_tokens": 0,
    }
    for line in path.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = row.get("usage", row) if isinstance(row, dict) else {}
        if not isinstance(usage, dict):
            continue
        totals["turns"] += 1
        input_tokens = int(
            usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        )
        output_tokens = int(
            usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        )
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["total_tokens"] += int(
            usage.get("total_tokens", 0) or input_tokens + output_tokens
        )
        totals["cache_read_tokens"] += int(
            usage.get("cache_read_tokens", usage.get("cached_tokens", 0)) or 0
        )
        totals["reasoning_tokens"] += int(usage.get("reasoning_tokens", 0) or 0)
    return totals
