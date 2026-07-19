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

import json
import logging
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from agent_formalizer.config import (
    BASE_IMAGE,
    CONTAINER_WORKSPACE,
    DOMAIN_OUTPUT_NAME,
    MODEL_GATEWAY_CONTAINER_PATH,
    MODEL_GATEWAY_HOST,
    MODEL_GATEWAY_PORT,
    MODEL_GATEWAY_SCRIPT,
    PROBLEM_OUTPUT_NAME,
    WEB_GATEWAY_CONTAINER_PATH,
    WEB_GATEWAY_HOST,
    WEB_GATEWAY_PORT,
    WEB_GATEWAY_SCRIPT,
)
from agent_formalizer.tools import resolve_agent_tools

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    """Result of a command executed inside a container."""

    stdout: str
    stderr: str
    exit_code: int


class AgentWorkspace:
    """Manages a single Docker container for one formalization problem."""

    def __init__(self, instance_id: str, container_name: str, adapter,
                 image: str | None = None):
        self.instance_id = instance_id
        self.adapter = adapter
        self.image_name = image or BASE_IMAGE
        self.container_name = container_name
        self.network_name = f"{container_name[:100]}-net"
        self.gateway_name = f"{container_name[:94]}-model-gateway"
        self.web_gateway_name = f"{container_name[:96]}-web-gateway"
        self.solver_gateway_name = f"{container_name[:94]}-solver-gateway"
        self._started = False
        self._network_created = False
        self._gateway_started = False
        self._web_gateway_started = False
        self._solver_gateway_started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> str:
        """Start the Docker container. Returns the container name."""
        self._remove_stale_resources()
        self._create_network()
        self._start_model_gateway()
        if self.adapter.network_mode == "controlled_web":
            self._start_web_gateway()
        tool_specs = resolve_agent_tools(self.adapter.agent_tools())
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
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "rm", "-f", self.gateway_name],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "rm", "-f", self.web_gateway_name], capture_output=True
        )
        subprocess.run(
            ["docker", "rm", "-f", self.solver_gateway_name], capture_output=True
        )
        subprocess.run(
            ["docker", "network", "rm", self.network_name],
            capture_output=True,
        )
        self._started = False
        self._gateway_started = False
        self._web_gateway_started = False
        self._solver_gateway_started = False
        self._network_created = False
        logger.debug("Removed container %s", self.container_name)

    def enforce_agent_deadline(self) -> None:
        """Freeze actions, cut the model route, then stop the complete tree."""
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
        for name in (
            self.container_name,
            self.gateway_name,
            self.web_gateway_name,
            self.solver_gateway_name,
        ):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
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

    def _start_model_gateway(self) -> None:
        if not MODEL_GATEWAY_SCRIPT.is_file():
            raise RuntimeError(f"Model gateway script missing: {MODEL_GATEWAY_SCRIPT}")
        gateway = self.adapter.model_gateway()
        cmd = [
            "docker", "run", "-d", "--pull", "never",
            "--name", self.gateway_name,
            "--network", self.network_name,
            "--network-alias", MODEL_GATEWAY_HOST,
            "--add-host", "host.docker.internal:host-gateway",
            "-e", f"PDDL_GATEWAY_UPSTREAM_ORIGIN={gateway['upstream_origin']}",
            "-e", f"PDDL_GATEWAY_MAX_MODEL_CALLS={gateway['max_model_calls']}",
            "-e", f"PDDL_GATEWAY_AUTH_MODE={gateway['auth_mode']}",
            "-e", "PDDL_GATEWAY_ALLOWED_MODELS=" + json.dumps(gateway["allowed_models"]),
            "-e", (
                "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES="
                + json.dumps(gateway["allowed_path_prefixes"])
            ),
            "-e", f"PDDL_GATEWAY_PORT={MODEL_GATEWAY_PORT}",
            "-v", f"{MODEL_GATEWAY_SCRIPT}:{MODEL_GATEWAY_CONTAINER_PATH}:ro",
        ]
        secret = self.adapter.model_gateway_secret()
        if secret:
            cmd.extend(["-e", f"PDDL_GATEWAY_API_KEY={secret}"])
        cmd.extend([self.image_name, "python3", MODEL_GATEWAY_CONTAINER_PATH])
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
        for _ in range(50):
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
        cmd = [
            "docker", "run", "-d", "--pull", "never",
            "--name", name,
            "--network", self.network_name,
            "--network-alias", spec.gateway_host,
            "--add-host", "host.docker.internal:host-gateway",
            "-e", f"PDDL_SOLVER_GATEWAY_PORT={spec.gateway_port}",
            "-v", f"{spec.gateway_dir_host}:{spec.gateway_dir_container}:ro",
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
        for spec in resolve_agent_tools(self.adapter.agent_tools()):
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
            for spec in resolve_agent_tools(self.adapter.agent_tools()):
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

    def validate_model_call_guard(self) -> dict:
        stats = self.model_gateway_stats()
        expected = self.adapter.max_model_calls
        passed = stats.get("max_model_calls") == expected
        return {
            "preset": "model-call-guard",
            "version": 1,
            "status": "pass" if passed else "fail",
            "configured_limit": expected,
            "gateway_reported_limit": stats.get("max_model_calls"),
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
