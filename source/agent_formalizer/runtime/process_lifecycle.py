"""Dedicated host subprocess supervisor; no per-tool or native timer changes.

Each invocation owns exactly one process tree. A Linux subreaper catches even
detached descendants; normal exit and cancellation both reap them before this
supervisor exits. Never enable process-wide subreaping in a threaded runner.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def command(argv):
    return [sys.executable, str(Path(__file__).resolve()), "--", *argv]


def terminate(process):
    """Ask the dedicated supervisor to drain its tree; bound broken cleanup."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
            raise RuntimeError("host process supervisor failed to drain its tree")


def _children():
    return [int(p) for p in Path(f"/proc/self/task/{os.getpid()}/children").read_text().split()]


def _drain(proc):
    started = time.monotonic()
    sent = set()
    while True:
        proc.poll()
        children = _children()
        if not children:
            return
        elapsed = time.monotonic() - started
        if elapsed >= 5:
            raise RuntimeError("host process descendants survived cleanup")
        sig = signal.SIGTERM if elapsed < 2 else signal.SIGKILL
        for pid in children:
            if pid == proc.pid:
                if proc.poll() is not None:
                    continue
            else:
                try:
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        continue
                except ChildProcessError:
                    continue
            # These are unreaped direct children of this single-threaded
            # supervisor: their PIDs cannot be recycled between wait and kill.
            if (pid, sig) not in sent:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
                sent.add((pid, sig))
        time.sleep(.01)


class _Cancelled(BaseException):
    pass


def main(argv):
    if not argv or argv[0] != "--" or len(argv) < 2:
        raise ValueError("expected -- and one command")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot enable subprocess reaping")
    def cancel(_signum, _frame):
        raise _Cancelled()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, cancel)
    proc = None
    code = 143
    try:
        proc = subprocess.Popen(argv[1:])  # Inherit stdio and the exact environment.
        code = proc.wait()
    except _Cancelled:
        pass
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        if proc is not None:
            _drain(proc)
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
