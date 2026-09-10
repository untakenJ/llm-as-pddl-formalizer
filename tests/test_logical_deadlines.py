from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import patch

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.timing import logical_time as lt
from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.timing.deadline_integration import monitor, validate
from agent_formalizer.external_calls.control import write_json

RUNTIME = Path(lt.__file__).with_name("runtime")
sys.modules.setdefault("benchmark_logical_time", lt)
spec = importlib.util.spec_from_file_location("native_deadlines_test", RUNTIME / "native_deadlines.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class LogicalDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="logical-deadline-test-")
        self.directory = Path(self.tmp.name)
        self.broker = lt.DeadlineBroker(self.directory)
        self.clock = AttemptClock(1000)
        self.broker.attach(self.clock)
        self.env = patch.dict(os.environ, {"BENCHMARK_DEADLINE_DIR": str(self.directory)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.broker.close()
        self.tmp.cleanup()

    def test_hidden_minutes_excluded_and_charge_once(self):
        with lt.Deadline(140) as deadline:
            before = deadline.remaining()
            self.broker.freeze()
            time.sleep(0.1)
            receipt = self.broker.settle("call", 51)
            self.assertAlmostEqual(before - deadline.remaining(), 51, delta=0.1)
            self.assertEqual(receipt, self.broker.settle("call", 51))
            self.assertAlmostEqual(before - deadline.remaining(), 51, delta=0.1)
            self.assertFalse(receipt["native_due"])

    def test_nested_deadline_wins_before_result(self):
        with lt.Deadline(140) as outer, lt.Deadline(120) as inner:
            self.broker.freeze()
            result = self.broker.settle("late-result", 160)
            self.assertTrue(inner.expired())
            self.assertGreater(outer.remaining(), 19)
            self.assertLessEqual(result["charged_seconds"], 120)
            self.assertEqual(result["native_due"], [inner.key])
            self.assertTrue(self.broker.pending(result["native_due"]))
        self.assertFalse(self.broker.pending(result["native_due"]))

    def test_socket_does_not_allow_clock_mutation(self):
        with self.assertRaises(RuntimeError):
            lt._rpc({"op": "pause"})
        self.assertFalse(self.broker.paused)

    def test_benchmark_budget_wins_before_native_deadline(self):
        self.clock = AttemptClock(0.5)
        self.broker.attach(self.clock)
        with lt.Deadline(10):
            self.broker.freeze()
            receipt = self.broker.settle("budget", 60)
            self.assertTrue(receipt["benchmark_due"])
            self.assertLessEqual(receipt["charged_seconds"], 0.5)
            self.assertFalse(receipt["native_due"])

    def test_new_monitor_retains_post_commit_sidecar_exit_invalidation(self):
        stop = threading.Event()
        workspace = SimpleNamespace(
            _deadline_broker=self.broker, _gateway_control_dir=self.directory,
            _solver_control_monitor=None, container_name="test-agent",
            gateway_name="test-gateway",
            _read_gateway_control=lambda: {"active_committed_streams": 1},
        )
        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, "false\n", "")
        with patch("agent_formalizer.timing.deadline_integration.subprocess.run", side_effect=run) as invoked:
            monitor(workspace, self.clock, stop)
        self.assertEqual(workspace._gateway_terminal_error["reason"], "post_commit_stream_failure")
        self.assertTrue(any(call.args[0][:2] == ["docker", "kill"] for call in invoked.call_args_list))

    def test_new_monitor_rejects_overlapping_external_calls(self):
        model = self.directory / "model-timing.json"
        solver = self.directory / "solver.json"
        for path in (model, solver):
            write_json(path, {"phase": "running", "call_id": path.name})
        workspace = SimpleNamespace(
            _deadline_broker=self.broker, _gateway_control_dir=self.directory,
            _solver_control_monitor=SimpleNamespace(path=solver),
            container_name="test-agent", _read_gateway_control=lambda: {},
        )
        with patch("agent_formalizer.timing.deadline_integration.subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
            monitor(workspace, self.clock, threading.Event())
        self.assertEqual(workspace._gateway_terminal_error["reason"], "external_call_stream_overlap")

    def test_real_clocks_are_unchanged(self):
        self.broker.freeze()
        real = time.monotonic()
        logical = lt.logical_now()
        time.sleep(0.08)
        self.assertGreater(time.monotonic() - real, 0.07)
        self.assertEqual(lt.logical_now(), logical)

    def test_node_native_deadlines_pause_without_changing_real_time(self):
        runtime = RUNTIME / "node-deadlines.cjs"
        script = f"""
const clock = require({json.dumps(str(runtime))});
const physical = Date.now(), logical = clock.nowMs();
const cancelled = clock.setTimeout(() => console.log('BAD_CANCELLED_TIMER'), 1);
clock.clearTimeout(cancelled);
const timer = clock.setTimeout(() => console.log('DEADLINE'), 400);
timer.unref(); timer.ref(); timer.refresh();
console.log('READY');
setTimeout(() => console.log(JSON.stringify({{physical:Date.now()-physical, logical:clock.nowMs()-logical}})), 600);
"""
        self.broker.freeze()
        proc = subprocess.Popen(["node", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), "READY")
            value = json.loads(proc.stdout.readline())
            self.assertGreater(value["physical"], 550)
            self.assertEqual(value["logical"], 0)
            receipt = self.broker.settle("node", 0.5)
            self.assertTrue(receipt["native_due"])
            out, err = proc.communicate(timeout=4)
            self.assertEqual(proc.returncode, 0, err)
            self.assertEqual(out.strip(), "DEADLINE")
            self.assertFalse(self.broker.leases)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_openclaw_overlay_targets_only_watchdogs(self):
        from agent_formalizer.timing.openclaw_deadlines import sources, transform
        root = Path('/usr/lib/node_modules/openclaw')
        if not root.exists():
            self.skipTest('locked OpenClaw runtime not installed')
        counts = []
        for path in sources(root):
            overlay, count = transform(path)
            counts.append(count)
            self.assertNotIn('globalThis.setTimeout =', overlay)
            if path.name.startswith('selection-'):
                self.assertIn('abortWarnTimer = setTimeout(', overlay)
                self.assertIn('abortTimer = __benchmarkSetTimeout(', overlay)
        self.assertEqual(counts, [3, 3, 1, 1, 1, 0, 1, 1])

    def test_async_native_timeout_and_cancellation(self):
        async def run():
            with self.assertRaises(TimeoutError):
                await lt.wait_for(asyncio.sleep(1), 0.06)
            result = await lt.wait_for(asyncio.sleep(0.01, result=42), 1)
            self.assertEqual(result, 42)
        asyncio.run(run())
        self.assertEqual(self.broker.leases, {})

    def test_generic_source_transform_preserves_native_result(self):
        source = '''\
import time
def code_run(timeout):
    start_t = time.time()
    return time.time() - start_t > timeout
'''
        scope = {}
        exec(native.transform(source, "ga", "fixture.py"), scope)
        self.assertFalse(scope["code_run"](1))
        self.assertFalse(self.broker.leases)
        with self.assertRaises(RuntimeError):
            native.transform("def code_run(timeout): pass", "ga", "drift.py")

    def test_gnu_timeout_actual_native_timer(self):
        library = self.directory / "timeout_deadline.so"
        subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-o", str(library), str(RUNTIME / "timeout_deadline.c"),
                        "-ldl", "-pthread", "-lm"], check=True, capture_output=True)
        env = {**os.environ, "LD_PRELOAD": str(library)}
        # Native timeout still returns 124, rather than a benchmark-made result.
        result = subprocess.run(["timeout", "0.15", "sleep", "3"], env=env, timeout=5)
        self.assertEqual(result.returncode, 124)
        kill_after = subprocess.run(["timeout", "--kill-after=0.1", "0.15", "sh", "-c", "trap '' TERM; sleep 3"],
                                    env=env, timeout=5, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(kill_after.returncode, -signal.SIGKILL)
        self.broker._prune()
        self.assertFalse(self.broker.leases)
        # A real process-group suspension does not spend this logical deadline.
        # Leave a seconds-scale setup margin under concurrent Docker tests.
        # A 300 ms native deadline can legitimately expire before the host
        # polling thread is scheduled; that says nothing about retry escrow.
        proc = subprocess.Popen(["timeout", "2", "sleep", "3"],
                                env=env, stdout=subprocess.PIPE, start_new_session=True)
        try:
            end = time.monotonic() + 2
            sleeping = False
            watcher_ready = False
            while time.monotonic() < end:
                # GNU can fork its command before arming its watchdog. Wait
                # for BOTH the command's physical sleep and the timer thread
                # after register RPC has returned. Stopping mid-register can
                # instead exercise the physical control-socket timeout.
                children = Path(f"/proc/{proc.pid}/task/{proc.pid}/children")
                for child in children.read_text().split() if children.exists() else []:
                    try:
                        sleeping = "nanosleep" in Path(f"/proc/{child}/wchan").read_text()
                    except FileNotFoundError:
                        pass
                    if sleeping:
                        break
                watchers = [p for p in Path(f'/proc/{proc.pid}/task').glob('*/wchan')
                            if p.parent.name != str(proc.pid)]
                watcher_ready = any('nanosleep' in p.read_text() for p in watchers if p.exists())
                registered = any(item['pid'] == proc.pid for item in self.broker.leases.values())
                if sleeping and watcher_ready and registered:
                    break
                time.sleep(0.005)
            self.assertTrue(sleeping, "child did not enter its physical sleep")
            self.assertTrue(watcher_ready, "parent had not finished arming the logical watchdog")
            self.assertTrue(self.broker.leases)
            os.killpg(proc.pid, signal.SIGSTOP)
            self.broker.freeze()
            time.sleep(3.2)
            receipt = self.broker.settle("retry", 0.03)
            self.assertFalse(receipt["native_due"])
            os.killpg(proc.pid, signal.SIGCONT)
            self.broker.resume()
            out, _ = proc.communicate(timeout=3)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(out, b"")
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGCONT)
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()


class DeadlineProfileTests(unittest.TestCase):
    def test_unsupported_harness_fails_closed_before_running(self):
        adapter = SimpleNamespace(name="zeroclaw", resolved_config=SimpleNamespace(raw={"resolved": {"external_call_timing": lt.POLICY_ID}}))
        with self.assertRaisesRegex(RuntimeError, "coverage not implemented"):
            validate(adapter)

    def test_nanobot_only_new_condition_propagates_runtime_environment(self):
        from agent_formalizer.claws import get_adapter
        from agent_formalizer.timing.deadline_integration import ENVIRONMENT_KEYS
        old = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool.json")
        new = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool_logical_deadline.json")
        configs = [get_adapter("nanobot", benchmark_profile=p, model="openai/gpt-4o-mini", api_key="not-real")._benchmark_config() for p in (old, new)]
        self.assertNotIn("allowedEnvKeys", configs[0]["tools"]["exec"])
        self.assertEqual(configs[1]["tools"]["exec"]["allowedEnvKeys"], list(ENVIRONMENT_KEYS))
        self.assertFalse(any("API_KEY" in key for key in ENVIRONMENT_KEYS))

    def test_opt_in_identity_leaves_original_unchanged(self):
        old = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool.json")
        new = load_benchmark_profile(HISTORICAL_PROFILES_DIR / "native_safety_streaming_solver_as_tool_logical_deadline.json")
        before = old.resolve(harness="generic").raw
        after = new.resolve(harness="generic").raw
        self.assertNotIn("external_call_timing", before["resolved"])
        self.assertEqual(after["resolved"]["external_call_timing"], lt.POLICY_ID)
        self.assertEqual(before["resolved"]["budgets"], after["resolved"]["budgets"])


if __name__ == "__main__":
    unittest.main()
