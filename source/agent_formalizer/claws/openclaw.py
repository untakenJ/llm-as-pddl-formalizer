"""OpenClaw CLI adapter for the agentic PDDL formalizer.

Wraps ``openclaw agent`` CLI calls with structured result handling, timeout
management, and per-problem agent isolation. Ported from ``claw-swe-bench``
(``claw_swebench/claws/openclaw.py``) and adapted for PDDL formalization: the
agent authors its PDDL files under ``CONTAINER_WORKSPACE`` instead of patching
``/testbed``, and ``iter_tool_calls`` exposes the session transcript so the
orchestrator can fold tool calls into the unified trace.

Isolation strategy: each problem gets a temporary OpenClaw agent
(via ``openclaw agents add`` / ``openclaw agents delete``), ensuring a fully
independent workspace, session store, and memory.

Container integration: the host's Node.js binary, the OpenClaw module
directory, and a **benchmark-isolated** OpenClaw state dir (not the
operator's ``~/.openclaw``) are bind-mounted into the container. The per-problem
workspace root (``/tmp/openclaw-pddl-workspaces``) is also mounted.
``openclaw agent --local`` runs *inside* the container so it can edit
``/workspace`` without contacting the host Gateway (which is loopback-only and
unreachable from Docker).
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterable

from agent_formalizer.config import (
    OPENCLAW_BENCHMARK_STATE_DIR,
    OPENCLAW_MODULE_DIR,
    OPENCLAW_NODE_BIN,
    PROVIDER_API_KEY_ENV,
    api_key_env_for_model,
    provider_for_model,
)
from agent_formalizer.claws.base import BaseClawAdapter
from agent_formalizer.result_types import AgentResult

logger = logging.getLogger(__name__)

# Extra buffer beyond the agent timeout for the subprocess (let OpenClaw handle
# its own timeout first; only kill the subprocess as a last resort).
SUBPROCESS_TIMEOUT_BUFFER = 60

# Base path for temporary agent workspaces on the host (bind-mounted into
# containers at the same path so OpenClaw sees the workspace created by
# ``openclaw agents add`` on the host).
TEMP_WORKSPACE_ROOT = Path("/tmp/openclaw-pddl-workspaces")

GOOGLE_VERTEX_PROVIDER = "google-vertex"
GOOGLE_VERTEX_API_KEY_FALLBACK_ENVS = ("GOOGLE_API_KEY",)
GOOGLE_VERTEX_CONTAINER_ENV = (
    "GOOGLE_CLOUD_PROJECT",
    "GCLOUD_PROJECT",
    "GOOGLE_CLOUD_PROJECT_ID",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_GENAI_USE_ENTERPRISE",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_API_KEY",
)


class OpenClawAdapter(BaseClawAdapter):
    """Drives the OpenClaw agent via CLI and returns structured results.

    Credentials are taken purely from the environment (populated from
    ``_private/.env``); the host's personal OpenClaw credential store is never
    read. Each model's API key comes from one environment variable, resolved via
    :func:`config.api_key_env_for_model` (per-model override, else provider
    default), and injected into the container under the provider's canonical env
    var name so OpenClaw's standard env-key resolution picks it up.
    """

    name = "openclaw"

    def __init__(
        self,
        model: str,
        timeout: int,
        max_turns: int | None = None,
        *,
        tools_profile: str = "coding",
        tools_allow: list[str] | None = None,
        tools_deny: list[str] | None = None,
        model_api_keys: dict[str, str] | None = None,
    ):
        # max_turns accepted for interface uniformity; OpenClaw has no
        # turn-limit flag (its own timeout bounds the run).
        super().__init__(model, timeout, max_turns)
        self.tools_profile = tools_profile
        self.tools_allow = tools_allow
        self.tools_deny = list(tools_deny or [])
        self.model_api_keys = dict(model_api_keys or {})
        self._config_lock = threading.Lock()
        self._ensure_benchmark_state()

    @property
    def _state_dir(self) -> Path:
        """Isolated OpenClaw state used for benchmark runs (not ~/.openclaw)."""
        return OPENCLAW_BENCHMARK_STATE_DIR

    # ------------------------------------------------------------------
    # Model authentication (env-only; no host credential store)
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        return provider_for_model(self.model)

    def api_key_env(self) -> str | None:
        """Env var configured to hold this model's API key."""
        return api_key_env_for_model(self.model, self.model_api_keys)

    def _canonical_provider_env(self) -> str | None:
        """Env var name OpenClaw recognizes for this model's provider."""
        return PROVIDER_API_KEY_ENV.get(self.provider) or self.api_key_env()

    def _resolved_api_key(self) -> str | None:
        env_var = self.api_key_env()
        if env_var:
            value = os.environ.get(env_var)
            if value:
                return value
        if self.provider == GOOGLE_VERTEX_PROVIDER:
            for fallback_env in GOOGLE_VERTEX_API_KEY_FALLBACK_ENVS:
                value = os.environ.get(fallback_env)
                if value:
                    return value
        return None

    def model_auth(self) -> dict:
        """Auth summary for trace/metadata (never includes the key value)."""
        env_var = self.api_key_env()
        return {
            "model": self.model,
            "provider": self.provider,
            "api_key_env": env_var,
            "api_key_present": bool(self._resolved_api_key()),
        }

    def tool_policy(self) -> dict:
        """Effective tool policy for this benchmark run (recorded in trace)."""
        policy = {
            "state_dir": str(self._state_dir),
            "profile": self.tools_profile,
        }
        if self.tools_allow:
            policy["allow"] = self.tools_allow
        if self.tools_deny:
            policy["deny"] = self.tools_deny
        return policy

    def _openclaw_env(self) -> dict[str, str]:
        """Environment for host-side ``openclaw`` subprocesses."""
        env = {
            **os.environ,
            "OPENCLAW_STATE_DIR": str(self._state_dir),
        }
        value = self._resolved_api_key()
        canonical = self._canonical_provider_env()
        if value and canonical:
            env[canonical] = value
        return env

    def _config_path(self) -> Path:
        return self._state_dir / "openclaw.json"

    def _ensure_benchmark_state(self) -> None:
        """Create the isolated state dir and pin benchmark tool policy."""
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._sync_benchmark_openclaw_json()

    def _sync_benchmark_openclaw_json(self) -> None:
        """Write benchmark-owned ``openclaw.json`` (tools/model/auth/plugins)."""
        config_path = self._config_path()
        data: dict = {}
        if config_path.is_file():
            try:
                data = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Resetting invalid benchmark openclaw.json")

        agents = data.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        defaults.setdefault("models", {})
        defaults["model"] = {"primary": self.model}
        agents.setdefault("list", [])

        tools = data.setdefault("tools", {})
        tools["profile"] = self.tools_profile
        if self.tools_allow:
            tools["allow"] = self.tools_allow
        else:
            tools.pop("allow", None)
        if self.tools_deny:
            tools["deny"] = self.tools_deny
        else:
            tools.pop("deny", None)

        # Do not inherit host plugins/skills that may register extra tools.
        data["plugins"] = {"entries": {}}

        # Auth is benchmark-owned and env-only: declare just the active model's
        # provider profile in ``api_key`` mode. The actual key is supplied to the
        # container via an environment variable (see container_run_args), and
        # OpenClaw resolves it through its standard env-key lookup. The host's
        # personal credential store is never read or copied.
        data["auth"] = {"profiles": self._auth_profiles()}

        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        logger.debug("Synced benchmark openclaw.json at %s", config_path)

    def _auth_profiles(self) -> dict:
        """Minimal ``api_key`` auth profile for the active model's provider."""
        provider = self.provider
        return {f"{provider}:api-key": {"provider": provider, "mode": "api_key"}}

    # ------------------------------------------------------------------
    # Container integration
    # ------------------------------------------------------------------

    def container_run_args(self, instance_id: str) -> list[str]:
        TEMP_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        args = [
            "-v", f"{OPENCLAW_NODE_BIN}:/usr/bin/node:ro",
            "-v", f"{OPENCLAW_MODULE_DIR}:/usr/lib/node_modules/openclaw:ro",
            "-v", f"{self._state_dir}:/root/.openclaw",
            # Per-problem agent workspaces live here on the host; the in-container
            # ``openclaw agent`` must see the same paths (otherwise WorkspaceVanishedError).
            "-v", f"{TEMP_WORKSPACE_ROOT}:{TEMP_WORKSPACE_ROOT}",
        ]
        exported_envs: set[str] = set()
        # Inject only the active model's API key, under the provider's canonical
        # env var name (so OpenClaw's standard env-key resolution finds it). The
        # source variable in _private/.env may be named anything (decoupled from
        # both the model id and OpenClaw's expected name).
        value = self._resolved_api_key()
        canonical = self._canonical_provider_env()
        if value and canonical:
            args.extend(["-e", f"{canonical}={value}"])
            exported_envs.add(canonical)
        else:
            logger.warning(
                "No API key for model %s (env var %s unset); OpenClaw auth will "
                "likely fail. Set it in _private/.env.",
                self.model, self.api_key_env(),
            )
        if self.provider == GOOGLE_VERTEX_PROVIDER:
            self._append_google_vertex_env(args, exported_envs)
        return args

    def _append_google_vertex_env(self, args: list[str], exported_envs: set[str]) -> None:
        """Pass Vertex project/location knobs through to the agent container."""
        for name in GOOGLE_VERTEX_CONTAINER_ENV:
            self._append_container_env(args, exported_envs, name)

        has_project = bool(
            os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        )
        if not has_project:
            logger.warning(
                "google-vertex requires GOOGLE_CLOUD_PROJECT or GCLOUD_PROJECT "
                "inside the container."
            )
        if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
            logger.warning(
                "google-vertex requires GOOGLE_CLOUD_LOCATION inside the container."
            )

    @staticmethod
    def _append_container_env(
        args: list[str], exported_envs: set[str], name: str, value: str | None = None
    ) -> None:
        if name in exported_envs:
            return
        resolved = os.environ.get(name) if value is None else value
        if not resolved:
            return
        args.extend(["-e", f"{name}={resolved}"])
        exported_envs.add(name)

    # ------------------------------------------------------------------
    # Agent lifecycle (isolation)
    # ------------------------------------------------------------------

    def create_agent(self, agent_id: str) -> None:
        """Create a temporary isolated OpenClaw agent.

        Each agent has its own workspace, session store, and memory.
        Thread-safe: openclaw.json writes are protected by _config_lock.
        """
        self._force_delete_agent(agent_id)

        workspace = TEMP_WORKSPACE_ROOT / agent_id
        workspace.mkdir(parents=True, exist_ok=True)

        with self._config_lock:
            self._sync_benchmark_openclaw_json()
            result = subprocess.run(
                [
                    "openclaw", "agents", "add", agent_id,
                    "--non-interactive",
                    "--workspace", str(workspace),
                    "--model", self.model,
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=self._openclaw_env(),
            )
            if result.returncode != 0 and "already exists" not in result.stderr:
                raise RuntimeError(
                    f"Failed to create agent {agent_id}: {result.stderr}"
                )

            self._set_agent_tools_policy(agent_id)

        logger.info("Created isolated agent: %s (workspace=%s)", agent_id, workspace)

    def delete_agent(self, agent_id: str) -> None:
        if not agent_id:
            return
        self._force_delete_agent(agent_id)

    def _force_delete_agent(self, agent_id: str) -> None:
        """Force delete an agent, its workspace, and state directories."""
        with self._config_lock:
            subprocess.run(
                ["openclaw", "agents", "delete", agent_id, "--force"],
                capture_output=True,
                text=True,
                timeout=30,
                env=self._openclaw_env(),
            )
        workspace = TEMP_WORKSPACE_ROOT / agent_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        agent_state = self._resolve_agent_state_dir(agent_id) or (
            self._state_dir / "agents" / agent_id
        )
        if agent_state.exists():
            shutil.rmtree(agent_state, ignore_errors=True)
        logger.debug("Force-deleted agent %s (workspace + state)", agent_id)

    def _set_agent_tools_policy(self, agent_id: str) -> None:
        """Pin per-agent tool policy in the benchmark ``openclaw.json``."""
        config_path = self._config_path()
        with open(config_path) as f:
            data = json.load(f)

        agent_tools: dict = {"profile": self.tools_profile}
        if self.tools_allow:
            agent_tools["allow"] = self.tools_allow
        if self.tools_deny:
            agent_tools["deny"] = self.tools_deny

        for agent in data.get("agents", {}).get("list", []):
            if agent.get("id") == agent_id:
                agent["tools"] = agent_tools
                break

        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug("Set agent tools policy for %s: %s", agent_id, agent_tools)

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        """Send a task to the specified agent running inside a container."""
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = artifact_dir / "agent_stdout.log" if artifact_dir else None
        stderr_path = artifact_dir / "agent_stderr.log" if artifact_dir else None

        cmd = [
            "docker", "exec", container_name,
            "node", "/usr/lib/node_modules/openclaw/openclaw.mjs",
            "agent",
            # Run embedded in the container. The host Gateway binds to loopback
            # (127.0.0.1) and is unreachable from inside Docker even via
            # host.docker.internal; --local resolves the model key from the
            # injected provider env var (see container_run_args) and uses the
            # bind-mounted benchmark state + workspace mount above.
            "--local",
            "--agent", agent_id,
            "--message", prompt,
            "--timeout", str(self.timeout),
            "--json",
        ]

        start_time = time.time()
        timed_out = False

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + SUBPROCESS_TIMEOUT_BUFFER,
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = -1
            stdout = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            logger.warning("OpenClaw subprocess timed out after %ds",
                           self.timeout + SUBPROCESS_TIMEOUT_BUFFER)

        duration = time.time() - start_time

        if stdout_path:
            stdout_path.write_text(stdout)
        if stderr_path:
            stderr_path.write_text(stderr)

        # Parse JSON output (may be in stdout or stderr depending on mode).
        # Gateway mode: {"status":"ok","result":{"payloads":[...],"meta":{...}}}
        # Embedded mode: {"payloads":[...],"meta":{...}}
        parsed = self._parse_output(stdout) or self._parse_output(stderr)

        if parsed and "result" in parsed:
            result_obj = parsed["result"]
            status = parsed.get("status", "ok")
        elif parsed and "payloads" in parsed:
            result_obj = parsed
            status = "ok"
        else:
            result_obj = {}
            status = "error" if parsed is None else parsed.get("status", "error")

        payloads = result_obj.get("payloads", [])
        agent_meta = result_obj.get("meta", {}).get("agentMeta", {})

        final_text = None
        if payloads:
            texts = [p.get("text") for p in payloads if isinstance(p, dict) and p.get("text")]
            if texts:
                final_text = "\n".join(texts)

        if timed_out:
            finish_reason = "timeout"
        elif parsed is None:
            finish_reason = "error"
        elif status != "ok":
            finish_reason = "error"
        elif not payloads or all(
            "couldn't generate" in (p.get("text") or "") for p in payloads
        ):
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
            session_id=agent_meta.get("sessionId"),
            session_file=_container_path_to_host(agent_meta.get("sessionFile")),
            openclaw_agent_id=_openclaw_agent_id_from_session_file(
                agent_meta.get("sessionFile")
            ),
            duration_seconds=round(duration, 1),
            usage=agent_meta.get("lastCallUsage", {}),
            final_text=final_text,
        )

    # ------------------------------------------------------------------
    # Session backup & step-by-step trace
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_agent_state_dir(
        agent_id: str,
        *,
        session_file: str | Path | None = None,
    ) -> Path | None:
        """Locate the OpenClaw agent state dir on the host.

        OpenClaw normalizes/truncates agent ids when registering agents, so the
        directory name under ``~/.openclaw/agents/`` often differs from the id
        we pass to ``openclaw agents add``.
        """
        if session_file:
            host = Path(_container_path_to_host(str(session_file)))
            if host.is_file():
                return host.parent.parent
            if host.parent.name == "sessions" and host.parent.parent.exists():
                return host.parent.parent

        agents_root = OPENCLAW_BENCHMARK_STATE_DIR / "agents"
        if not agents_root.is_dir():
            return None

        exact = agents_root / agent_id
        if exact.is_dir():
            return exact

        needle = agent_id.lower()
        matches = [
            d for d in agents_root.iterdir()
            if d.is_dir() and (
                d.name == needle
                or d.name.startswith(needle[:40])
                or needle.startswith(d.name)
            )
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            matches.sort(key=lambda p: len(p.name), reverse=True)
            return matches[0]
        return None

    def _sessions_dir(
        self,
        agent_id: str,
        *,
        session_file: str | Path | None = None,
    ) -> Path | None:
        state_dir = self._resolve_agent_state_dir(agent_id, session_file=session_file)
        if state_dir is None:
            return None
        return state_dir / "sessions"

    def _iter_session_files(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | Path | None = None,
    ) -> list[Path]:
        """Return session JSONL paths to parse (backed-up copy preferred)."""
        backed = artifact_dir / "sessions"
        if session_id:
            for base in (backed, self._sessions_dir(agent_id, session_file=session_file)):
                if base is None:
                    continue
                for name in (
                    f"{session_id}.jsonl",
                    f"{session_id}.trajectory.jsonl",
                ):
                    path = base / name
                    if path.is_file():
                        return [path]

        candidates: list[Path] = []
        for base in (backed, self._sessions_dir(agent_id, session_file=session_file)):
            if base is None or not base.is_dir():
                continue
            for path in sorted(base.glob("*.jsonl")):
                if path.name.endswith(".trajectory.jsonl"):
                    continue
                candidates.append(path)
        if candidates:
            return candidates

        if session_file:
            host = Path(_container_path_to_host(str(session_file)))
            if host.is_file():
                return [host]
        return []

    def _make_sessions_readable(
        self,
        container_name: str,
        sessions_dir: Path,
    ) -> None:
        """Widen permissions on session files created as root inside the container.

        OpenClaw writes ``*.trajectory.jsonl`` sidecars with mode ``600`` when
        ``openclaw agent --local`` runs in Docker as root. The bind-mounted
        benchmark state dir is then unreadable to the host user during backup.
        """
        container_path = _host_path_to_container(sessions_dir)
        if not container_path:
            return
        try:
            subprocess.run(
                [
                    "docker", "exec", container_name,
                    "bash", "-c",
                    f"chmod -R a+rX {shlex.quote(container_path)}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(
                "Could not chmod session dir in container %s: %s",
                container_name, e,
            )

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> None:
        """Copy session JSONL files from an agent into ``dest/sessions``."""
        sessions_dir = self._sessions_dir(agent_id, session_file=session_file)
        out = dest / "sessions"
        out.mkdir(parents=True, exist_ok=True)

        if container_name and sessions_dir and sessions_dir.is_dir():
            self._make_sessions_readable(container_name, sessions_dir)

        copied = 0
        if sessions_dir and sessions_dir.is_dir():
            for f in sessions_dir.glob("*.jsonl"):
                try:
                    shutil.copy2(f, out / f.name)
                    copied += 1
                except OSError as e:
                    logger.warning("Could not copy session file %s: %s", f, e)

        if session_file and copied == 0:
            host = Path(_container_path_to_host(session_file))
            if host.is_file():
                try:
                    shutil.copy2(host, out / host.name)
                except OSError as e:
                    logger.warning("Could not copy session file %s: %s", host, e)

    def iter_agent_steps(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        """Yield normalized per-step records from OpenClaw session JSONL."""
        for path in self._iter_session_files(
            agent_id, artifact_dir, session_id=session_id, session_file=session_file
        ):
            try:
                lines = path.read_text(errors="replace").splitlines()
            except OSError:
                continue
            step_idx = 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for rec in _session_entry_to_steps(entry, step_idx):
                    rec["session_file"] = path.name
                    step_idx += 1
                    yield rec

    def iter_tool_calls(
        self,
        agent_id: str,
        artifact_dir: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
    ) -> Iterable[dict]:
        """Yield tool-call records derived from :meth:`iter_agent_steps`."""
        index = 0
        for rec in self.iter_agent_steps(
            agent_id,
            artifact_dir,
            session_id=session_id,
            session_file=session_file,
        ):
            event = rec.get("event")
            if event == "tool_call":
                yield {
                    "index": index,
                    "kind": "call",
                    "name": rec.get("tool"),
                    "arguments": rec.get("arguments"),
                    "result": None,
                    "ok": None,
                    "session_file": rec.get("session_file"),
                    "step": rec.get("step"),
                }
                index += 1
            elif event == "tool_result":
                yield {
                    "index": index,
                    "kind": "result",
                    "name": rec.get("tool"),
                    "arguments": None,
                    "result": rec.get("output"),
                    "ok": rec.get("ok"),
                    "session_file": rec.get("session_file"),
                    "step": rec.get("step"),
                }
                index += 1

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_output(text: str) -> dict | None:
        """Try to parse JSON from ``openclaw agent --json`` output.

        Tool-failure log lines may precede the JSON and contain '{' themselves,
        and the agent JSON is pretty-printed across many lines — so scan every
        '{' and accept the first object that looks like agent output.
        """
        if not text:
            return None

        decoder = json.JSONDecoder()
        idx = text.find("{")
        while idx != -1:
            try:
                obj, _ = decoder.raw_decode(text[idx:])
                if isinstance(obj, dict) and (
                    "payloads" in obj or "result" in obj or "status" in obj
                ):
                    return obj
            except json.JSONDecodeError:
                pass
            idx = text.find("{", idx + 1)

        return None


def _container_path_to_host(path: str | None) -> str | None:
    """Map an OpenClaw path from inside the container to the host state dir."""
    if not path:
        return None
    for prefix in ("/root/.openclaw", "/home/node/.openclaw"):
        if path.startswith(prefix + "/") or path == prefix:
            rel = path[len(prefix) :].lstrip("/")
            return str(OPENCLAW_BENCHMARK_STATE_DIR / rel) if rel else str(OPENCLAW_BENCHMARK_STATE_DIR)
    return path


def _host_path_to_container(path: Path | str) -> str | None:
    """Map a host benchmark-state path to its in-container ``/root/.openclaw`` path."""
    host = Path(path)
    try:
        rel = host.resolve().relative_to(OPENCLAW_BENCHMARK_STATE_DIR.resolve())
    except ValueError:
        return None
    return f"/root/.openclaw/{rel.as_posix()}" if rel.parts else "/root/.openclaw"


def _openclaw_agent_id_from_session_file(session_file: str | None) -> str | None:
    if not session_file:
        return None
    host = Path(_container_path_to_host(session_file))
    parts = host.parts
    try:
        idx = parts.index("agents")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return None


def _truncate_text(value: str, max_len: int = 500) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[:max_len]}... ({len(value)} chars)"


def _sanitize_content_block(block: dict) -> dict:
    """Strip huge encrypted/signature blobs from session content blocks."""
    if not isinstance(block, dict):
        return block
    out: dict = {}
    for key, val in block.items():
        if key in ("thinkingSignature", "textSignature", "encrypted_content"):
            if isinstance(val, str) and len(val) > 120:
                out[key] = f"<truncated {len(val)} chars>"
            else:
                out[key] = val
        elif key == "openclawReasoningReplay":
            out[key] = "<omitted>"
        elif key == "thinking" and isinstance(val, str):
            out[key] = _truncate_text(val)
        else:
            out[key] = val
    return out


def _content_to_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    joined = "\n".join(parts).strip()
    return joined or None


def _session_entry_to_steps(entry: dict, step_idx: int) -> list[dict]:
    """Convert one OpenClaw session JSONL line into normalized step record(s)."""
    if not isinstance(entry, dict):
        return []

    etype = entry.get("type")
    ts = entry.get("timestamp")

    if etype == "session":
        return [{
            "step": step_idx,
            "event": "session_meta",
            "timestamp": ts,
            "session_id": entry.get("id"),
            "cwd": entry.get("cwd"),
        }]

    if etype == "model_change":
        return [{
            "step": step_idx,
            "event": "model_change",
            "timestamp": ts,
            "provider": entry.get("provider"),
            "model": entry.get("modelId"),
        }]

    if etype != "message":
        return []

    msg = entry.get("message") or {}
    role = msg.get("role")
    base = {
        "timestamp": ts or msg.get("timestamp"),
        "message_id": entry.get("id"),
        "parent_id": entry.get("parentId"),
    }

    if role == "user":
        content = msg.get("content")
        return [{
            **base,
            "step": step_idx,
            "event": "user_message",
            "role": "user",
            "content": _content_to_text(content),
            "raw_content": [
                _sanitize_content_block(b)
                for b in (content or [])
                if isinstance(b, dict)
            ],
        }]

    if role == "toolResult":
        content = msg.get("content")
        return [{
            **base,
            "step": step_idx,
            "event": "tool_result",
            "tool": msg.get("toolName"),
            "tool_call_id": msg.get("toolCallId"),
            "output": _content_to_text(content),
            "details": msg.get("details"),
            "ok": not msg.get("isError", False),
            "is_error": bool(msg.get("isError", False)),
        }]

    if role == "assistant":
        steps: list[dict] = []
        offset = 0
        for block in msg.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            sub = {**base, "step": step_idx + offset, "model": msg.get("model")}
            if btype == "thinking":
                steps.append({
                    **sub,
                    "event": "assistant_thinking",
                    "thinking": _truncate_text(block.get("thinking") or ""),
                })
            elif btype == "toolCall":
                steps.append({
                    **sub,
                    "event": "tool_call",
                    "tool": block.get("name"),
                    "tool_call_id": block.get("id"),
                    "arguments": block.get("arguments"),
                    "stop_reason": msg.get("stopReason"),
                })
            elif btype == "text":
                steps.append({
                    **sub,
                    "event": "assistant_message",
                    "content": block.get("text"),
                    "stop_reason": msg.get("stopReason"),
                    "usage": msg.get("usage"),
                })
            offset += 1
        if steps:
            return steps
        return [{
            **base,
            "step": step_idx,
            "event": "assistant_message",
            "content": _content_to_text(msg.get("content")),
            "usage": msg.get("usage"),
        }]

    return []
