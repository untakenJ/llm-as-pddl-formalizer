"""Execution-granular, immutable transport snapshots; no agent-loop hooks.

Only terminal execution directories are copied. Native terminal records are
written after collection/cleanup; mutable leases, summaries and live SQLite
databases outside those directories are never used as recovery checkpoints.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import tempfile

from .protocol import (canonical, digest, exact, file_hash, private_json, read_json,
                       relative, safe_path, sha256, validate_job, validate_node)
from .store import Store, lock


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_file(source, target):
    """Create-only durable copy, refusing a source changed during collection."""
    before = source.stat()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    target.chmod(0o600)
    after = source.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Evidence changed while copying; checkpoint not committed")
    return {"size": target.stat().st_size, "sha256": file_hash(target)}


def durable_tree(root):
    for parent, _, _ in os.walk(root, topdown=False):
        fsync_directory(Path(parent))


def catalog(directory):
    path = directory / "checkpoint-index.json"
    return read_json(path) if path.exists() else {"schema_version": 1, "checkpoints": []}


def checkpoint_manifest(directory, checkpoint_id):
    sha256(checkpoint_id)
    value = read_json(safe_path(directory, f"checkpoints/{checkpoint_id}/transport-manifest.json"))
    if digest(value) != checkpoint_id:
        raise ValueError("Checkpoint manifest identity mismatch")
    return value


def _compatible_node(config):
    # Authentication/identity are rotated on a replacement VM; execution
    # resources, services, bindings and absolute paths must remain frozen.
    return {k: v for k, v in config.items() if k not in {"node_id", "token_file", "max_recovery_bytes"}}


def validate_manifest(manifest):
    exact(manifest, {"schema_version", "kind", "key", "generation", "request_sha256", "spec", "node_config",
                     "remote_job_root", "files", "excluded_nonregular"})
    spec = validate_job(manifest["spec"])
    validate_node(manifest["node_config"])
    if manifest["schema_version"] != 1 or manifest["request_sha256"] != digest(spec):
        raise ValueError("Checkpoint schema/request mismatch")
    if type(manifest["generation"]) is not int or manifest["generation"] < 1:
        raise ValueError("Invalid checkpoint generation")
    expected_root = Path(manifest["node_config"]["state_dir"]) / "jobs" / spec["job_id"]
    if str(expected_root) != manifest["remote_job_root"]:
        raise ValueError("Checkpoint node/output root mismatch")
    key = manifest["key"]
    if manifest["kind"] == "execution":
        if not re.fullmatch(r"output/llm-as-formalizer-agent/[^/]+/[^/]+/[^/]+/p[0-9]+/executions/execution-[0-9]+", key):
            raise ValueError("Invalid execution checkpoint path")
        relative(key)
        if not any(key + "/" + terminal in manifest["files"] for terminal in ("execution_result.json", "infra_invalid.json")):
            raise ValueError("Checkpoint lacks its terminal record")
    elif manifest["kind"] == "adjudication":
        path, content_hash = key.rsplit(":", 1)
        relative(path); sha256(content_hash)
        if not re.fullmatch(r"output/llm-as-formalizer-agent/[^/]+/[^/]+/[^/]+/execution_validity_events.jsonl", path):
            raise ValueError("Invalid adjudication checkpoint path")
        if set(manifest["files"]) != {path} or manifest["files"][path]["sha256"] != content_hash:
            raise ValueError("Adjudication content mismatch")
    else:
        raise ValueError("Unsupported checkpoint kind")
    for name, row in manifest["files"].items():
        relative(name)
        if manifest["kind"] == "execution" and not (
                name.startswith(key + "/") or name.startswith("output/infra-diagnostics/")
                or re.fullmatch(r"evidence/(request|node|configuration|operational|services)-[0-9]+\.json", name)):
            raise ValueError("Execution checkpoint includes mutable/unowned state")
        exact(row, {"size", "sha256"}); sha256(row["sha256"])
        if type(row["size"]) is not int or row["size"] < 0:
            raise ValueError("Invalid checkpoint file size")
    return manifest


def _publish(directory, spec, node, generation, kind, key, roots, index):
    base = directory / "checkpoints"
    base.mkdir(exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".sealing-", dir=base))
    files = {}; excluded = []
    try:
        for root in roots:
            paths = sorted(root.rglob("*")) if root.is_dir() else [root]
            for path in paths:
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
                if name not in files:
                    files[name] = copy_file(path, safe_path(staging, name))
        manifest = {"schema_version": 1, "kind": kind, "key": key,
                    "generation": generation, "request_sha256": digest(spec),
                    "spec": spec, "node_config": node, "remote_job_root": str(directory),
                    "files": files, "excluded_nonregular": sorted(excluded)}
        validate_manifest(manifest)
        checkpoint_id = digest(manifest)
        private_json(staging / "transport-manifest.json", manifest, replace=False)
        durable_tree(staging)
        target = base / checkpoint_id
        if not target.exists():
            os.rename(staging, target)
            fsync_directory(base)
        row = {"checkpoint_id": checkpoint_id, "kind": kind, "key": key,
               "generation": generation, "files": len(files)}
        if not any(item["checkpoint_id"] == checkpoint_id for item in index["checkpoints"]):
            index["checkpoints"].append(row)
            private_json(directory / "checkpoint-index.json", index)
        return row
    finally:
        # Only this invocation's private staging tree; source links were refused.
        if staging.exists():
            shutil.rmtree(staging)


def publish_ready(directory, spec, node, generation):
    """Called by the remote owner, outside the benchmark. Safe to call repeatedly.

    No outcome-based selection: valid failures and every infra-invalid terminal
    execution are published. Shared adjudication ledgers have separate revisions.
    """
    if spec["kind"] != "agent_cell":
        return catalog(directory)
    from agent_formalizer.configuration.operational_config import safe_operational_component
    from agent_formalizer.results.execution_validity import cell_dir_for_model_dir

    with lock(directory / "checkpoint.lock", blocking=True):
        index = catalog(directory)
        known = {(row["kind"], row["key"]) for row in index["checkpoints"]}
        # Do not recursively traverse the potentially large trace trees on each poll.
        output = directory / "output" / "llm-as-formalizer-agent"
        cells = set()
        for execution in sorted(output.glob("*/*/*/p*/executions/execution-*")):
            safe_path(directory, execution.relative_to(directory).as_posix())
            if not re.fullmatch(r"execution-[0-9]+", execution.name):
                continue
            model_dir = execution.parents[2]
            cell, attempt = cell_dir_for_model_dir(model_dir)
            cells.add(cell)
            key = execution.relative_to(directory).as_posix()
            if ("execution", key) in known:
                continue
            valid = execution / "execution_result.json"
            invalid = execution / "infra_invalid.json"
            terminal = valid if valid.is_file() else invalid
            if not terminal.is_file():
                continue  # Includes interrupted/live executions, never a partial snapshot.
            safe_path(directory, terminal.relative_to(directory).as_posix())
            record = read_json(terminal)
            if terminal == valid and not (record.get("complete") is True and record.get("attempt_valid") is True):
                raise ValueError("Malformed valid terminal execution")
            if terminal == invalid and record.get("attempt_valid") is not False:
                raise ValueError("Malformed invalid terminal execution")
            roots = [execution]
            domain, dataset, model, problem = execution.relative_to(output).parts[:4]
            suffix = "/".join(map(safe_operational_component, (domain, dataset, model, problem)))
            for diag in (directory / "output/infra-diagnostics").glob(
                    f"*/{suffix}/attempt-{attempt:03d}/{execution.name}"):
                safe_path(directory, diag.relative_to(directory).as_posix())
                roots.append(diag)
            for name in ("request", "node", "configuration", "operational", "services"):
                evidence = directory / "evidence" / f"{name}-{generation}.json"
                if evidence.is_file():
                    roots.append(evidence)
            _publish(directory, spec, node, generation, "execution", key, roots, index)
        for cell in sorted(cells):
            events = cell / "execution_validity_events.jsonl"
            if not events.exists():
                continue
            safe_path(directory, events.relative_to(directory).as_posix())
            # Same lock as native adjudication, so never copy a partial JSONL event.
            with lock(cell / ".execution_validity.lock", blocking=True):
                key = events.relative_to(directory).as_posix() + ":" + file_hash(events)
                if ("adjudication", key) not in known:
                    _publish(directory, spec, node, generation, "adjudication", key, [events], index)
        return index


def acknowledge(directory, checkpoint_id, receipt):
    manifest = checkpoint_manifest(directory, checkpoint_id)
    expected = {"checkpoint_id": checkpoint_id, "manifest_sha256": checkpoint_id,
                "request_sha256": manifest["request_sha256"]}
    if receipt != expected:
        raise ValueError("Receipt does not identify this checkpoint")
    path = directory / "checkpoint-acks" / (checkpoint_id + ".json")
    with lock(directory / "checkpoint-acks.lock", blocking=True):
        if path.exists():
            if read_json(path) != receipt:
                raise ValueError("Checkpoint receipt changed")
        else:
            private_json(path, receipt, replace=False)
    return receipt


def recovery_bundle(mirror, archive):
    """Export only controller-confirmed complete snapshots, never .part downloads."""
    state = read_json(mirror / "sync-state.json")
    files = {}; manifests = []
    # Serialize with sync so the chosen durable receipt set is a consistent prefix.
    for row in state["checkpoints"]:
        checkpoint_id = sha256(row["checkpoint_id"])
        root = safe_path(mirror, "checkpoints/" + checkpoint_id)
        manifest = validate_manifest(read_json(root / "transport-manifest.json"))
        receipt = read_json(root / "collection-receipt.json")
        if (digest(manifest) != checkpoint_id or receipt != {
                "checkpoint_id": checkpoint_id, "manifest_sha256": checkpoint_id,
                "request_sha256": manifest["request_sha256"]} or manifest["spec"] != state["spec"]):
            raise ValueError("Unverified checkpoint cannot be recovered")
        manifests.append(manifest)
        for name, expected in manifest["files"].items():
            source = safe_path(root, name)
            if source.stat().st_size != expected["size"] or file_hash(source) != expected["sha256"]:
                raise ValueError("Collected evidence no longer matches its receipt")
            if name in files and files[name][1] != expected and manifest["kind"] != "adjudication":
                raise ValueError("Immutable execution evidence has conflicting copies")
            files[name] = (source, expected)
    origin = state["origin"]
    reference = manifests[-1] if manifests else dict(origin, request_sha256=digest(origin["spec"]))
    if any(m["request_sha256"] != reference["request_sha256"] or _compatible_node(m["node_config"]) != _compatible_node(reference["node_config"])
           or m["remote_job_root"] != reference["remote_job_root"] for m in manifests):
        raise ValueError("Cannot merge different jobs/nodes into a recovery archive")
    # Include all manifests/receipts as immutable historical evidence. Do not
    # restore derived validity views, active leases or old queue/process records.
    if origin["spec"] != reference["spec"] or _compatible_node(origin["node_config"]) != _compatible_node(reference["node_config"]):
        raise ValueError("Controller origin differs from checkpoints")
    recovery = {"schema_version": 1, "spec": origin["spec"], "node_config": origin["node_config"],
                "remote_job_root": reference["remote_job_root"],
                "previous_generation": max([origin["generation"]] + [m["generation"] for m in manifests]),
                "checkpoints": manifests, "files": {name: row for name, (_, row) in files.items()},
                "unsynchronized_policy": "rerun_missing_slots_after_source_node_retired"}
    import io
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as stream:
            payload = canonical(recovery)
            item = tarfile.TarInfo("recovery.json"); item.size = len(payload)
            stream.addfile(item, io.BytesIO(payload))
            for name, (source, expected) in sorted(files.items()):
                item = tarfile.TarInfo("payload/" + name); item.size = expected["size"]; item.mode = 0o600
                with source.open("rb") as reader:
                    stream.addfile(item, reader)
        output.flush(); os.fsync(output.fileno())
    fsync_directory(archive.parent)
    return {"archive_sha256": file_hash(archive), "files": len(files), "checkpoints": len(manifests)}


def restore(archive, node, *, reason, source_node_retired=False):
    """Offline import on an empty replacement node, at the SAME absolute paths.

    Retirement is an explicit operator attestation, not inferred from a failed
    SSH connection. The worker must be stopped. Queue admission is committed last.
    """
    validate_node(node)
    if source_node_retired is not True or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Confirmed source-node retirement and an audit reason are required")
    store = Store(Path(node["state_dir"]))
    with lock(store.root / "worker.lock"):
        if store.list():
            raise ValueError("Recovery requires an empty replacement-node queue")
        staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=store.root))
        try:
            total = 0; seen = set()
            with tarfile.open(archive, "r:gz") as stream:
                for member in stream:
                    if not member.isfile() or member.name in seen or len(seen) >= 200000:
                        raise ValueError("Recovery accepts unique regular files only")
                    if member.name != "recovery.json" and not member.name.startswith("payload/"):
                        raise ValueError("Unexpected recovery member")
                    if member.name == "recovery.json" and member.size > 32 * 1024**2:
                        raise ValueError("Recovery metadata exceeds size limit")
                    total += member.size
                    if total > node.get("max_recovery_bytes", 64 * 1024**3):
                        raise ValueError("Recovery archive exceeds expanded size limit")
                    target = safe_path(staging, member.name)
                    with stream.extractfile(member) as source:
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with target.open("xb") as out:
                            shutil.copyfileobj(source, out, 1024 * 1024)
                            out.flush(); os.fsync(out.fileno())
                        target.chmod(0o600)
                    seen.add(member.name)
            evidence = read_json(staging / "recovery.json")
            exact(evidence, {"schema_version", "spec", "node_config", "remote_job_root", "previous_generation",
                             "checkpoints", "files", "unsynchronized_policy"})
            spec = validate_job(evidence["spec"])
            if evidence["schema_version"] != 1 or evidence["unsynchronized_policy"] != "rerun_missing_slots_after_source_node_retired":
                raise ValueError("Unsupported recovery schema/policy")
            old = validate_node(evidence["node_config"])
            expected_files = {}
            for manifest in evidence["checkpoints"]:
                validate_manifest(manifest)
                if (manifest["spec"] != spec or manifest["remote_job_root"] != evidence["remote_job_root"]
                        or _compatible_node(manifest["node_config"]) != _compatible_node(old)):
                    raise ValueError("Recovery checkpoint belongs to another job/node")
                for name, expected in manifest["files"].items():
                    if name in expected_files and expected_files[name] != expected and manifest["kind"] != "adjudication":
                        raise ValueError("Conflicting immutable recovery files")
                    expected_files[name] = expected
            if (type(evidence["previous_generation"]) is not int or evidence["previous_generation"] < 1
                    or evidence["files"] != expected_files
                    or any(m["generation"] > evidence["previous_generation"] for m in evidence["checkpoints"])):
                raise ValueError("Recovery inventory/generation does not match checkpoint evidence")
            # IDs/authentication may change; paths, services and resource policy may not.
            if _compatible_node(old) != _compatible_node(node):
                raise ValueError("Replacement node must retain frozen paths/services/configuration")
            directory = store.directory(spec["job_id"])
            if str(directory) != evidence["remote_job_root"]:
                raise ValueError("Recovery requires identical absolute output paths")
            from .bundle import verify
            if digest(verify(store.root / "releases" / spec["release_id"])) != spec["release_id"]:
                raise ValueError("Install the original frozen release before recovery")
            if seen != {"recovery.json"} | {"payload/" + name for name in evidence["files"]}:
                raise ValueError("Recovery inventory mismatch")
            for name, expected in evidence["files"].items():
                if name.split("/", 1)[0] not in {"output", "evidence"}:
                    raise ValueError("Recovery file outside evidence roots")
                source = safe_path(staging / "payload", name)
                if source.stat().st_size != expected["size"] or file_hash(source) != expected["sha256"]:
                    raise ValueError("Recovery file checksum mismatch")
            payload = staging / "payload"
            payload.mkdir(exist_ok=True, mode=0o700)
            private_json(payload / "evidence" / "node-loss-recovery.json", {
                "reason": reason, "source_node_retired": True, "source_node_id": old["node_id"],
                "replacement_node_id": node["node_id"], "archive_sha256": file_hash(archive),
                "recovery": evidence}, replace=False)
            private_json(payload / "node.json", node, replace=False)
            durable_tree(payload)
            if directory.exists():
                # A crash after atomic rename but before queue commit is retryable;
                # never merge into or overwrite any other output directory.
                prior = read_json(directory / "evidence/node-loss-recovery.json")
                if prior["archive_sha256"] != file_hash(archive):
                    raise ValueError("Existing output is not this recovery transaction")
                for name, expected in evidence["files"].items():
                    target = safe_path(directory, name)
                    if target.stat().st_size != expected["size"] or file_hash(target) != expected["sha256"]:
                        raise ValueError("Previously staged recovery evidence has changed")
            else:
                os.rename(payload, directory)
                fsync_directory(directory.parent)
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                import time
                now = time.time()
                db.execute("INSERT INTO jobs(id,spec,identity,status,generation,created,updated) VALUES(?,?,?,'queued',?,?,?)",
                           (spec["job_id"], canonical(spec).decode(), digest(spec), evidence["previous_generation"] + 1, now, now))
                store.event(db, spec["job_id"], "restored_after_node_loss", {
                    "reason": reason, "source_node_retired": True, "archive_sha256": file_hash(archive),
                    "policy": evidence["unsynchronized_policy"]})
            return store.get(spec["job_id"])
        finally:
            if staging.exists():
                shutil.rmtree(staging)
