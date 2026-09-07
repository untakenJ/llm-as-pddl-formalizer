"""Bounded JSONL storage for optional infrastructure diagnostic events."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any


class JsonlDiagnosticStorage:
    def __init__(
        self,
        *,
        event_path: str | Path,
        manifest_path: str | Path,
        run_budget_path: str | Path,
        max_event_bytes: int,
        max_run_bytes: int,
    ):
        self.event_path = Path(event_path)
        self.manifest_path = Path(manifest_path)
        self.run_budget_path = Path(run_budget_path)
        self.max_event_bytes = int(max_event_bytes)
        self.max_run_bytes = int(max_run_bytes)
        for path in (self.event_path, self.manifest_path, self.run_budget_path):
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass

    @staticmethod
    def _json_bytes(value: dict[str, Any]) -> bytes:
        return (
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _match_parent_ownership(path: Path) -> None:
        """Keep bind-mounted artifacts owned like their host-created directory."""
        try:
            parent = path.parent.stat()
            os.chown(path, parent.st_uid, parent.st_gid)
        except OSError:
            pass

    def encode_event(self, event: dict[str, Any]) -> tuple[bytes | None, bool]:
        payload = self._json_bytes(event)
        if len(payload) <= self.max_event_bytes:
            return payload, False

        original_sha256 = hashlib.sha256(payload).hexdigest()
        compact = dict(event)
        compact.pop("raw", None)
        diagnostics = dict(compact.get("diagnostics") or {})
        diagnostics.update(
            {
                "event_truncated": True,
                "original_event_sha256": original_sha256,
                "original_event_bytes": len(payload),
            }
        )
        compact["diagnostics"] = diagnostics
        payload = self._json_bytes(compact)
        if len(payload) <= self.max_event_bytes:
            return payload, True

        provider_payload = compact.get("provider")
        encoded_provider = json.dumps(
            provider_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        compact["provider"] = {
            "truncated": True,
            "sha256": hashlib.sha256(encoded_provider).hexdigest(),
            "original_json_bytes": len(encoded_provider),
        }
        payload = self._json_bytes(compact)
        return (payload, True) if len(payload) <= self.max_event_bytes else (None, True)

    def _reserve_run_bytes(self, size: int) -> str:
        with self.run_budget_path.open("a+", encoding="utf-8") as stream:
            try:
                self.run_budget_path.chmod(0o600)
            except OSError:
                pass
            self._match_parent_ownership(self.run_budget_path)
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "busy"
            try:
                stream.seek(0)
                raw = stream.read().strip()
                used = int(raw) if raw else 0
                if used + size > self.max_run_bytes:
                    return "exhausted"
                stream.seek(0)
                stream.truncate()
                stream.write(str(used + size))
                stream.flush()
                os.fsync(stream.fileno())
                return "reserved"
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def append(self, event: dict[str, Any]) -> tuple[str, int, bool]:
        payload, truncated = self.encode_event(event)
        if payload is None:
            return "event_too_large", 0, True
        reservation = self._reserve_run_bytes(len(payload))
        if reservation != "reserved":
            return f"run_budget_{reservation}", 0, truncated
        with self.event_path.open("ab") as stream:
            if self.event_path.stat().st_size == 0:
                try:
                    self.event_path.chmod(0o600)
                except OSError:
                    pass
                self._match_parent_ownership(self.event_path)
            stream.write(payload)
            stream.flush()
        return "written", len(payload), truncated

    def write_manifest(self, value: dict[str, Any]) -> None:
        temporary = self.manifest_path.with_name(
            f".{self.manifest_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        self._match_parent_ownership(temporary)
        os.replace(temporary, self.manifest_path)
