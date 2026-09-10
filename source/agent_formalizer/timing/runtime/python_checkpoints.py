"""Call-boundary receipts for Python native deadlines, never physical clocks.

The host is authoritative. Local deadline registration and stream reads do not
perform IPC; the control thread exchanges only boundary snapshots. Contexts are
observed, not replaced: recovery is rejected if the retained continuation has
progressed in parallel. No prompt or context content leaves this process.
"""
import contextlib
import json
import math
import os
from pathlib import Path
import socket
import threading
import time

_lock = threading.RLock()
_ready = threading.Event()
_state = None
_deadlines = set()
_contexts = {}
_snapshot = None
_tools = 0
_parallel = False
_failure = None
_started = False


def _fingerprint(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError, RuntimeError):
        return None


def _listen():
    global _state, _snapshot, _parallel, _failure
    try:
        directory = Path(os.environ['BENCHMARK_DEADLINE_DIR'])
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.connect(str(directory / 'checkpoint.sock'))
            with channel.makefile('rb') as stream:
                for line in stream:
                    message = json.loads(line)
                    operation = message['op']
                    if operation not in {'hello', 'checkpoint', 'prepare', 'settle', 'resume'}:
                        raise RuntimeError('unknown checkpoint operation')
                    with _lock:
                        _state = message
                        if operation == 'hello':
                            _ready.set()
                            continue
                        if operation == 'checkpoint':
                            _snapshot = {key: _fingerprint(value) for key, value in _contexts.items()}
                            _parallel = _tools > 1
                        changed = (message.get('rollback') and
                                   (_snapshot is None or _parallel or any(
                                       saved is None or key not in _contexts or
                                       _fingerprint(_contexts[key]) != saved
                                       for key, saved in (_snapshot or {}).items())))
                        if operation == 'resume':
                            _snapshot = None
                        reply = {'sequence': message['sequence']}
                        if changed:
                            reply['error'] = 'checkpoint_business_state_changed'
                        else:
                            reply['target'] = min((d.target for d in _deadlines), default=None)
                        channel.sendall((json.dumps(reply) + '\n').encode())
        raise RuntimeError('checkpoint channel closed')
    except Exception as exc:
        _failure = type(exc).__name__
        _ready.set()
        # Do not let a harness catch this adapter failure and count the
        # resulting business error as a valid model/tool outcome.
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as report:
                report.settimeout(1)
                report.connect(str(Path(os.environ['BENCHMARK_DEADLINE_DIR']) / 'broker.sock'))
                report.sendall(b'{"op":"failure"}\n')
                report.recv(512)
        except OSError:
            pass  # a dead broker is independently detected by the host monitor


def ready():
    global _started
    with _lock:
        if not _started:
            _started = True
            threading.Thread(target=_listen, name='benchmark-checkpoint', daemon=True).start()
    if not _ready.wait(15) or _failure:
        raise RuntimeError('benchmark checkpoint control unavailable: ' + str(_failure))


def now():
    ready()
    with _lock:
        state = _state
        return state['logical'] + (0.0 if state['paused'] else
                                  max(0.0, time.monotonic() - state['anchor']))


class Deadline:
    def __init__(self, seconds):
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('deadline must be finite and nonnegative')
        ready()
        with _lock:
            self.target = now() + seconds
            _deadlines.add(self)

    def remaining(self):
        return max(0.0, self.target - now())

    def expired(self):
        return self.remaining() <= 0

    def close(self):
        with _lock:
            _deadlines.discard(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@contextlib.contextmanager
def watch_context(value):
    ready()
    key = object()
    with _lock:
        _contexts[key] = value
    try:
        yield
    finally:
        with _lock:
            _contexts.pop(key, None)


@contextlib.contextmanager
def tool_activity():
    global _tools, _parallel
    ready()
    with _lock:
        _tools += 1
        if _snapshot is not None and _tools > 1:
            _parallel = True
    try:
        yield
    finally:
        with _lock:
            _tools -= 1
