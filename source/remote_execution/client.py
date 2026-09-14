"""Small synchronous control client. Transport failures never retry an agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from .protocol import (CHUNK_SIZE, canonical, digest, endpoint, file_hash, identifier,
                       private_json, read_json, safe_path, secret_file, sha256, validate_job)


def resolve_evidence_path(mirror: Path, recorded_path: str) -> Path:
    """Resolve a remote absolute/relative evidence reference without editing it.

    Call this when inspecting trace/validity references in a collected mirror;
    do not run write-oriented benchmark repair/audit commands against a mirror.
    """
    manifest = read_json(mirror / "transport-manifest.json")
    path = Path(recorded_path)
    if path.is_absolute():
        path = path.relative_to(manifest["remote_job_root"])
    name = path.as_posix()
    if name not in manifest["files"]:
        raise ValueError("Reference is not part of this artifact snapshot")
    result = safe_path(mirror, name)
    if file_hash(result) != manifest["files"][name]["sha256"]:
        raise ValueError("Local evidence hash mismatch")
    return result


class Client:
    def __init__(self, base_url: str, token_file: Path, *, timeout=30):
        self.base_url = endpoint(base_url, loopback=True)
        self.token = secret_file(token_file)
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, *, method="GET", value=None, data=None, binary=False):
        if value is not None:
            data = canonical(value)
        request = Request(self.base_url + path, data=data, method=method,
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/octet-stream" if value is None else "application/json"})
        with self.opener.open(request, timeout=self.timeout) as response:
            payload = response.read(32 * 1024 * 1024 + 1)
        if len(payload) > 32 * 1024 * 1024:
            raise ValueError("Control response exceeds limit")
        return payload if binary else json.loads(payload)

    def upload(self, archive: Path, release_id: str):
        sha256(release_id)
        archive_hash = file_hash(archive)
        route = "/uploads/" + archive_hash
        offset = self.request(route)["offset"]
        if not 0 <= offset <= archive.stat().st_size:
            raise ValueError("Remote upload offset invalid")
        with archive.open("rb") as stream:
            stream.seek(offset)
            while chunk := stream.read(CHUNK_SIZE):
                row = self.request(route + "?" + urlencode({"offset": offset}), method="PUT", data=chunk)
                offset += len(chunk)
                if row["offset"] != offset:
                    raise ValueError("Remote upload offset changed")
        return self.request("/releases", method="POST", value={"archive_sha256": archive_hash, "release_id": release_id})

    def submit(self, spec):
        return self.request("/jobs", method="POST", value=validate_job(spec))

    def status(self, job_id):
        return self.request("/jobs/" + identifier(job_id))

    def resume(self, job_id, generation, reason):
        return self.request("/jobs/" + identifier(job_id) + "/resume", method="POST",
                            value={"generation": generation, "reason": reason})

    def collect(self, job_id, destination: Path, *, generation=None):
        """Append a read-only mirror under destination/job/generation-N.

        A matching partial download resumes. Existing different data is never
        replaced. Completion.json and execution validity evidence stay byte-for-byte.
        """
        row = self.status(job_id)
        generation = generation if generation is not None else row["generation"]
        route = "/jobs/" + identifier(job_id)
        manifest = self.request(route + "/artifacts?" + urlencode({"generation": generation}))
        if manifest["generation"] != generation:
            raise ValueError("Artifact generation mismatch")
        expected_manifest = row["detail"].get("artifacts_sha256")
        if generation == row["generation"] and expected_manifest is not None and expected_manifest != digest(manifest):
            raise ValueError("Manifest is not the committed job snapshot")
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = safe_path(destination, job_id + f"/generation-{generation}")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        metadata = directory / "transport-manifest.json"
        if metadata.exists():
            if read_json(metadata) != manifest:
                raise ValueError("Local destination belongs to different evidence")
        else:
            private_json(metadata, manifest, replace=False)
        for name, expected in manifest["files"].items():
            if name.split("/", 1)[0] not in {"output", "logs", "evidence"}:
                raise ValueError("Artifact is outside job evidence roots")
            if type(expected["size"]) is not int or expected["size"] < 0:
                raise ValueError("Invalid artifact size")
            sha256(expected["sha256"])
            path = safe_path(directory, name)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists():
                if not path.is_file() or file_hash(path) != expected["sha256"]:
                    raise ValueError("Existing artifact differs; refusing to overwrite")
                continue
            # Partial paths cannot collide with agent-authored artifact names.
            parts = directory / ".transfer-parts"; parts.mkdir(exist_ok=True, mode=0o700)
            partial = safe_path(parts, digest({"path": name}) + ".part")
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > expected["size"]:
                raise ValueError("Partial artifact exceeds declared size")
            with partial.open("ab") as output:
                while offset < expected["size"]:
                    chunk = self.request(route + "/file?" + urlencode({"generation": generation, "path": name,
                                         "offset": offset}), binary=True)
                    if not chunk or len(chunk) > min(CHUNK_SIZE, expected["size"] - offset):
                        raise ValueError("Incomplete/oversized artifact chunk")
                    output.write(chunk); output.flush(); os.fsync(output.fileno())
                    offset += len(chunk)
            if file_hash(partial) != expected["sha256"]:
                raise ValueError("Artifact checksum mismatch; partial evidence retained for inspection")
            os.link(partial, path)  # Create-only even if another collector raced us.
            partial.unlink()
        receipt = {"job_id": job_id, "generation": generation, "request_sha256": row["identity"],
                   "release_id": row["spec"]["release_id"], "manifest_sha256": digest(manifest),
                   "files": len(manifest["files"]), "read_only_mirror": True}
        receipt_path = directory / "collection-receipt.json"
        if receipt_path.exists():
            if read_json(receipt_path) != receipt:
                raise ValueError("Collection receipt differs")
        else:
            private_json(receipt_path, receipt, replace=False)
        return receipt
