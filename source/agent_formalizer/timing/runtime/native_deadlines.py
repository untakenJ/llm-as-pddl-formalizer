"""Small, inspected native-runtime transformations and gateway socket waits.

Only named watchdog functions are transformed. A missed source pattern fails
closed at import, rather than silently claiming native timing compatibility.
"""
import ast
import importlib.abc
import importlib.machinery
import os
import socket
import ssl
import sys

from benchmark_logical_time import Deadline, wait_for

TARGETS = {
    "generic": {"ga": "code_run"},
    "nanobot": {"nanobot.agent.tools.shell": "execute"},
    "hermes": {"tools.environments.base": "_wait_for_process"},
}


def transform(source, module, filename):
    tree = ast.parse(source, filename)
    changes = 0

    class Rewrite(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            nonlocal changes
            if ((module == "ga" and node.name == "code_run") or
                    (module == "tools.environments.base" and node.name == "_wait_for_process")):
                class Check(ast.NodeTransformer):
                    def visit_Compare(self, test):
                        nonlocal changes
                        expr = ast.unparse(test)
                        if expr in {"time.time() - start_t > timeout", "time.monotonic() > deadline"}:
                            changes += 1
                            return ast.copy_location(ast.parse("_benchmark_deadline.expired()", mode="eval").body, test)
                        return self.generic_visit(test)
                node = Check().visit(node)
                wrapper = ast.parse("with __import__('benchmark_logical_time').Deadline(timeout) as _benchmark_deadline:\n    pass").body[0]
                wrapper.body = node.body
                node.body = [wrapper]
                return node
            return self.generic_visit(node)

        def visit_Await(self, node):
            nonlocal changes
            if module == "nanobot.agent.tools.shell" and isinstance(node.value, ast.Call):
                call = node.value
                if (ast.unparse(call.func) == "asyncio.wait_for" and call.args
                        and ast.unparse(call.args[0]) == "process.communicate()"):
                    changes += 1
                    call.func = ast.parse("__import__('benchmark_logical_time').wait_for", mode="eval").body
            return self.generic_visit(node)

    tree = Rewrite().visit(tree)
    if changes != 1:
        raise RuntimeError(f"logical deadline native source mismatch: {module}: {changes}")
    return compile(ast.fix_missing_locations(tree), filename, "exec")


class Finder(importlib.abc.MetaPathFinder):
    def __init__(self):
        checkpoint = os.environ.get('BENCHMARK_EXTERNAL_CALL_TIMING') == 'call-checkpoint-v1'
        if checkpoint:
            from python_native_checkpoints import TARGETS as targets, transform as rewrite
        else:
            targets, rewrite = TARGETS, transform
        self.targets, self.rewrite = targets, rewrite

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.targets.get(os.environ.get("BENCHMARK_DEADLINE_HARNESS"), {}):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            raise RuntimeError("logical deadline source is unavailable: " + fullname)

        rewrite = self.rewrite
        class Loader(importlib.machinery.SourceFileLoader):
            def get_code(self, name):
                return rewrite(self.get_data(self.path).decode("utf-8"), name, self.path)
        spec.loader = Loader(fullname, spec.origin)
        return spec


def install():
    if os.environ.get('BENCHMARK_EXTERNAL_CALL_TIMING') == 'call-checkpoint-v1':
        from python_checkpoints import ready
        ready()
    sys.meta_path.insert(0, Finder())
    # Sync Python gateway reads (requests/urllib/SSL). The low-level socket
    # retries its *read*, not the HTTP/model request, so no partial bytes replay.
    # Local control sockets and arbitrary external endpoints are not changed.
    native_socket = socket.socket

    def gateway(sock):
        try:
            peer = sock.getpeername()
            return isinstance(peer, tuple) and peer[1] in {8766, 8768}
        except OSError:
            return False

    def read_with_deadline(sock, method, *args, **kwargs):
        timeout = sock.gettimeout()
        if timeout is None or timeout <= 0 or not gateway(sock):
            return method(*args, **kwargs)
        with Deadline(timeout) as deadline:
            try:
                while True:
                    if deadline.expired():
                        raise socket.timeout("timed out")
                    sock.settimeout(min(0.1, deadline.remaining()))
                    try:
                        return method(*args, **kwargs)
                    except socket.timeout:
                        continue
            finally:
                sock.settimeout(timeout)

    class LogicalSocket(native_socket):
        def recv_into(self, *args, **kwargs):
            return read_with_deadline(self, super().recv_into, *args, **kwargs)

        def recv(self, *args, **kwargs):
            return read_with_deadline(self, super().recv, *args, **kwargs)

    socket.socket = LogicalSocket
    original_ssl_read = ssl.SSLSocket.read
    def ssl_read(self, *args, **kwargs):
        return read_with_deadline(self, lambda *a, **k: original_ssl_read(self, *a, **k), *args, **kwargs)
    ssl.SSLSocket.read = ssl_read

    # httpcore's async backends have their own cancellation deadlines. Replace
    # only stream.read's deadline; the receive operation and bytes stay native.
    try:
        from httpcore._backends.anyio import AnyIOStream
        from httpcore import ReadTimeout
        original_read = AnyIOStream.read
        async def async_read(self, max_bytes, timeout=None):
            if os.environ.get('BENCHMARK_EXTERNAL_CALL_TIMING') == 'call-checkpoint-v1':
                peer = self.get_extra_info('server_addr')
                if not (isinstance(peer, tuple) and peer[1] in {8766, 8768}):
                    return await original_read(self, max_bytes, timeout=timeout)
            try:
                return await wait_for(original_read(self, max_bytes, timeout=None), timeout)
            except TimeoutError as exc:
                raise ReadTimeout(str(exc)) from exc
        AnyIOStream.read = async_read
    except ImportError:
        pass
