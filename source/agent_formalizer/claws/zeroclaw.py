"""ZeroClaw adapter for the current V3 multi-agent configuration schema."""

from __future__ import annotations

import json
from pathlib import Path

from agent_formalizer.claws.common import (
    EnvConfiguredAdapter,
    run_captured_agent,
)
from agent_formalizer.configuration.config import (
    CONTAINER_WORKSPACE,
    ZEROCLAW_BIN,
    ZEROCLAW_SOURCE_PATH,
    ZEROCLAW_VERSION_NOTE_PATH,
)
from agent_formalizer.result_types import AgentResult

ZEROCLAW_CONFIG_DIR = "/tmp/zeroclaw-pddl-benchmark"
ZEROCLAW_AGENT_ALIAS = "benchmark"

ZEROCLAW_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "gemini": "gemini",
    # Custom routes through ZeroClaw's OpenAI-compatible transport, which
    # preserves Gemini extra_content/thought signatures across tool exchanges.
    "google-vertex": "custom",
    "deepseek": "deepseek",
    "logits": "custom",
    "dashscope": "qwen",
}

ZEROCLAW_NONINTERACTIVE_APPROVALS = [
    "shell",
    "file_read",
    "file_write",
    "file_edit",
    "glob_search",
    "content_search",
    "calculator",
    "image_info",
    "git_operations",
    "tool_search",
    "browser",
    "browser_open",
    "web_search",
    "web_search_tool",
    "web_fetch",
    "weather",
]
# Backward-compatible name for external inspection; this is an approval list,
# not an adapter-level tool allowlist.
ZEROCLAW_ALLOWED_TOOLS = ZEROCLAW_NONINTERACTIVE_APPROVALS


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
                "bash source/agent_formalizer/runtime/install_harnesses.sh zeroclaw"
            )

    def container_run_args(self, instance_id: str) -> list[str]:
        return ["-v", f"{self.execution_binary()}:/usr/local/bin/zeroclaw:ro"]

    def execution_binary(self):
        from agent_formalizer.timing.deadline_integration import policy
        if policy(self) == 'call-checkpoint-v1':
            from agent_formalizer.timing.zeroclaw_deadlines import prepared
            return prepared()[0]
        return ZEROCLAW_BIN

    def state_isolation_spec(self, instance_id: str) -> dict:
        spec = super().state_isolation_spec(instance_id)
        spec["shared_readonly_bind_sources"] = [
            *spec.get("shared_readonly_bind_sources", []),
            str(self.execution_binary()),
        ]
        return spec

    def post_container_start(self, workspace) -> None:
        result = workspace.run_in_container(f"mkdir -p {ZEROCLAW_CONFIG_DIR}")
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create ZeroClaw config dir: {result.stderr}")
        if not workspace.write_text_file(
            f"{ZEROCLAW_CONFIG_DIR}/config.toml", self._benchmark_config_toml()
        ):
            raise RuntimeError("Failed to provision isolated ZeroClaw config")

    def _benchmark_config_toml(self) -> str:
        family = self.zeroclaw_provider
        q = json.dumps
        approvals = ", ".join(q(tool) for tool in ZEROCLAW_NONINTERACTIVE_APPROVALS)
        # ZeroClaw's `custom` family defaults to prompt-guided tools
        # (native_tools unset/false). Vertex is reached through the OpenAI
        # chat-completions gateway, so native tool schemas + tool-result
        # history must stay enabled; otherwise the model retries the same
        # file_write and the harness loop detector aborts.
        native_tools_line = (
            "native_tools = true\n" if family == "custom" else ""
        )
        return f"""schema_version = 3

[providers.models.{family}.benchmark]
model = {q(self.openai_compatible_model)}
uri = {q(self.zeroclaw_api_base)}
timeout_secs = {int(self.timeout)}
wire_api = "chat_completions"
{native_tools_line}
[agents.{ZEROCLAW_AGENT_ALIAS}]
model_provider = "{family}.benchmark"
risk_profile = "benchmark"
runtime_profile = "benchmark"

[agents.{ZEROCLAW_AGENT_ALIAS}.workspace]
path = {q(CONTAINER_WORKSPACE)}

[risk_profiles.benchmark]
level = "supervised"
workspace_only = true
require_approval_for_medium_risk = false
block_high_risk_commands = true
auto_approve = [{approvals}]
always_ask = []
allowed_tools = []
excluded_tools = []

[runtime_profiles.benchmark]
agentic = true
max_actions_per_hour = 20
max_cost_per_day_cents = 500
# Preserve the pinned native-clean per-shell timeout.  The common 1800s
# harness deadline is enforced independently by the benchmark runner.
shell_timeout_secs = 60
parallel_tools = false
strict_tool_parsing = false

"""

    def tool_policy(self) -> dict:
        return {
            "registry": "pinned-native-unfiltered",
            "noninteractive_auto_approve": list(ZEROCLAW_NONINTERACTIVE_APPROVALS),
            "workspace_only": True,
            "network_mode": self.network_mode,
            "memory": "official-clean-ephemeral",
            "delegation": "native-risk-profile-default",
            "schema_version": 3,
            "state": "throwaway-container",
            "skills": self.skills_mode,
        }

    def effective_config(self) -> dict:
        value = super().effective_config()
        value["harness_config"] = {
            "format": "toml",
            "content": self._benchmark_config_toml(),
        }
        return value

    def runtime_info(self) -> dict:
        from agent_formalizer.results.provenance import git_info, run_text

        version = run_text([str(ZEROCLAW_BIN), "--version"])
        if ZEROCLAW_VERSION_NOTE_PATH.is_file():
            note = ZEROCLAW_VERSION_NOTE_PATH.read_text(encoding="utf-8").strip()
            if note:
                version = f"{version} ({note})"
        overlay = {}
        from agent_formalizer.timing.deadline_integration import policy
        if policy(self) == 'call-checkpoint-v1':
            from agent_formalizer.timing.zeroclaw_deadlines import prepared
            binary, manifest = prepared()
            overlay = {'execution_binary': str(binary),
                       'execution_binary_sha256': manifest['binary_sha256'],
                       'native_deadline_overlay': manifest['implementation']}
        return {
            **super().runtime_info(),
            **overlay,
            "binary": str(ZEROCLAW_BIN),
            "version": version,
            "source": git_info(ZEROCLAW_SOURCE_PATH),
        }

    def skills_info(self) -> dict:
        from agent_formalizer.results.provenance import file_manifest

        paths = [
            path for path in ZEROCLAW_SOURCE_PATH.glob("shared/skills/**/*")
            if "__pycache__" not in path.parts and path.suffix != ".pyc"
        ]
        return {
            "mode": self.skills_mode,
            "baseline": "pinned-official-clean-install-with-no-installed-skills",
            "manifest": file_manifest(paths, root=ZEROCLAW_SOURCE_PATH),
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
        # The real provider credential exists only in the gateway sidecar.
        provider_key = "benchmark-gateway-placeholder"
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
            timeout=self.remaining_timeout(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            container_name=container_name,
            attempt_clock=self.current_attempt_clock(),
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

    def raw_evidence_roots(self, artifact_dir: Path) -> list[Path]:
        # Cost rows are usage evidence, not a native conversation transcript.
        return [
            artifact_dir / "costs.jsonl",
            artifact_dir / "sessions",
            artifact_dir / "gateway",
        ]

    def analysis_evidence_spec(self) -> dict:
        return {
            "schema_version": 1,
            "analysis_source": {
                "kind": "native_runtime_reasoning_content",
                "native_harness_exposure": "structured",
                "absence_is_model_attributable": False,
                "text_fields": ["reasoning_content"],
                "opaque_fields": [],
            },
            "raw_session": {
                "adapter_persistence": "not_implemented",
                "collector": "none",
            },
            "normalized_analysis": {
                "status": "not_implemented",
                "known_loss_modes": [
                    "adapter_collects_usage_but_no_native_conversation"
                ],
            },
        }


def _parse_costs(path: Path) -> dict:
    """Sum ZeroClaw cost rows into disjoint benchmark token buckets."""
    if not path.is_file():
        return {}
    totals = {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "reasoning": 0,
    }
    for line in path.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = row.get("usage", row) if isinstance(row, dict) else {}
        if not isinstance(usage, dict):
            continue
        prompt_tokens = max(0, int(
            usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        ))
        output_tokens = max(0, int(
            usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        ))
        cached_tokens = max(0, int(
            usage.get(
                "cached_input_tokens",
                usage.get("cache_read_tokens", usage.get("cached_tokens", 0)),
            )
            or 0
        ))
        cached_tokens = min(prompt_tokens, cached_tokens)
        totals["input"] += prompt_tokens - cached_tokens
        totals["output"] += output_tokens
        totals["cacheRead"] += cached_tokens
        totals["reasoning"] += max(
            0, int(usage.get("reasoning_tokens", 0) or 0)
        )
    totals["total"] = (
        totals["input"]
        + totals["output"]
        + totals["cacheRead"]
        + totals["cacheWrite"]
    )
    return totals
