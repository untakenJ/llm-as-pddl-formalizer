"""Real control sockets/clock, mocked Docker only; no external API requests."""
import concurrent.futures
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.timing.call_checkpoint import CheckpointBroker, CheckpointClosed, RecoveryUnsafe
from agent_formalizer.timing.checkpoint_monitor import monitor
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.external_calls.control import ToolControl, read_json, write_json


class ConcurrentCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="checkpoint-concurrent-")
        self.root = Path(self.tmp.name)
        self.broker = CheckpointBroker(self.root / "deadlines", self.root / "events.jsonl")
        self.clock = AttemptClock(15)
        self.stop = threading.Event()
        self.model_state = {}
        self.workspace = SimpleNamespace(
            _deadline_broker=self.broker, _gateway_control_dir=self.root,
            _solver_control_monitor=SimpleNamespace(path=self.root / "solver.json"),
            _gateway_terminal_error=None, container_name="mock-native-agent", gateway_name="mock-gateway",
            _read_gateway_control=lambda: dict(self.model_state),
            enforce_agent_deadline=lambda: self.stop.set())
        self.docker = patch("agent_formalizer.timing.checkpoint_monitor.subprocess.run",
                            return_value=SimpleNamespace(returncode=0, stdout="true"))
        self.commands = self.docker.start()
        self.thread = threading.Thread(target=monitor, args=(self.workspace, self.clock, self.stop))
        self.thread.start()

    def tearDown(self):
        self.stop.set()
        self.thread.join(5)
        self.docker.stop()
        self.broker.close()
        self.tmp.cleanup()

    def control(self, name):
        return ToolControl(self.root / (name + ".json"), independent=True)

    def test_owner_cleanup_at_checkpoint_does_not_invalidate(self):
        def closing(*args):
            self.broker.close()
            raise CheckpointClosed('owner cleanup')
        with patch.object(self.broker, 'freeze', side_effect=closing):
            write_json(self.root / 'model-timing.json', {'call_id': 'closing', 'phase': 'running'})
            self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.assertIsNone(self.workspace._gateway_terminal_error)
        self.assertEqual(self.commands.call_count, 0)

    def test_lost_participant_recovery_has_accurate_classification(self):
        error = RecoveryUnsafe('lost checkpoint peer',
                               classification='checkpoint_participant_lost_during_recovery')
        with patch.object(self.broker, 'freeze', side_effect=error):
            write_json(self.root / 'model-timing.json', {'call_id': 'recovery', 'phase': 'running'})
            self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        terminal = self.workspace._gateway_terminal_error
        self.assertEqual(terminal['reason'], 'external_call_recovery_unsafe')
        self.assertEqual(terminal['classification'], 'checkpoint_participant_lost_during_recovery')

    def test_two_models_and_solver_can_overlap_without_double_charging(self):
        first = self.control("solver")
        first.begin()
        time.sleep(0.15)
        second, third = self.control("model-timing"), self.control("model-timing")
        second.begin()
        third.begin()
        time.sleep(0.2)
        self.assertNotEqual(second.path, third.path)
        self.assertFalse(self.clock.snapshot()["paused"])
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            list(pool.map(lambda control: control.finish(0.4), [first, second, third]))
        self.assertIsNone(self.workspace._gateway_terminal_error)
        snapshot = self.clock.snapshot()
        self.assertAlmostEqual(snapshot["active_duration_seconds"], snapshot["wall_duration_seconds"], delta=0.12)
        self.assertLess(snapshot["active_duration_seconds"], 1.0)  # not 3 x 0.4 s
        self.assertEqual(self.commands.call_count, 0)

    def test_stale_stream_snapshot_is_not_an_invalidator(self):
        self.model_state = {"active_committed_streams": 1}
        control = self.control("model-timing")
        control.begin()
        control.finish(0.03)
        self.assertIsNone(self.workspace._gateway_terminal_error)
        self.assertFalse(self.clock.snapshot()["paused"])
        self.assertFalse(any(c.args[0][1] == "kill" for c in self.commands.call_args_list))

    def test_state_handoff_during_inspect_does_not_poison_later_recovery(self):
        self.model_state = {"active_committed_streams": 1}
        def inspected(*args, **kwargs):
            self.model_state = {"active_committed_streams": 0}
            return SimpleNamespace(returncode=0, stdout="true")
        self.commands.side_effect = inspected
        control = self.control("model-timing")
        control.begin()
        control.publish(rollback_count=1)
        time.sleep(0.05)
        control.finish(0.01)
        self.assertIsNone(self.workspace._gateway_terminal_error)

    def test_actual_recovery_crossing_native_progress_has_specific_evidence(self):
        solver, model = self.control("solver"), self.control("model-timing")
        solver.begin()
        model.begin()
        solver.publish(rollback_count=1)
        self.thread.join(2)
        error = self.workspace._gateway_terminal_error
        self.assertEqual(error["reason"], "external_call_recovery_unsafe")
        self.assertEqual(error["evidence"]["recovering_calls"], {solver.state["call_id"]: 1})

    def test_native_cancellation_is_not_control_disappearance(self):
        control = self.control("solver")
        control.begin()
        control.publish(phase="cancelled", pause_requested=False)
        time.sleep(0.1)
        other = self.control("model-timing")
        other.begin()
        other.finish(0.01)
        self.assertIsNone(self.workspace._gateway_terminal_error)

    def test_native_deadline_does_not_require_agent_cleanup_to_exit(self):
        # A live native lease can remain while an agent catches its timeout.
        import os
        control = self.control("solver")
        control.begin()
        self.broker.leases["native-cleanup"] = {"pid": os.getpid(), "target": self.broker.logical + 0.05}
        from agent_formalizer.external_calls.control import NativeDeadlineExpired
        with self.assertRaises(NativeDeadlineExpired):
            control.finish(0.1)
        control.publish(phase="native_done")
        self.assertIsNone(self.workspace._gateway_terminal_error)

    def test_next_model_cannot_resurrect_settled_native_timeout(self):
        import os
        from agent_formalizer.external_calls.control import NativeDeadlineExpired
        previous = self.control('solver')
        previous.begin()
        self.broker.leases['native'] = {'pid': os.getpid(), 'target': self.broker.logical + 0.01}
        original = self.broker.settle
        following = self.control('model-timing')

        def settled(*args, **kwargs):
            receipt = original(*args, **kwargs)
            # The native timeout callback immediately initiates a new request.
            # Publish without blocking the controller thread on begin's ACK.
            following.publish(call_id='subsequent-native-model', phase='running', pause_requested=True,
                              pause_started_unix=time.time(), started_monotonic=time.monotonic(),
                              charged_seconds=0.0, terminal_infra_error=None, rollback_count=0)
            return receipt

        with patch.object(self.broker, 'settle', side_effect=settled):
            with self.assertRaises(NativeDeadlineExpired):
                previous.finish(0.2)
        previous.publish(phase='native_done')
        self.broker.leases.pop('native', None)
        following.finish(0.01)
        self.assertIsNone(self.workspace._gateway_terminal_error)


if __name__ == "__main__":
    unittest.main()
