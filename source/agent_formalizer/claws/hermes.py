"""Hermes Agent adapter with benchmark-owned configuration and state."""

from __future__ import annotations

import json
import logging
import shlex
import shutil
import sqlite3
from pathlib import Path

from agent_formalizer.claws.common import (
    INTERNAL_API_KEY_ENV,
    EnvConfiguredAdapter,
    PythonRuntimeMixin,
    run_captured_agent,
    safe_component,
)
from agent_formalizer.config import CONTAINER_WORKSPACE, HERMES_ENV_PATH
from agent_formalizer.optional_evidence import inspect_sqlite_analysis_fields
from agent_formalizer.result_types import AgentResult

logger = logging.getLogger(__name__)

HERMES_HOME = "/tmp/hermes-pddl-benchmark"
HERMES_STATE_DB = "state.db"
HERMES_SNAPSHOT_DB = "state.snapshot.db"

HERMES_PROVIDER_MAP = {
    "openai": "openai-api",
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "gemini": "gemini",
    "google-vertex": "custom",
    "deepseek": "deepseek",
    "logits": "custom",
    "dashscope": "alibaba",
}


class HermesAdapter(PythonRuntimeMixin, EnvConfiguredAdapter):
    """Run Hermes in-container without reading ``~/.hermes``."""

    name = "hermes"
    runtime_env = HERMES_ENV_PATH
    install_target = "hermes"

    @property
    def hermes_provider(self) -> str:
        try:
            return HERMES_PROVIDER_MAP[self.provider]
        except KeyError as exc:
            raise ValueError(
                f"Hermes has no provider mapping for '{self.raw_provider}'."
            ) from exc

    def validate_runtime(self) -> None:
        super().validate_runtime()
        self.validate_python_runtime()
        self.hermes_provider

    def container_run_args(self, instance_id: str) -> list[str]:
        return self.python_runtime_mount_args()

    @staticmethod
    def _task_home(instance_id: str) -> str:
        """Return the in-container Hermes home owned by one problem run."""
        if not instance_id:
            raise ValueError("Hermes requires a non-empty problem instance_id")
        return f"{HERMES_HOME}/{safe_component(instance_id)}"

    def post_container_start(self, workspace) -> None:
        task_home = self._task_home(workspace.instance_id)
        result = workspace.run_in_container(
            f"mkdir -p {shlex.quote(task_home + '/sessions')}"
        )
        if result.exit_code != 0:
            raise RuntimeError(
                f"Failed to create isolated Hermes home: {result.stderr}"
            )
        if not workspace.write_text_file(
            f"{task_home}/config.yaml",
            json.dumps(self._benchmark_config(), indent=2) + "\n",
        ):
            raise RuntimeError("Failed to provision isolated Hermes config")

    def _benchmark_config(self) -> dict:
        model_config = {
            "default": self.openai_compatible_model,
            "provider": self.hermes_provider,
            "base_url": self.api_base,
        }
        if self.is_google_vertex:
            # Hermes expands ${...} at config-load time. Empty Authorization
            # overrides the OpenAI SDK's Bearer header so Vertex authenticates
            # only through x-goog-api-key.
            model_config["default_headers"] = {
                "Authorization": "",
                "x-goog-api-key": f"${{{INTERNAL_API_KEY_ENV}}}",
            }
        return {
            "model": {
                **model_config,
            },
            "agent": {
                "verbose": False,
            },
            "terminal": {
                "backend": "local",
                "cwd": CONTAINER_WORKSPACE,
                "home_mode": "workspace",
            },
            "plugins": {"enabled": [], "disabled": []},
            "skills": {"external_dirs": [], "inline_shell": False},
        }

    def tool_policy(self) -> dict:
        return {
            "toolsets": "native-default",
            "rules": "official-clean-home",
            "plugins": "disabled",
            "state": "per-problem-home-in-throwaway-container",
            "workspace": CONTAINER_WORKSPACE,
        }

    def effective_config(self) -> dict:
        value = super().effective_config()
        value["harness_config"] = self._benchmark_config()
        return value

    def runtime_info(self) -> dict:
        return {
            **super().runtime_info(),
            **self.python_runtime_info("hermes-agent"),
        }

    def skills_info(self) -> dict:
        from agent_formalizer.provenance import file_manifest

        packages = sorted(
            (self.runtime_env / "lib").glob("python*/site-packages/hermes_cli")
        )
        package = packages[0] if packages else None
        paths = [package / "default_soul.py"] if package else []
        return {
            "mode": self.skills_mode,
            "baseline": "official-empty-user-home",
            "external_dirs": [],
            "inline_shell": False,
            "runtime_seeds_default_soul": True,
            "manifest": (
                file_manifest(paths, root=package.parent) if package else []
            ),
        }

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        task_home = self._task_home(instance_id or "")
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = artifact_dir / "agent_stdout.log" if artifact_dir else None
        stderr_path = artifact_dir / "agent_stderr.log" if artifact_dir else None

        argv = [
            "hermes",
            "chat",
            "-q",
            prompt,
            "--quiet",
            "--yolo",
            "--provider",
            self.hermes_provider,
            "--model",
            self.openai_compatible_model,
        ]
        code = (
            "import sys; "
            f"sys.argv = {argv!r}; "
            "from hermes_cli.main import main; "
            "raise SystemExit(main())"
        )
        cmd = ["docker", "exec", "-w", CONTAINER_WORKSPACE]
        extra_env = {
            "HERMES_HOME": task_home,
            "HERMES_ENABLE_PROJECT_PLUGINS": "0",
            "NO_COLOR": "1",
        }
        if self.is_google_vertex:
            # The custom OpenAI-compatible transport requires a non-empty SDK
            # key even though the benchmark header above is authoritative.
            extra_env.update(
                {
                    "OPENAI_API_KEY": "vertex-auth-via-x-goog-api-key",
                    "OPENAI_BASE_URL": self.api_base,
                }
            )
        cmd.extend(self.docker_exec_env_args(extra_env))
        cmd.extend([container_name, str(self.runtime_python), "-c", code])
        return run_captured_agent(
            cmd,
            timeout=self.remaining_timeout(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            container_name=container_name,
            attempt_clock=self.current_attempt_clock(),
        )

    def collect_usage(self, workspace, artifact_dir: Path) -> dict:
        """Save one problem's self-contained Hermes DB and aggregate its usage.

        Hermes commits session updates to SQLite in WAL mode. Copying only
        ``state.db`` can therefore omit committed rows that still live in
        ``state.db-wal``. Once the agent process has exited, create a consistent
        SQLite backup inside its per-problem container and copy that standalone
        database to the problem's output directory.

        Accounting is diagnostic data: collection failures are recorded in
        ``sessions/usage.json`` and must not turn a valid formalization into a
        pipeline exception.
        """
        sessions = artifact_dir / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        state_db = sessions / HERMES_STATE_DB
        usage_path = sessions / "usage.json"
        raw_sessions = sessions / "raw"
        raw_state = sessions / "raw_state"

        # A retry writes to the same problem directory. Remove only Hermes
        # artifacts from the previous attempt so the new record cannot be
        # combined with stale WAL/session files.
        for path in (
            state_db,
            Path(f"{state_db}-wal"),
            Path(f"{state_db}-shm"),
            Path(f"{state_db}-journal"),
            usage_path,
        ):
            path.unlink(missing_ok=True)
        for path in (raw_sessions, raw_state):
            if path.exists():
                shutil.rmtree(path)

        task_home = self._task_home(workspace.instance_id)
        source_db = f"{task_home}/{HERMES_STATE_DB}"
        snapshot_db = f"{task_home}/{HERMES_SNAPSHOT_DB}"
        report = {
            "schema_version": 1,
            "source": "hermes-state-db",
            "instance_id": workspace.instance_id,
            "database": HERMES_STATE_DB,
            "snapshot_method": "sqlite-backup",
            "hermes_home": task_home,
        }

        try:
            snapshot = workspace.run_in_container(
                self._snapshot_command(source_db, snapshot_db), timeout=120
            )
            if snapshot.exit_code != 0:
                detail = (snapshot.stderr or snapshot.stdout or "unknown error").strip()
                raise RuntimeError(f"Hermes SQLite snapshot failed: {detail}")
            if not workspace.copy_from_container(snapshot_db, str(state_db)):
                raise RuntimeError("Hermes SQLite snapshot could not be copied")

            usage = _read_hermes_usage(state_db)
            report["status"] = "ok"
            report["usage"] = usage
        except Exception as exc:
            # Preserve the original DB bundle for post-mortem inspection when
            # creation of the standalone snapshot fails.
            raw_state.mkdir(parents=True, exist_ok=True)
            copied = []
            for suffix in ("", "-wal", "-shm", "-journal"):
                name = f"{HERMES_STATE_DB}{suffix}"
                if workspace.copy_from_container(
                    f"{source_db}{suffix}", str(raw_state / name)
                ):
                    copied.append(name)
            report.update(
                {
                    "status": "error",
                    "error": str(exc),
                    "raw_state_files": copied,
                }
            )
            usage = {}
            logger.warning(
                "Hermes state collection failed for %s: %s",
                workspace.instance_id,
                exc,
            )

        try:
            raw_sessions_copied = workspace.copy_from_container(
                f"{task_home}/sessions", str(raw_sessions)
            )
        except Exception as exc:
            raw_sessions_copied = False
            report["raw_sessions_error"] = str(exc)
            logger.warning(
                "Hermes raw-session collection failed for %s: %s",
                workspace.instance_id,
                exc,
            )
        if not raw_sessions_copied:
            raw_sessions.mkdir(parents=True, exist_ok=True)
            report["raw_sessions_copied"] = False
        else:
            report["raw_sessions_copied"] = True

        usage_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        return usage

    def backup_session(
        self,
        agent_id: str,
        dest: Path,
        *,
        session_id: str | None = None,
        session_file: str | None = None,
        container_name: str | None = None,
    ) -> dict:
        """Report the state copied by ``collect_usage`` without copying twice."""
        sessions = dest / "sessions"
        usage_path = sessions / "usage.json"
        report: dict = {}
        try:
            value = json.loads(usage_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                report = value
        except (OSError, json.JSONDecodeError):
            pass
        state_present = (sessions / HERMES_STATE_DB).is_file()
        raw_files = sum(
            1
            for root_name in ("raw", "raw_state")
            for path in (sessions / root_name).glob("**/*")
            if path.is_file()
        )
        if state_present:
            status = "persisted"
        elif raw_files:
            status = "failed_partial"
        elif report.get("status") == "error":
            status = "failed"
        else:
            status = "missing"
        return {
            "status": status,
            "collector": "hermes-wal-aware-usage-hook",
            "canonical_state_database": state_present,
            "raw_fallback_files": raw_files,
            "state_snapshot_status": report.get("status", "unknown"),
            "raw_sessions_copied": report.get("raw_sessions_copied"),
            "raw_sessions_error_type_recorded": bool(
                report.get("raw_sessions_error")
            ),
        }

    def analysis_evidence_spec(self) -> dict:
        return {
            "schema_version": 1,
            "analysis_source": {
                "kind": "native_session_database_message_fields",
                "native_harness_exposure": "structured",
                "absence_is_model_attributable": False,
                "text_fields": ["reasoning", "reasoning_content"],
                "opaque_fields": [
                    "reasoning_details",
                    "codex_reasoning_items",
                ],
            },
            "raw_session": {
                "adapter_persistence": "implemented",
                "collector": "hermes-wal-aware-usage-hook",
            },
            "normalized_analysis": {
                "status": "not_implemented",
                "known_loss_modes": [
                    "state_database_messages_are_not_projected_to_agent_steps"
                ],
            },
        }

    def inspect_analysis_evidence(self, artifact_dir: Path) -> dict:
        return inspect_sqlite_analysis_fields(
            artifact_dir / "sessions" / HERMES_STATE_DB,
            artifact_dir=artifact_dir,
            text_fields={"reasoning", "reasoning_content"},
            opaque_fields={"reasoning_details", "codex_reasoning_items"},
        )

    def _snapshot_command(self, source_db: str, snapshot_db: str) -> str:
        """Build the in-container command for a WAL-aware SQLite backup."""
        code = (
            "import sqlite3\n"
            "from pathlib import Path\n"
            f"src = Path({source_db!r})\n"
            f"dst = Path({snapshot_db!r})\n"
            "if not src.is_file():\n"
            "    raise FileNotFoundError(f'Hermes state DB not found: {src}')\n"
            "dst.unlink(missing_ok=True)\n"
            "source = sqlite3.connect(src, timeout=30)\n"
            "target = sqlite3.connect(dst, timeout=30)\n"
            "source.backup(target)\n"
            "target.commit()\n"
            "target.execute('PRAGMA journal_mode=DELETE').fetchone()\n"
            "target.close()\n"
            "source.close()\n"
        )
        return f"{shlex.quote(str(self.runtime_python))} -c {shlex.quote(code)}"


def _read_hermes_usage(db_path: Path) -> dict:
    """Aggregate the session counters in one problem-owned Hermes snapshot."""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sessions)")
        }
        if not columns:
            raise RuntimeError("Hermes snapshot has no sessions table")

        counters = (
            "message_count",
            "tool_call_count",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "api_call_count",
        )
        costs = ("estimated_cost_usd", "actual_cost_usd")
        expressions = ["COUNT(*) AS session_count"]
        fields = ["session_count"]
        for name in counters:
            if name in columns:
                expressions.append(
                    f"COALESCE(SUM(COALESCE({name}, 0)), 0) AS {name}"
                )
            else:
                expressions.append(f"0 AS {name}")
            fields.append(name)
        for name in costs:
            if name in columns:
                expressions.extend(
                    (f"SUM({name}) AS {name}", f"COUNT({name}) AS {name}_count")
                )
            else:
                expressions.extend((f"NULL AS {name}", f"0 AS {name}_count"))
            fields.extend((name, f"{name}_count"))
        row = connection.execute(
            f"SELECT {', '.join(expressions)} FROM sessions"
        ).fetchone()

    values = dict(zip(fields, row, strict=True))
    usage = {
        "input": int(values["input_tokens"]),
        "output": int(values["output_tokens"]),
        "cacheRead": int(values["cache_read_tokens"]),
        "cacheWrite": int(values["cache_write_tokens"]),
        "reasoning": int(values["reasoning_tokens"]),
        "apiCalls": int(values["api_call_count"]),
        "sessions": int(values["session_count"]),
        "messages": int(values["message_count"]),
        "toolCalls": int(values["tool_call_count"]),
        "estimatedCostUsd": (
            float(values["estimated_cost_usd"])
            if values["estimated_cost_usd_count"]
            else None
        ),
        "actualCostUsd": (
            float(values["actual_cost_usd"])
            if values["actual_cost_usd_count"]
            else None
        ),
    }
    usage["total"] = (
        usage["input"]
        + usage["output"]
        + usage["cacheRead"]
        + usage["cacheWrite"]
    )
    return usage
