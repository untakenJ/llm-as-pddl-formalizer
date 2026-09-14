from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_formalizer.docker.network_resources import (
    DEFAULT_OPTIONS, DEFAULT_POOLS, MANAGED, OWNER, VERSION,
    NetworkResourceError, NetworkResources, capacity_snapshot, owner_dead,
    process_identity, validate_options,
)
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.orchestrator import run_batch


def net(identifier="a" * 64, name="test-net", labels=None, subnet="10.240.0.0/24"):
    return {"Id": identifier, "Name": name, "Driver": "bridge", "Internal": True,
            "Labels": labels or {}, "Containers": {},
            "IPAM": {"Config": [{"Subnet": subnet}]}}


class FakeDocker:
    def __init__(self):
        self.networks = []
        self.containers = []
        self.commands = []
        self.routes = []
        self.fail_delete = False
        self.keep_deleted = False
        self.lose_create_response = False
        self.create_failures = 0
        self.sequence = 1

    def __call__(self, args):
        self.commands.append(args)
        if args[:3] == ["docker", "network", "ls"]:
            return "\n".join(n["Id"] for n in self.networks)
        if args[:3] == ["docker", "network", "inspect"]:
            return json.dumps([n for n in self.networks if n["Id"] in args[3:]])
        if args[:3] == ["docker", "ps", "-aq"]:
            return "\n".join(c["Id"] for c in self.containers)
        if args[:3] == ["docker", "inspect", "--type"]:
            return "\n".join(json.dumps(c) for c in self.containers if c["Id"] in args[6:])
        if args[:3] == ["ip", "-j", "-4"]:
            return json.dumps(self.routes)
        if args[:3] == ["docker", "network", "create"]:
            if self.create_failures:
                self.create_failures -= 1
                raise NetworkResourceError("all predefined address pools have been fully subnetted")
            labels = dict(args[i + 1].split("=", 1) for i, a in enumerate(args) if a == "--label")
            identifier = f"{self.sequence:064x}"
            self.sequence += 1
            self.networks.append(net(identifier, args[-1], labels,
                                     f"10.240.{len(self.networks)}.0/24"))
            if self.lose_create_response:
                self.lose_create_response = False
                raise NetworkResourceError("network create: TimeoutExpired")
            return identifier + "\n"
        if args[:2] == ["docker", "rm"]:
            if self.fail_delete:
                raise NetworkResourceError("container removal failed")
            if not self.keep_deleted:
                self.containers = [c for c in self.containers if c["Id"] != args[-1]]
            return args[-1]
        if args[:2] == ["docker", "stop"]:
            return args[-1]
        if args[:3] == ["docker", "network", "rm"]:
            if self.fail_delete:
                raise NetworkResourceError("network has active endpoints")
            if not self.keep_deleted:
                self.networks = [n for n in self.networks if n["Id"] != args[-1]]
            return args[-1]
        raise AssertionError(f"Unexpected fake Docker command: {args}")

    def add_container(self, name, labels, network, *, identifier="c" * 64):
        self.containers.append({"Id": identifier, "Name": "/" + name,
            "Labels": labels, "Mode": network["Name"],
            "Networks": {network["Name"]: {"NetworkID": network["Id"]}}})

    def deletions(self):
        return [a for a in self.commands if a[:2] == ["docker", "rm"]
                or a[:3] == ["docker", "network", "rm"]]


class NetworkResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.docker = FakeDocker()
        self.manager = NetworkResources(evidence_dir=self.root / "evidence")
        self.manager.root = self.root
        self.manager.daemon_id = "fake-daemon"
        self.manager.pools = [{"Base": "10.240.0.0/16", "Size": 24}]
        self.manager._command = self.docker

    def tearDown(self):
        self.temp.cleanup()

    def create(self, suffix="one"):
        return self.manager.create("test-" + suffix + "-net", ["test-" + suffix], "run-" + suffix)

    def make_dead(self, record):
        record["process"] = {**record["process"], "boot_id": "previous-boot"}
        record["created_at"] = time.time() - 1000
        self.manager._write_record(record)

    def test_default_pool_count_and_route_conflicts(self):
        result = capacity_snapshot(DEFAULT_POOLS, [], [])
        self.assertEqual(result["total_subnets"], 31)
        result = capacity_snapshot(DEFAULT_POOLS,
            [net(subnet="172.17.0.0/16")], [{"dst": "172.18.0.0/16"}, {"dst": "default"}])
        self.assertEqual(result["free_subnets"], 29)
        # Multiple addresses/routes in one subnet consume one allocation, not three.
        result = capacity_snapshot(DEFAULT_POOLS, [net(subnet="172.17.0.0/16")],
            [{"dst": "172.17.0.1/32"}, {"dst": "172.17.255.255"}])
        self.assertEqual(result["free_subnets"], 30)

    def test_smaller_configured_subnets_have_more_capacity(self):
        self.assertEqual(capacity_snapshot(self.manager.pools, [], [])["free_subnets"], 256)
        self.assertEqual(capacity_snapshot(self.manager.pools, [], [{"dst": "10.0.0.0/8"}])["free_subnets"], 0)

    def test_invalid_pool_is_not_assumed_safe(self):
        with self.assertRaises(NetworkResourceError):
            capacity_snapshot([{"Base": "0.0.0.0/0", "Size": 24}], [], [])

    def test_options_are_strict(self):
        for value in ({}, {**DEFAULT_OPTIONS, "extra": 1},
                      {**DEFAULT_OPTIONS, "poll_seconds": 61},
                      {**DEFAULT_OPTIONS, "safety_margin": True}):
            with self.assertRaises(ValueError):
                validate_options(value)

    def test_cleanup_is_verified_and_idempotent(self):
        record, labels = self.create()
        self.docker.add_container("test-one", labels, self.docker.networks[0])
        self.assertTrue(self.manager.cleanup(record))
        self.assertEqual(record["phase"], "cleaned")
        self.assertFalse(self.docker.networks)
        self.assertFalse(self.docker.containers)
        self.assertEqual(len(self.docker.deletions()), 2)
        self.assertTrue(self.manager.cleanup(record))
        self.assertEqual(len(self.docker.deletions()), 2)
        self.assertTrue(any("cleanup_verified" in p.read_text() for p in (self.root / "evidence").iterdir()))

    def test_live_owner_empty_network_survives_gc(self):
        record, _ = self.create()
        record["created_at"] -= 1000
        self.manager._write_record(record)
        with self.manager._lock():
            self.assertEqual(self.manager._maintain(), [])
        self.assertEqual(len(self.docker.networks), 1)
        self.assertFalse(self.docker.deletions())

    def test_orphan_empty_network_is_recovered_but_legacy_is_preserved(self):
        record, _ = self.create()
        self.make_dead(record)
        self.docker.networks.append(net("f" * 64, "legacy-net", subnet="10.240.10.0/24"))
        self.manager.preflight(6)
        self.assertEqual([n["Name"] for n in self.docker.networks], ["legacy-net"])

    def test_dead_owner_container_kept_until_collection_authorizes_cleanup(self):
        record, labels = self.create()
        # Also represents an exited/created container: there are no active endpoints.
        self.docker.add_container("test-one", labels, self.docker.networks[0])
        self.make_dead(record)
        with self.manager._lock():
            self.manager._maintain()
        self.assertFalse(self.docker.deletions())
        self.assertTrue(any(c[:2] == ["docker", "stop"] for c in self.docker.commands))
        record["phase"] = "cleanup_ready"
        self.manager._write_record(record)
        with self.manager._lock():
            self.manager._maintain()
        self.assertEqual(len(self.docker.deletions()), 2)

    def test_foreign_container_reference_protects_network_and_all_targets(self):
        record, labels = self.create()
        self.docker.add_container("test-one", labels, self.docker.networks[0])
        self.docker.add_container("unrelated", {}, self.docker.networks[0], identifier="d" * 64)
        self.assertFalse(self.manager.cleanup(record))
        self.assertFalse(self.docker.deletions())
        self.assertEqual(record["phase"], "cleanup_failed")

    def test_replaced_resource_name_is_never_deleted(self):
        record, _ = self.create()
        self.docker.networks[0]["Labels"] = {}
        self.assertFalse(self.manager.cleanup(record))
        self.assertFalse(self.docker.deletions())

    def test_failed_delete_stops_without_retry_and_blocks_new_admissions(self):
        record, _ = self.create()
        self.docker.fail_delete = True
        self.assertFalse(self.manager.cleanup(record))
        self.assertEqual(len(self.docker.deletions()), 1)
        with patch("agent_formalizer.docker.network_resources.time.sleep", side_effect=InterruptedError("test stop")):
            with self.assertRaises(InterruptedError):
                self.manager.preflight()
        self.assertEqual(len(self.docker.deletions()), 1)
        # Operator resolves the residue out of band; read-only reconciliation resumes.
        self.docker.networks.clear()
        self.assertEqual(self.manager.preflight()["free_subnets"], 256)

    def test_success_exit_code_without_actual_removal_is_failure(self):
        record, _ = self.create()
        self.docker.keep_deleted = True
        self.assertFalse(self.manager.cleanup(record))
        self.assertEqual(record["phase"], "cleanup_failed")

    def test_capacity_wait_does_not_create_or_consume_an_execution_retry(self):
        self.manager.pools = [{"Base": "10.240.0.0/24", "Size": 24}]
        self.manager.options["safety_margin"] = 0
        self.docker.networks = [net()]
        def release(_):
            self.assertFalse(any(a[:3] == ["docker", "network", "create"] for a in self.docker.commands))
            self.docker.networks.clear()
        with patch("agent_formalizer.docker.network_resources.time.sleep", side_effect=release) as sleep:
            record, _ = self.create()
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(sum(a[:3] == ["docker", "network", "create"] for a in self.docker.commands), 1)
        self.assertEqual(record["phase"], "active")

    def test_allocation_race_exhaustion_retries_same_reservation(self):
        self.docker.create_failures = 1
        with patch("agent_formalizer.docker.network_resources.time.sleep") as sleep:
            record, _ = self.create()
        creates = [a for a in self.docker.commands if a[:3] == ["docker", "network", "create"]]
        self.assertEqual(creates[0], creates[1])
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)

    def test_lost_create_response_adopts_own_labeled_network(self):
        self.docker.lose_create_response = True
        self.manager.pools = [{"Base": "10.240.0.0/24", "Size": 24}]
        self.manager.options["safety_margin"] = 0
        with patch("agent_formalizer.docker.network_resources.time.sleep"):
            record, _ = self.create()
        self.assertEqual(record["network_id"], self.docker.networks[0]["Id"])
        self.assertEqual(sum(a[:3] == ["docker", "network", "create"] for a in self.docker.commands), 1)

    def test_owner_death_requires_boot_pid_start_identity(self):
        current = process_identity()
        self.assertFalse(owner_dead(current, current))
        self.assertTrue(owner_dead({**current, "boot_id": "prior-boot"}, current))
        self.assertTrue(owner_dead({**current, "start_ticks": "0"}, current))
        self.assertFalse(owner_dead({}, current))
        with patch("agent_formalizer.docker.network_resources._start_ticks", side_effect=PermissionError):
            self.assertFalse(owner_dead(current, current))

    def test_command_timeout_is_finite(self):
        manager = NetworkResources()
        with patch("agent_formalizer.docker.network_resources.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("docker", 20)) as run:
            with self.assertRaises(NetworkResourceError):
                manager._command(["docker", "network", "ls"])
        self.assertEqual(run.call_args.kwargs["timeout"], 20)

    def test_symlink_registry_record_refused(self):
        target = self.root / "elsewhere"
        target.write_text("{}")
        (self.root / ("b" * 32 + ".json")).symlink_to(target)
        with self.assertRaises(OSError):
            list(self.manager._records())
        self.assertFalse(self.docker.deletions())

    def test_workspace_cleanup_failure_keeps_flags_and_does_not_raise(self):
        workspace = AgentWorkspace("instance", "test-one", SimpleNamespace())
        workspace._network_resources = self.manager
        workspace._network_record, _ = self.create()
        workspace._started = workspace._network_created = True
        self.docker.fail_delete = True
        workspace.cleanup()
        self.assertTrue(workspace._network_created)
        self.assertTrue(workspace._started)

    def test_shared_lock_serializes_threads(self):
        other = NetworkResources()
        other.root, other.daemon_id = self.root, self.manager.daemon_id
        entered = threading.Event()
        def take_lock():
            with other._lock():
                entered.set()
        with self.manager._lock():
            worker = threading.Thread(target=take_lock)
            worker.start()
            self.assertFalse(entered.wait(0.1))
        worker.join(2)
        self.assertTrue(entered.is_set())

    def test_shared_lock_serializes_processes(self):
        script = (
            "from pathlib import Path; import sys; "
            "from agent_formalizer.docker.network_resources import NetworkResources; "
            "m = NetworkResources(); m.root = Path(sys.argv[1]); "
            "print('ready', flush=True); "
            "\nwith m._lock(): print('acquired', flush=True)"
        )
        with self.manager._lock():
            process = subprocess.Popen([sys.executable, "-c", script, str(self.root)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(process.stdout.readline().strip(), "ready")
            time.sleep(0.1)
            self.assertIsNone(process.poll())
        output, error = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, error)
        self.assertEqual(output.strip(), "acquired")

    def test_batch_preflight_precedes_dispatch_and_completed_resume_skips_it(self):
        adapter = SimpleNamespace(name="hermes", validate_runtime=lambda: None,
            resolved_config=SimpleNamespace(attempts_per_case=1, sha256="config", label="profile"))
        for selected in (None, 1):
            state = {"problems": {"p01": {"attempts": {"1": {"selected_execution": selected}}}}}
            order = []
            with patch("agent_formalizer.orchestrator._freeze_execution_reference", return_value=(None, "image")), \
                 patch("agent_formalizer.orchestrator.validate_runtime_lock", return_value={}), \
                 patch("agent_formalizer.orchestrator._adapter_code_sha256", return_value="code"), \
                 patch("agent_formalizer.orchestrator._config_qualified_label", return_value="model"), \
                 patch("agent_formalizer.orchestrator.refresh_cell_state", return_value=state), \
                 patch("agent_formalizer.orchestrator.NetworkResources") as manager, \
                 patch("agent_formalizer.orchestrator.run_parallel", side_effect=lambda *a, **kw: order.append("dispatch") or []):
                manager.return_value.preflight.side_effect = lambda n: order.append(("preflight", n))
                run_batch(adapter, "domain", "dataset", [1], workers=6, out_dir_root=self.root)
            self.assertEqual(order, [("preflight", 1), "dispatch"] if selected is None else ["dispatch"])


if __name__ == "__main__":
    unittest.main()
