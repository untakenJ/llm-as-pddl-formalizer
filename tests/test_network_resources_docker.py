"""Opt-in, no-model Docker lifecycle smoke test; only UUID-named test resources."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from agent_formalizer.configuration.config import BASE_IMAGE
from agent_formalizer.docker.network_resources import DEFAULT_OPTIONS, NetworkResources, label_args


@unittest.skipUnless(os.environ.get("RUN_NETWORK_RESOURCE_DOCKER_TESTS") == "1",
                     "set RUN_NETWORK_RESOURCE_DOCKER_TESTS=1 for local Docker lifecycle smoke")
class NetworkResourcesDockerTests(unittest.TestCase):
    def test_dead_process_empty_network_recovered_without_touching_live_owner(self):
        manager = NetworkResources(options={**DEFAULT_OPTIONS, "orphan_grace_seconds": 1})
        before = set(manager._command(["docker", "network", "ls", "-q", "--no-trunc"]).split())
        name = "pddl-network-orphan-smoke-" + uuid.uuid4().hex
        live_record = None
        try:
            live_record, _ = manager.create(name + "-live-net", [], "network-orphan-smoke")
            script = (
                "import json, sys; "
                "from agent_formalizer.docker.network_resources import NetworkResources; "
                "m = NetworkResources(); "
                "record, _ = m.create(sys.argv[1], [], 'network-orphan-smoke'); "
                "print(json.dumps(record), flush=True)"
            )
            process = subprocess.run([sys.executable, "-c", script, name + "-dead-net"],
                capture_output=True, text=True, check=True, timeout=30)
            dead_record = json.loads(process.stdout)
            # Owner has exited without cleanup. No container or evidence is lost.
            time.sleep(1.1)
            manager.preflight()
            remaining = set(manager._command(["docker", "network", "ls", "-q", "--no-trunc"]).split())
            self.assertNotIn(dead_record["network_id"], remaining)
            self.assertEqual(remaining, before | {live_record["network_id"]})
        finally:
            if live_record is not None:
                self.assertTrue(manager.cleanup(live_record), "Cleanup failed; inspect, do not force retry")
        self.assertEqual(set(manager._command(["docker", "network", "ls", "-q", "--no-trunc"]).split()), before)

    def test_two_workers_creation_stopped_reference_and_verified_cleanup(self):
        def command(args):
            return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout
        before_networks = set(command(["docker", "network", "ls", "-q", "--no-trunc"]).split())
        before_containers = set(command(["docker", "ps", "-aq", "--no-trunc"]).split())
        image = command(["docker", "image", "inspect", "--format", "{{.Id}}", BASE_IMAGE]).strip()
        with tempfile.TemporaryDirectory(prefix="pddl-network-smoke-evidence-") as temporary:
            evidence = Path(temporary)
            preflight = NetworkResources(evidence_dir=evidence)
            snapshot = preflight.preflight(2)
            self.assertGreaterEqual(snapshot["free_subnets"], 2 + DEFAULT_OPTIONS["safety_margin"])
            def worker(_):
                manager = NetworkResources(evidence_dir=evidence)
                name = "pddl-network-smoke-" + uuid.uuid4().hex
                record = None
                try:
                    record, labels = manager.create(name + "-net", [name], "network-lifecycle-smoke")
                    # A created (not running) container still references its network.
                    identifier = command(["docker", "create", "--pull", "never", "--name", name,
                        "--network", name + "-net", *label_args(labels), image, "true"]).strip()
                    with manager._lock():
                        manager._maintain()
                    self.assertEqual(command(["docker", "inspect", "--format", "{{.Id}}", identifier]).strip(), identifier)
                    return record["network_id"]
                finally:
                    record = record or manager.pending_record
                    if record is not None:
                        self.assertTrue(manager.cleanup(record), "Cleanup failed: inspect the shared registry; do not force retry")
            with ThreadPoolExecutor(max_workers=2) as pool:
                created = list(pool.map(worker, range(2)))
            self.assertEqual(len(set(created)), 2)
            events = [json.loads(line) for p in evidence.glob("*.jsonl") for line in p.read_text().splitlines()]
            self.assertEqual(sum(e["event"] == "cleanup_verified" for e in events), 2)
        self.assertEqual(set(command(["docker", "network", "ls", "-q", "--no-trunc"]).split()), before_networks)
        self.assertEqual(set(command(["docker", "ps", "-aq", "--no-trunc"]).split()), before_containers)


if __name__ == "__main__":
    unittest.main()
