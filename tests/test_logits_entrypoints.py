"""Exercise package, host-script and standalone-sidecar imports with local HTTP."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from agent_formalizer.configuration.config import (
    LOGITS_BRIDGE_SCRIPT, LOGITS_GATEWAY_SCRIPT, LOGITS_MODEL_ASSETS_ROOT, PACKAGE_DIR,
    MODEL_GATEWAY_SCRIPT, PROVIDER_REASONING_MODULE,
)
from agent_formalizer.compute_platforms.logits.logits_openai_bridge import DEFAULT_MODEL_ASSETS_ROOT


# Replace only the remote model backend. Both HTTP services, authentication,
# gateway accounting and the production entrypoint execute normally.
RUNNER = '''
import importlib, runpy, sys
from types import SimpleNamespace
mode, entrypoint, import_root = sys.argv[1:]
sys.path.insert(0, import_root)
name = 'agent_formalizer.compute_platforms.logits.logits_openai_bridge' if mode == 'package' else 'logits_openai_bridge'
bridge = importlib.import_module(name)
class Backend:
    def __init__(self, *, model, **kwargs):
        self.model = model
        self.convention = SimpleNamespace(id='local-test')
    def chat_completion(self, body):
        return {'id': 'local-test', 'model': self.model, 'choices': [
            {'index': 0, 'message': {'role': 'assistant', 'content': 'relocated bridge'},
             'finish_reason': 'stop'}]}
    def close(self):
        pass
bridge.LogitsChatBackend = Backend
if mode == 'package':
    runpy.run_module('agent_formalizer.compute_platforms.logits.logits_gateway', run_name='__main__')
else:
    runpy.run_path(entrypoint, run_name='__main__')
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LogitsEntrypointTests(unittest.TestCase):
    def test_default_assets_match_installed_host_assets(self):
        self.assertEqual(DEFAULT_MODEL_ASSETS_ROOT, LOGITS_MODEL_ASSETS_ROOT)

    def test_package_entrypoint(self):
        self.check_entrypoint('package')

    def test_host_script_entrypoint_without_pythonpath(self):
        self.check_entrypoint('host')

    def test_flat_sidecar_without_repository_imports(self):
        self.check_entrypoint('sidecar')

    def check_entrypoint(self, mode):
        with tempfile.TemporaryDirectory(prefix='logits-entrypoint-') as tmp:
            directory = Path(tmp)
            entrypoint = LOGITS_GATEWAY_SCRIPT
            import_root = PACKAGE_DIR.parent if mode == 'package' else entrypoint.parent
            if mode == 'sidecar':
                for source in (LOGITS_GATEWAY_SCRIPT, LOGITS_BRIDGE_SCRIPT,
                               MODEL_GATEWAY_SCRIPT, PROVIDER_REASONING_MODULE):
                    shutil.copy2(source, directory / source.name)
                for name in ('external_calls', 'infra_diagnostics'):
                    shutil.copytree(PACKAGE_DIR / name, directory / name,
                                    ignore=shutil.ignore_patterns('__pycache__'))
                entrypoint = directory / entrypoint.name
                import_root = directory
            port, bridge_port = free_port(), free_port()
            while bridge_port == port:
                bridge_port = free_port()
            env = {
                'PATH': os.defpath,
                'PYTHONDONTWRITEBYTECODE': '1',
                'PDDL_LOGITS_MODEL': 'Qwen/Qwen3.5-4B',
                'PDDL_LOGITS_BRIDGE_PORT': str(bridge_port),
                'PDDL_GATEWAY_PORT': str(port),
                'PDDL_GATEWAY_LISTEN_HOST': '127.0.0.1',
                'PDDL_GATEWAY_API_KEY': 'local-test-key',
                'PDDL_GATEWAY_ALLOWED_MODELS': '["Qwen/Qwen3.5-4B"]',
                'PDDL_GATEWAY_ALLOWED_PATH_PREFIXES': '["/v1"]',
            }
            process = subprocess.Popen(
                [sys.executable, '-c', RUNNER, mode, str(entrypoint), str(import_root)],
                cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            origin = f'http://127.0.0.1:{port}'
            try:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        self.fail(process.communicate(timeout=2)[1])
                    try:
                        with opener.open(origin + '/__benchmark__/health', timeout=0.2):
                            break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() >= deadline:
                            self.fail('gateway did not become healthy')
                        time.sleep(0.02)
                request = urllib.request.Request(
                    origin + '/v1/chat/completions',
                    data=json.dumps({'model': 'Qwen/Qwen3.5-4B', 'messages': [
                        {'role': 'user', 'content': 'hello'}]}).encode(),
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer placeholder'},
                )
                with opener.open(request, timeout=5) as response:
                    result = json.load(response)
                self.assertEqual(result['choices'][0]['message']['content'], 'relocated bridge')
                with opener.open(origin + '/__benchmark__/status', timeout=2) as response:
                    stats = json.load(response)
                self.assertEqual(stats['model_calls'], 1)
                self.assertEqual(stats['tool_calls'], 0)
                self.assertEqual(stats['action_steps'], 1)
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
