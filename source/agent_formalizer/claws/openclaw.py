"""OpenClaw CLI adapter for the agentic PDDL formalizer.

Wraps ``openclaw agent`` CLI calls with structured result handling, timeout
management, and per-attempt agent isolation. Ported from ``claw-swe-bench``
(``claw_swebench/claws/openclaw.py``) and adapted for PDDL formalization: the
agent authors its PDDL files under ``CONTAINER_WORKSPACE`` instead of patching
``/testbed``, and ``iter_tool_calls`` exposes the session transcript so the
orchestrator can fold tool calls into the unified trace.

Isolation strategy: each execution attempt gets a temporary OpenClaw state
directory and workspace. Only those two attempt-owned directories are mounted
into its container. OpenClaw's recoverable ``agents delete`` operation may move
files to ``.Trash`` inside that state, after which the complete attempt root is
hard-deleted. No state directory is mounted into a later attempt.

Container integration: the host's Node.js binary, the OpenClaw module
directory, and a **benchmark-isolated** OpenClaw state dir (not the
operator's ``~/.openclaw``) are bind-mounted into the container. The current
attempt workspace is mounted both at its registered absolute path and at the
official ``/workspace`` path, so relative OpenClaw writes and official artifact
writes address the same files.
``openclaw agent --local`` runs *inside* the container so it can edit
``/workspace`` without contacting the host Gateway (which is loopback-only and
unreachable from Docker).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent_formalizer.config import (
    MODEL_GATEWAY_HOST,
    MODEL_GATEWAY_PORT,
    OPENCLAW_BENCHMARK_STATE_DIR,
    OPENCLAW_MODULE_DIR,
    OPENCLAW_NODE_BIN,
    PROVIDER_API_KEY_ENV,
    api_key_env_for_model,
    provider_for_model,
)
from agent_formalizer.claws.base import (
    BaseClawAdapter,
    run_process_with_attempt_clock,
)
from agent_formalizer.claws.common import provider_spec, google_vertex_settings, split_model_id
from agent_formalizer.result_types import AgentResult

logger = logging.getLogger(__name__)

# Extra buffer beyond the agent timeout for the subprocess (let OpenClaw handle
# its own timeout first; only kill the subprocess as a last resort).
AGENT_ADMIN_TIMEOUT = 120
AGENT_ADD_ATTEMPTS = 3

# Only fully isolated state is implemented. A future controlled-sharing study
# must add an explicit, profile-hashed policy rather than reusing Trash or other
# incidental harness state.
OPENCLAW_STATE_SHARING_MODE = "isolated"


@dataclass
class _OpenClawAttemptState:
    instance_id: str
    root: Path
    state_dir: Path
    workspace_dir: Path
    requested_agent_id: str | None = None
    registered_agent_id: str | None = None

GOOGLE_VERTEX_PROVIDER = "google-vertex"


class OpenClawAdapter(BaseClawAdapter):
    """Drives the OpenClaw agent via CLI and returns structured results.

    The host's personal OpenClaw config and credential store are never read.
    OpenClaw receives only a placeholder credential; the actual provider secret
    is held by the benchmark model-gateway sidecar.
    """

    name = "openclaw"

    def __init__(
        self,
        model: str,
        timeout: int,
        max_action_steps: int = 200,
        *,
        tools_profile: str = "coding",
        tools_allow: list[str] | None = None,
        tools_deny: list[str] | None = None,
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
        self.tools_profile = tools_profile
        self.tools_allow = tools_allow
        self.tools_deny = list(tools_deny or [])
        self.model_api_keys = dict(model_api_keys or {})
        self._api_key = api_key
        self._api_key_name = api_key_name
        self.credential_metadata = dict(credential_metadata or {})
        self.provider_options = dict(provider_options or {})
        self._config_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._attempt_states: dict[str, _OpenClawAttemptState] = {}
        self._agent_attempts: dict[str, str] = {}
        OPENCLAW_BENCHMARK_STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._run_state_dir = (
            OPENCLAW_BENCHMARK_STATE_DIR
            / f"run-{os.getpid()}-{uuid.uuid4().hex[:12]}"
        )
        self._run_state_dir.mkdir(mode=0o700)
        self._control_state_dir = self._run_state_dir / "control"
        self._attempts_root = self._run_state_dir / "attempts"
        self._attempts_root.mkdir(mode=0o700)
        atexit.register(self._cleanup_run_state)
        self._ensure_benchmark_state(self._control_state_dir)

    @property
    def _state_dir(self) -> Path:
        """Adapter-control state, never mounted into an attempt container."""
        return self._control_state_dir

    def _cleanup_run_state(self) -> None:
        with self._state_lock:
            self._attempt_states.clear()
            self._agent_attempts.clear()
        try:
            shutil.rmtree(self._run_state_dir)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning(
                "Could not remove OpenClaw benchmark run state %s: %s",
                self._run_state_dir,
                exc,
            )

    def _prepare_attempt_state(self, instance_id: str) -> _OpenClawAttemptState:
        """Create or return the state mounted exclusively into one attempt."""
        with self._state_lock:
            existing = self._attempt_states.get(instance_id)
            if existing is not None:
                return existing
            digest = hashlib.sha256(instance_id.encode()).hexdigest()[:20]
            root = self._attempts_root / f"attempt-{digest}-{uuid.uuid4().hex[:8]}"
            root.mkdir(mode=0o700)
            state_dir = root / "state"
            workspace_dir = root / "workspace"
            state_dir.mkdir(mode=0o700)
            workspace_dir.mkdir(mode=0o700)
            attempt = _OpenClawAttemptState(
                instance_id=instance_id,
                root=root,
                state_dir=state_dir,
                workspace_dir=workspace_dir,
            )
            self._attempt_states[instance_id] = attempt
        try:
            self._ensure_benchmark_state(state_dir)
        except Exception:
            with self._state_lock:
                self._attempt_states.pop(instance_id, None)
            shutil.rmtree(root, ignore_errors=True)
            raise
        return attempt

    def _attempt_for_instance(self, instance_id: str) -> _OpenClawAttemptState:
        with self._state_lock:
            attempt = self._attempt_states.get(instance_id)
        if attempt is None:
            raise RuntimeError(f"OpenClaw attempt state is not prepared: {instance_id}")
        return attempt

    def _attempt_for_agent(self, agent_id: str) -> _OpenClawAttemptState:
        with self._state_lock:
            instance_id = self._agent_attempts.get(agent_id)
            attempt = self._attempt_states.get(instance_id) if instance_id else None
        if attempt is None:
            raise RuntimeError(f"OpenClaw agent has no isolated attempt state: {agent_id}")
        return attempt

    # ------------------------------------------------------------------
    # Model authentication (env-only; no host credential store)
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        return provider_for_model(self.model)

    def api_key_env(self) -> str | None:
        """Env var configured to hold this model's API key."""
        return self._api_key_name or api_key_env_for_model(self.model, self.model_api_keys)

    def _canonical_provider_env(self) -> str | None:
        """Env var name OpenClaw recognizes for this model's provider."""
        return PROVIDER_API_KEY_ENV.get(self.provider) or self.api_key_env()

    def _resolved_api_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        env_var = self.api_key_env()
        return os.environ.get(env_var) if env_var else None

    def model_auth(self) -> dict:
        """Auth summary for trace/metadata (never includes the key value)."""
        env_var = self.api_key_env()
        value = {
            "model": self.model,
            "provider": self.provider,
            "api_base": f"http://{MODEL_GATEWAY_HOST}:{MODEL_GATEWAY_PORT}",
            "upstream_api_base": self.upstream_api_base(),
            "api_key_env": env_var,
            "api_key_present": bool(self._resolved_api_key()),
        }
        if self.credential_metadata:
            value["credential"] = dict(self.credential_metadata)
        return value

    def validate_runtime(self) -> None:
        if not Path(OPENCLAW_NODE_BIN).is_file():
            raise RuntimeError(f"OpenClaw Node.js binary not found: {OPENCLAW_NODE_BIN}")
        if not Path(OPENCLAW_MODULE_DIR).is_dir():
            raise RuntimeError(f"OpenClaw module directory not found: {OPENCLAW_MODULE_DIR}")
        if not self._resolved_api_key():
            raise RuntimeError(
                f"No API key for {self.model}. Pass it explicitly or set only "
                f"{self.api_key_env()} for the benchmark runner."
            )
        if self.provider == GOOGLE_VERTEX_PROVIDER:
            google_vertex_settings(self.provider_options)

    def tool_policy(self) -> dict:
        """Effective tool policy for this benchmark run (recorded in trace)."""
        policy = {
            "state_dir": "<benchmark-attempt-isolated-state>",
            "state_scope": "per_attempt",
            "cross_attempt_reuse": False,
            "state_sharing_mode": OPENCLAW_STATE_SHARING_MODE,
            "profile": self.tools_profile,
        }
        if self.tools_allow:
            policy["allow"] = self.tools_allow
        if self.tools_deny:
            policy["deny"] = self.tools_deny
        policy["skills"] = self.skills_mode
        return policy

    def effective_config(self) -> dict:
        value = super().effective_config()
        config_path = self._config_path()
        config = json.loads(config_path.read_text()) if config_path.is_file() else {}
        # Agent registrations are ephemeral run state, not configuration.
        if isinstance(config.get("agents"), dict):
            config["agents"] = {**config["agents"], "list": []}
        value["harness_config"] = config
        return value

    def runtime_info(self) -> dict:
        from agent_formalizer.provenance import run_text

        return {
            **super().runtime_info(),
            "node_binary": str(OPENCLAW_NODE_BIN),
            "node_version": run_text([str(OPENCLAW_NODE_BIN), "--version"]),
            "module_dir": str(OPENCLAW_MODULE_DIR),
            "openclaw_version": run_text(
                [
                    str(OPENCLAW_NODE_BIN),
                    str(Path(OPENCLAW_MODULE_DIR) / "openclaw.mjs"),
                    "--version",
                ]
            ),
        }

    def skills_info(self) -> dict:
        from agent_formalizer.provenance import file_manifest

        root = Path(OPENCLAW_MODULE_DIR)
        paths = [
            path for path in (root / "skills").glob("**/*")
            if "__pycache__" not in path.parts and path.suffix != ".pyc"
        ]
        return {
            "mode": self.skills_mode,
            "baseline": "pinned-host-install-bundled-skills-only",
            "personal_and_extra_dirs": [],
            "manifest": file_manifest(paths, root=root),
        }

    def upstream_api_base(self) -> str:
        if self.provider == GOOGLE_VERTEX_PROVIDER:
            options = self.provider_options.get("google_vertex", {})
            location = options.get("location") or "global"
            return options.get("origin") or (
                "https://aiplatform.googleapis.com"
                if location == "global"
                else f"https://{location}-aiplatform.googleapis.com"
            )
        return provider_spec(self.model).api_base

    def model_gateway(self) -> dict:
        value = super().model_gateway()
        value["auth_mode"] = provider_spec(self.model).gateway_auth_mode
        _, runtime_model = split_model_id(self.model)
        value["allowed_models"] = sorted({self.model, runtime_model})
        return value

    def model_gateway_secret(self) -> str | None:
        return self._resolved_api_key()

    def _openclaw_env(self, state_dir: Path | None = None) -> dict[str, str]:
        """Hermetic environment for host-side ``openclaw`` subprocesses.

        Keep ordinary process settings such as ``PATH`` and the selected model
        credential, but discard operator-provided OpenClaw knobs.  In
        particular, an ambient profile/config path must not redirect benchmark
        administration commands back to a personal state directory.
        """
        resolved_state = state_dir or self._state_dir
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(resolved_state),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "NO_COLOR": "1",
            "OPENCLAW_STATE_DIR": str(resolved_state),
            "OPENCLAW_CONFIG_PATH": str(self._config_path(resolved_state)),
            "OPENCLAW_NO_AUTO_UPDATE": "1",
        }
        value = "benchmark-gateway-placeholder"
        canonical = self._canonical_provider_env()
        if canonical:
            env[canonical] = value
        return env

    @staticmethod
    def _openclaw_command(*args: str) -> list[str]:
        return [
            str(OPENCLAW_NODE_BIN),
            str(Path(OPENCLAW_MODULE_DIR) / "openclaw.mjs"),
            *args,
        ]

    def _config_path(self, state_dir: Path | None = None) -> Path:
        return (state_dir or self._state_dir) / "openclaw.json"

    def _ensure_benchmark_state(self, state_dir: Path | None = None) -> None:
        """Create the isolated state dir and pin benchmark tool policy."""
        resolved_state = state_dir or self._state_dir
        resolved_state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._sync_benchmark_openclaw_json(resolved_state)

    def _sync_benchmark_openclaw_json(
        self, state_dir: Path | None = None
    ) -> None:
        """Write benchmark-owned ``openclaw.json`` (tools/model/auth/plugins)."""
        resolved_state = state_dir or self._state_dir
        config_path = self._config_path(resolved_state)

        # Every attempt starts from an empty registration list. Controlled
        # cross-attempt state sharing is deliberately not implemented here.
        data: dict = {
            "agents": {"defaults": {}, "list": []},
            "models": {
                "mode": "merge",
                "providers": {self.provider: self._gateway_provider_config()},
            },
            "skills": {
                "load": {"extraDirs": [], "watch": False},
            },
        }

        agents = data["agents"]
        defaults = agents["defaults"]
        defaults.setdefault("models", {})
        defaults["model"] = {"primary": self.model}
        if self.skills_mode != "official":
            defaults["skills"] = []

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

    def _gateway_provider_config(self) -> dict:
        from urllib.parse import urlsplit

        api_by_provider = {
            "openai": "openai-responses",
            "anthropic": "anthropic-messages",
            "openrouter": "openai-completions",
            "deepseek": "openai-completions",
            "dashscope": "openai-completions",
            "qwen": "openai-completions",
            "google": "google-generative-ai",
            "gemini": "google-generative-ai",
            "google-vertex": "google-vertex",
        }
        _, runtime_model = split_model_id(self.model)
        upstream_path = urlsplit(self.upstream_api_base()).path.rstrip("/")
        gateway_base = f"http://{MODEL_GATEWAY_HOST}:{MODEL_GATEWAY_PORT}"
        if self.provider != GOOGLE_VERTEX_PROVIDER:
            gateway_base += upstream_path
        return {
            "baseUrl": gateway_base,
            "api": api_by_provider.get(self.provider, "openai-completions"),
            "request": {"allowPrivateNetwork": True},
            "models": [
                {
                    "id": runtime_model,
                    "name": runtime_model,
                    "reasoning": True,
                    "input": ["text"],
                    "contextWindow": 1048576,
                    "maxTokens": 65536,
                }
            ],
        }

    def _auth_profiles(self) -> dict:
        """Minimal ``api_key`` auth profile for the active model's provider."""
        provider = self.provider
        return {f"{provider}:api-key": {"provider": provider, "mode": "api_key"}}

    # ------------------------------------------------------------------
    # Container integration
    # ------------------------------------------------------------------

    def container_run_args(self, instance_id: str) -> list[str]:
        attempt = self._prepare_attempt_state(instance_id)
        args = [
            "-v", f"{OPENCLAW_NODE_BIN}:/usr/bin/node:ro",
            "-v", f"{OPENCLAW_MODULE_DIR}:/usr/lib/node_modules/openclaw:ro",
            "-v", f"{attempt.state_dir}:/root/.openclaw:rw",
            "-e", "OPENCLAW_STATE_DIR=/root/.openclaw",
            "-e", "OPENCLAW_CONFIG_PATH=/root/.openclaw/openclaw.json",
            "-e", "OPENCLAW_NO_AUTO_UPDATE=1",
            # OpenClaw stores the host absolute workspace path in openclaw.json,
            # so make precisely this attempt's path available at the same path.
            # Mount the same directory at /workspace to make the prompt, relative
            # tool writes, and official artifact contract describe one workspace.
            "-v", f"{attempt.workspace_dir}:{attempt.workspace_dir}:rw",
            "-v", f"{attempt.workspace_dir}:/workspace:rw",
        ]
        exported_envs: set[str] = set()
        # OpenClaw sees only a syntactically valid placeholder. Authentication
        # is replaced by the sidecar when it forwards the request.
        value = "benchmark-gateway-placeholder"
        canonical = self._canonical_provider_env()
        if canonical:
            args.extend(["-e", f"{canonical}={value}"])
            exported_envs.add(canonical)
        if self.provider == GOOGLE_VERTEX_PROVIDER:
            self._append_google_vertex_env(args, exported_envs)
        return args

    def state_isolation_spec(self, instance_id: str) -> dict:
        spec = super().state_isolation_spec(instance_id)
        attempt = self._attempt_for_instance(instance_id)
        with self._state_lock:
            other_roots = {
                item.root for key, item in self._attempt_states.items()
                if key != instance_id
            }
        spec.update(
            {
                "attempt_root": str(attempt.root),
                "writable_bind_sources": [
                    str(attempt.state_dir),
                    str(attempt.workspace_dir),
                ],
                "shared_readonly_bind_sources": [
                    str(OPENCLAW_NODE_BIN),
                    str(OPENCLAW_MODULE_DIR),
                ],
                "tests": {
                    "attempt_root_exists": attempt.root.is_dir(),
                    "attempt_root_not_shared": attempt.root not in other_roots,
                    "attempt_root_under_run_attempts": (
                        attempt.root.resolve().parent
                        == self._attempts_root.resolve()
                    ),
                    "control_state_outside_attempt": (
                        self._control_state_dir.resolve()
                        != attempt.state_dir.resolve()
                    ),
                    "fresh_state_has_no_trash": not (
                        attempt.state_dir / ".Trash"
                    ).exists(),
                    "workspace_is_attempt_private": attempt.workspace_dir.is_dir(),
                },
            }
        )
        return spec

    def _append_google_vertex_env(self, args: list[str], exported_envs: set[str]) -> None:
        """Pass only non-secret, resolved Vertex routing values."""
        project, location, _ = google_vertex_settings(self.provider_options)
        for name, value in (
            ("GOOGLE_CLOUD_PROJECT", project),
            ("GOOGLE_CLOUD_LOCATION", location),
            ("GOOGLE_GENAI_USE_VERTEXAI", "true"),
        ):
            self._append_container_env(args, exported_envs, name, value)

    @staticmethod
    def _append_container_env(
        args: list[str], exported_envs: set[str], name: str, value: str | None = None
    ) -> None:
        if name in exported_envs:
            return
        resolved = value
        if not resolved:
            return
        args.extend(["-e", f"{name}={resolved}"])
        exported_envs.add(name)

    # ------------------------------------------------------------------
    # Agent lifecycle (isolation)
    # ------------------------------------------------------------------

    def create_agent(
        self, agent_id: str, *, instance_id: str | None = None
    ) -> None:
        """Create an agent inside a fresh, attempt-owned state directory."""
        if instance_id is None:
            raise ValueError("OpenClaw requires an instance_id for state isolation")
        attempt_state = self._attempt_for_instance(instance_id)
        attempt_state.requested_agent_id = agent_id

        with self._config_lock:
            # Reset only this fresh attempt's config. No registration or state is
            # copied from the adapter control state or another attempt.
            self._sync_benchmark_openclaw_json(attempt_state.state_dir)
            command = self._openclaw_command(
                "agents", "add", agent_id,
                "--non-interactive",
                "--workspace", str(attempt_state.workspace_dir),
                "--model", self.model,
                "--json",
            )
            last_error = ""
            for add_attempt in range(1, AGENT_ADD_ATTEMPTS + 1):
                if self.deadline_exceeded():
                    raise TimeoutError("OpenClaw startup reached benchmark deadline")
                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=min(AGENT_ADMIN_TIMEOUT, self.remaining_timeout()),
                        env=self._openclaw_env(attempt_state.state_dir),
                    )
                except subprocess.TimeoutExpired:
                    last_error = (
                        f"timed out after {AGENT_ADMIN_TIMEOUT}s "
                        f"(attempt {add_attempt}/{AGENT_ADD_ATTEMPTS})"
                    )
                else:
                    registered = self._registered_agent_for_workspace(attempt_state)
                    if registered is not None:
                        break
                    last_error = (
                        f"returncode={result.returncode}: "
                        f"{result.stderr.strip() or result.stdout.strip() or 'no registration'}"
                    )
                if add_attempt < AGENT_ADD_ATTEMPTS and not self.deadline_exceeded():
                    time.sleep(add_attempt)
            else:
                raise RuntimeError(f"Failed to create agent {agent_id}: {last_error}")

            registered = self._registered_agent_for_workspace(attempt_state)
            if registered is None:
                raise RuntimeError(
                    "OpenClaw created no registration for the isolated workspace "
                    f"{attempt_state.workspace_dir}"
                )
            attempt_state.registered_agent_id = registered
            with self._state_lock:
                self._agent_attempts[agent_id] = instance_id
                self._agent_attempts[registered] = instance_id
            self._set_agent_tools_policy(attempt_state, registered)

        logger.info(
            "Created isolated agent: requested=%s registered=%s state=%s workspace=%s",
            agent_id,
            registered,
            attempt_state.state_dir,
            attempt_state.workspace_dir,
        )

    def delete_agent(
        self, agent_id: str, *, instance_id: str | None = None
    ) -> None:
        """Delete all state for one attempt, including OpenClaw Trash."""
        attempt_state = None
        if instance_id is not None:
            with self._state_lock:
                attempt_state = self._attempt_states.get(instance_id)
        if attempt_state is None and agent_id:
            try:
                attempt_state = self._attempt_for_agent(agent_id)
            except RuntimeError:
                return
        if attempt_state is None:
            return

        registered = attempt_state.registered_agent_id
        if registered:
            try:
                result = subprocess.run(
                    self._openclaw_command(
                        "agents", "delete", registered, "--force"
                    ),
                    capture_output=True,
                    text=True,
                    timeout=AGENT_ADMIN_TIMEOUT,
                    env=self._openclaw_env(attempt_state.state_dir),
                )
                if result.returncode != 0:
                    logger.warning(
                        "OpenClaw native delete failed for %s; hard-deleting its "
                        "attempt root: %s",
                        registered,
                        result.stderr.strip() or result.stdout.strip(),
                    )
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Timed out natively deleting OpenClaw agent %s; hard-deleting "
                    "its attempt root",
                    registered,
                )

        self._hard_delete_attempt(attempt_state)
        with self._state_lock:
            self._attempt_states.pop(attempt_state.instance_id, None)
            for key, value in list(self._agent_attempts.items()):
                if value == attempt_state.instance_id:
                    self._agent_attempts.pop(key, None)
        logger.debug("Hard-deleted isolated OpenClaw attempt %s", attempt_state.instance_id)

    def prepare_agent_cleanup(
        self,
        agent_id: str,
        *,
        instance_id: str | None = None,
        container_name: str | None = None,
    ) -> None:
        """Restore host teardown access only for this attempt's two mounts."""
        if not container_name:
            return
        attempt_state = None
        if instance_id is not None:
            with self._state_lock:
                attempt_state = self._attempt_states.get(instance_id)
        if attempt_state is None:
            try:
                attempt_state = self._attempt_for_agent(agent_id)
            except RuntimeError:
                return
        try:
            result = self._run_container_cleanup_command(
                container_name,
                ["chmod", "-R", "a+rwX", "/root/.openclaw", "/workspace"],
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "Could not prepare isolated OpenClaw state cleanup for %s: %s",
                attempt_state.instance_id,
                exc,
            )
            return
        if result.returncode != 0:
            logger.warning(
                "Could not prepare isolated OpenClaw state cleanup for %s: %s",
                attempt_state.instance_id,
                (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
            )

    def _hard_delete_attempt(self, attempt_state: _OpenClawAttemptState) -> None:
        root = attempt_state.root
        attempts_root = self._attempts_root.resolve()
        if root.is_symlink() or root.resolve().parent != attempts_root:
            raise RuntimeError(f"Refusing to delete unexpected OpenClaw state path: {root}")
        try:
            shutil.rmtree(root)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError(
                f"Could not remove isolated OpenClaw attempt state {root}: {exc}"
            ) from exc
        if root.exists():
            raise RuntimeError(f"OpenClaw attempt state still exists after cleanup: {root}")

    def _registered_agent_for_workspace(
        self, attempt_state: _OpenClawAttemptState
    ) -> str | None:
        config_path = self._config_path(attempt_state.state_dir)
        if not config_path.is_file():
            return None
        try:
            data = json.loads(config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        workspace = attempt_state.workspace_dir.resolve()
        matches = []
        for entry in data.get("agents", {}).get("list", []):
            configured = entry.get("workspace")
            if not isinstance(configured, str):
                continue
            try:
                same_workspace = Path(configured).resolve() == workspace
            except OSError:
                same_workspace = False
            if same_workspace and isinstance(entry.get("id"), str):
                matches.append(entry["id"])
        if len(matches) > 1:
            raise RuntimeError(
                f"Multiple OpenClaw registrations share isolated workspace {workspace}"
            )
        return matches[0] if matches else None

    def _set_agent_tools_policy(
        self, attempt_state: _OpenClawAttemptState, agent_id: str
    ) -> None:
        """Pin per-agent tool policy in the benchmark ``openclaw.json``."""
        config_path = self._config_path(attempt_state.state_dir)
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
        else:
            raise RuntimeError(f"OpenClaw registration disappeared: {agent_id}")

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
        attempt_state = self._attempt_for_agent(agent_id)
        registered_agent_id = attempt_state.registered_agent_id
        if not registered_agent_id:
            raise RuntimeError(f"OpenClaw agent is not registered: {agent_id}")
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
            "--agent", registered_agent_id,
            "--message", prompt,
            "--timeout", str(self.timeout),
            "--json",
        ]

        start_time = time.time()
        timed_out = False

        try:
            clock = self.current_attempt_clock()
            result = (
                run_process_with_attempt_clock(
                    cmd,
                    clock=clock,
                    capture_output=True,
                    text=True,
                )
                if clock is not None
                else subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.remaining_timeout(),
                )
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            subprocess.run(
                ["docker", "kill", container_name], capture_output=True, timeout=30
            )
            exit_code = -1
            stdout = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            logger.warning("OpenClaw subprocess reached the %.3fs deadline", self.timeout)

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
            session_file=_container_path_to_host(
                agent_meta.get("sessionFile"), attempt_state.state_dir
            ),
            openclaw_agent_id=(
                _openclaw_agent_id_from_session_file(
                    agent_meta.get("sessionFile"), attempt_state.state_dir
                )
                or registered_agent_id
            ),
            duration_seconds=round(duration, 1),
            usage=_normalize_openclaw_usage(agent_meta),
            final_text=final_text,
        )

    # ------------------------------------------------------------------
    # Session backup & step-by-step trace
    # ------------------------------------------------------------------

    def _resolve_agent_state_dir(
        self,
        agent_id: str,
        *,
        session_file: str | Path | None = None,
    ) -> Path | None:
        """Locate this agent's exact state dir within its own attempt root."""
        try:
            attempt_state = self._attempt_for_agent(agent_id)
        except RuntimeError:
            return None
        registered_agent_id = attempt_state.registered_agent_id
        if not registered_agent_id:
            return None
        exact = attempt_state.state_dir / "agents" / registered_agent_id

        if session_file:
            host = self._isolated_session_path(attempt_state, session_file)
            if host is None or host.parent.name != "sessions":
                return None
            if host.parent.parent.resolve() != exact.resolve():
                return None
        return exact if exact.is_dir() else None

    @staticmethod
    def _isolated_session_path(
        attempt_state: _OpenClawAttemptState,
        session_file: str | Path,
    ) -> Path | None:
        """Map a session path only when it remains inside this attempt state."""
        mapped = Path(
            _container_path_to_host(str(session_file), attempt_state.state_dir)
        )
        try:
            mapped.resolve().relative_to(attempt_state.state_dir.resolve())
        except (OSError, ValueError):
            return None
        return mapped

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
            try:
                attempt_state = self._attempt_for_agent(agent_id)
            except RuntimeError:
                return []
            host = self._isolated_session_path(attempt_state, session_file)
            if host is not None and host.is_file():
                return [host]
        return []

    def _make_sessions_readable(
        self,
        agent_id: str,
        container_name: str,
        sessions_dir: Path,
    ) -> None:
        """Make benchmark-owned state readable and removable by the host user.

        OpenClaw writes ``*.trajectory.jsonl`` sidecars with mode ``600`` when
        ``openclaw agent --local`` runs in Docker as root. The bind-mounted
        benchmark state dir can otherwise be unreadable or impossible to clean
        up from the unprivileged host process after backup.
        """
        try:
            attempt_state = self._attempt_for_agent(agent_id)
        except RuntimeError:
            return
        container_sessions = _host_path_to_container(
            sessions_dir, attempt_state.state_dir
        )
        if container_sessions is None:
            return
        try:
            result = self._run_container_cleanup_command(
                container_name,
                ["chmod", "-R", "a+rwX", container_sessions],
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(
                "Could not chmod session dir in container %s: %s",
                container_name, e,
            )
            return
        if result.returncode != 0:
            logger.debug(
                "Could not chmod session dir in container %s: %s",
                container_name,
                (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
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
            self._make_sessions_readable(agent_id, container_name, sessions_dir)

        copied = 0
        if sessions_dir and sessions_dir.is_dir():
            for f in sessions_dir.glob("*.jsonl"):
                try:
                    shutil.copy2(f, out / f.name)
                    copied += 1
                except OSError as e:
                    logger.warning("Could not copy session file %s: %s", f, e)

        if session_file and copied == 0:
            try:
                attempt_state = self._attempt_for_agent(agent_id)
            except RuntimeError:
                return
            host = self._isolated_session_path(attempt_state, session_file)
            if host is not None and host.is_file():
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


def _container_path_to_host(path: str | None, state_dir: Path) -> str | None:
    """Map an OpenClaw path from inside the container to the host state dir."""
    if not path:
        return None
    for prefix in ("/root/.openclaw", "/home/node/.openclaw"):
        if path.startswith(prefix + "/") or path == prefix:
            rel = path[len(prefix) :].lstrip("/")
            return str(state_dir / rel) if rel else str(state_dir)
    return path


def _host_path_to_container(path: Path | str, state_dir: Path) -> str | None:
    """Map a host benchmark-state path to its in-container ``/root/.openclaw`` path."""
    host = Path(path)
    try:
        rel = host.resolve().relative_to(state_dir.resolve())
    except ValueError:
        return None
    return f"/root/.openclaw/{rel.as_posix()}" if rel.parts else "/root/.openclaw"


def _openclaw_agent_id_from_session_file(
    session_file: str | None, state_dir: Path
) -> str | None:
    if not session_file:
        return None
    host = Path(_container_path_to_host(session_file, state_dir))
    parts = host.parts
    try:
        idx = parts.index("agents")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return None


def _normalize_openclaw_usage(agent_meta: object) -> dict:
    """Return aggregate run usage rather than OpenClaw's last-call snapshot.

    OpenClaw exposes both ``agentMeta.usage`` (aggregate) and
    ``agentMeta.lastCallUsage``.  Its aggregate ``total`` field may retain the
    last call's total, so recompute it from the disjoint token buckets.
    """
    if not isinstance(agent_meta, dict):
        return {}
    aggregate = agent_meta.get("usage")
    if not isinstance(aggregate, dict) or not any(
        aggregate.get(key) for key in ("input", "output", "cacheRead", "cacheWrite")
    ):
        aggregate = agent_meta.get("lastCallUsage")
    if not isinstance(aggregate, dict):
        return {}

    def token(name: str) -> int:
        try:
            return max(0, int(aggregate.get(name, 0) or 0))
        except (TypeError, ValueError):
            return 0

    usage = {
        "input": token("input"),
        "output": token("output"),
        "cacheRead": token("cacheRead"),
        "cacheWrite": token("cacheWrite"),
    }
    if not any(usage.values()):
        return {}
    usage["total"] = sum(usage.values())
    return usage


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
