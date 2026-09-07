"""Manage the agent's Docker container lifecycle for one PDDL problem.

Responsibilities:
- Start / stop a container from the configured base image.
- Execute commands inside the container.
- Seed the workspace with the textual domain/problem descriptions.
- Read the agent-authored PDDL files back out.

Claw-specific container integration (bind mounts, env vars, post-start
provisioning) is delegated to the claw adapter via two hooks:
- adapter.container_run_args(instance_id) -> extra ``docker run`` args
- adapter.post_container_start(workspace)  -> e.g. copy a config file in

Ported in spirit from ``claw-swe-bench`` (``claw_swebench/workspace.py``) but
the SWE-bench repo/git machinery is replaced with a simple seeded workspace,
since here the agent produces two PDDL files rather than a code patch.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import shlex
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from agent_formalizer.config import (
    BASE_IMAGE,
    CONTAINER_WORKSPACE,
    DOMAIN_OUTPUT_NAME,
    EXTERNAL_CALLS_CONTAINER_PATH,
    EXTERNAL_CALLS_PACKAGE,
    INFRA_DIAGNOSTICS_CONTAINER_PATH,
    INFRA_DIAGNOSTICS_PACKAGE,
    MODEL_GATEWAY_CONTAINER_PATH,
    MODEL_GATEWAY_HOST,
    MODEL_GATEWAY_PORT,
    MODEL_GATEWAY_SCRIPT,
    PROVIDER_REASONING_CONTAINER_PATH,
    PROVIDER_REASONING_MODULE,
    LOGITS_BRIDGE_CONTAINER_PATH,
    LOGITS_BRIDGE_ENV_PATH,
    LOGITS_BRIDGE_PORT,
    LOGITS_BRIDGE_SCRIPT,
    LOGITS_GATEWAY_CONTAINER_PATH,
    LOGITS_GATEWAY_SCRIPT,
    LOGITS_MODEL_ASSETS_ROOT,
    PROBLEM_OUTPUT_NAME,
    related_docker_resource_name,
    WEB_GATEWAY_CONTAINER_PATH,
    WEB_GATEWAY_HOST,
    WEB_GATEWAY_PORT,
    WEB_GATEWAY_SCRIPT,
)
from agent_formalizer.tools import resolve_agent_tools
from agent_formalizer.external_calls.control import ToolControlMonitor, read_json
from agent_formalizer import deadline_integration

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    """Result of a command executed inside a container."""

    stdout: str
    stderr: str
    exit_code: int


class AgentWorkspace:
    """Manages a single Docker container for one formalization problem."""

    def __init__(
        self,
        instance_id: str,
        container_name: str,
        adapter,
        image: str | None = None,
        artifact_dir: Path | None = None,
        diagnostics_plan=None,
    ):
        self.instance_id = instance_id
        self.adapter = adapter
        self.image_name = image or BASE_IMAGE
        self.container_name = container_name
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self.diagnostics_plan = diagnostics_plan
        # Hash the complete parent name into every related resource.  Prefix
        # slicing used to discard the per-problem/attempt suffix and made
        # concurrent sweeps remove one another's containers.
        self.network_name = related_docker_resource_name(container_name, "net")
        self.gateway_name = related_docker_resource_name(
            container_name, "model-gateway"
        )
        self.web_gateway_name = related_docker_resource_name(
            container_name, "web-gateway"
        )
        self.solver_gateway_name = related_docker_resource_name(
            container_name, "solver-gateway"
        )
        self._started = False
        self._network_created = False
        self._gateway_started = False
        self._web_gateway_started = False
        self._solver_gateway_started = False
        self._gateway_secret_dir: Path | None = None
        self._gateway_control_dir: Path | None = None
        self._gateway_control_path: Path | None = None
        self._gateway_cancel_path: Path | None = None
        self._gateway_monitor_stop: threading.Event | None = None
        self._gateway_monitor_thread: threading.Thread | None = None
        self._gateway_terminal_error: dict | None = None
        self._gateway_monitor_error: str | None = None
        self._gateway_action_step_limit_reached = False
        self._gateway_evidence_dir: Path | None = None
        self._solver_control_monitor: ToolControlMonitor | None = None
        self._deadline_broker = None
        self._deadline_bundle = None
        self._deadline_directory = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> str:
        """Start the Docker container. Returns the container name."""
        deadline_integration.validate(self.adapter)
        self._remove_stale_resources()
        self._create_network()
        self._start_model_gateway()
        if self.adapter.network_mode == "controlled_web":
            self._start_web_gateway()
        tool_specs = resolve_agent_tools(self.adapter.runtime_tools())
        for spec in tool_specs:
            self._start_tool_gateway(spec)

        logger.info("Starting container %s from image %s",
                    self.container_name, self.image_name)
        resources = self.adapter.resolved_config.raw["resolved"][
            "container_resources"
        ]
        cmd = [
            "docker", "run", "-d",
            "--pull", "never",
            "--name", self.container_name,
            "--network", self.network_name,
            "--pids-limit", str(resources["pids_limit"]),
            "--memory", resources["memory"],
            "--memory-swap", resources["memory_swap"],
        ]
        fixed_environment = self.adapter.resolved_config.raw["resolved"][
            "environment"
        ]["fixed"]
        for name, value in fixed_environment.items():
            cmd.extend(["-e", f"{name}={value}"])
        no_proxy_hosts = ["model-gateway"]
        if self.adapter.network_mode == "controlled_web":
            no_proxy_hosts.append("web-gateway")
        for spec in tool_specs:
            no_proxy_hosts.append(spec.gateway_host)
        no_proxy_hosts.extend(["127.0.0.1", "localhost"])
        if self.adapter.network_mode == "controlled_web":
            proxy = f"http://{WEB_GATEWAY_HOST}:{WEB_GATEWAY_PORT}"
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                cmd.extend(["-e", f"{name}={proxy}"])
            cmd.extend([
                "-e",
                "NO_PROXY=" + ",".join(no_proxy_hosts),
            ])
        for spec in tool_specs:
            if not spec.cli_host_path.is_file():
                raise RuntimeError(f"agent tool CLI missing: {spec.cli_host_path}")
            cmd.extend([
                "-v", f"{spec.cli_host_path}:{spec.cli_container_path}:ro",
                "-e", (
                    f"{spec.env_gateway}=http://{spec.gateway_host}:"
                    f"{spec.gateway_port}"
                ),
            ])
        cmd.extend(self.adapter.container_run_args(self.instance_id))
        if deadline_integration.selected(self.adapter):
            cmd.extend(deadline_integration.prepare(self))
        cmd.extend([self.image_name, "tail", "-f", "/dev/null"])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container: {result.stderr.strip()}")
        self._started = True

        self.adapter.post_container_start(self)
        logger.info("Container %s started.", self.container_name)
        return self.container_name

    def cleanup(self) -> None:
        """Force-remove the container (best effort)."""
        self.stop_model_gateway_monitor()
        if self._deadline_broker is not None:
            self._deadline_broker.close()
            self._deadline_broker = None
        subprocess.run(
            ["docker", "rm", "-f", "-v", self.container_name],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "rm", "-f", "-v", self.gateway_name],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "rm", "-f", "-v", self.web_gateway_name], capture_output=True
        )
        subprocess.run(
            ["docker", "rm", "-f", "-v", self.solver_gateway_name], capture_output=True
        )
        subprocess.run(
            ["docker", "network", "rm", self.network_name],
            capture_output=True,
        )
        self._cleanup_gateway_secret()
        self._cleanup_gateway_control()
        self._started = False
        self._gateway_started = False
        self._web_gateway_started = False
        self._solver_gateway_started = False
        self._network_created = False
        logger.debug("Removed container %s", self.container_name)

    def enforce_agent_deadline(self) -> None:
        """Freeze actions, cut the model route, then stop the complete tree."""
        if self._gateway_cancel_path is not None:
            try:
                self._gateway_cancel_path.write_text("benchmark_deadline\n")
            except OSError:
                pass
        if self._started:
            try:
                subprocess.run(
                    ["docker", "pause", self.container_name],
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                logger.error("Timed out pausing agent container at deadline")
        if self._network_created and self._gateway_started:
            try:
                subprocess.run(
                    [
                        "docker", "network", "disconnect", "-f",
                        self.network_name, self.gateway_name,
                    ],
                    capture_output=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                logger.error("Timed out cutting model route at agent deadline")
        if self._started:
            try:
                subprocess.run(
                    ["docker", "kill", self.container_name],
                    capture_output=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                logger.error("Timed out killing agent container at deadline")

    def _remove_stale_resources(self) -> None:
        self._cleanup_gateway_secret()
        self._cleanup_gateway_control()
        for name in (
            self.container_name,
            self.gateway_name,
            self.web_gateway_name,
            self.solver_gateway_name,
        ):
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
        subprocess.run(
            ["docker", "network", "rm", self.network_name], capture_output=True
        )

    def _create_network(self) -> None:
        cmd = ["docker", "network", "create"]
        # The agent always lives on an internal network. Optional web access is
        # through a separate allowlist proxy, never ordinary container egress.
        cmd.append("--internal")
        cmd.append(self.network_name)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create benchmark network: {result.stderr.strip()}")
        self._network_created = True

    def _stage_gateway_secret(self, secret: str) -> Path:
        """Materialize one gateway-only secret without putting it in argv."""
        directory = Path(tempfile.mkdtemp(prefix="pddl-model-gateway-secret-"))
        directory.chmod(0o700)
        path = directory / "api-key"
        path.write_text(secret)
        path.chmod(0o600)
        self._gateway_secret_dir = directory
        return path

    def _cleanup_gateway_secret(self) -> None:
        if self._gateway_secret_dir is not None:
            shutil.rmtree(self._gateway_secret_dir, ignore_errors=True)
            self._gateway_secret_dir = None

    def _stage_gateway_control(self) -> Path:
        """Create a secret-free host/sidecar control channel for pause events."""
        directory = Path(tempfile.mkdtemp(prefix="pddl-model-gateway-control-"))
        directory.chmod(0o700)
        self._gateway_control_dir = directory
        self._gateway_control_path = directory / "state.json"
        self._gateway_cancel_path = directory / "benchmark-cancelled"
        return self._gateway_control_path

    def _cleanup_gateway_control(self) -> None:
        if self._gateway_control_dir is not None:
            shutil.rmtree(self._gateway_control_dir, ignore_errors=True)
        self._gateway_control_dir = None
        self._gateway_control_path = None
        self._gateway_cancel_path = None

    def _read_gateway_control(self) -> dict | None:
        path = self._gateway_control_path
        if path is None:
            return None
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def start_model_gateway_monitor(self, attempt_clock) -> None:
        """Pause the agent container and active clock during transparent retry."""
        if self._gateway_monitor_thread is not None:
            raise RuntimeError("model gateway monitor is already running")
        stop = threading.Event()
        self._gateway_monitor_stop = stop
        self._gateway_terminal_error = None
        self._gateway_monitor_error = None
        self._gateway_action_step_limit_reached = False

        if self._deadline_broker is not None:
            thread = threading.Thread(target=deadline_integration.monitor,
                                      args=(self, attempt_clock, stop), daemon=True,
                                      name=f"logical-deadline-{self.container_name[:32]}")
            self._gateway_monitor_thread = thread
            thread.start()
            return

        def monitor() -> None:
            paused = False

            def run_control(command, **kwargs):
                if self._solver_control_monitor is not None:
                    kwargs["timeout"] = 5
                return subprocess.run(command, **kwargs)

            streaming_mode = (
                getattr(getattr(self.adapter, "resolved_config", None),
                        "model_response_delivery", {}).get("mode")
                == "native_streaming"
            )
            last_gateway_liveness_check = 0.0
            try:
                while not stop.is_set():
                    control = self._read_gateway_control()
                    if self._solver_control_monitor is not None:
                        control = self._solver_control_monitor.merge(control or {}, attempt_clock)
                    if control is None:
                        stop.wait(0.05)
                        continue
                    terminal = control.get("terminal_infra_error")
                    now = time.monotonic()
                    if (
                        terminal is None
                        and streaming_mode
                        and control.get("active_committed_streams", 0) > 0
                        and now - last_gateway_liveness_check >= 0.25
                    ):
                        last_gateway_liveness_check = now
                        gateway_state = run_control(
                            [
                                "docker", "inspect", "--format",
                                "{{.State.Running}}", self.gateway_name,
                            ],
                            capture_output=True,
                            text=True,
                        )
                        if (
                            gateway_state.returncode != 0
                            or gateway_state.stdout.strip() != "true"
                        ):
                            terminal = {
                                "reason": "post_commit_stream_failure",
                                "stream_error_type": "GatewaySidecarExit",
                                "recorded_at": datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat().replace("+00:00", "Z"),
                            }
                    action_limit_reached = bool(
                        control.get("action_step_limit_reached")
                    )
                    pause_requested = bool(control.get("pause_requested"))
                    if pause_requested and not paused:
                        pause_started = control.get("pause_started_unix")
                        retroactive = (
                            max(0.0, time.time() - float(pause_started))
                            if isinstance(pause_started, (int, float))
                            else 0.0
                        )
                        attempt_clock.pause(retroactive_seconds=retroactive)
                        result = run_control(
                            ["docker", "pause", self.container_name],
                            capture_output=True,
                        )
                        if result.returncode != 0:
                            attempt_clock.resume()
                            self._gateway_monitor_error = "gateway_pause_failed"
                            run_control(
                                ["docker", "kill", self.container_name],
                                capture_output=True,
                            )
                            return
                        paused = True
                    elif not pause_requested and paused:
                        unpause = run_control(
                            ["docker", "unpause", self.container_name],
                            capture_output=True,
                        )
                        if self._solver_control_monitor is not None and unpause.returncode != 0:
                            raise RuntimeError("solver recovery could not unpause the agent")
                        attempt_clock.resume()
                        paused = False

                    if isinstance(terminal, dict):
                        self._gateway_terminal_error = dict(terminal)
                        # The container remains unable to observe the synthetic
                        # terminal response: freeze it before ending execution.
                        if not paused:
                            attempt_clock.pause()
                            run_control(
                                ["docker", "pause", self.container_name],
                                capture_output=True,
                            )
                            paused = True
                        run_control(
                            ["docker", "kill", self.container_name],
                            capture_output=True,
                        )
                        return
                    if action_limit_reached:
                        self._gateway_action_step_limit_reached = True
                        run_control(
                            ["docker", "kill", self.container_name],
                            capture_output=True,
                        )
                        return
                    if self._solver_control_monitor is not None:
                        if self._solver_control_monitor.acknowledge(paused=paused, clock=attempt_clock):
                            self.enforce_agent_deadline()
                            return
                    stop.wait(0.05)
            except Exception:
                logger.exception("External call monitor failed for %s", self.container_name)
                self._gateway_monitor_error = (
                    "external_call_control_failed" if self._solver_control_monitor is not None
                    else "gateway_pause_failed"
                )
                if self._solver_control_monitor is not None:
                    attempt_clock.cancel("external_call_control_failed")
                if not paused:
                    attempt_clock.resume()  # A Docker pause may have timed out after clock.pause().
                try:
                    run_control(["docker", "kill", self.container_name], capture_output=True)
                except subprocess.TimeoutExpired:
                    logger.error("Docker kill timed out after external-call control failure")
            finally:
                if paused:
                    try:
                        run_control(
                            ["docker", "unpause", self.container_name],
                            capture_output=True,
                        )
                    except subprocess.TimeoutExpired:
                        logger.error("Docker unpause timed out after external-call control failure")
                    finally:
                        attempt_clock.resume()

        thread = threading.Thread(
            target=monitor,
            name=f"gateway-monitor-{self.container_name[:40]}",
            daemon=True,
        )
        self._gateway_monitor_thread = thread
        thread.start()

    def stop_model_gateway_monitor(self) -> None:
        stop = self._gateway_monitor_stop
        thread = self._gateway_monitor_thread
        if stop is not None:
            stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._gateway_monitor_stop = None
        self._gateway_monitor_thread = None

    def gateway_terminal_infra_error(self) -> dict | None:
        if self._gateway_terminal_error is None:
            control = self._read_gateway_control()
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
            control = self._read_gateway_control()
            self._gateway_action_step_limit_reached = bool(
                control and control.get("action_step_limit_reached")
            )
        return self._gateway_action_step_limit_reached

    def _start_model_gateway(self) -> None:
        if not MODEL_GATEWAY_SCRIPT.is_file():
            raise RuntimeError(f"Model gateway script missing: {MODEL_GATEWAY_SCRIPT}")
        if not PROVIDER_REASONING_MODULE.is_file():
            raise RuntimeError(
                f"Provider reasoning module missing: {PROVIDER_REASONING_MODULE}"
            )
        if not INFRA_DIAGNOSTICS_PACKAGE.is_dir():
            raise RuntimeError(
                f"Infrastructure diagnostics package missing: {INFRA_DIAGNOSTICS_PACKAGE}"
            )
        gateway = self.adapter.model_gateway()
        control_path = self._stage_gateway_control()
        container_control_dir = "/run/benchmark-control"
        container_control_path = f"{container_control_dir}/state.json"
        container_cancel_path = f"{container_control_dir}/benchmark-cancelled"
        evidence_dir = (
            self.artifact_dir / "gateway"
            if self.artifact_dir is not None
            else control_path.parent / "evidence"
        )
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.chmod(0o700)
        for name in (
            "provider_reasoning.jsonl",
            "reasoning_capture_status.json",
        ):
            evidence_path = evidence_dir / name
            evidence_path.touch(exist_ok=True)
            evidence_path.chmod(0o600)
        self._gateway_evidence_dir = evidence_dir
        diagnostics_args: list[str] = [
            "-v",
            (
                f"{INFRA_DIAGNOSTICS_PACKAGE}:"
                f"{INFRA_DIAGNOSTICS_CONTAINER_PATH}:ro"
            ),
        ]
        if self.diagnostics_plan is not None:
            try:
                diagnostics_run_root = self.diagnostics_plan.run_root
                diagnostics_execution_dir = self.diagnostics_plan.execution_dir
                diagnostics_run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                diagnostics_execution_dir.mkdir(
                    parents=True, exist_ok=True, mode=0o700
                )
                diagnostics_run_root.chmod(0o700)
                diagnostics_execution_dir.chmod(0o700)
                container_diagnostics_root = "/run/infra-diagnostics"
                relative_execution = diagnostics_execution_dir.relative_to(
                    diagnostics_run_root
                )
                runtime_config = {
                    **self.diagnostics_plan.runtime_config,
                    "event_path": str(
                        Path(container_diagnostics_root)
                        / relative_execution
                        / "events.jsonl"
                    ),
                    "manifest_path": str(
                        Path(container_diagnostics_root)
                        / relative_execution
                        / "diagnostics_manifest.json"
                    ),
                    "run_budget_path": str(
                        Path(container_diagnostics_root) / ".run-bytes"
                    ),
                }
                diagnostics_config_path = (
                    control_path.parent / "infra-diagnostics.json"
                )
                diagnostics_config_path.write_text(
                    json.dumps(runtime_config, indent=2, ensure_ascii=False) + "\n"
                )
                diagnostics_config_path.chmod(0o600)
                container_diagnostics_config = (
                    f"{container_control_dir}/infra-diagnostics.json"
                )
                diagnostics_args.extend(
                    [
                        "-e",
                        (
                            "PDDL_GATEWAY_INFRA_DIAGNOSTICS_CONFIG="
                            f"{container_diagnostics_config}"
                        ),
                        "--mount",
                        (
                            f"type=bind,source={diagnostics_run_root},"
                            f"target={container_diagnostics_root}"
                        ),
                    ]
                )
            except OSError as exc:
                logger.warning(
                    "Infrastructure diagnostics disabled for %s: %s",
                    self.container_name,
                    exc,
                )
        container_evidence_dir = "/run/benchmark-evidence"
        transport = gateway.get("transport")
        entrypoint_host = MODEL_GATEWAY_SCRIPT
        entrypoint_container = MODEL_GATEWAY_CONTAINER_PATH
        runtime_command = ["python3", MODEL_GATEWAY_CONTAINER_PATH]
        transport_args: list[str] = []
        if transport == "logits-rest-openai-v1":
            runtime_python = LOGITS_BRIDGE_ENV_PATH / "bin" / "python"
            required = [LOGITS_GATEWAY_SCRIPT, LOGITS_BRIDGE_SCRIPT, runtime_python]
            missing = [str(path) for path in required if not path.is_file()]
            if missing or not LOGITS_MODEL_ASSETS_ROOT.is_dir():
                raise RuntimeError(
                    "Logits gateway runtime is incomplete. Run: bash "
                    "source/agent_formalizer/install_harnesses.sh logits"
                )
            entrypoint_host = LOGITS_GATEWAY_SCRIPT
            entrypoint_container = LOGITS_GATEWAY_CONTAINER_PATH
            runtime_command = [str(runtime_python), LOGITS_GATEWAY_CONTAINER_PATH]
            runtime_root = LOGITS_BRIDGE_ENV_PATH.parent
            transport_args.extend(
                [
                    "-e", f"PDDL_LOGITS_MODEL={gateway['upstream_model']}",
                    "-e", f"PDDL_LOGITS_BRIDGE_PORT={LOGITS_BRIDGE_PORT}",
                    "-e", "PDDL_LOGITS_ORIGIN=https://api.logits.dev",
                    "-e", f"PDDL_LOGITS_MODEL_ASSETS_ROOT={LOGITS_MODEL_ASSETS_ROOT}",
                    "-e", f"PDDL_LOGITS_LEDGER_PATH={container_control_dir}/logits.jsonl",
                    "-v", f"{LOGITS_BRIDGE_SCRIPT}:{LOGITS_BRIDGE_CONTAINER_PATH}:ro",
                    "-v", f"{MODEL_GATEWAY_SCRIPT}:{MODEL_GATEWAY_CONTAINER_PATH}:ro",
                    "-v", f"{runtime_root}:{runtime_root}:ro",
                ]
            )
            resolved_python = runtime_python.resolve()
            try:
                resolved_python.relative_to(runtime_root)
            except ValueError:
                resolved_home = resolved_python.parent.parent
                link_target = Path(os.readlink(runtime_python))
                if not link_target.is_absolute():
                    link_target = runtime_python.parent / link_target
                embedded_home = link_target.parent.parent
                transport_args.extend(
                    ["-v", f"{resolved_home}:{embedded_home}:ro"]
                )
        elif transport is not None:
            raise RuntimeError(f"Unsupported model gateway transport: {transport}")

        cmd = [
            "docker", "run", "-d", "--pull", "never",
            "--name", self.gateway_name,
            "--network", self.network_name,
            "--network-alias", MODEL_GATEWAY_HOST,
            "--add-host", "host.docker.internal:host-gateway",
            "-e", f"PDDL_GATEWAY_UPSTREAM_ORIGIN={gateway['upstream_origin']}",
            "-e", f"PDDL_GATEWAY_MAX_MODEL_CALLS={gateway['max_model_calls']}",
            "-e", f"PDDL_GATEWAY_MAX_ACTION_STEPS={gateway['max_action_steps']}",
            "-e", f"PDDL_GATEWAY_AUTH_MODE={gateway['auth_mode']}",
            "-e", f"PDDL_GATEWAY_PROVIDER={gateway.get('provider', 'unknown')}",
            "-e", "PDDL_GATEWAY_ALLOWED_MODELS=" + json.dumps(gateway["allowed_models"]),
            "-e", (
                "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES="
                + json.dumps(gateway["allowed_path_prefixes"])
            ),
            "-e", f"PDDL_GATEWAY_PORT={MODEL_GATEWAY_PORT}",
            "-e", (
                "PDDL_GATEWAY_MAX_TRANSIENT_RETRIES="
                + str(gateway["transient_error_policy"]["max_retries"])
            ),
            "-e", (
                "PDDL_GATEWAY_TRANSIENT_BACKOFF_SECONDS="
                + json.dumps(gateway["transient_error_policy"]["backoff_seconds"])
            ),
            "-e", (
                "PDDL_GATEWAY_MAX_RETRY_AFTER_SECONDS="
                + str(gateway["transient_error_policy"]["max_retry_after_seconds"])
            ),
            "-e", (
                "PDDL_GATEWAY_RETRYABLE_HTTP_STATUSES="
                + json.dumps(
                    gateway["transient_error_policy"]["retryable_http_statuses"]
                )
            ),
            "-e", (
                "PDDL_GATEWAY_REQUEST_OVERRIDES="
                + json.dumps(gateway.get("request_overrides", {}), sort_keys=True)
            ),
            "-e", f"PDDL_GATEWAY_CONTROL_FILE={container_control_path}",
            "-e", f"PDDL_GATEWAY_BENCHMARK_CANCEL_FILE={container_cancel_path}",
            "-e", (
                "PDDL_GATEWAY_RESPONSE_DELIVERY="
                + gateway.get("response_delivery", "buffered_atomic")
            ),
            "-e",
            (
                "PDDL_GATEWAY_REASONING_PATH="
                f"{container_evidence_dir}/provider_reasoning.jsonl"
            ),
            "-e",
            (
                "PDDL_GATEWAY_REASONING_STATUS_PATH="
                f"{container_evidence_dir}/reasoning_capture_status.json"
            ),
            "--mount",
            (
                f"type=bind,source={control_path.parent},"
                f"target={container_control_dir}"
            ),
            "--mount",
            (
                f"type=bind,source={evidence_dir},"
                f"target={container_evidence_dir}"
            ),
            "-v", f"{entrypoint_host}:{entrypoint_container}:ro",
            "-v", f"{EXTERNAL_CALLS_PACKAGE}:{EXTERNAL_CALLS_CONTAINER_PATH}:ro",
            "-v",
            (
                f"{PROVIDER_REASONING_MODULE}:"
                f"{PROVIDER_REASONING_CONTAINER_PATH}:ro"
            ),
        ]
        cmd.extend(diagnostics_args)
        cmd.extend(transport_args)
        if deadline_integration.selected(self.adapter):
            if transport == "logits-rest-openai-v1":
                raise RuntimeError("logical deadlines are not implemented for the logits bridge")
            cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}",
                        "-e", f"PDDL_GATEWAY_EXTERNAL_CALL_TIMING={deadline_integration.policy(self.adapter)}",
                        "-e", "PDDL_GATEWAY_LOGICAL_CONTROL_FILE=/run/benchmark-control/model-timing.json"])
        secret = self.adapter.model_gateway_secret()
        if secret:
            secret_path = self._stage_gateway_secret(secret)
            container_secret_path = "/run/secrets/pddl-model-api-key"
            cmd.extend([
                "-e", f"PDDL_GATEWAY_API_KEY_FILE={container_secret_path}",
                "--mount",
                (
                    f"type=bind,source={secret_path},"
                    f"target={container_secret_path},readonly"
                ),
            ])
        cmd.extend([self.image_name, *runtime_command])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start model gateway: {result.stderr.strip()}")
        self._gateway_started = True

        # Only sidecars receive an egress-capable attachment.
        result = subprocess.run(
            [
                "docker", "network", "connect", "--gw-priority", "1",
                "bridge", self.gateway_name,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to attach model gateway egress: {result.stderr.strip()}"
            )
        health = None
        health_attempts = 600 if transport == "logits-rest-openai-v1" else 50
        for _ in range(health_attempts):
            health = subprocess.run(
                [
                    "docker", "exec", self.gateway_name, "python3", "-c",
                    (
                        "import urllib.request; "
                        f"urllib.request.urlopen('http://127.0.0.1:{MODEL_GATEWAY_PORT}/"
                        "__benchmark__/health', timeout=2).read()"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if health.returncode == 0:
                break
            time.sleep(0.1)
        else:
            error = health.stderr.strip() if health else "unknown startup error"
            raise RuntimeError(f"Model gateway did not become ready: {error}")
        if deadline_integration.selected(self.adapter) and read_json(control_path.parent / "model-timing.json") is None:
            raise RuntimeError("model logical-deadline control is not readable by the host monitor")

    def _start_web_gateway(self) -> None:
        if not WEB_GATEWAY_SCRIPT.is_file():
            raise RuntimeError(f"Controlled-web gateway missing: {WEB_GATEWAY_SCRIPT}")
        allowlist = self.adapter.network_policy()["controlled_web_allowlist"]
        cmd = [
            "docker", "run", "-d", "--pull", "never",
            "--name", self.web_gateway_name,
            "--network", self.network_name,
            "--network-alias", WEB_GATEWAY_HOST,
            "--add-host", "host.docker.internal:host-gateway",
            "-e", f"PDDL_WEB_GATEWAY_PORT={WEB_GATEWAY_PORT}",
            "-e", "PDDL_WEB_GATEWAY_ALLOWLIST=" + json.dumps(allowlist),
            "-v", f"{WEB_GATEWAY_SCRIPT}:{WEB_GATEWAY_CONTAINER_PATH}:ro",
            self.image_name, "python3", WEB_GATEWAY_CONTAINER_PATH,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to start controlled-web gateway: {result.stderr.strip()}"
            )
        self._web_gateway_started = True
        result = subprocess.run(
            [
                "docker", "network", "connect", "--gw-priority", "1",
                "bridge", self.web_gateway_name,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to attach controlled-web gateway egress: {result.stderr.strip()}"
            )
        for _ in range(50):
            health = subprocess.run(
                [
                    "docker", "exec", self.web_gateway_name, "python3", "-c",
                    (
                        "import urllib.request; "
                        f"urllib.request.urlopen('http://127.0.0.1:{WEB_GATEWAY_PORT}/"
                        "__benchmark__/health',timeout=2).read()"
                    ),
                ],
                capture_output=True, text=True, timeout=5,
            )
            if health.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Controlled-web gateway did not become ready")

    def _start_tool_gateway(self, spec) -> None:
        """Start one optional tool sidecar (currently used by pddl_solver)."""
        if not spec.gateway_dir_host.is_dir():
            raise RuntimeError(f"agent tool package missing: {spec.gateway_dir_host}")
        entry = spec.gateway_dir_host / spec.gateway_entrypoint
        if not entry.is_file():
            raise RuntimeError(f"agent tool gateway entrypoint missing: {entry}")
        container_entry = f"{spec.gateway_dir_container.rstrip('/')}/{spec.gateway_entrypoint}"
        # One named container per attempt for the solver tool today.
        name = self.solver_gateway_name
        external_args = ["-v", f"{EXTERNAL_CALLS_PACKAGE}:{EXTERNAL_CALLS_CONTAINER_PATH}:ro"]
        resolved = getattr(getattr(self.adapter, "resolved_config", None), "raw", {}).get("resolved", {})
        policy = resolved.get("solver_error_routing")
        if policy:
            if self._gateway_control_dir is None or self._gateway_evidence_dir is None:
                raise RuntimeError("solver recovery requires model gateway control and evidence")
            self._solver_control_monitor = ToolControlMonitor(self._gateway_control_dir / "solver.json")
            external_args.extend([
                # Private 0600 control/evidence must remain readable by the
                # host monitor; root-owned bind outputs break the handshake.
                "--user", f"{os.getuid()}:{os.getgid()}",
                "-e", f"PDDL_SOLVER_ERROR_ROUTING={policy}",
                "-e", f"PDDL_SOLVER_EXTERNAL_CALL_TIMING={deadline_integration.policy(self.adapter) or ''}",
                "-e", "PDDL_SOLVER_CONTROL_FILE=/run/benchmark-control/solver.json",
                "-e", "PDDL_SOLVER_CANCEL_FILE=/run/benchmark-control/benchmark-cancelled",
                "-e", "PDDL_SOLVER_EVIDENCE_DIR=/run/benchmark-evidence/solver_calls",
                "-v", f"{self._gateway_control_dir}:/run/benchmark-control",
                "-v", f"{self._gateway_evidence_dir}:/run/benchmark-evidence",
            ])
        cmd = [
            "docker", "run", "-d", "--pull", "never",
            "--name", name,
            "--network", self.network_name,
            "--network-alias", spec.gateway_host,
            "--add-host", "host.docker.internal:host-gateway",
            "-e", f"PDDL_SOLVER_GATEWAY_PORT={spec.gateway_port}",
            "-e", (
                "PDDL_SOLVER_UPSTREAM_BASE="
                + self.adapter.solver_upstream_base(containerized=True)
            ),
            "-e", (
                "PDDL_SOLVER_UPSTREAM_HEALTH_REQUIRED="
                + ("1" if self.adapter.solver_backend() == "local" else "0")
            ),
            "-v", f"{spec.gateway_dir_host}:{spec.gateway_dir_container}:ro",
            *external_args,
            self.image_name, "python3", container_entry,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to start {spec.tool_id} gateway: {result.stderr.strip()}"
            )
        self._solver_gateway_started = True
        result = subprocess.run(
            [
                "docker", "network", "connect", "--gw-priority", "1",
                "bridge", name,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to attach {spec.tool_id} gateway egress: {result.stderr.strip()}"
            )
        for _ in range(50):
            health = subprocess.run(
                [
                    "docker", "exec", name, "python3", "-c",
                    (
                        "import urllib.request; "
                        f"urllib.request.urlopen('http://127.0.0.1:{spec.gateway_port}/"
                        "__benchmark__/health', timeout=2).read()"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if health.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"{spec.tool_id} gateway did not become ready")
        if self._solver_control_monitor is not None and read_json(self._solver_control_monitor.path) is None:
            raise RuntimeError("solver recovery control is not readable by the host monitor")

    def model_gateway_stats(self) -> dict:
        if not self._gateway_started:
            return {}
        code = (
            "import urllib.request; "
            f"print(urllib.request.urlopen('http://127.0.0.1:{MODEL_GATEWAY_PORT}/"
            "__benchmark__/status', timeout=5).read().decode())"
        )
        result = subprocess.run(
            ["docker", "exec", self.gateway_name, "python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "gateway status unavailable"}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": "gateway returned invalid status"}

    def model_gateway_ledger(self) -> list[dict]:
        """Return the secret-free per-request ledger from inside the sidecar."""
        if not self._gateway_started:
            return []
        code = (
            "import urllib.request; "
            f"print(urllib.request.urlopen('http://127.0.0.1:{MODEL_GATEWAY_PORT}/"
            "__benchmark__/ledger', timeout=5).read().decode())"
        )
        result = subprocess.run(
            ["docker", "exec", self.gateway_name, "python3", "-c", code],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            return []
        try:
            return list(json.loads(result.stdout).get("ledger", []))
        except (json.JSONDecodeError, TypeError):
            return []

    def validate_network_policy(self) -> dict:
        """Exercise the effective network boundary before harness timing."""
        tests: dict[str, bool] = {}
        inspected = subprocess.run(
            ["docker", "network", "inspect", self.network_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
        try:
            network_record = json.loads(inspected.stdout)[0]
        except (json.JSONDecodeError, IndexError, TypeError):
            network_record = {}
        tests["agent_network_is_internal"] = (
            inspected.returncode == 0 and network_record.get("Internal") is True
        )
        health = self.run_in_container(
            "python3 -c "
            + shlex.quote(
                f"import urllib.request; urllib.request.urlopen('http://{MODEL_GATEWAY_HOST}:"
                f"{MODEL_GATEWAY_PORT}/__benchmark__/health',timeout=3).read()"
            ),
            timeout=10,
        )
        tests["model_gateway_reachable"] = health.exit_code == 0
        for spec in resolve_agent_tools(self.adapter.runtime_tools()):
            solver_health = self.run_in_container(
                "python3 -c "
                + shlex.quote(
                    f"import urllib.request; urllib.request.urlopen('http://{spec.gateway_host}:"
                    f"{spec.gateway_port}/__benchmark__/health',timeout=3).read()"
                ),
                timeout=10,
            )
            tests[f"{spec.tool_id}_gateway_reachable"] = solver_health.exit_code == 0
            cli = self.run_in_container(
                f"test -x {shlex.quote(spec.cli_container_path)} && "
                f"{shlex.quote(spec.cli_container_path)} --help >/dev/null",
                timeout=10,
            )
            tests[f"{spec.tool_id}_cli_present"] = cli.exit_code == 0
        direct_ip = self.run_in_container(
            "python3 -c "
            + shlex.quote(
                "import socket; socket.create_connection(('1.1.1.1',443),3)"
            ),
            timeout=10,
        )
        tests["direct_public_ip_blocked"] = direct_ip.exit_code != 0
        host_gateway = self.run_in_container(
            "python3 -c "
            + shlex.quote(
                "import socket; socket.getaddrinfo('host.docker.internal',80)"
            ),
            timeout=10,
        )
        tests["host_gateway_unavailable"] = host_gateway.exit_code != 0
        direct_http = self.run_in_container(
            "python3 -c "
            + shlex.quote(
                "import urllib.request; "
                "urllib.request.build_opener(urllib.request.ProxyHandler({})).open("
                "'http://example.com',timeout=3).read()"
            ),
            timeout=10,
        )
        tests["proxy_bypass_blocked"] = direct_http.exit_code != 0
        connect = self.run_in_container(
            "python3 -c "
            + shlex.quote(
                "import http.client; "
                f"c=http.client.HTTPConnection('{MODEL_GATEWAY_HOST}',{MODEL_GATEWAY_PORT},timeout=3); "
                "c.set_tunnel('example.com',443); c.request('GET','/'); c.getresponse()"
            ),
            timeout=10,
        )
        tests["model_gateway_connect_rejected"] = connect.exit_code != 0
        if self.adapter.network_mode == "controlled_web":
            proxy_health = self.run_in_container(
                "python3 -c "
                + shlex.quote(
                    f"import urllib.request; urllib.request.urlopen('http://{WEB_GATEWAY_HOST}:"
                    f"{WEB_GATEWAY_PORT}/__benchmark__/health',timeout=3).read()"
                ),
                timeout=10,
            )
            tests["controlled_web_gateway_reachable"] = proxy_health.exit_code == 0
            unlisted = self.run_in_container(
                "python3 -c "
                + shlex.quote(
                    "import urllib.request; urllib.request.urlopen("
                    "'http://not-allowlisted.invalid',timeout=3).read()"
                ),
                timeout=10,
            )
            tests["controlled_web_unlisted_host_rejected"] = unlisted.exit_code != 0
        return {
            "preset": "network-model-only",
            "version": 2,
            "mode": self.adapter.network_mode,
            "status": "pass" if all(tests.values()) else "fail",
            "tests": tests,
        }

    def validate_environment_policy(self) -> dict:
        """Verify fixed env/proxy semantics and gateway-only real credentials."""
        result = self.run_in_container("env", timeout=10)
        values: dict[str, str] = {}
        if result.exit_code == 0:
            for line in result.stdout.splitlines():
                name, separator, value = line.partition("=")
                if separator:
                    values[name] = value

        fixed = self.adapter.resolved_config.raw["resolved"]["environment"]["fixed"]
        tests = {
            "container_env_readable": result.exit_code == 0,
            "fixed_environment_exact": all(values.get(k) == v for k, v in fixed.items()),
        }
        secret = self.adapter.model_gateway_secret()
        tests["real_model_secret_absent"] = not secret or all(
            secret not in value for value in values.values()
        )
        proxy_names = {
            "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "no_proxy",
        }
        present_proxy_names = sorted(proxy_names.intersection(values))
        if self.adapter.network_mode == "model_only":
            tests["proxy_environment_absent"] = not present_proxy_names
        else:
            expected = f"http://{WEB_GATEWAY_HOST}:{WEB_GATEWAY_PORT}"
            no_proxy = ["model-gateway", "web-gateway"]
            for spec in resolve_agent_tools(self.adapter.runtime_tools()):
                no_proxy.append(spec.gateway_host)
            no_proxy.extend(["127.0.0.1", "localhost"])
            tests["controlled_proxy_environment_exact"] = all(
                values.get(name) == expected
                for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
            ) and values.get("NO_PROXY") == ",".join(no_proxy)
        return {
            "preset": "environment-isolation",
            "version": 1,
            "status": "pass" if all(tests.values()) else "fail",
            "tests": tests,
            "environment_names": sorted(values),
            "proxy_environment_names": present_proxy_names,
        }

    def validate_action_step_guard(self) -> dict:
        stats = self.model_gateway_stats()
        expected_model_calls = self.adapter.max_model_calls
        expected_action_steps = self.adapter.max_action_steps
        expected_routing = self.adapter.resolved_config.model_error_routing
        expected_delivery = self.adapter.resolved_config.model_response_delivery["mode"]
        reported_routing = stats.get("transient_policy", {})
        expected_gateway_routing = {
            "max_retries": expected_routing["max_retries"],
            "backoff_seconds": expected_routing["backoff_seconds"],
            "max_retry_after_seconds": expected_routing["max_retry_after_seconds"],
            "retryable_http_statuses": expected_routing["retryable_http_statuses"],
        }
        passed = (
            stats.get("max_model_calls") == expected_model_calls
            and stats.get("max_action_steps") == expected_action_steps
            and stats.get("model_calls") == 0
            and stats.get("tool_calls") == 0
            and stats.get("action_steps") == 0
            and reported_routing == expected_gateway_routing
            and stats.get("streaming_mode") == expected_delivery
        )
        return {
            "preset": "action-step-guard",
            "version": 2 if expected_delivery == "native_streaming" else 1,
            "status": "pass" if passed else "fail",
            "configured_model_call_limit": expected_model_calls,
            "gateway_reported_model_call_limit": stats.get("max_model_calls"),
            "configured_action_step_limit": expected_action_steps,
            "gateway_reported_action_step_limit": stats.get("max_action_steps"),
            "configured_transient_policy": expected_gateway_routing,
            "gateway_reported_transient_policy": reported_routing,
            "configured_response_delivery": expected_delivery,
            "gateway_reported_response_delivery": stats.get("streaming_mode"),
        }

    def validate_state_isolation(self) -> dict:
        """Verify every host mount is either attempt-private or immutable.

        Read-only runtime, binary, and tool mounts are reproducible baselines;
        writable container-layer state is discarded with the per-attempt
        container. Any undeclared writable *or read-only* bind fails, since a
        read-only mount of prior sessions would still leak cross-case data.
        """
        spec = self.adapter.state_isolation_spec(self.instance_id)
        inspected = subprocess.run(
            ["docker", "inspect", self.container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        mounts: list[dict] = []
        inspect_ok = inspected.returncode == 0
        if inspect_ok:
            try:
                payload = json.loads(inspected.stdout)
                mounts = payload[0].get("Mounts", [])
                inspect_ok = isinstance(mounts, list)
            except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                inspect_ok = False

        def resolved(path: str) -> str:
            return str(Path(path).resolve())

        writable_binds = sorted(
            {
                resolved(mount["Source"])
                for mount in mounts
                if isinstance(mount, dict)
                and mount.get("Type") == "bind"
                and mount.get("RW") is True
                and isinstance(mount.get("Source"), str)
            }
        )
        readonly_binds = sorted(
            {
                resolved(mount["Source"])
                for mount in mounts
                if isinstance(mount, dict)
                and mount.get("Type") == "bind"
                and mount.get("RW") is False
                and isinstance(mount.get("Source"), str)
            }
        )
        non_bind_mounts = [
            mount for mount in mounts
            if isinstance(mount, dict) and mount.get("Type") != "bind"
        ]
        expected_binds = sorted(
            {resolved(path) for path in spec.get("writable_bind_sources", [])}
        )
        expected_private_readonly = sorted(
            {
                resolved(path)
                for path in spec.get("private_readonly_bind_sources", [])
            }
        )
        expected_shared_readonly = {
            resolved(path)
            for path in spec.get("shared_readonly_bind_sources", [])
        }
        expected_shared_readonly.update(
            resolved(tool_spec.cli_host_path)
            for tool_spec in resolve_agent_tools(self.adapter.runtime_tools())
        )
        if self._deadline_bundle is not None:
            expected_shared_readonly.add(resolved(str(self._deadline_bundle)))
            expected_private_readonly.append(resolved(str(self._deadline_directory)))
        expected_readonly = sorted(
            {*expected_private_readonly, *expected_shared_readonly}
        )
        attempt_root_value = spec.get("attempt_root")
        attempt_root = (
            Path(attempt_root_value).resolve() if attempt_root_value else None
        )
        expected_under_attempt_root = True
        if attempt_root is not None:
            for source in [*expected_binds, *expected_private_readonly]:
                try:
                    Path(source).relative_to(attempt_root)
                except ValueError:
                    expected_under_attempt_root = False
                    break

        adapter_tests = dict(spec.get("tests", {}))
        tests = {
            "container_inspect_succeeded": inspect_ok,
            "isolation_mode_is_explicit": spec.get("mode") == "isolated",
            "scope_is_per_attempt": spec.get("scope") == "per_attempt",
            "personal_harness_state_excluded": (
                spec.get("personal_harness_state") == "excluded"
            ),
            "cross_attempt_reuse_disabled": (
                spec.get("cross_attempt_reuse") is False
            ),
            "writable_bind_mounts_exact": writable_binds == expected_binds,
            "readonly_bind_mounts_exact": readonly_binds == expected_readonly,
            "undeclared_volume_or_other_mounts_absent": not non_bind_mounts,
            "declared_bind_mounts_exist": all(
                Path(path).exists()
                for path in [*expected_binds, *expected_readonly]
            ),
            "declared_bind_mounts_under_attempt_root": (
                expected_under_attempt_root
            ),
            **adapter_tests,
        }
        return {
            "preset": "state-isolation",
            "version": 1,
            "status": "pass" if all(tests.values()) else "fail",
            "implementation": (
                "per-attempt container plus exact private/immutable bind allowlists"
            ),
            "mode": spec.get("mode"),
            "attempt_root": str(attempt_root) if attempt_root else None,
            "expected_writable_bind_sources": expected_binds,
            "observed_writable_bind_sources": writable_binds,
            "expected_readonly_bind_sources": expected_readonly,
            "observed_readonly_bind_sources": readonly_binds,
            "tests": tests,
        }

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def run_in_container(self, cmd: str, timeout: int = 300) -> ExecResult:
        """Execute a bash command inside the container."""
        try:
            result = subprocess.run(
                ["docker", "exec", self.container_name, "bash", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ExecResult(result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out after %ds: %s", timeout, cmd[:100])
            return ExecResult("", "TIMEOUT", -1)

    def copy_from_container(self, container_path: str, host_path: str) -> bool:
        result = subprocess.run(
            ["docker", "cp", f"{self.container_name}:{container_path}", host_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            logger.warning(
                "docker cp from %s:%s failed: %s",
                self.container_name,
                container_path,
                detail or f"exit {result.returncode}",
            )
            return False
        return True

    def copy_to_container(self, host_path: str, container_path: str) -> bool:
        result = subprocess.run(
            ["docker", "cp", host_path, f"{self.container_name}:{container_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            logger.warning(
                "docker cp to %s:%s failed: %s",
                self.container_name,
                container_path,
                detail or f"exit {result.returncode}",
            )
            return False
        return True

    # ------------------------------------------------------------------
    # PDDL-formalizer specifics
    # ------------------------------------------------------------------

    def seed_workspace(self, domain_description: str, problem_description: str) -> None:
        """Create the workspace dir and drop the textual descriptions in it.

        The descriptions are also embedded directly in the prompt, but having
        them on disk lets the agent re-read them with its own file tools.
        """
        created = self.run_in_container(
            f"mkdir -p {shlex.quote(CONTAINER_WORKSPACE)}/input"
        )
        if created.exit_code != 0:
            raise RuntimeError(f"task seed mkdir failed: {created.stderr}")
        domain_ok = self.write_text_file(
            f"{CONTAINER_WORKSPACE}/input/domain_description.txt", domain_description
        )
        problem_ok = self.write_text_file(
            f"{CONTAINER_WORKSPACE}/input/problem_description.txt", problem_description
        )
        if not domain_ok or not problem_ok:
            raise RuntimeError("task seed file write failed")

    def write_text_file(self, container_path: str, content: str) -> bool:
        """Write ``content`` to ``container_path`` via a heredoc-free stdin pipe."""
        proc = subprocess.run(
            ["docker", "exec", "-i", self.container_name,
             "bash", "-c", f"cat > {shlex.quote(container_path)}"],
            input=content,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.warning("Failed to seed %s: %s", container_path, proc.stderr)
            return False
        return True

    def read_pddl_outputs(self) -> tuple[str | None, str | None]:
        """Read the agent-authored domain/problem files from the workspace.

        Returns ``(domain_file, problem_file)``; either may be None if missing.
        """
        domain = self._read_file(f"{CONTAINER_WORKSPACE}/{DOMAIN_OUTPUT_NAME}")
        problem = self._read_file(f"{CONTAINER_WORKSPACE}/{PROBLEM_OUTPUT_NAME}")
        return domain, problem

    def freeze_pddl_outputs(self) -> dict[str, bytes | None]:
        """Atomically snapshot official delivery files without rewriting bytes."""
        artifact = self.adapter.resolved_config.raw["resolved"]["artifact_contract"]
        names = {
            "domain": artifact["workspace_domain_file"],
            "problem": artifact["workspace_problem_file"],
        }
        paused = False
        pause = subprocess.run(
            ["docker", "pause", self.container_name], capture_output=True
        )
        paused = pause.returncode == 0
        outputs: dict[str, bytes | None] = {}
        try:
            with tempfile.TemporaryDirectory(prefix="pddl-artifact-freeze-") as temp:
                root = Path(temp)
                for role, name in names.items():
                    destination = root / name
                    copied = self.copy_from_container(
                        f"{CONTAINER_WORKSPACE}/{name}", str(destination)
                    )
                    outputs[role] = destination.read_bytes() if copied else None
        finally:
            if paused:
                subprocess.run(
                    ["docker", "unpause", self.container_name], capture_output=True
                )
        return outputs

    def _read_file(self, container_path: str) -> str | None:
        result = self.run_in_container(f"cat {shlex.quote(container_path)}")
        if result.exit_code != 0:
            return None
        return result.stdout
