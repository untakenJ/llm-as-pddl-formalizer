"""Host-local Docker admission and owned-resource lifecycle, outside agent time.

No daemon configuration changes, global prune, or model/tool calls. The shared
lock coordinates cooperating runners using the same local daemon and Unix UID.
Unknown/legacy resources and crash survivors with uncollected evidence are kept.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid


logger = logging.getLogger(__name__)
PREFIX = "org.agentic-formalizer-bench.network."
MANAGED = PREFIX + "managed"
OWNER = PREFIX + "owner"
VERSION = "v1"
DEFAULT_OPTIONS = {
    "safety_margin": 2,
    "docker_timeout_seconds": 20,
    "poll_seconds": 10,
    "orphan_grace_seconds": 60,
}
DEFAULT_POOLS = [
    {"Base": f"172.{n}.0.0/16", "Size": 16} for n in range(17, 32)
] + [{"Base": "192.168.0.0/16", "Size": 20}]
_ID = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"[0-9a-f]{32}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class NetworkResourceError(RuntimeError):
    """Operational resource failure, never evidence about the agent."""


def validate_options(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != set(DEFAULT_OPTIONS):
        raise ValueError("network_resources must contain exactly " + ", ".join(DEFAULT_OPTIONS))
    for key, number in value.items():
        minimum = 0 if key == "safety_margin" else 1
        if isinstance(number, bool) or not isinstance(number, int) or number < minimum:
            raise ValueError(f"network_resources.{key} must be an integer >= {minimum}")
    if value["poll_seconds"] > 60 or value["docker_timeout_seconds"] > 60:
        raise ValueError("network_resources poll/command timeouts must be <= 60 seconds")
    return dict(value)


def options_from(operational=None) -> dict:
    return validate_options(
        operational.raw.get("network_resources", DEFAULT_OPTIONS)
        if operational is not None else DEFAULT_OPTIONS
    )


def _start_ticks(pid: int) -> str:
    # comm can itself contain spaces and parentheses; field 22 follows its last ')'.
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def process_identity() -> dict:
    return {
        "pid": os.getpid(), "uid": os.getuid(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "start_ticks": _start_ticks(os.getpid()),
    }


def owner_dead(owner: dict, current: dict) -> bool:
    """Unknown identity/permission errors are NOT permission to reclaim."""
    try:
        if owner["uid"] != current["uid"] or int(owner["pid"]) <= 0:
            return False
        if not owner["boot_id"] or not str(owner["start_ticks"]).isdigit():
            return False
        if owner["boot_id"] != current["boot_id"]:
            return True
        return _start_ticks(int(owner["pid"])) != str(owner["start_ticks"])
    except FileNotFoundError:
        return True
    except (OSError, KeyError, ValueError, IndexError):
        return False


def capacity_snapshot(pools: list, networks: list, routes: list) -> dict:
    """Conservative IPv4 capacity estimate, including foreign networks/routes."""
    candidates = set()
    for pool in pools:
        base = ipaddress.ip_network(pool["Base"])
        size = int(pool["Size"])
        if base.version != 4:
            continue
        if not base.prefixlen <= size <= 30 or size - base.prefixlen > 16:
            raise NetworkResourceError("Unsupported/oversized Docker address pool; inspect configuration")
        candidates.update(base.subnets(new_prefix=size))
    occupied = []
    for network in networks:
        for config in network.get("IPAM", {}).get("Config", []) or []:
            if config.get("Subnet"):
                subnet = ipaddress.ip_network(config["Subnet"], strict=False)
                if subnet.version == 4:
                    occupied.append(subnet)
    for route in routes:
        destination = route.get("dst", "default")
        if destination not in ("default", "0.0.0.0/0"):
            subnet = ipaddress.ip_network(destination, strict=False)
            if subnet.version == 4:
                occupied.append(subnet)
    free = [n for n in candidates if not any(n.overlaps(o) for o in occupied)]
    return {"total_subnets": len(candidates), "free_subnets": len(free),
            "occupied_or_route_conflicted": len(candidates) - len(free)}


class NetworkResources:
    def __init__(self, *, options=None, evidence_dir: Path | None = None):
        self.options = validate_options(DEFAULT_OPTIONS if options is None else options)
        self.evidence_dir = Path(evidence_dir) if evidence_dir is not None else None
        self.identity = process_identity()
        self.root: Path | None = None
        self.daemon_id = None
        self.pools = None
        self.evidence_id = uuid.uuid4().hex
        self.pending_record = None

    def _command(self, args: list[str]) -> str:
        try:
            result = subprocess.run(args, capture_output=True, text=True,
                                    timeout=self.options["docker_timeout_seconds"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NetworkResourceError(f"{args[:3]}: {type(exc).__name__}") from exc
        if result.returncode:
            raise NetworkResourceError(f"{args[:3]}: {result.stderr.strip()[:2000]}")
        return result.stdout

    def _initialize(self):
        if self.root is not None:
            return
        # Route and PID checks refer to this host, so a remote daemon is unsafe.
        endpoint = os.environ.get("DOCKER_HOST")
        if not endpoint:
            endpoint = self._command(["docker", "context", "inspect", "--format",
                                      '{{.Endpoints.docker.Host}}']).strip()
        if not endpoint.startswith("unix://"):
            raise NetworkResourceError("network resource management requires a local Unix Docker socket")
        info = json.loads(self._command(["docker", "info", "--format",
            '{"id":{{json .ID}},"pools":{{json .DefaultAddressPools}}}']))
        if not isinstance(info.get("id"), str) or not info["id"]:
            raise NetworkResourceError("Docker daemon identity is unavailable")
        self.daemon_id = info["id"]
        self.pools = info.get("pools") or DEFAULT_POOLS
        digest = hashlib.sha256(self.daemon_id.encode()).hexdigest()[:20]
        root = Path(f"/tmp/pddl-benchmark-networks-{os.getuid()}-{digest}")
        root.mkdir(mode=0o700, exist_ok=True)
        metadata = root.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise NetworkResourceError(f"Unsafe shared network registry: {root}")
        self.root = root

    @contextlib.contextmanager
    def _lock(self):
        self._initialize()
        descriptor = os.open(self.root / "host.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
                raise NetworkResourceError("Unsafe network lock file")
            # Never hold the lock while sleeping for capacity or running an agent.
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _write_record(self, record):
        token = record["token"]
        if not _TOKEN.fullmatch(token):
            raise NetworkResourceError("Invalid resource owner token")
        target = self.root / f"{token}.json"
        temporary = self.root / f"{token}.{uuid.uuid4().hex}.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(record, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)

    def _records(self):
        for path in self.root.glob("*.json"):
            if not _TOKEN.fullmatch(path.stem):
                continue
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
                    raise NetworkResourceError("Unsafe resource record")
                record = json.load(source)
            if record.get("token") != path.stem or record.get("daemon_id") != self.daemon_id:
                raise NetworkResourceError("Network registry identity mismatch")
            yield record

    def _event(self, event, **details):
        row = {"time": time.time(), "event": event, "registry": str(self.root),
               "daemon_id": self.daemon_id, **details}
        # Shared durable audit is required before destructive operations.
        fd = os.open(self.root / "events.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as output:
            output.write(json.dumps(row, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())
        if self.evidence_dir is not None:
            try:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                path = self.evidence_dir / f"network-lifecycle-{self.evidence_id}.jsonl"
                with path.open("a") as output:
                    output.write(json.dumps(row, sort_keys=True) + "\n")
            except OSError as exc:
                logger.warning("Could not copy optional network lifecycle evidence: %s", exc)

    def _inventory(self):
        ids = self._command(["docker", "network", "ls", "-q", "--no-trunc"]).split()
        if not all(_ID.fullmatch(value) for value in ids):
            raise NetworkResourceError("Unexpected network IDs")
        networks = json.loads(self._command(["docker", "network", "inspect", *ids])) if ids else []
        ids = self._command(["docker", "ps", "-aq", "--no-trunc"]).split()
        if not all(_ID.fullmatch(value) for value in ids):
            raise NetworkResourceError("Unexpected container IDs")
        # Never read container environment, mounts, commands, or credentials.
        fmt = ('{"Id":{{json .Id}},"Name":{{json .Name}},"Labels":{{json .Config.Labels}},'
               '"Networks":{{json .NetworkSettings.Networks}},"Mode":{{json .HostConfig.NetworkMode}}}')
        containers = [json.loads(line) for line in self._command(
            ["docker", "inspect", "--type", "container", "--format", fmt, *ids]).splitlines()] if ids else []
        return networks, containers

    @staticmethod
    def _owned(resource, record):
        labels = resource.get("Labels") or {}
        return labels.get(MANAGED) == VERSION and labels.get(OWNER) == record["token"]

    @staticmethod
    def _references(container, network):
        return (network["Name"] in (container.get("Networks") or {})
                or container.get("Mode") in (network["Id"], network["Name"])
                or any(v.get("NetworkID") == network["Id"] for v in (container.get("Networks") or {}).values()))

    def _targets(self, record, networks, containers):
        names = record["containers"]
        if len(names) != len(set(names)) or len(names) > 4 or not all(_NAME.fullmatch(n) for n in names):
            raise NetworkResourceError("Invalid owned container names")
        if not _NAME.fullmatch(record["network"]):
            raise NetworkResourceError("Invalid owned network name")
        nets = [n for n in networks if n["Name"] == record["network"] or self._owned(n, record)]
        owned = [c for c in containers if c["Name"].lstrip("/") in names or self._owned(c, record)]
        if len(nets) > 1 or any(n["Name"] != record["network"] or not self._owned(n, record)
                               or n["Driver"] != "bridge" or not n.get("Internal")
                               or (record.get("network_id") and n["Id"] != record["network_id"])
                               for n in nets):
            raise NetworkResourceError("Network ownership mismatch; manual inspection required")
        if any(c["Name"].lstrip("/") not in names or not self._owned(c, record) for c in owned):
            raise NetworkResourceError("Container ownership mismatch; manual inspection required")
        if any(not _ID.fullmatch(r["Id"]) for r in nets + owned):
            raise NetworkResourceError("Unexpected resource ID")
        for network in nets:
            if any(self._references(c, network) and not self._owned(c, record) for c in containers):
                raise NetworkResourceError("Foreign container references owned network; preserving it")
        return nets, owned

    def _remove(self, record, *, orphan_empty_only=False):
        networks, containers = self._inventory()
        nets, owned = self._targets(record, networks, containers)
        if orphan_empty_only and (owned or any(n.get("Containers") for n in nets)):
            if not record.get("preservation_reported"):
                self._event("orphan_preserved_uncollected_evidence", token=record["token"],
                            network_ids=[n["Id"] for n in nets], container_ids=[c["Id"] for c in owned])
                record["preservation_reported"] = True
                self._write_record(record)
            return False
        # Validate every exact target BEFORE any deletion; refuse foreign endpoints.
        self._event("cleanup_targets", token=record["token"],
                    networks=nets, containers=owned, orphan_empty_only=orphan_empty_only)
        for container in owned:
            # Refresh IDs/ownership to detect replacement and newly attached resources.
            fresh_nets, fresh_containers = self._inventory()
            _, fresh_owned = self._targets(record, fresh_nets, fresh_containers)
            if not any(c["Id"] == container["Id"] for c in fresh_owned):
                raise NetworkResourceError("Container changed during cleanup")
            self._command(["docker", "rm", "-f", "-v", container["Id"]])
            if any(c["Id"] == container["Id"] for c in self._inventory()[1]):
                raise NetworkResourceError("Container still exists after removal")
        fresh_nets, fresh_containers = self._inventory()
        remaining, remaining_containers = self._targets(record, fresh_nets, fresh_containers)
        if remaining_containers:
            raise NetworkResourceError("Containers remain; refusing network removal")
        for network in remaining:
            if network.get("Containers") or any(self._references(c, network) for c in fresh_containers):
                raise NetworkResourceError("Network has endpoints; refusing removal")
            self._command(["docker", "network", "rm", network["Id"]])
            if any(n["Id"] == network["Id"] for n in self._inventory()[0]):
                raise NetworkResourceError("Network still exists after removal")
        record["phase"] = "cleaned"
        self._write_record(record)
        self._event("cleanup_verified", token=record["token"])
        return True

    def _maintain(self):
        """Called only under the host lock; failures stop admission, not agents."""
        blocked = []
        for record in self._records():
            if record["phase"] == "cleaned":
                continue
            if record["phase"] == "cleanup_failed":
                # Never retry a failed delete automatically. Operator can remove
                # the exact residual resources; read-only reconciliation unblocks.
                nets, owned = self._targets(record, *self._inventory())
                if not nets and not owned:
                    record["phase"] = "cleaned"
                    self._write_record(record)
                    self._event("cleanup_reconciled", token=record["token"])
                else:
                    blocked.append(record["token"])
                continue
            if not owner_dead(record["process"], self.identity):
                continue
            if time.time() - record["created_at"] < self.options["orphan_grace_seconds"]:
                continue
            try:
                self._remove(record, orphan_empty_only=record["phase"] != "cleanup_ready")
            except (NetworkResourceError, OSError, ValueError) as exc:
                record.update(phase="cleanup_failed", error=str(exc))
                self._write_record(record)
                self._event("cleanup_failed", token=record["token"], error=str(exc))
                blocked.append(record["token"])
        return blocked

    def _capacity(self):
        networks, _ = self._inventory()
        routes = json.loads(self._command(["ip", "-j", "-4", "route", "show", "table", "all"]))
        return capacity_snapshot(self.pools, networks, routes)

    def _wait(self, action, required):
        started = time.monotonic()
        last_reason = None
        while True:
            try:
                with self._lock():
                    blocked = self._maintain()
                    # Resolve a lost create response by inspecting the exact
                    # labeled reservation, even if other callers used the margin.
                    if action and self.pending_record and not blocked:
                        nets, owned = self._targets(self.pending_record, *self._inventory())
                        if nets and not owned:
                            result = action()
                            self._event("admitted_existing_reservation", token=self.pending_record["token"])
                            return result
                    snapshot = self._capacity()
                    need = required + self.options["safety_margin"]
                    reason = f"cleanup_failed:{','.join(blocked)}" if blocked else (
                        f"free_subnets={snapshot['free_subnets']} required_with_margin={need}"
                        if snapshot["free_subnets"] < need else None)
                    if reason is None:
                        result = action() if action else snapshot
                        self._event("admitted", requested_networks=required, capacity=snapshot,
                                    wait_seconds=time.monotonic() - started, options=self.options)
                        return result
                    if reason != last_reason:
                        self._event("admission_paused", reason=reason, capacity=snapshot)
            except (NetworkResourceError, OSError, ValueError) as exc:
                reason = str(exc)
                if self.root is not None and reason != last_reason:
                    try:
                        self._event("admission_paused", reason=reason)
                    except OSError:
                        logger.exception("Network audit unavailable; keeping admissions paused")
            if reason != last_reason:
                logger.warning("Docker network admission paused (agent clock not started): %s", reason)
                last_reason = reason
            time.sleep(self.options["poll_seconds"])

    def preflight(self, workers=1):
        if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
            raise ValueError("network preflight workers must be positive")
        return self._wait(None, workers)

    def create(self, network: str, containers: list[str], run_id: str):
        if not _NAME.fullmatch(network) or not all(_NAME.fullmatch(n) for n in containers):
            raise ValueError("Invalid Docker resource name")
        self.pending_record = None
        token = uuid.uuid4().hex
        record = {"token": token, "phase": "active", "created_at": time.time(),
                  "process": self.identity, "network": network, "containers": containers,
                  "run_id": run_id}
        labels = {MANAGED: VERSION, OWNER: token,
                  PREFIX + "run": hashlib.sha256(run_id.encode()).hexdigest()[:24],
                  PREFIX + "pid": str(self.identity["pid"]),
                  PREFIX + "uid": str(self.identity["uid"]),
                  PREFIX + "boot": self.identity["boot_id"],
                  PREFIX + "start": self.identity["start_ticks"]}
        def allocate():
            record["daemon_id"] = self.daemon_id
            networks, existing = self._inventory()
            matches = [n for n in networks if n["Name"] == network]
            if len(matches) == 1 and self._owned(matches[0], record):
                self._targets(record, networks, existing)
                record["network_id"] = matches[0]["Id"]
                self._write_record(record)
                return record, labels
            if any(n["Name"] == network for n in networks) or any(c["Name"].lstrip("/") in containers for c in existing):
                raise NetworkResourceError("Resource name already exists; refusing stale-name deletion")
            self.pending_record = record
            self._write_record(record)  # ownership exists even if create response is lost
            self._event("network_create_requested", token=token, network=network)
            args = ["docker", "network", "create", "--internal", *label_args(labels), network]
            identifier = self._command(args).strip()
            if not _ID.fullmatch(identifier):
                raise NetworkResourceError("Unexpected created network ID")
            record["network_id"] = identifier
            self._write_record(record)
            return record, labels
        return self._wait(allocate, 1)

    def cleanup(self, record):
        """Called only after collection; failures do not replace the agent result."""
        try:
            with self._lock():
                if record["phase"] == "cleaned":
                    return True
                if record["phase"] == "cleanup_failed":
                    return False
                record["phase"] = "cleanup_ready"
                self._write_record(record)
                return self._remove(record)
        except (NetworkResourceError, OSError, ValueError) as exc:
            record.update(phase="cleanup_failed", error=str(exc))
            try:
                with self._lock():
                    self._write_record(record)
                    self._event("cleanup_failed", token=record["token"], error=str(exc))
            except Exception:
                logger.exception("Could not persist network cleanup failure")
            logger.error("Docker cleanup failed; new admissions will pause: %s", exc)
            return False


def label_args(labels):
    return [part for key, value in sorted(labels.items()) for part in ("--label", f"{key}={value}")]
