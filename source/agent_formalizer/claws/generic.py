"""GenericAgent adapter with per-attempt memory, temp files, and model config."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable

from agent_formalizer.claws.common import (
    INTERNAL_API_KEY_ENV,
    EnvConfiguredAdapter,
    PythonRuntimeMixin,
    safe_component,
)
from agent_formalizer.configuration.config import (
    CONTAINER_WORKSPACE,
    GENERIC_BENCHMARK_STATE_DIR,
    GENERIC_ENV_PATH,
    GENERIC_REPO_PATH,
)
from agent_formalizer.results.optional_evidence import inspect_tagged_response_logs
from agent_formalizer.result_types import AgentResult

logger = logging.getLogger(__name__)

ROUND_END = "[ROUND END]"
GENERIC_CONTAINER_HOME = "/tmp/genericagent-pddl-benchmark"
GENERIC_CONTAINER_CONFIG = f"{GENERIC_CONTAINER_HOME}/config"
ANTHROPIC_USAGE_RE = re.compile(
    r"\[Cache\]\s*input=(\d+)\s*creation=(\d+)\s*read=(\d+)"
)
OAI_INPUT_RE = re.compile(r"\[Cache\]\s*input=(\d+)\s*cached=(\d+)")
OAI_OUTPUT_RE = re.compile(r"\[Output\]\s*tokens=(\d+)")


class GenericAgentAdapter(PythonRuntimeMixin, EnvConfiguredAdapter):
    """Run GenericAgent with benchmark-owned config and clean official memory."""

    name = "generic"
    runtime_env = GENERIC_ENV_PATH
    runtime_repo = GENERIC_REPO_PATH
    install_target = "generic"

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
            model_api_keys=model_api_keys,
            api_key=api_key,
            api_key_name=api_key_name,
            credential_metadata=credential_metadata,
            provider_options=provider_options,
            max_model_calls=max_model_calls,
            allow_network=allow_network,
            network_mode=network_mode,
            skills_mode=skills_mode,
            benchmark_profile=benchmark_profile,
            resolved_config=resolved_config,
        )
        self._state_lock = threading.Lock()
        self._instance_states: dict[str, Path] = {}
        self._agent_states: dict[str, Path] = {}

    def validate_runtime(self) -> None:
        super().validate_runtime()
        self.validate_python_runtime()
        required = [
            self.runtime_repo / "agentmain.py",
            self.runtime_repo / "llmcore.py",
            self.runtime_repo / "assets" / "tools_schema.json",
            self.runtime_repo / "assets" / "tools_schema_cn.json",
            self.runtime_repo / "memory",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(
                "GenericAgent runtime is incomplete: "
                + ", ".join(missing)
                + ". Run: bash source/agent_formalizer/runtime/install_harnesses.sh generic"
            )

    def container_run_args(self, instance_id: str) -> list[str]:
        state = self._prepare_instance_state(instance_id)
        config_dir = state / "config"
        args = self.python_runtime_mount_args()
        # Mount the pinned repo read-only, then overlay only per-attempt
        # writable state (temp/memory). Do not bind-mount individual files
        # under that read-only tree: Docker's archive walk for `docker cp`
        # fails on nested file mounts over a read-only parent, which silently
        # drops official /workspace delivery files after a successful agent run.
        args.extend(
            [
                "-v", f"{self.runtime_repo}:{self.runtime_repo}:ro",
                "-v", f"{state / 'temp'}:{self.runtime_repo / 'temp'}:rw",
                "-v", f"{state / 'memory'}:{self.runtime_repo / 'memory'}:rw",
                "-v", f"{config_dir}:{GENERIC_CONTAINER_CONFIG}:ro",
            ]
        )
        return args

    def _prepare_instance_state(self, instance_id: str) -> Path:
        GENERIC_BENCHMARK_STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Docker cannot create a nested mountpoint below a read-only parent
        # mount. GenericAgent does not ship this runtime directory, so create
        # the empty mountpoint once in the repository-local harness cache.
        (self.runtime_repo / "temp").mkdir(exist_ok=True)
        state = GENERIC_BENCHMARK_STATE_DIR / f"attempt-{safe_component(instance_id)}"
        with self._state_lock:
            existing = self._instance_states.get(instance_id)
            if existing is not None:
                return existing
            if state.exists():
                raise RuntimeError(
                    "Refusing to reuse pre-existing GenericAgent attempt state: "
                    f"{state}"
                )
            try:
                (state / "temp").mkdir(parents=True)
                (state / "config").mkdir()
                if self.skills_mode == "official":
                    shutil.copytree(self.runtime_repo / "memory", state / "memory")
                else:
                    (state / "memory").mkdir()
                (state / "config" / "mykey.py").write_text(self._mykey_source())
                self._copy_official_schemas(state / "config")
            except Exception:
                shutil.rmtree(state, ignore_errors=True)
                raise
            self._instance_states[instance_id] = state
        return state

    def state_isolation_spec(self, instance_id: str) -> dict:
        spec = super().state_isolation_spec(instance_id)
        with self._state_lock:
            state = self._instance_states.get(instance_id)
            other_states = {
                path for key, path in self._instance_states.items()
                if key != instance_id
            }
        if state is None:
            spec["tests"] = {"attempt_state_prepared": False}
            return spec
        spec.update(
            {
                "attempt_root": str(state),
                "writable_bind_sources": [
                    str(state / "temp"),
                    str(state / "memory"),
                ],
                "private_readonly_bind_sources": [str(state / "config")],
                "shared_readonly_bind_sources": [
                    *spec.get("shared_readonly_bind_sources", []),
                    str(self.runtime_repo),
                ],
                "tests": {
                    "attempt_state_prepared": state.is_dir(),
                    "attempt_root_not_shared": state not in other_states,
                    "attempt_root_under_benchmark_cache": (
                        state.resolve().parent
                        == GENERIC_BENCHMARK_STATE_DIR.resolve()
                    ),
                    "config_is_attempt_private": (state / "config").is_dir(),
                    "memory_is_attempt_private": (state / "memory").is_dir(),
                    "temp_is_attempt_private": (state / "temp").is_dir(),
                },
            }
        )
        return spec

    def _mykey_source(self) -> str:
        variable = (
            "native_claude_config_benchmark"
            if self.provider == "anthropic"
            else "native_oai_config_benchmark"
        )
        api_key_expr = (
            repr("vertex-auth-via-x-goog-api-key")
            if self.is_google_vertex
            else f"os.environ.get({INTERNAL_API_KEY_ENV!r}, '')"
        )
        return (
            "import os\n\n"
            f"{variable} = {{\n"
            "    'name': 'pddl-benchmark',\n"
            f"    'apikey': {api_key_expr},\n"
            f"    'apibase': {self.api_base!r},\n"
            f"    'model': {self.openai_compatible_model!r},\n"
            "    'api_mode': 'chat_completions',\n"
            f"    'read_timeout': {max(120, int(self.timeout))},\n"
            "}\n"
        )

    def _copy_official_schemas(self, config_dir: Path) -> None:
        """Keep a host-side copy of the pinned official schemas for audit.

        Runtime still reads ``assets/tools_schema*.json`` from the read-only
        repository mount; these copies are not remounted over that tree.
        """
        for filename in ("tools_schema.json", "tools_schema_cn.json"):
            source = self.runtime_repo / "assets" / filename
            shutil.copyfile(source, config_dir / filename)

    # Compatibility alias for callers from the earlier implementation.
    _write_filtered_schemas = _copy_official_schemas

    def _official_tool_names(self) -> list[str]:
        try:
            schema = json.loads(
                (self.runtime_repo / "assets" / "tools_schema.json").read_text()
            )
        except (OSError, json.JSONDecodeError):
            return []
        return sorted(
            entry.get("function", {}).get("name")
            for entry in schema
            if entry.get("function", {}).get("name")
        )

    def tool_policy(self) -> dict:
        native = self._official_tool_names()
        noninteractive_exclusions = [
            name for name in ("ask_user", "start_long_term_update")
            if name in native
        ]
        return {
            "native_schema": native,
            "effective": [
                name for name in native if name not in noninteractive_exclusions
            ],
            "envelope_noninteractive_exclusions": noninteractive_exclusions,
            "tool_schema": "pinned-official-unmodified",
            "web_egress": self.network_mode,
            "plugins": "pinned-official-repository",
            "user_tools": False,
            "memory": (
                "per-attempt-official-clean-copy"
                if self.skills_mode == "official"
                else "per-attempt-empty"
            ),
            "state_dir": "<benchmark-attempt-isolated-state>",
            "state_scope": "per_attempt",
            "cross_attempt_reuse": False,
        }

    def effective_config(self) -> dict:
        value = super().effective_config()
        value["harness_config"] = {
            "model_config_source": self._mykey_source(),
            "tool_schemas": "pinned-official-unmodified",
            "plugins": "pinned-official-repository",
            "memory": self.tool_policy()["memory"],
        }
        return value

    def runtime_info(self) -> dict:
        from agent_formalizer.results.provenance import git_info

        return {
            **super().runtime_info(),
            **self.python_runtime_info(),
            "source": git_info(self.runtime_repo),
        }

    def skills_info(self) -> dict:
        from agent_formalizer.results.provenance import file_manifest

        paths = [
            path for path in (self.runtime_repo / "memory").glob("**/*")
            if "__pycache__" not in path.parts and path.suffix != ".pyc"
        ]
        return {
            "mode": self.skills_mode,
            "baseline": "clean-copy-of-pinned-official-memory-bundle",
            "manifest": file_manifest(paths, root=self.runtime_repo),
        }

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        if instance_id is None:
            raise ValueError("GenericAgent requires an instance_id")
        state = self._instance_states[instance_id]
        with self._state_lock:
            self._agent_states[agent_id] = state

        host_task = state / "temp" / agent_id
        host_task.mkdir(parents=True, exist_ok=True)
        for stale in host_task.glob("output*.txt"):
            stale.unlink()
        (host_task / "input.txt").write_text(prompt)

        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent_stdout.log" if artifact_dir else None
        stderr_path = artifact_dir / "agent_stderr.log" if artifact_dir else None

        cmd = ["docker", "exec", "-w", CONTAINER_WORKSPACE]
        cmd.extend(
            self.docker_exec_env_args(
                {
                    "PYTHONPATH": f"{GENERIC_CONTAINER_CONFIG}:{self.runtime_repo}",
                    # Usage is emitted by the pinned runtime with print().
                    # The adapter may observe the native round-end sentinel
                    # before block-buffered stdout is flushed, so make those
                    # diagnostic lines durable without changing agent logic.
                    "PYTHONUNBUFFERED": "1",
                    "GA_LANG": "en",
                    "HOME": GENERIC_CONTAINER_HOME,
                    "NO_COLOR": "1",
                }
            )
        )
        cmd.extend(
            [
                container_name,
                str(self.runtime_python),
                str(self.runtime_repo / "agentmain.py"),
                "--task",
                agent_id,
                "--llm_no",
                "0",
                "--nobg",
                "--verbose",
                "--no-user-tools",
            ]
        )

        capture_stdout = stdout_path or state / "agent_stdout.log"
        capture_stderr = stderr_path or state / "agent_stderr.log"
        started = time.monotonic()
        output_path = host_task / "output.txt"
        sentinel_seen = False
        timed_out = False
        clock = self.current_attempt_clock()
        fallback_deadline = started + self.timeout
        with capture_stdout.open("w") as stdout_fp, capture_stderr.open("w") as stderr_fp:
            proc = subprocess.Popen(cmd, stdout=stdout_fp, stderr=stderr_fp, text=True)
            try:
                while (
                    not clock.expired()
                    if clock is not None
                    else time.monotonic() < fallback_deadline
                ):
                    if output_path.is_file():
                        try:
                            if ROUND_END in output_path.read_text(errors="replace"):
                                sentinel_seen = True
                                break
                        except OSError:
                            pass
                    if proc.poll() is not None:
                        break
                    time.sleep(0.5)
                else:
                    timed_out = True
            finally:
                if proc.poll() is None:
                    if timed_out:
                        subprocess.run(
                            ["docker", "kill", container_name],
                            capture_output=True,
                            timeout=30,
                        )
                    proc.terminate()
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

        stdout = capture_stdout.read_text(errors="replace")

        output = output_path.read_text(errors="replace") if output_path.is_file() else ""
        final_text = output.split(ROUND_END, 1)[0].rstrip() or None
        self._make_state_host_writable(container_name)
        if timed_out and not sentinel_seen:
            finish_reason = "timeout"
        elif sentinel_seen:
            finish_reason = "stop"
        else:
            finish_reason = "error"

        return AgentResult(
            success=finish_reason == "stop",
            timeout=timed_out,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            finish_reason=finish_reason,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            session_id=agent_id,
            session_file=str(output_path),
            duration_seconds=round(time.monotonic() - started, 1),
            usage=_parse_usage_text(stdout or ""),
            final_text=final_text,
        )

    def _make_state_host_writable(self, container_name: str) -> None:
        """Restore host cleanup access to files created by container root."""
        try:
            result = self._run_container_cleanup_command(
                container_name,
                [
                    "chmod",
                    "-R",
                    "a+rwX",
                    str(self.runtime_repo / "temp"),
                    str(self.runtime_repo / "memory"),
                ],
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not prepare GenericAgent state cleanup: %s", exc)
            return
        if result.returncode != 0:
            logger.warning(
                "Could not prepare GenericAgent state cleanup: %s",
                (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
            )

    def prepare_agent_cleanup(
        self,
        agent_id: str,
        *,
        instance_id: str | None = None,
        container_name: str | None = None,
    ) -> None:
        if container_name:
            self._make_state_host_writable(container_name)

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> dict:
        state = self._agent_states.get(agent_id)
        if not state:
            return {
                "status": "failed",
                "collector": "genericagent-state-copy",
                "reason": "attempt_state_unavailable",
                "files_copied": 0,
            }
        source = state / "temp" / agent_id
        output = dest / "sessions" / "generic"
        output.mkdir(parents=True, exist_ok=True)
        copied = 0
        failures: list[str] = []
        for name in ("input.txt", "output.txt", "stdout.log", "stderr.log", "_history.json"):
            path = source / name
            if path.is_file():
                try:
                    shutil.copy2(path, output / name)
                    copied += 1
                except OSError as exc:
                    failures.append(type(exc).__name__)
        responses = state / "temp" / "model_responses"
        if responses.is_dir():
            try:
                shutil.copytree(
                    responses, output / "model_responses", dirs_exist_ok=True
                )
                copied += sum(
                    1
                    for path in (output / "model_responses").glob("**/*")
                    if path.is_file()
                )
            except OSError as exc:
                failures.append(type(exc).__name__)
        if copied and failures:
            status = "failed_partial"
        elif copied:
            status = "persisted"
        elif failures:
            status = "failed"
        else:
            status = "missing"
        return {
            "status": status,
            "collector": "genericagent-state-copy",
            "files_copied": copied,
            "copy_failures": len(failures),
            "error_types": sorted(set(failures)),
        }

    def analysis_evidence_spec(self) -> dict:
        return {
            "schema_version": 1,
            "analysis_source": {
                "kind": "native_model_response_log_blocks",
                "native_harness_exposure": "conditional",
                "absence_is_model_attributable": False,
                "text_fields": ["thinking"],
                "opaque_fields": [],
            },
            "raw_session": {
                "adapter_persistence": "implemented",
                "collector": "genericagent-state-copy",
            },
            "normalized_analysis": {
                "status": "partial",
                "known_loss_modes": [
                    "only_final_output_text_is_projected_to_agent_steps"
                ],
            },
        }

    def inspect_analysis_evidence(self, artifact_dir: Path) -> dict:
        response_dir = artifact_dir / "sessions" / "generic" / "model_responses"
        return inspect_tagged_response_logs(
            sorted(response_dir.glob("model_responses_*.txt")),
            artifact_dir=artifact_dir,
        )

    def iter_agent_steps(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        output = artifact_dir / "sessions" / "generic" / "output.txt"
        if not output.is_file():
            return []
        text = output.read_text(errors="replace").split(ROUND_END, 1)[0].rstrip()
        return [
            {
                "step": 0,
                "event": "message",
                "role": "assistant",
                "content": text,
                "session_file": "output.txt",
            }
        ]

    def delete_agent(
        self, agent_id: str, *, instance_id: str | None = None
    ) -> None:
        with self._state_lock:
            state = self._agent_states.pop(agent_id, None)
            if state is None and instance_id is not None:
                state = self._instance_states.get(instance_id)
            if state:
                for key, value in list(self._instance_states.items()):
                    if value == state:
                        self._instance_states.pop(key, None)
                for key, value in list(self._agent_states.items()):
                    if value == state:
                        self._agent_states.pop(key, None)
                if state.exists():
                    try:
                        shutil.rmtree(state)
                    except OSError as exc:
                        # Teardown must not replace a completed benchmark result.
                        logger.warning("Could not remove GenericAgent state %s: %s", state, exc)


def _parse_usage_text(text: str) -> dict:
    """Sum GenericAgent token accounting lines across all model calls."""
    total = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    anthropic_spans: list[tuple[int, int]] = []
    for match in ANTHROPIC_USAGE_RE.finditer(text or ""):
        total["input"] += int(match.group(1))
        total["cacheWrite"] += int(match.group(2))
        total["cacheRead"] += int(match.group(3))
        anthropic_spans.append((match.start(), match.end()))
    for match in OAI_INPUT_RE.finditer(text or ""):
        if any(start <= match.start() < end for start, end in anthropic_spans):
            continue
        prompt = int(match.group(1))
        cached = min(prompt, int(match.group(2)))
        # OpenAI-compatible prompt/input tokens include the cached subset.
        # Store disjoint buckets, matching OpenClaw/Hermes/Nanobot.
        total["input"] += prompt - cached
        total["cacheRead"] += cached
    for match in OAI_OUTPUT_RE.finditer(text or ""):
        total["output"] += int(match.group(1))
    total["total"] = sum(total.values())
    return total
