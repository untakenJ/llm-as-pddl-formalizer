"""Host-only execution services for the benchmark-owned minimum agent.

Unlike the native third-party harnesses, the minimum agent has no shell, file,
tool, memory, or plugin surface to sandbox.  It runs as a repository-owned
standard-library subprocess and can reach only per-attempt loopback services:
the fixed-route model gateway and, when configured, the fixed solver gateway.
"""

from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from agent_formalizer.config import MODEL_GATEWAY_SCRIPT
from agent_formalizer.tools.solver import (
    GATEWAY_ENTRYPOINT as SOLVER_GATEWAY_ENTRYPOINT,
    SOLVER_DIR,
)


logger = logging.getLogger(__name__)


def _loopback_port() -> int:
    """Reserve an available loopback port for immediate subprocess startup."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str, *, timeout: float = 5) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object from {url}")
    return value


class MinimumHostWorkspace:
    """Per-attempt host runtime with auditable loopback-only service routes."""

    image_name: str | None = None

    def __init__(
        self,
        instance_id: str,
        runtime_name: str,
        adapter,
        *,
        artifact_dir: Path,
    ):
        self.instance_id = instance_id
        self.container_name = runtime_name  # logical name retained in shared evidence APIs
        self.adapter = adapter
        self.artifact_dir = Path(artifact_dir)
        self.workspace_dir = self.artifact_dir / "minimum_agent_workspace"
        self.model_gateway_port = _loopback_port()
        self.solver_gateway_port: int | None = None
        self.model_gateway_origin = f"http://127.0.0.1:{self.model_gateway_port}"
        self.solver_gateway_origin: str | None = None
        self._processes: list[subprocess.Popen] = []
        self._log_streams: list = []
        self._gateway_process: subprocess.Popen | None = None
        self._solver_process: subprocess.Popen | None = None
        self._secret_dir: Path | None = None
        self._control_dir: Path | None = None
        self._control_path: Path | None = None
        self._gateway_monitor_stop: threading.Event | None = None
        self._gateway_monitor_thread: threading.Thread | None = None
        self._gateway_terminal_error: dict | None = None
        self._gateway_monitor_error: str | None = None
        self._gateway_action_step_limit_reached = False
        self._deadline_enforced = False

    @property
    def runtime_api_base(self) -> str:
        path = urlsplit(self.adapter.direct_api_base).path.rstrip("/")
        return self.model_gateway_origin + path

    def _fixed_environment(self) -> dict[str, str]:
        return dict(
            self.adapter.resolved_config.raw["resolved"]["environment"]["fixed"]
        )

    def _stage_secret(self, secret: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="pddl-minimum-gateway-secret-"))
        directory.chmod(0o700)
        path = directory / "api-key"
        path.write_text(secret, encoding="utf-8")
        path.chmod(0o600)
        self._secret_dir = directory
        return path

    def _stage_control(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="pddl-minimum-gateway-control-"))
        directory.chmod(0o700)
        self._control_dir = directory
        self._control_path = directory / "state.json"
        return self._control_path

    def _spawn(
        self,
        argv: list[str],
        *,
        env: dict[str, str],
        log_stem: str,
    ) -> subprocess.Popen:
        stdout = (self.artifact_dir / f"{log_stem}.stdout.log").open(
            "ab", buffering=0
        )
        stderr = (self.artifact_dir / f"{log_stem}.stderr.log").open(
            "ab", buffering=0
        )
        self._log_streams.extend([stdout, stderr])
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env)
        self._processes.append(process)
        return process

    @staticmethod
    def _wait_healthy(process: subprocess.Popen, url: str, label: str) -> None:
        last_error = "not ready"
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(
                    f"{label} exited during startup with code {process.returncode}"
                )
            try:
                if _get_json(url, timeout=1).get("status") == "ok":
                    return
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.05)
        raise RuntimeError(f"{label} did not become ready: {last_error}")

    def _start_model_gateway(self) -> None:
        if not MODEL_GATEWAY_SCRIPT.is_file():
            raise RuntimeError(f"model gateway script missing: {MODEL_GATEWAY_SCRIPT}")
        gateway = self.adapter.model_gateway()
        secret = self.adapter.model_gateway_secret()
        if not secret:
            raise RuntimeError("model gateway credential is unavailable")
        control_path = self._stage_control()
        secret_path = self._stage_secret(secret)
        policy = gateway["transient_error_policy"]
        env = {
            **self._fixed_environment(),
            "PDDL_GATEWAY_UPSTREAM_ORIGIN": gateway["upstream_origin"],
            "PDDL_GATEWAY_MAX_MODEL_CALLS": str(gateway["max_model_calls"]),
            "PDDL_GATEWAY_MAX_ACTION_STEPS": str(gateway["max_action_steps"]),
            "PDDL_GATEWAY_AUTH_MODE": gateway["auth_mode"],
            "PDDL_GATEWAY_API_KEY_FILE": str(secret_path),
            "PDDL_GATEWAY_ALLOWED_MODELS": json.dumps(gateway["allowed_models"]),
            "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES": json.dumps(
                gateway["allowed_path_prefixes"]
            ),
            "PDDL_GATEWAY_PORT": str(self.model_gateway_port),
            "PDDL_GATEWAY_LISTEN_HOST": "127.0.0.1",
            "PDDL_GATEWAY_MAX_TRANSIENT_RETRIES": str(policy["max_retries"]),
            "PDDL_GATEWAY_TRANSIENT_BACKOFF_SECONDS": json.dumps(
                policy["backoff_seconds"]
            ),
            "PDDL_GATEWAY_MAX_RETRY_AFTER_SECONDS": str(
                policy["max_retry_after_seconds"]
            ),
            "PDDL_GATEWAY_RETRYABLE_HTTP_STATUSES": json.dumps(
                policy["retryable_http_statuses"]
            ),
            "PDDL_GATEWAY_REQUEST_OVERRIDES": json.dumps(
                gateway.get("request_overrides", {}), sort_keys=True
            ),
            "PDDL_GATEWAY_CONTROL_FILE": str(control_path),
        }
        self._gateway_process = self._spawn(
            [sys.executable, str(MODEL_GATEWAY_SCRIPT)],
            env=env,
            log_stem="minimum_model_gateway",
        )
        self._wait_healthy(
            self._gateway_process,
            self.model_gateway_origin + "/__benchmark__/health",
            "minimum model gateway",
        )

    def _start_solver_gateway(self) -> None:
        entrypoint = SOLVER_DIR / SOLVER_GATEWAY_ENTRYPOINT
        if not entrypoint.is_file():
            raise RuntimeError(f"solver gateway script missing: {entrypoint}")
        self.solver_gateway_port = _loopback_port()
        self.solver_gateway_origin = (
            f"http://127.0.0.1:{self.solver_gateway_port}"
        )
        env = {
            **self._fixed_environment(),
            "PDDL_SOLVER_GATEWAY_PORT": str(self.solver_gateway_port),
            "PDDL_SOLVER_GATEWAY_LISTEN_HOST": "127.0.0.1",
        }
        self._solver_process = self._spawn(
            [sys.executable, str(entrypoint)],
            env=env,
            log_stem="minimum_solver_gateway",
        )
        self._wait_healthy(
            self._solver_process,
            self.solver_gateway_origin + "/__benchmark__/health",
            "minimum solver gateway",
        )

    def start(self) -> str:
        if self.adapter.network_mode != "model_only":
            raise RuntimeError("minimum host runtime supports only model_only mode")
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        if self.workspace_dir.exists():
            if self.workspace_dir.resolve().parent != self.artifact_dir.resolve():
                raise RuntimeError(
                    f"Refusing to reset unexpected minimum workspace: {self.workspace_dir}"
                )
            shutil.rmtree(self.workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._start_model_gateway()
        if self.adapter.minimum_config["solver_feedback"]["enabled"]:
            self._start_solver_gateway()
        self.adapter.configure_host_execution(
            api_base=self.runtime_api_base,
            solver_gateway=self.solver_gateway_origin,
            workspace_dir=self.workspace_dir,
        )
        logger.info("Minimum host runtime %s started", self.instance_id)
        return self.container_name

    def seed_workspace(
        self, domain_description: str, problem_description: str
    ) -> None:
        # Inputs are transported only in the fixed initial conversation prompt.
        return None

    def _read_control(self) -> dict | None:
        if self._control_path is None:
            return None
        try:
            value = json.loads(self._control_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def start_model_gateway_monitor(self, attempt_clock) -> None:
        if self._gateway_monitor_thread is not None:
            raise RuntimeError("model gateway monitor is already running")
        stop = threading.Event()
        self._gateway_monitor_stop = stop
        self._gateway_terminal_error = None
        self._gateway_monitor_error = None
        self._gateway_action_step_limit_reached = False

        def monitor() -> None:
            paused = False
            try:
                while not stop.is_set():
                    control = self._read_control()
                    if control is None:
                        stop.wait(0.05)
                        continue
                    pause_requested = bool(control.get("pause_requested"))
                    if pause_requested and not paused:
                        pause_started = control.get("pause_started_unix")
                        retroactive = (
                            max(0.0, time.time() - float(pause_started))
                            if isinstance(pause_started, (int, float))
                            else 0.0
                        )
                        attempt_clock.pause(retroactive_seconds=retroactive)
                        paused = True
                    elif not pause_requested and paused:
                        attempt_clock.resume()
                        paused = False
                    terminal = control.get("terminal_infra_error")
                    if isinstance(terminal, dict):
                        self._gateway_terminal_error = dict(terminal)
                        return
                    if bool(control.get("action_step_limit_reached")):
                        self._gateway_action_step_limit_reached = True
                        return
                    stop.wait(0.05)
            finally:
                if paused:
                    attempt_clock.resume()

        thread = threading.Thread(
            target=monitor,
            name=f"minimum-gateway-monitor-{self.instance_id[:40]}",
            daemon=True,
        )
        self._gateway_monitor_thread = thread
        thread.start()

    def stop_model_gateway_monitor(self) -> None:
        if self._gateway_monitor_stop is not None:
            self._gateway_monitor_stop.set()
        thread = self._gateway_monitor_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._gateway_monitor_stop = None
        self._gateway_monitor_thread = None

    def gateway_terminal_infra_error(self) -> dict | None:
        if self._gateway_terminal_error is None:
            control = self._read_control()
            terminal = control.get("terminal_infra_error") if control else None
            if isinstance(terminal, dict):
                self._gateway_terminal_error = dict(terminal)
        return (
            dict(self._gateway_terminal_error)
            if self._gateway_terminal_error is not None
            else None
        )

    def gateway_monitor_error(self) -> str | None:
        return self._gateway_monitor_error

    def gateway_action_step_limit_reached(self) -> bool:
        if not self._gateway_action_step_limit_reached:
            control = self._read_control()
            self._gateway_action_step_limit_reached = bool(
                control and control.get("action_step_limit_reached")
            )
        return self._gateway_action_step_limit_reached

    def model_gateway_stats(self) -> dict:
        if self._gateway_process is None or self._gateway_process.poll() is not None:
            return {"error": "minimum model gateway unavailable"}
        try:
            return _get_json(
                self.model_gateway_origin + "/__benchmark__/status", timeout=5
            )
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    def model_gateway_ledger(self) -> list[dict]:
        if self._gateway_process is None or self._gateway_process.poll() is not None:
            return []
        try:
            value = _get_json(
                self.model_gateway_origin + "/__benchmark__/ledger", timeout=5
            )
            ledger = value.get("ledger", [])
            return list(ledger) if isinstance(ledger, list) else []
        except Exception:
            return []

    def validate_network_policy(self) -> dict:
        runtime_url = urlsplit(self.runtime_api_base)
        tests = {
            "execution_backend_is_host": True,
            "controlled_web_disabled": self.adapter.network_mode == "model_only",
            "model_gateway_bound_to_loopback": runtime_url.hostname == "127.0.0.1",
            "model_gateway_reachable": self.model_gateway_stats().get("error") is None,
            "model_selectable_tools_absent": self.adapter.agent_tools() == [],
            "workspace_not_exposed_to_model": not self.adapter.tool_policy().get(
                "workspace_visible_to_model", True
            ),
        }
        return {
            "preset": "network-model-only",
            "version": 2,
            "mode": self.adapter.network_mode,
            "implementation": "benchmark-owned host runtime with fixed loopback routes",
            "status": "pass" if all(tests.values()) else "fail",
            "tests": tests,
        }

    def validate_environment_policy(self) -> dict:
        values = self._fixed_environment()
        fixed = self.adapter.resolved_config.raw["resolved"]["environment"]["fixed"]
        secret = self.adapter.model_gateway_secret()
        tests = {
            "runtime_environment_explicit": True,
            "fixed_environment_exact": values == fixed,
            "real_model_secret_absent": not secret
            or all(secret not in value for value in values.values()),
            "gateway_secret_staged_by_file": bool(
                self._secret_dir and (self._secret_dir / "api-key").is_file()
            ),
        }
        return {
            "preset": "environment-isolation",
            "version": 1,
            "implementation": "explicit minimum-runtime environment; secret is gateway-only",
            "status": "pass" if all(tests.values()) else "fail",
            "tests": tests,
            "environment_names": sorted(values),
            "proxy_environment_names": [],
        }

    def validate_action_step_guard(self) -> dict:
        stats = self.model_gateway_stats()
        expected_routing = self.adapter.resolved_config.model_error_routing
        expected_gateway_routing = {
            "max_retries": expected_routing["max_retries"],
            "backoff_seconds": expected_routing["backoff_seconds"],
            "max_retry_after_seconds": expected_routing["max_retry_after_seconds"],
            "retryable_http_statuses": expected_routing["retryable_http_statuses"],
        }
        passed = (
            stats.get("max_model_calls") == self.adapter.max_model_calls
            and stats.get("max_action_steps") == self.adapter.max_action_steps
            and stats.get("model_calls") == 0
            and stats.get("tool_calls") == 0
            and stats.get("action_steps") == 0
            and stats.get("transient_policy") == expected_gateway_routing
        )
        return {
            "preset": "action-step-guard",
            "version": 1,
            "status": "pass" if passed else "fail",
            "configured_model_call_limit": self.adapter.max_model_calls,
            "gateway_reported_model_call_limit": stats.get("max_model_calls"),
            "configured_action_step_limit": self.adapter.max_action_steps,
            "gateway_reported_action_step_limit": stats.get("max_action_steps"),
            "configured_transient_policy": expected_gateway_routing,
            "gateway_reported_transient_policy": stats.get("transient_policy", {}),
        }

    def validate_state_isolation(self) -> dict:
        spec = self.adapter.state_isolation_spec(self.instance_id)
        host_binding = getattr(self.adapter._host_execution, "value", None)
        tests = {
            "isolation_mode_is_explicit": spec.get("mode") == "isolated",
            "scope_is_per_attempt": spec.get("scope") == "per_attempt",
            "personal_harness_state_excluded": (
                spec.get("personal_harness_state") == "excluded"
            ),
            "cross_attempt_reuse_disabled": (
                spec.get("cross_attempt_reuse") is False
            ),
            "workspace_is_attempt_private": (
                self.workspace_dir.resolve().parent == self.artifact_dir.resolve()
            ),
            "workspace_exists": self.workspace_dir.is_dir(),
            "thread_local_binding_matches_attempt": (
                isinstance(host_binding, dict)
                and Path(host_binding.get("workspace_dir", "")).resolve()
                == self.workspace_dir.resolve()
            ),
            "model_gateway_is_loopback_only": (
                urlsplit(self.model_gateway_origin).hostname == "127.0.0.1"
            ),
            "model_has_no_filesystem_or_memory_tools": (
                self.adapter.agent_tools() == []
                and not self.adapter.tool_policy().get(
                    "workspace_visible_to_model", True
                )
            ),
        }
        return {
            "preset": "state-isolation",
            "version": 1,
            "status": "pass" if all(tests.values()) else "fail",
            "implementation": (
                "per-attempt host workspace and thread-local loopback services; "
                "no model filesystem, memory, or shell surface"
            ),
            "mode": spec.get("mode"),
            "attempt_root": str(self.workspace_dir),
            "expected_writable_bind_sources": [],
            "observed_writable_bind_sources": [],
            "expected_readonly_bind_sources": [],
            "observed_readonly_bind_sources": [],
            "tests": tests,
        }

    def freeze_pddl_outputs(self) -> dict[str, bytes | None]:
        contract = self.adapter.resolved_config.raw["resolved"]["artifact_contract"]
        outputs: dict[str, bytes | None] = {}
        for role, key in (
            ("domain", "workspace_domain_file"),
            ("problem", "workspace_problem_file"),
        ):
            path = self.workspace_dir / contract[key]
            outputs[role] = path.read_bytes() if path.is_file() else None
        return outputs

    def enforce_agent_deadline(self) -> None:
        # run_process_with_attempt_clock owns and kills the minimum runtime
        # subprocess.  Keep the gateway alive until its final ledger is read.
        self._deadline_enforced = True

    def cleanup(self) -> None:
        self.stop_model_gateway_monitor()
        self.adapter.clear_host_execution()
        for process in reversed(self._processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        self._processes.clear()
        for stream in self._log_streams:
            stream.close()
        self._log_streams.clear()
        if self._secret_dir is not None:
            shutil.rmtree(self._secret_dir, ignore_errors=True)
        if self._control_dir is not None:
            shutil.rmtree(self._control_dir, ignore_errors=True)
        self._secret_dir = None
        self._control_dir = None
        self._control_path = None
