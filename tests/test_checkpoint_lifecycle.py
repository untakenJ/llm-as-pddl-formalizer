"""Deterministic peer-exit races over real local sockets; no model/solver API."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from agent_formalizer.timing.call_checkpoint import (
    CheckpointBroker, CheckpointClosed, RecoveryUnsafe,
    _participant_status, _process_identity,
)
from agent_formalizer.claws.base import AttemptClock

RUNTIME = Path(__file__).resolve().parents[1] / 'source/agent_formalizer/timing/runtime/node-checkpoints.cjs'


PEER = r'''
import json, os, socket, sys, threading
channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
channel.connect(sys.argv[1])
stream = channel.makefile('rb')
hello = json.loads(stream.readline())
assert hello['op'] == 'hello'
def listen():
    try:
        for line in stream:
            message = json.loads(line)
            if sys.argv[2] == 'exit_before_ack':
                os._exit(0)
            sequence = message['sequence']
            if sys.argv[2] == 'bad_ack_then_exit':
                sequence = 'wrong-sequence'
            channel.sendall((json.dumps({'sequence': sequence, 'target': None}) + '\n').encode())
            if sys.argv[2] == 'bad_ack_then_exit':
                os._exit(0)
    except OSError:
        pass
threading.Thread(target=listen, daemon=True).start()
print('READY', flush=True)
command = sys.stdin.readline().strip()
if command.startswith('notice'):
    notice = {'event': 'participant_exit', 'version': 1, 'participant': hello['participant'],
              'origin': 'native_exit', 'exit_code': 0}
    if command == 'notice_wrong_identity':
        notice['participant'] = 'another-connection'
    if command == 'notice_control_failure':
        notice.update(origin='control_failure', exit_code=70)
    channel.sendall((json.dumps(notice) + '\n').encode())
    if command == 'notice_then_bad_ack':
        channel.sendall(b'{"sequence":"wrong"}\n')
if command == 'close' or command.startswith('notice'):
    channel.shutdown(socket.SHUT_RDWR)
    channel.close()
    print('CLOSED', flush=True)
    sys.stdin.readline()  # Deliberately alive with no control connection.
'''


class ProcessIdentityTests(unittest.TestCase):
    def test_read_errors_are_unknown_not_exits(self):
        for error in [PermissionError(), OSError('read failed')]:
            with self.subTest(error=type(error).__name__), patch.object(Path, 'read_text', side_effect=error):
                self.assertEqual(_process_identity(123), ('unknown', None))
        with patch.object(Path, 'read_text', return_value='malformed'):
            self.assertEqual(_process_identity(123), ('unknown', None))
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError()):
            self.assertEqual(_process_identity(123), ('exited', None))

    def test_pid_reuse_and_missing_initial_identity(self):
        with patch('agent_formalizer.timing.call_checkpoint._process_identity', return_value=('alive', 200)):
            self.assertEqual(_participant_status({'pid': 123, 'start_time': 100}), 'exited')
            self.assertEqual(_participant_status({'pid': 123, 'start_time': 200}), 'alive')
            self.assertEqual(_participant_status({'pid': 123, 'start_time': None}), 'unknown')

    def test_real_process_start_time_is_captured(self):
        status, start = _process_identity(os.getpid())
        self.assertEqual(status, 'alive')
        self.assertIsInstance(start, int)


class CheckpointLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='checkpoint-lifecycle-')
        self.root = Path(self.tmp.name)
        self.broker = CheckpointBroker(self.root, self.root / 'events.jsonl')
        self.clock = AttemptClock(30)
        self.broker.attach(self.clock)
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.communicate(timeout=3)
        self.broker.close()
        self.tmp.cleanup()

    def peer(self, mode='normal'):
        child = subprocess.Popen(
            [sys.executable, '-u', '-c', PEER, str(self.root / 'checkpoint.sock'), mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.children.append(child)
        self.assertEqual(child.stdout.readline().strip(), 'READY')
        with self.broker.clients_lock:
            client = next(c for c in self.broker.clients.values() if c['pid'] == child.pid)
        return child, client

    def node(self, body, *, before_load=''):
        # Capture only the fixture's checkpoint socket to inject teardown and
        # transport faults; production does not monkey-patch net or native exit.
        script = f'''
const net = require('node:net'), fs = require('node:fs');
const connect = net.createConnection; let channel;
net.createConnection = (...args) => (channel = connect(...args));
{before_load}
const runtime = require({json.dumps(str(RUNTIME))});
(async () => {{ await runtime.ready(); {body} }})().catch(e => {{console.error(e); process.exit(1);}});
'''
        child = subprocess.Popen(['node', '-e', script], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 env={**os.environ, 'BENCHMARK_DEADLINE_DIR': str(self.root)})
        self.children.append(child)
        return child

    def command(self, child, command):
        child.stdin.write(command + '\n')
        child.stdin.flush()
        if command == 'close' or command.startswith('notice'):
            self.assertEqual(child.stdout.readline().strip(), 'CLOSED')
        else:
            self.assertEqual(child.wait(timeout=3), 0)

    def until(self, predicate):
        end = time.monotonic() + 3
        while not predicate() and time.monotonic() < end:
            time.sleep(0.005)
        self.assertTrue(predicate())

    def events(self):
        return [json.loads(line) for line in (self.root / 'events.jsonl').read_text().splitlines()]

    def test_exit_between_snapshot_and_send_keeps_other_peer_running(self):
        child, dying = self.peer()
        _, live = self.peer()
        original = self.broker._send
        failures = []

        def send(client, message):
            if client is dying and message['op'] == 'checkpoint':
                self.command(child, 'exit')
                try:
                    original(client, message)
                except BrokenPipeError:
                    failures.append('real-broken-pipe')
                    raise
            else:
                original(client, message)

        with patch.object(self.broker, '_send', side_effect=send):
            self.broker.freeze('model')
        self.assertEqual(failures, ['real-broken-pipe'])
        self.assertNotIn(dying['key'], self.broker.clients)
        self.assertIn(live['key'], self.broker.clients)
        self.assertNotIn(dying['key'], self.broker.checkpoint_participants)
        self.broker.settle('model', 0.1, rollback=True)
        self.broker.resume()
        self.assertIsNone(self.broker.failure)
        self.assertEqual([e['disposition'] for e in self.events()
                          if e.get('event') == 'checkpoint_participant_disconnected'], ['exited'])

    def test_exit_after_send_before_ack_is_not_control_failure(self):
        child, dying = self.peer('exit_before_ack')
        self.peer()
        self.broker.freeze('model')
        self.assertEqual(child.wait(timeout=3), 0)
        self.assertNotIn(dying['key'], self.broker.checkpoint_participants)
        self.broker.settle('model', 0.1)
        self.broker.resume()
        self.assertIsNone(self.broker.failure)

    def test_registry_lock_is_not_held_during_send(self):
        self.peer()
        original = self.broker._send
        acquired = threading.Event()

        def send(client, message):
            def inspect_registry():
                with self.broker.clients_lock:
                    acquired.set()
            thread = threading.Thread(target=inspect_registry)
            thread.start()
            try:
                self.assertTrue(acquired.wait(1), 'global registry lock held during socket I/O')
            finally:
                thread.join(1)
            original(client, message)

        with patch.object(self.broker, '_send', side_effect=send):
            self.broker.freeze('model')

    def test_live_peer_send_failure_is_still_invalid(self):
        child, dying = self.peer()
        original = self.broker._send

        def send(client, message):
            if client is dying:
                self.command(child, 'close')
            original(client, message)

        with patch.object(self.broker, '_send', side_effect=send):
            with self.assertRaisesRegex(RuntimeError, 'call_checkpoint_control_failed'):
                self.broker.freeze('model')
        self.assertIsNone(child.poll())
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')

    def test_idle_eof_from_live_peer_is_not_silently_removed(self):
        child, _ = self.peer()
        self.command(child, 'close')
        self.until(lambda: self.broker.failure is not None)
        with self.assertRaisesRegex(RuntimeError, 'call_checkpoint_control_failed'):
            self.broker.freeze('next-model')

    def test_native_exit_notice_allows_slow_teardown_and_other_participants(self):
        child, dying = self.peer()
        _, live = self.peer()
        self.command(child, 'notice')
        self.until(lambda: dying['disposition'] is not None)
        time.sleep(0.65)  # Deliberately past the old EOF/alive invalidation bound.
        self.assertIsNone(child.poll())
        self.assertEqual(dying['disposition'], 'native_exiting')
        self.broker.freeze('next-model')
        self.broker.settle('next-model', 0.1, rollback=True)
        self.broker.resume()
        self.assertIn(live['key'], self.broker.clients)
        self.assertIsNone(self.broker.failure)

    def test_notice_retirement_cannot_bypass_real_recovery(self):
        child, dying = self.peer()
        self.broker.freeze('solver')
        self.command(child, 'notice')
        self.until(lambda: dying['disposition'] is not None)
        self.assertIn(dying['key'], self.broker.checkpoint_participants)
        with self.assertRaisesRegex(RecoveryUnsafe, 'lost during recovery'):
            self.broker.settle('solver', 0.1, rollback=True)
        self.assertNotIn('solver', self.broker.settled)

    def assert_notice_fault(self, command):
        child, client = self.peer()
        self.command(child, command)
        self.until(lambda: client['disposition'] is not None)
        self.assertEqual(client['disposition'], 'control_failed')
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')

    def test_exit_notice_cannot_name_another_participant(self):
        self.assert_notice_fault('notice_wrong_identity')

    def test_control_failure_exit_notice_is_invalid(self):
        self.assert_notice_fault('notice_control_failure')

    def test_exit_notice_does_not_hide_a_subsequent_protocol_fault(self):
        self.assert_notice_fault('notice_then_bad_ack')

    def test_exit_notice_does_not_override_unknown_process_identity(self):
        child, client = self.peer()
        with patch('agent_formalizer.timing.call_checkpoint._participant_status', return_value='unknown'):
            self.command(child, 'notice')
            self.until(lambda: client['disposition'] is not None)
        self.assertEqual(client['disposition'], 'control_failed')

    def test_notice_arriving_during_send_failure_confirmation_is_consumed(self):
        child, client = self.peer()
        entered = threading.Event()
        original = self.broker._send

        def send(peer, message):
            if peer is client:
                # Model the send thread observing EPIPE before the reader has
                # consumed the terminal record already on the same connection.
                entered.set()
                raise BrokenPipeError('exit racing send')
            original(peer, message)

        def retire():
            if entered.wait(2):
                self.command(child, 'notice')

        notifier = threading.Thread(target=retire)
        notifier.start()
        try:
            with patch.object(self.broker, '_send', side_effect=send):
                self.broker.freeze('model')
        finally:
            notifier.join(3)
        self.assertFalse(notifier.is_alive())
        self.assertEqual(client['disposition'], 'native_exiting')
        self.assertIsNone(self.broker.failure)

    def test_real_node_exit_notice_precedes_slow_handle_cleanup(self):
        child = self.node('''
process.on('exit', () => {
  channel._handle.close();
  fs.writeSync(1, 'EXITING\\n');
  const end = Date.now() + 1200; while (Date.now() < end) {}
});
console.log('READY'); process.stdin.once('data', () => process.exit(0));
''')
        self.assertEqual(child.stdout.readline().strip(), 'READY')
        client = next(c for c in self.broker.clients.values() if c['pid'] == child.pid)
        child.stdin.write('exit\n')
        child.stdin.flush()
        self.assertEqual(child.stdout.readline().strip(), 'EXITING')
        self.until(lambda: client['disposition'] is not None)
        self.assertEqual(client['disposition'], 'native_exiting')
        time.sleep(0.65)
        self.assertIsNone(child.poll())
        self.assertIsNone(self.broker.failure)
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertEqual(out, '')

    def test_before_exit_and_synthetic_exit_do_not_retire_a_live_node(self):
        child = self.node('''
process.emit('exit', 0);
process.once('beforeExit', () => {
  console.log('REVIVED');
  setTimeout(() => console.log('CONTINUED'), 700);
});
''')
        self.assertEqual(child.stdout.readline().strip(), 'REVIVED')
        client = next(c for c in self.broker.clients.values() if c['pid'] == child.pid)
        self.assertIsNone(client['exit_notice'])
        self.broker.freeze('healthy')
        self.broker.settle('healthy', 0.01)
        self.broker.resume()
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertEqual(out.strip(), 'CONTINUED')
        self.until(lambda: client['disposition'] is not None)
        self.assertEqual(client['exit_notice']['origin'], 'native_exit')
        self.assertIsNone(self.broker.failure)

    def test_real_node_control_failure_exit_is_not_native_retirement(self):
        child = self.node("setTimeout(()=>{}, 3000); console.log('READY');")
        self.assertEqual(child.stdout.readline().strip(), 'READY')
        client = next(c for c in self.broker.clients.values() if c['pid'] == child.pid)
        self.broker._send(client, {'op': 'invalid-fixture-command'})
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 70, err)
        self.until(lambda: client['disposition'] is not None)
        self.assertEqual(client['exit_notice']['origin'], 'control_failure')
        self.assertEqual(client['disposition'], 'control_failed')
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')

    def test_native_nonzero_exit_is_not_an_infrastructure_failure(self):
        child = self.node('process.exit(7);')
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 7, err)
        self.until(lambda: not self.broker.clients)
        notices = [e for e in self.events() if e['event'] == 'checkpoint_participant_exit_notice']
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]['origin'], 'native_exit')
        self.assertEqual(notices[0]['exit_code'], 7)
        self.assertIsNone(self.broker.failure)

    def test_blocked_exit_notice_is_not_retried_and_keeps_native_exit_code(self):
        child = self.node('process.exit(7);', before_load='''
const originalWrite = fs.writeSync;
fs.writeSync = function(fd, value, ...args) {
  if (Buffer.isBuffer(value) && value.toString().includes('participant_exit')) {
    originalWrite(1, 'NOTICE_ATTEMPT\\n');
    throw Object.assign(new Error('fixture EAGAIN'), {code: 'EAGAIN'});
  }
  return originalWrite(fd, value, ...args);
};
''')
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 7, err)
        self.assertEqual(out.strip(), 'NOTICE_ATTEMPT')
        self.until(lambda: not self.broker.clients)
        self.assertIsNone(self.broker.failure)  # OS exit proof, not a missing notice.
        self.assertFalse(any(e['event'] == 'checkpoint_participant_exit_notice' for e in self.events()))

    def test_exit_notice_does_not_overtake_a_buffered_ack(self):
        child = self.node('''
Object.defineProperty(channel, 'writableLength', {get: () => 1});
process.exit(0);
''', before_load='''
const originalWrite = fs.writeSync;
fs.writeSync = function(fd, value, ...args) {
  if (Buffer.isBuffer(value) && value.toString().includes('participant_exit'))
    originalWrite(1, 'UNSAFE_NOTICE\\n');
  return originalWrite(fd, value, ...args);
};
''')
        out, err = child.communicate(timeout=3)
        self.assertEqual(child.returncode, 0, err)
        self.assertEqual(out, '')
        self.until(lambda: not self.broker.clients)
        self.assertIsNone(self.broker.failure)
        self.assertFalse(any(e['event'] == 'checkpoint_participant_exit_notice' for e in self.events()))

    def test_native_exit_cannot_clear_a_preexisting_host_fault(self):
        child = self.node("console.log('READY'); process.stdin.once('data', ()=>process.exit(0));")
        self.assertEqual(child.stdout.readline().strip(), 'READY')
        self.broker.failure = 'call_checkpoint_control_failed'
        self.command(child, 'exit')
        self.until(lambda: not self.broker.clients)
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')

    def test_ack_does_not_hide_observed_live_disconnect(self):
        child, client = self.peer()
        original = self.broker._send

        def send(peer, message):
            original(peer, message)
            # Supply a matching ACK, then an observed disconnect before the
            # barrier consumes it; the peer intentionally remains alive.
            peer['reply'] = {'sequence': message['sequence'], 'target': None}
            peer['state'] = 'disconnected'
            peer['event'].set()
            self.command(child, 'close')

        with patch.object(self.broker, '_send', side_effect=send):
            with self.assertRaisesRegex(RuntimeError, 'call_checkpoint_control_failed'):
                self.broker.freeze('model')
        self.assertIsNone(child.poll())
        self.assertEqual(client['disposition'], 'control_failed')

    def test_unknown_liveness_after_disconnect_fails_closed(self):
        child, _ = self.peer()
        with patch('agent_formalizer.timing.call_checkpoint._participant_status', return_value='unknown'):
            self.command(child, 'close')
            # Failure is published before the receive thread appends evidence.
            self.until(lambda: self.broker.failure is not None and bool(self.events()))
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')
        self.assertEqual(self.events()[-1]['process_status'], 'unknown')

    def test_transient_unknown_needs_subsequent_confirmed_exit(self):
        child, client = self.peer()
        # Hold the per-peer lock to keep the EOF handler from retiring first.
        with client['lock']:
            self.command(child, 'exit')
            with patch('agent_formalizer.timing.call_checkpoint._participant_status',
                       side_effect=['unknown', 'exited']):
                self.assertEqual(self.broker._disconnect(client, 'send'), 'exited')
        self.assertIsNone(self.broker.failure)
        event = self.events()[-1]
        self.assertEqual(event['initial_process_status'], 'unknown')
        self.assertEqual(event['process_status'], 'exited')

    def test_protocol_fault_is_not_erased_by_immediate_exit(self):
        child, _ = self.peer('bad_ack_then_exit')
        with self.assertRaisesRegex(RuntimeError, 'call_checkpoint_control_failed'):
            self.broker.freeze('model')
        self.assertEqual(child.wait(timeout=3), 0)
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')

    def test_retired_checkpoint_member_cannot_bypass_recovery_check(self):
        child, client = self.peer()
        self.broker.freeze('solver')
        self.command(child, 'exit')
        self.until(lambda: client['key'] not in self.broker.clients)
        self.assertIsNone(self.broker.failure)
        with self.assertRaisesRegex(RecoveryUnsafe, 'lost during recovery') as caught:
            self.broker.settle('solver', 0.1, rollback=True)
        self.assertEqual(caught.exception.classification, 'checkpoint_participant_lost_during_recovery')
        self.assertNotIn('solver', self.broker.settled)

    def test_same_exit_without_recovery_preserves_native_outcome(self):
        child, client = self.peer()
        self.broker.freeze('solver')
        self.command(child, 'exit')
        self.until(lambda: client['key'] not in self.broker.clients)
        self.broker.settle('solver', 0.1)
        self.broker.resume()
        self.assertIsNone(self.broker.failure)
        self.assertFalse(self.broker.checkpoint_participants)

    def test_repeated_retirement_does_not_erase_later_explicit_fault(self):
        child, client = self.peer()
        self.command(child, 'exit')
        self.until(lambda: client['disposition'] is not None)
        self.broker._disconnect(client, 'ack')
        self.broker._disconnect(client, 'protocol', ValueError('bad ACK'), protocol=True)
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')
        self.assertEqual(len([e for e in self.events()
                              if e.get('event') == 'checkpoint_participant_disconnected']), 1)

    def test_cleanup_racing_send_ends_without_new_failure(self):
        self.peer()
        original = self.broker._send
        entered, release = threading.Event(), threading.Event()
        errors = []

        def send(client, message):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release sender')
            original(client, message)

        def freeze():
            try:
                self.broker.freeze('model')
            except Exception as exc:
                errors.append(exc)

        with patch.object(self.broker, '_send', side_effect=send):
            worker = threading.Thread(target=freeze)
            worker.start()
            self.assertTrue(entered.wait(2))
            closer = threading.Thread(target=self.broker.close)
            closer.start()
            try:
                self.until(lambda: self.broker.closed)
            finally:
                release.set()
                worker.join(3)
                closer.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(closer.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], CheckpointClosed)
        self.assertIsNone(self.broker.failure)


if __name__ == '__main__':
    unittest.main()
