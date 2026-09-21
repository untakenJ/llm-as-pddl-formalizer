"""Host-only execution services for the benchmark-owned minimum agent.

Unlike the native third-party harnesses, the minimum agent has no shell, file,
tool, memory, or plugin surface to sandbox.  It runs as a repository-owned
standard-library subprocess and can reach only per-attempt loopback services:
the fixed-route model gateway and, when configured, the fixed solver gateway.
"""

from __future__ import annotations

import datetime
from agent_formalizer.external_calls.control import ToolControlMonitor, read_json
from agent_formalizer.runtime import process_lifecycle

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from agent_formalizer.configuration.config import (
    LOGITS_BRIDGE_ENV_PATH,
    LOGITS_GATEWAY_SCRIPT,
    LOGITS_MODEL_ASSETS_ROOT,
    MODEL_GATEWAY_SCRIPT,
)
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


def _post_empty_json(url: str, *, timeout: float = 5) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, data=b"", method="POST")
    with opener.open(request, timeout=timeout) as response:
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
        diagnostics_plan=None,
    ):
        self.instance_id = instance_id
        self.container_name = runtime_name  # logical name retained in shared evidence APIs
        self.adapter = adapter
        self.artifact_dir = Path(artifact_dir)
        self.diagnostics_plan = diagnostics_plan
        self.workspace_dir = self.artifact_dir / "minimum_agent_workspace"
        self.model_gateway_port = _loopback_port()
        self.logits_bridge_port = _loopback_port()
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
        self._cancel_path: Path | None = None
        self._gateway_native_exit_path: Path | None = None
        self._gateway_monitor_stop: threading.Event | None = None
        self._gateway_monitor_thread: threading.Thread | None = None
        self._gateway_terminal_error: dict | None = None
        self._gateway_monitor_error: str | None = None
        self._gateway_action_step_limit_reached = False
        self._deadline_enforced = False
        self._solver_control_monitor: ToolControlMonitor | None = None

    @property
    def runtime_api_base(self) -> str:
        path = urlsplit(self.adapter.api_base).path.rstrip("/")
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
        self._cancel_path = directory / "benchmark-cancelled"
        self._gateway_native_exit_path = directory / "native-harness-exited"
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
        process = subprocess.Popen(process_lifecycle.command(argv), stdout=stdout,
                                   stderr=stderr, env=env, start_new_session=True)
        self._processes.append(process)
        return process

    @staticmethod
    def _wait_healthy(process: subprocess.Popen, url: str, label: str) -> None:
        last_error = "not ready"
        for _ in range(600):
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
        transport = gateway.get("transport")
        evidence_dir = self.artifact_dir / "gateway"
        evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        env = {
            **self._fixed_environment(),
            "PDDL_GATEWAY_UPSTREAM_ORIGIN": gateway["upstream_origin"],
            # Minimum intentionally requests a complete, non-streamed answer.
            # A healthy reasoning response may take more than 600s. Do not
            # impose a shorter hidden generation limit than the active clock;
            # allow the parent watchdog to own that boundary (small grace).
            "PDDL_GATEWAY_UPSTREAM_TIMEOUT_SECONDS": str(max(600, self.adapter.timeout + 5)),
            "PDDL_GATEWAY_MAX_MODEL_CALLS": str(gateway["max_model_calls"]),
            "PDDL_GATEWAY_MAX_ACTION_STEPS": str(gateway["max_action_steps"]),
            "PDDL_GATEWAY_AUTH_MODE": gateway["auth_mode"],
            "PDDL_GATEWAY_PROVIDER": gateway.get("provider", "unknown"),
            "PDDL_GATEWAY_REASONING_PATH": str(evidence_dir / "provider_reasoning.jsonl"),
            "PDDL_GATEWAY_REASONING_STATUS_PATH": str(evidence_dir / "reasoning_capture_status.json"),
            "PDDL_GATEWAY_FULL_TRACE_PATH": str(evidence_dir / "provider_full_trace.jsonl"),
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
            "PDDL_GATEWAY_BENCHMARK_CANCEL_FILE": str(self._cancel_path),
            "PDDL_GATEWAY_NATIVE_EXIT_FILE": str(self._gateway_native_exit_path),
            "PDDL_GATEWAY_RESPONSE_DELIVERY": gateway.get(
                "response_delivery", "buffered_atomic"
            ),
        }
        if self.diagnostics_plan is not None:
            try:
                run_root = self.diagnostics_plan.run_root
                execution_dir = self.diagnostics_plan.execution_dir
                run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                execution_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                run_root.chmod(0o700)
                execution_dir.chmod(0o700)
                runtime_config = {
                    **self.diagnostics_plan.runtime_config,
                    "event_path": str(execution_dir / "events.jsonl"),
                    "manifest_path": str(
                        execution_dir / "diagnostics_manifest.json"
                    ),
                    "run_budget_path": str(run_root / ".run-bytes"),
                }
                diagnostics_config_path = (
                    control_path.parent / "infra-diagnostics.json"
                )
                diagnostics_config_path.write_text(
                    json.dumps(runtime_config, indent=2, ensure_ascii=False) + "\n"
                )
                diagnostics_config_path.chmod(0o600)
                env["PDDL_GATEWAY_INFRA_DIAGNOSTICS_CONFIG"] = str(
                    diagnostics_config_path
                )
            except OSError as exc:
                logger.warning(
                    "Infrastructure diagnostics disabled for %s: %s",
                    self.container_name,
                    exc,
                )
        command = [sys.executable, str(MODEL_GATEWAY_SCRIPT)]
        if transport == "logits-rest-openai-v1":
            runtime_python = LOGITS_BRIDGE_ENV_PATH / "bin" / "python"
            if not runtime_python.is_file() or not LOGITS_MODEL_ASSETS_ROOT.is_dir():
                raise RuntimeError(
                    "Logits gateway runtime is incomplete. Run: bash "
                    "source/agent_formalizer/runtime/install_harnesses.sh logits"
                )
            env.update(
                {
                    "PDDL_LOGITS_MODEL": gateway["upstream_model"],
                    "PDDL_LOGITS_BRIDGE_PORT": str(self.logits_bridge_port),
                    "PDDL_LOGITS_ORIGIN": "https://api.logits.dev",
                    "PDDL_LOGITS_MODEL_ASSETS_ROOT": str(LOGITS_MODEL_ASSETS_ROOT),
                    "PDDL_LOGITS_LEDGER_PATH": str(
                        self.artifact_dir / "minimum_logits_gateway.jsonl"
                    ),
                }
            )
            command = [str(runtime_python), str(LOGITS_GATEWAY_SCRIPT)]
        elif transport is not None:
            raise RuntimeError(f"Unsupported model gateway transport: {transport}")
        self._gateway_process = self._spawn(
            command,
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
            "PDDL_SOLVER_UPSTREAM_BASE": self.adapter.solver_upstream_base(
                containerized=False
            ),
            "PDDL_SOLVER_UPSTREAM_HEALTH_REQUIRED": (
                "1" if self.adapter.solver_backend() in {"local", "public_then_local"} else "0"
            ),
        }
        policy = self.adapter.resolved_config.raw["resolved"].get("solver_error_routing")
        if self.adapter.solver_backend() == "public_then_local":
            if not policy:
                raise RuntimeError("public_then_local tool requires solver recovery/control")
            env.update({
                "PDDL_SOLVER_BACKEND": "public_then_local",
                "PDDL_SOLVER_FALLBACK_BASE": self.adapter.solver_fallback_base(containerized=False),
            })
        if policy:
            if self._control_dir is None or self._cancel_path is None:
                raise RuntimeError("solver recovery requires gateway control")
            self._solver_control_monitor = ToolControlMonitor(self._control_dir / "solver.json")
            env.update({
                "PDDL_SOLVER_ERROR_ROUTING": policy,
                "PDDL_SOLVER_CONTROL_FILE": str(self._solver_control_monitor.path),
                "PDDL_SOLVER_CANCEL_FILE": str(self._cancel_path),
                "PDDL_SOLVER_EVIDENCE_DIR": str(self.artifact_dir / "gateway" / "solver_calls"),
            })
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
        if self._solver_control_monitor is not None and read_json(self._solver_control_monitor.path) is None:
            raise RuntimeError("solver recovery control is not readable by the host monitor")

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
                    if self._solver_control_monitor is not None:
                        control = self._solver_control_monitor.merge(control or {}, attempt_clock)
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
                    if (
                        terminal is None
                        and self.adapter.resolved_config.model_response_delivery[
                            "mode"
                        ] == "native_streaming"
                        and control.get("active_committed_streams", 0) > 0
                        and self._gateway_process is not None
                        and self._gateway_process.poll() is not None
                    ):
                        terminal = {
                            "reason": "post_commit_stream_failure",
                            "stream_error_type": "GatewaySidecarExit",
                        }
                    if isinstance(terminal, dict):
                        self._gateway_terminal_error = dict(terminal)
                        attempt_clock.cancel("gateway_terminal_infra_error")
                        return
                    if bool(control.get("action_step_limit_reached")):
                        self._gateway_action_step_limit_reached = True
                        attempt_clock.cancel("action_step_limit")
                        return
                    if self._solver_control_monitor is not None:
                        if self._solver_control_monitor.acknowledge(paused=paused, clock=attempt_clock):
                            self.enforce_agent_deadline()
                            return
                    stop.wait(0.05)
            except Exception:
                logger.exception("External call monitor failed for %s", self.instance_id)
                self._gateway_monitor_error = "external_call_control_failed"
                attempt_clock.cancel("external_call_control_failed")
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
            elif self._solver_control_monitor is not None:
                state = read_json(self._solver_control_monitor.path) or {}
                if isinstance(state.get("terminal_infra_error"), dict):
                    self._gateway_terminal_error = dict(state["terminal_infra_error"])
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

    def finalize_model_gateway_after_native_exit(
        self, *, wait_seconds: float = 2.0
    ) -> dict:
        """Settle host-gateway requests after the Minimum runtime exits."""
        report = {
            "schema_version": 1,
            "requested_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "status": "not_started",
            "wait_seconds": wait_seconds,
        }
        if self._gateway_process is None or self._gateway_process.poll() is not None:
            return report
        if self._gateway_native_exit_path is not None:
            try:
                self._gateway_native_exit_path.write_text(
                    "native_harness_exit\n", encoding="utf-8"
                )
            except OSError as exc:
                report["marker_error"] = type(exc).__name__
        try:
            report["gateway_acknowledgement"] = _post_empty_json(
                self.model_gateway_origin + "/__benchmark__/native-exit",
                timeout=max(1.0, min(5.0, wait_seconds + 1.0)),
            )
        except (OSError, ValueError, urllib.error.URLError) as exc:
            report["gateway_error"] = type(exc).__name__

        deadline = time.monotonic() + max(0.0, wait_seconds)
        control = self._read_control()
        while (
            control is not None
            and control.get("in_flight_requests", 0)
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
            control = self._read_control()
        report["final_control"] = control
        if control is None:
            report["status"] = "status_collection_failed"
        elif control.get("in_flight_requests", 0) == 0:
            report["status"] = "settled"
        else:
            report["status"] = "active_requests_retained_in_ledger"
        report["completed_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        try:
            evidence_path = self.artifact_dir / "gateway/native_exit_finalization.json"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = evidence_path.with_name(f".{evidence_path.name}.tmp")
            temporary.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, evidence_path)
        except OSError:
            logger.exception("Could not persist minimum gateway native-exit evidence")
        return report

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
        expected_delivery = self.adapter.resolved_config.model_response_delivery["mode"]
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
            and stats.get("streaming_mode") == expected_delivery
        )
        return {
            "preset": "action-step-guard",
            "version": 2 if expected_delivery == "native_streaming" else 1,
            "status": "pass" if passed else "fail",
            "configured_model_call_limit": self.adapter.max_model_calls,
            "gateway_reported_model_call_limit": stats.get("max_model_calls"),
            "configured_action_step_limit": self.adapter.max_action_steps,
            "gateway_reported_action_step_limit": stats.get("max_action_steps"),
            "configured_transient_policy": expected_gateway_routing,
            "gateway_reported_transient_policy": stats.get("transient_policy", {}),
            "configured_response_delivery": expected_delivery,
            "gateway_reported_response_delivery": stats.get("streaming_mode"),
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
        if self._cancel_path is not None:
            try:
                self._cancel_path.write_text("benchmark_deadline\n")
            except OSError:
                pass

    def cleanup(self) -> None:
        errors = []
        for cleanup in (self.stop_model_gateway_monitor, self.adapter.clear_host_execution):
            try:
                cleanup()
            except Exception as exc:
                errors.append(str(exc))
                logger.exception("Could not stop minimum host monitor/state")
        for process in reversed(self._processes):
            try:
                process_lifecycle.terminate(process)
            except Exception as exc:
                errors.append(str(exc))
                logger.exception("Could not drain minimum host process")
        self._processes.clear()
        for stream in self._log_streams:
            try:
                stream.close()
            except Exception as exc:
                errors.append(str(exc))
                logger.exception("Could not close minimum process log")
        self._log_streams.clear()
        if self._secret_dir is not None:
            shutil.rmtree(self._secret_dir, ignore_errors=True)
        if self._control_dir is not None:
            shutil.rmtree(self._control_dir, ignore_errors=True)
        self._secret_dir = None
        self._control_dir = None
        self._control_path = None
        self._cancel_path = None
        self._gateway_native_exit_path = None
        if errors:
            raise RuntimeError("minimum process cleanup failed: " + "; ".join(errors))
