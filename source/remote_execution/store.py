"""Durable admission/idempotency and bounded, immutable artifact snapshots."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import stat
import time
from contextlib import contextmanager
from pathlib import Path

from .protocol import canonical, digest, file_hash, identifier, private_json, read_json, safe_path, validate_job


@contextmanager
def lock(path: Path, *, blocking=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield stream


def process_identity():
    return {"pid": os.getpid(), "process_group": os.getpgrp(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}


def group_alive(directory: Path):
    marker = directory / "process-owner.json"
    if not marker.exists():
        return False
    identity = read_json(marker)
    if identity["boot_id"] != Path("/proc/sys/kernel/random/boot_id").read_text().strip():
        return False
    for stat_path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat_path.read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            continue
        if int(fields[2]) == identity["process_group"] and fields[0] != "Z":
            return True
    return False


class Store:
    def __init__(self, root: Path):
        if root.is_symlink():
            raise ValueError("Node state cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = root.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Node state must be owner-only")
        self.root = root.resolve(strict=True)
        for name in ("jobs", "releases", "uploads"):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, spec TEXT NOT NULL, identity TEXT NOT NULL,
                status TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 1,
                created REAL NOT NULL, updated REAL NOT NULL, detail TEXT NOT NULL DEFAULT '{}')""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                at REAL NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "queue.sqlite3", timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def directory(self, job_id):
        return self.root / "jobs" / identifier(job_id)

    def get(self, job_id):
        identifier(job_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown job")
        value = dict(row)
        value["spec"] = json.loads(value["spec"])
        value["detail"] = json.loads(value["detail"])
        return value

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,status,generation,created,updated FROM jobs ORDER BY created,id")]

    @staticmethod
    def event(db, job_id, event, detail):
        db.execute("INSERT INTO events(job_id,at,event,detail) VALUES(?,?,?,?)",
                   (job_id, time.time(), event, canonical(detail).decode()))

    def submit(self, spec):
        validate_job(spec)
        identity = digest(spec)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT identity FROM jobs WHERE id=?", (spec["job_id"],)).fetchone()
            if row is not None:
                if row["identity"] != identity:
                    raise ValueError("Job ID already belongs to a different frozen request")
            else:
                now = time.time()
                db.execute("INSERT INTO jobs(id,spec,identity,status,created,updated) VALUES(?,?,?,'queued',?,?)",
                           (spec["job_id"], canonical(spec).decode(), identity, now, now))
                self.event(db, spec["job_id"], "submitted", {"identity": identity})
        return self.get(spec["job_id"])

    def transition(self, job_id, status, detail=None, *, expected=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown job")
            if expected is not None and row["status"] not in expected:
                raise ValueError("Job state changed; query status before retrying")
            db.execute("UPDATE jobs SET status=?,updated=?,detail=? WHERE id=?",
                       (status, time.time(), canonical(detail or {}).decode(), job_id))
            self.event(db, job_id, status, detail or {})
        return self.get(job_id)

    def events(self, job_id, after=0):
        self.get(job_id)
        with self.connect() as db:
            return [dict(row) | {"detail": json.loads(row["detail"])} for row in db.execute(
                "SELECT * FROM events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT 200",
                (job_id, after))]

    def resume(self, job_id, reason, generation):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("Explicit operational resume reason required")
        with lock(self.directory(job_id) / "owner.lock"):
            if group_alive(self.directory(job_id)):
                raise ValueError("An execution process group is still alive; do not relaunch")
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT status,generation FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row is None:
                    raise KeyError("Unknown job")
                # An identical retried request must not queue two generations.
                if row["generation"] == generation + 1:
                    return self.get(job_id)
                if row["generation"] != generation or row["status"] not in {"failed", "needs_attention"}:
                    raise ValueError("Resume needs a matching stopped generation")
                db.execute("UPDATE jobs SET status='queued',generation=generation+1,updated=?,detail='{}' WHERE id=?",
                           (time.time(), job_id))
                self.event(db, job_id, "resume_requested", {"reason": reason, "previous_generation": generation})
        return self.get(job_id)


def seal_artifacts(directory: Path, generation: int):
    """Only transport job-owned evidence, never node secrets/runtime bindings.

    Symlinks and special files are recorded as exclusions, not dereferenced.
    A snapshot is advertised only after its manifest is durably committed.
    """
    files = {}; excluded = []
    snapshot = directory / "snapshots" / str(generation)
    snapshot.mkdir(parents=True, mode=0o700)
    for prefix in ("output", "logs", "evidence"):
        base = directory / prefix
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            name = path.relative_to(directory).as_posix()
            try:
                safe_path(directory, name)
            except ValueError:
                excluded.append(name)
                continue
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                excluded.append(name)
                continue
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("rb") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            target.chmod(0o600)
            files[name] = {"size": target.stat().st_size, "sha256": file_hash(target)}
    manifest = {"schema_version": 1, "generation": generation, "files": files,
                "excluded_nonregular": excluded, "remote_job_root": str(directory)}
    private_json(directory / f"artifacts-{generation}.json", manifest, replace=False)
    return manifest
