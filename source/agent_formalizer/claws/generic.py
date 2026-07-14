"""GenericAgent adapter with per-run memory, temp files, tools, and model config."""

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
from agent_formalizer.config import (
    CONTAINER_WORKSPACE,
    GENERIC_BENCHMARK_STATE_DIR,
    GENERIC_ENV_PATH,
    GENERIC_REPO_PATH,
)
from agent_formalizer.result_types import AgentResult

logger = logging.getLogger(__name__)

ROUND_END = "[ROUND END]"
GENERIC_EFFECTIVE_MAX_TURNS = 180
FILTERED_GENERIC_TOOLS = {
    "code_run",
    "file_read",
    "file_patch",
    "file_write",
    "update_working_checkpoint",
}

ANTHROPIC_USAGE_RE = re.compile(
    r"\[Cache\]\s*input=(\d+)\s*creation=(\d+)\s*read=(\d+)"
)
OAI_INPUT_RE = re.compile(r"\[Cache\]\s*input=(\d+)\s*cached=(\d+)")
OAI_OUTPUT_RE = re.compile(r"\[Output\]\s*tokens=(\d+)")


class GenericAgentAdapter(PythonRuntimeMixin, EnvConfiguredAdapter):
    """Run GenericAgent without its host ``mykey.py``, plugins, or memory."""

    name = "generic"
    runtime_env = GENERIC_ENV_PATH
    runtime_repo = GENERIC_REPO_PATH
    install_target = "generic"

    def __init__(
        self,
        model: str,
        timeout: int,
        max_turns: int | None = None,
        *,
        model_api_keys: dict[str, str] | None = None,
    ):
        requested = max_turns
        super().__init__(
            model,
            timeout,
            GENERIC_EFFECTIVE_MAX_TURNS,
            model_api_keys=model_api_keys,
        )
        if requested not in (None, GENERIC_EFFECTIVE_MAX_TURNS):
            logger.warning(
                "GenericAgent currently hardcodes max_turns=%d; requested %s is ignored",
                GENERIC_EFFECTIVE_MAX_TURNS,
                requested,
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
                + ". Run: bash source/agent_formalizer/install_harnesses.sh generic"
            )

    def container_run_args(self, instance_id: str) -> list[str]:
        state = self._prepare_instance_state(instance_id)
        config_dir = state / "config"
        args = self.python_runtime_mount_args()
        args.extend(
            [
                "-v", f"{self.runtime_repo}:{self.runtime_repo}:ro",
                "-v", f"{state / 'temp'}:{self.runtime_repo / 'temp'}:rw",
                "-v", f"{state / 'memory'}:{self.runtime_repo / 'memory'}:rw",
                "-v", f"{state / 'empty-plugins'}:{self.runtime_repo / 'plugins'}:ro",
                "-v", (
                    f"{config_dir / 'tools_schema.json'}:"
                    f"{self.runtime_repo / 'assets' / 'tools_schema.json'}:ro"
                ),
                "-v", (
                    f"{config_dir / 'tools_schema_cn.json'}:"
                    f"{self.runtime_repo / 'assets' / 'tools_schema_cn.json'}:ro"
                ),
                "-v", f"{config_dir}:{config_dir}:ro",
            ]
        )
        return args

    def _prepare_instance_state(self, instance_id: str) -> Path:
        GENERIC_BENCHMARK_STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Docker cannot create a nested mountpoint below a read-only parent
        # mount. GenericAgent does not ship this runtime directory, so create
        # the empty mountpoint once in the repository-local harness cache.
        (self.runtime_repo / "temp").mkdir(exist_ok=True)
        state = GENERIC_BENCHMARK_STATE_DIR / safe_component(instance_id)
        with self._state_lock:
            if state.exists():
                shutil.rmtree(state)
            (state / "temp").mkdir(parents=True)
            (state / "config").mkdir()
            (state / "empty-plugins").mkdir()
            shutil.copytree(self.runtime_repo / "memory", state / "memory")
            (state / "config" / "mykey.py").write_text(self._mykey_source())
            if self.is_google_vertex:
                (state / "config" / "sitecustomize.py").write_text(
                    self._vertex_sitecustomize_source()
                )
            self._write_filtered_schemas(state / "config")
            self._instance_states[instance_id] = state
        return state

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

    @staticmethod
    def _vertex_sitecustomize_source() -> str:
        """Patch GenericAgent's requests transport without editing its checkout."""
        return (
            "import os\n"
            "from urllib.parse import urlsplit\n"
            "import requests.sessions\n\n"
            "_pddl_original_request = requests.sessions.Session.request\n"
            "def _pddl_vertex_request(self, method, url, **kwargs):\n"
            "    host = urlsplit(str(url)).hostname or ''\n"
            "    if host == 'aiplatform.googleapis.com' or "
            "host.endswith('-aiplatform.googleapis.com'):\n"
            "        headers = dict(kwargs.get('headers') or {})\n"
            "        for name in list(headers):\n"
            "            if name.lower() == 'authorization':\n"
            "                headers.pop(name)\n"
            "        headers['x-goog-api-key'] = "
            "os.environ.get('PDDL_BENCHMARK_API_KEY', '')\n"
            "        kwargs['headers'] = headers\n"
            "    return _pddl_original_request(self, method, url, **kwargs)\n"
            "requests.sessions.Session.request = _pddl_vertex_request\n"
        )

    def _write_filtered_schemas(self, config_dir: Path) -> None:
        for filename in ("tools_schema.json", "tools_schema_cn.json"):
            source = self.runtime_repo / "assets" / filename
            schema = json.loads(source.read_text())
            filtered = [
                entry
                for entry in schema
                if entry.get("function", {}).get("name") in FILTERED_GENERIC_TOOLS
            ]
            (config_dir / filename).write_text(
                json.dumps(filtered, indent=2, ensure_ascii=False) + "\n"
            )

    def tool_policy(self) -> dict:
        return {
            "allowed": sorted(FILTERED_GENERIC_TOOLS),
            "web": False,
            "plugins": False,
            "user_tools": False,
            "memory": "per-run-clean-copy",
            "state_dir": str(GENERIC_BENCHMARK_STATE_DIR),
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

        config_dir = state / "config"
        cmd = ["docker", "exec", "-w", CONTAINER_WORKSPACE]
        cmd.extend(
            self.docker_exec_env_args(
                {
                    "PYTHONPATH": f"{config_dir}:{self.runtime_repo}",
                    "GA_LANG": "en",
                    "HOME": "/tmp/genericagent-pddl-benchmark",
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
        deadline = started + self.timeout
        with capture_stdout.open("w") as stdout_fp, capture_stderr.open("w") as stderr_fp:
            proc = subprocess.Popen(cmd, stdout=stdout_fp, stderr=stderr_fp, text=True)
            try:
                while time.monotonic() < deadline:
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
            subprocess.run(
                [
                    "docker",
                    "exec",
                    container_name,
                    "chmod",
                    "-R",
                    "a+rwX",
                    str(self.runtime_repo / "temp"),
                    str(self.runtime_repo / "memory"),
                ],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not prepare GenericAgent state cleanup: %s", exc)

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> None:
        state = self._agent_states.get(agent_id)
        if not state:
            return
        source = state / "temp" / agent_id
        output = dest / "sessions" / "generic"
        output.mkdir(parents=True, exist_ok=True)
        for name in ("input.txt", "output.txt", "stdout.log", "stderr.log", "_history.json"):
            path = source / name
            if path.is_file():
                shutil.copy2(path, output / name)
        responses = state / "temp" / "model_responses"
        if responses.is_dir():
            shutil.copytree(responses, output / "model_responses", dirs_exist_ok=True)

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

    def delete_agent(self, agent_id: str) -> None:
        with self._state_lock:
            state = self._agent_states.pop(agent_id, None)
            if state is None:
                for instance_id, candidate in self._instance_states.items():
                    if agent_id.startswith(f"pddl-{instance_id}-"):
                        state = candidate
                        break
            if state:
                for key, value in list(self._instance_states.items()):
                    if value == state:
                        self._instance_states.pop(key, None)
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
        total["input"] += int(match.group(1))
        total["cacheRead"] += int(match.group(2))
    for match in OAI_OUTPUT_RE.finditer(text or ""):
        total["output"] += int(match.group(1))
    return total
