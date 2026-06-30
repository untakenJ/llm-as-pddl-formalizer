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

import logging
import shlex
import subprocess
from dataclasses import dataclass

from agent_formalizer.config import (
    BASE_IMAGE,
    CONTAINER_MEMORY,
    CONTAINER_PIDS_LIMIT,
    CONTAINER_WORKSPACE,
    DOMAIN_OUTPUT_NAME,
    PROBLEM_OUTPUT_NAME,
)

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
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> str:
        """Start the Docker container. Returns the container name."""
        # Remove any stale container with the same name.
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
        )

        logger.info("Starting container %s from image %s",
                    self.container_name, self.image_name)
        cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "--pids-limit", str(CONTAINER_PIDS_LIMIT),
            "--memory", CONTAINER_MEMORY,
            "--memory-swap", CONTAINER_MEMORY,  # no swap: cgroup-OOM stays in-container
            "--add-host", "host.docker.internal:host-gateway",
        ]
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
        if not self._started:
            return
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
        )
        self._started = False
        logger.debug("Removed container %s", self.container_name)

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
        )
        return result.returncode == 0

    def copy_to_container(self, host_path: str, container_path: str) -> bool:
        result = subprocess.run(
            ["docker", "cp", host_path, f"{self.container_name}:{container_path}"],
            capture_output=True,
        )
        return result.returncode == 0

    # ------------------------------------------------------------------
    # PDDL-formalizer specifics
    # ------------------------------------------------------------------

    def seed_workspace(self, domain_description: str, problem_description: str) -> None:
        """Create the workspace dir and drop the textual descriptions in it.

        The descriptions are also embedded directly in the prompt, but having
        them on disk lets the agent re-read them with its own file tools.
        """
        self.run_in_container(f"mkdir -p {shlex.quote(CONTAINER_WORKSPACE)}/input")
        self._write_file(
            f"{CONTAINER_WORKSPACE}/input/domain_description.txt", domain_description
        )
        self._write_file(
            f"{CONTAINER_WORKSPACE}/input/problem_description.txt", problem_description
        )

    def _write_file(self, container_path: str, content: str) -> None:
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

    def read_pddl_outputs(self) -> tuple[str | None, str | None]:
        """Read the agent-authored domain/problem files from the workspace.

        Returns ``(domain_file, problem_file)``; either may be None if missing.
        """
        domain = self._read_file(f"{CONTAINER_WORKSPACE}/{DOMAIN_OUTPUT_NAME}")
        problem = self._read_file(f"{CONTAINER_WORKSPACE}/{PROBLEM_OUTPUT_NAME}")
        return domain, problem

    def _read_file(self, container_path: str) -> str | None:
        result = self.run_in_container(f"cat {shlex.quote(container_path)}")
        if result.exit_code != 0:
            return None
        return result.stdout
