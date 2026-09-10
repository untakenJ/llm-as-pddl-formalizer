"""Native Python continuation, timeout and fast-path checks without real APIs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from agent_formalizer.timing.call_checkpoint import CheckpointBroker, RecoveryUnsafe
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.configuration.config import HERMES_ENV_PATH, NANOBOT_ENV_PATH, GENERIC_REPO_PATH

RUNTIME = Path(__file__).resolve().parents[1] / 'source/agent_formalizer/timing/runtime'


class PythonCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='python-checkpoint-test-')
        self.broker = CheckpointBroker(self.tmp.name)
        self.clock = AttemptClock(30)
        self.broker.attach(self.clock)
        self.processes = []

    def tearDown(self):
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
            proc.communicate(timeout=5)
        self.broker.close()
        self.tmp.cleanup()

    def start(self, body):
        code = f'''import sys, os, json, time
sys.path.insert(0, {str(RUNTIME)!r})
from agent_formalizer.timing import logical_time
sys.modules['benchmark_logical_time'] = logical_time
os.environ['BENCHMARK_DEADLINE_DIR'] = {self.tmp.name!r}
os.environ['BENCHMARK_EXTERNAL_CALL_TIMING'] = 'call-checkpoint-v1'
import python_checkpoints as cp
cp.ready()
''' + body
        proc = subprocess.Popen([sys.executable, '-u', '-c', code], env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(proc)
        self.assertEqual(proc.stdout.readline().strip(), 'READY')
        return proc

    def test_retained_context_and_timer_only_charge_accepted_request(self):
        proc = self.start('''data = [{'role':'user','content':'unchanged'}]
with cp.watch_context(data), logical_time.Deadline(10) as deadline:
    physical = time.monotonic()
    print('READY')
    input()
    print(json.dumps({'remaining':deadline.remaining(), 'physical':time.monotonic()-physical, 'data':data}))
''')
        self.broker.freeze('model')
        time.sleep(0.2)
        receipt = self.broker.settle('model', 1.0, rollback=True)
        self.assertFalse(receipt['native_due'])
        self.broker.resume()
        out, err = proc.communicate('\n', timeout=5)
        self.assertEqual(proc.returncode, 0, err)
        value = json.loads(out)
        self.assertAlmostEqual(value['remaining'], 9, delta=0.15)
        self.assertGreater(value['physical'], 0.2)
        self.assertEqual(value['data'], [{'role': 'user', 'content': 'unchanged'}])

    def test_actual_native_async_timeout_still_cancels(self):
        proc = self.start('''import asyncio
async def main():
    async def native():
        print('READY')
        await asyncio.sleep(100)
    try:
        await logical_time.wait_for(native(), 0.3)
    except TimeoutError:
        print('NATIVE_TIMEOUT')
asyncio.run(main())
''')
        self.broker.freeze('solver')
        receipt = self.broker.settle('solver', 1)
        self.assertTrue(receipt['native_due'])
        out, err = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(out.strip(), 'NATIVE_TIMEOUT')

    def test_changed_business_state_rejects_actual_recovery_not_healthy_call(self):
        proc = self.start('''data = []
with cp.watch_context(data):
    print('READY')
    input()
    data.append('legitimate concurrent result')
    print('CHANGED')
    input()
''')
        self.broker.freeze('solver')
        proc.stdin.write('\n'); proc.stdin.flush()
        self.assertEqual(proc.stdout.readline().strip(), 'CHANGED')
        self.broker.barrier('prepare', rollback=False)
        with self.assertRaises(RecoveryUnsafe):
            self.broker.barrier('prepare', rollback=True)
        proc.communicate('\n', timeout=5)

    def test_many_python_stream_read_deadlines_have_no_per_event_rpc(self):
        proc = self.start('''print('READY')
input()
started = time.monotonic()
for _ in range(25000):
    with logical_time.Deadline(10) as d:
        d.remaining()
print(time.monotonic()-started)
input()
''')
        proc.stdin.write('\n'); proc.stdin.flush()
        elapsed = float(proc.stdout.readline())
        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(self.broker.clients), 1)
        self.assertFalse(self.broker.leases)
        print(f'25000 Python local deadline pairs: {elapsed:.3f}s')
        proc.communicate('\n', timeout=5)

    def test_all_locked_native_python_sites_validate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('native_checkpoint_test', RUNTIME / 'python_native_checkpoints.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for harness, targets in module.TARGETS.items():
            root = GENERIC_REPO_PATH if harness == 'generic' else next(((HERMES_ENV_PATH if harness == 'hermes' else NANOBOT_ENV_PATH) / 'lib').glob('python*/site-packages'))
            for name in targets:
                path = root / (name.replace('.', '/') + '.py')
                with self.subTest(module=name):
                    module.transform(path.read_text(), name, str(path))
        with self.assertRaisesRegex(RuntimeError, 'source mismatch'):
            module.transform('pass', 'ga', 'drift.py')

    def test_explicit_adapter_channel_failure_is_reported(self):
        proc = self.start("print('READY')\ninput()\n")
        with self.broker.clients_lock:
            client = next(iter(self.broker.clients.values()))
            self.broker._send(client, {'op': 'invalid-test-operation'})
        until = time.monotonic() + 3
        while not self.broker.failure and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(self.broker.failure, 'call_checkpoint_control_failed')
        proc.communicate('\n', timeout=5)

    def test_async_transport_overlay_only_targets_external_call_gateways(self):
        proc = self.start('''import asyncio, types
calls=[]
class Stream:
    def __init__(self, port): self.port=port
    def get_extra_info(self, name): return ('127.0.0.1', self.port)
    async def read(self, n, timeout=None):
        calls.append([self.port, timeout])
        return b'unchanged'
core=types.ModuleType('httpcore'); core.ReadTimeout=TimeoutError
backend=types.ModuleType('httpcore._backends.anyio'); backend.AnyIOStream=Stream
sys.modules['httpcore']=core; sys.modules['httpcore._backends.anyio']=backend
import native_deadlines
native_deadlines.install()
print('READY')
input()
async def run():
    assert await Stream(80).read(100, timeout=0.1) == b'unchanged'
    assert await Stream(8766).read(100, timeout=0.1) == b'unchanged'
asyncio.run(run())
print(json.dumps(calls))
''')
        out, err = proc.communicate('\n', timeout=5)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(json.loads(out), [[80, 0.1], [8766, None]])
