"""Real Node watchdogs, local sockets and immutable call fixtures; no API keys."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.timing.call_checkpoint import CheckpointBroker, POLICY_ID
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.external_calls.checkpoint import RequestCheckpoint
from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.timing.deadline_integration import validate

RUNTIME = Path(__file__).resolve().parents[1] / "source/agent_formalizer/timing/runtime/node-checkpoints.cjs"


class RequestCheckpointTests(unittest.TestCase):
    def test_same_pending_request_not_another_agent_turn(self):
        events = []
        request = b'{"messages":[{"role":"assistant","tool_calls":[{"id":"fixed"}]}]}'
        checkpoint = RequestCheckpoint(request, event=events.append)
        for reason in ("429", "connection_reset", "429"):
            checkpoint.discard(reason)
            self.assertIs(checkpoint.body, request)
        checkpoint.commit()
        self.assertEqual([e["action"] for e in events], ["checkpoint", "rollback", "rollback", "rollback", "commit"])
        self.assertEqual(checkpoint.discarded, 3)
        self.assertEqual(len({e["request_sha256"] for e in events}), 1)
        with self.assertRaises(RuntimeError):
            checkpoint.discard("post_commit_stream_failure")
        with self.assertRaises(RuntimeError):
            checkpoint.commit()

    def test_profile_is_separate_and_five_native_adapters_supported(self):
        from agent_formalizer.claws import get_adapter
        new = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool_call_checkpoint.json")
        old = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool_logical_deadline.json")
        self.assertEqual(new.resolve(harness="openclaw").raw["resolved"]["external_call_timing"], POLICY_ID)
        self.assertEqual(old.resolve(harness="openclaw").raw["resolved"]["external_call_timing"], "logical-deadline-v1")
        for harness in ("generic", "nanobot", "hermes", "zeroclaw"):
            adapter = get_adapter(harness, benchmark_profile=new, model="openai/gpt-4o-mini", api_key="not-real")
            validate(adapter)


class NativeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="call-checkpoint-test-")
        self.broker = CheckpointBroker(self.tmp.name)
        self.clock = AttemptClock(100)
        self.broker.attach(self.clock)
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=3)
        self.broker.close()
        self.tmp.cleanup()

    def node(self, body):
        script = f"const runtime=require({json.dumps(str(RUNTIME))}); (async()=>{{await runtime.ready(); {body}}})().catch(e=>{{console.error(e); process.exit(1)}});"
        child = subprocess.Popen(["node", "-e", script], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "BENCHMARK_DEADLINE_DIR": self.tmp.name})
        self.children.append(child)
        return child

    def test_hidden_delay_restores_remaining_budget(self):
        child = self.node("""
const physical=Date.now();
runtime.setTimeout(()=>console.log(JSON.stringify({elapsed:Date.now()-physical})), 500);
console.log('READY');
""")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        time.sleep(0.65)
        receipt = self.broker.settle("retry", 0.1, rollback=True)
        self.assertFalse(receipt["native_due"])
        self.broker.resume()
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertGreater(json.loads(out)["elapsed"], 950)
        self.assertGreater(self.clock.snapshot()["infra_pause_seconds"], 0.5)

    def test_real_timeout_wins_before_candidate_commit(self):
        child = self.node("runtime.setTimeout(()=>console.log('NATIVE_TIMEOUT'), 300); console.log('READY');")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        result = self.broker.settle("input_too_slow", 0.5)
        self.assertTrue(result["native_due"])
        self.assertLessEqual(result["charged_seconds"], 0.3)
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertEqual(out.strip(), "NATIVE_TIMEOUT")
        self.assertFalse(self.broker.pending(result["native_due"]))

    def test_cancelled_watchdog_does_not_reappear_at_settlement(self):
        child = self.node("""
const timer=runtime.setTimeout(()=>console.log('BAD'),300);
setTimeout(()=>{runtime.clearTimeout(timer);console.log('CANCELLED')},100);
setTimeout(()=>{},600); console.log('READY');
""")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        self.assertEqual(child.stdout.readline().strip(), "CANCELLED")
        self.assertFalse(self.broker.settle("cancel", 0.8)["native_due"])
        self.broker.resume()
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertNotIn("BAD", out)

    def test_fired_inner_deadline_does_not_wait_for_live_outer_deadline(self):
        child = self.node("runtime.setTimeout(()=>console.log('INNER'),300);runtime.setTimeout(()=>console.log('OUTER'),900);console.log('READY');")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        result = self.broker.settle("nested", 0.5)
        self.assertTrue(result["native_due"])
        self.assertEqual(child.stdout.readline().strip(), "INNER")
        self.assertFalse(self.broker.pending(result["native_due"]))
        self.broker.resume()
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertEqual(out.strip(), "OUTER")

    def test_business_changes_cannot_be_silently_replayed(self):
        child = self.node("""
const context={messages:[{role:'user',content:'same input'}]}; runtime.watchContext(context);
setTimeout(()=>{context.messages.push({role:'tool',content:'concurrent result'});console.log('CHANGED')},100);
setTimeout(()=>{},1000); console.log('READY');
""")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        self.assertEqual(child.stdout.readline().strip(), "CHANGED")
        with self.assertRaisesRegex(RuntimeError, "participant failed"):
            self.broker.settle("unsafe", 0.01, rollback=True)

    def test_parallel_native_tools_fail_closed_on_rollback(self):
        child = self.node("runtime.enterTool();runtime.enterTool();setTimeout(()=>{},1000); console.log('READY');")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        with self.assertRaisesRegex(RuntimeError, "participant failed"):
            self.broker.settle("parallel", 0.01, rollback=True)

    def test_stream_hot_path_has_no_io_or_blocking_wait(self):
        child = self.node("""
const fs=require('node:fs'); fs.readFileSync=()=>{throw new Error('stream path filesystem read')};
Atomics.wait=()=>{throw new Error('stream path synchronous wait')};
const start=performance.now();
for(let i=0;i<25000;i++){const timer=runtime.setTimeout(()=>{},1000);runtime.clearTimeout(timer);}
console.log(JSON.stringify({pairs:25000,ms:performance.now()-start}));
""")
        out, err = child.communicate(timeout=8)
        self.assertEqual(child.returncode, 0, err)
        metric = json.loads(out)
        self.assertLess(metric["ms"], 3000)  # Old synchronous implementation takes minutes.
        print("checkpoint timer throughput:", metric)

    def test_identical_settlement_is_not_charged_twice(self):
        self.broker.freeze()
        before = self.clock.remaining()
        receipt = self.broker.settle("same", 2)
        self.assertEqual(receipt, self.broker.settle("same", 2))
        self.assertAlmostEqual(before - self.clock.remaining(), 2, delta=0.1)

    def test_busy_native_event_loop_is_not_a_three_second_invalidator(self):
        child = self.node("console.log('READY'); const end=Date.now()+3300; while(Date.now()<end){}; setTimeout(()=>{},300);")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        receipt = self.broker.settle("busy", 0.01)
        self.broker.resume()
        self.assertIsNone(self.broker.failure)
        self.assertGreater(receipt["charged_seconds"], 3)
        out, err = child.communicate(timeout=4)
        self.assertEqual(child.returncode, 0, err)

    def test_cyclic_native_context_is_allowed_without_recovery(self):
        child = self.node("const context={}; context.self=context; runtime.watchContext(context); setTimeout(()=>{},500); console.log('READY');")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        self.broker.settle("healthy-cycle", 0.01)
        self.broker.resume()
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)

    def test_no_hidden_128_participant_invalidation_limit(self):
        # Fill the registry, not the machine with 128 extra Node processes.
        keys = [f"fixture-{i}" for i in range(128)]
        with self.broker.clients_lock:
            self.broker.clients.update({key: {} for key in keys})
        try:
            child = self.node("console.log('READY');")
            out, err = child.communicate(timeout=3)
            self.assertEqual(child.returncode, 0, err)
            self.assertEqual(out.strip(), "READY")
            self.assertIsNone(self.broker.failure)
        finally:
            with self.broker.clients_lock:
                for key in keys:
                    self.broker.clients.pop(key, None)

    def test_throwing_native_timeout_callback_is_not_a_protocol_failure(self):
        child = self.node("runtime.setTimeout(()=>{throw new Error('native callback failure')},200); console.log('READY');")
        self.assertEqual(child.stdout.readline().strip(), "READY")
        self.broker.freeze()
        self.broker.settle("native-throw", 0.3)
        out, err = child.communicate(timeout=3)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("native callback failure", err)
        self.assertNotIn("checkpoint control failed", err)
        self.assertIsNone(self.broker.failure)


if __name__ == "__main__":
    unittest.main()
