"""Pinned native loops with scripted model/solver services, no real API budget."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from profile_fixtures import HISTORICAL_PROFILES_DIR

from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.claws import get_adapter
from agent_formalizer.claws.base import AttemptClock
from agent_formalizer.workspace import AgentWorkspace
from test_external_calls_gateway import Backend, SUBMIT, TIMEOUT, PLAN
from test_logical_deadlines_docker import DelayedBackend


class LoopBackend(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.server.requests.append(raw)
        number = len(self.server.requests)
        if number == 1:
            time.sleep(getattr(self.server, 'failure_delay', 0.3))
            self.send_response(429)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')
            return
        request = json.loads(raw)
        message = {'role': 'assistant', 'content': 'Done.'}
        if number == 2:
            name = {'generic': 'code_run', 'hermes': 'terminal',
                    'nanobot': 'exec', 'zeroclaw': 'shell'}[self.server.harness]
            available = [t['function']['name'] for t in request.get('tools', [])]
            if name not in available:
                self.server.error = f'{name} missing from {available}'
            command = 'cd /workspace && pddl-solver'
            if self.server.harness == 'zeroclaw':
                # Its native command policy permits Python, not arbitrary
                # CLI names. Do not relax that policy just for this adapter.
                command = 'python3 solver_fixture.py'
            args = {'code': "import subprocess; print(subprocess.run(['pddl-solver'], cwd='/workspace', capture_output=True, text=True).stdout)"} if name == 'code_run' else {'command': command}
            if self.server.background:
                args.update({'background': True} if self.server.harness == 'hermes' else {'yield_time_ms': 1})
            message = {'role': 'assistant', 'content': 'I will check the fixture once.',
                       'reasoning_content': 'Call the native tool and retain its result.',
                       'tool_calls': [{'id': 'fixture-solver-once', 'type': 'function',
                                       'function': {'name': name, 'arguments': json.dumps(args)}}]}
        if number == 3 and self.server.background:
            # Keep this healthy model request open while the native background
            # child finishes startup and reaches its solver gateway.
            time.sleep(2)
            content = next(m['content'] for m in reversed(request['messages']) if m.get('role') == 'tool')
            if self.server.harness == 'hermes':
                key = re.search(r'proc_[a-z0-9]+', str(content)).group(0)
                name, args = 'process', {'action': 'wait', 'session_id': key, 'timeout': 30}
            else:
                key = re.search(r'session_id: ([a-z0-9]+)', str(content)).group(1)
                name, args = 'write_stdin', {'session_id': key, 'chars': '', 'wait_for': '(move a b)', 'wait_timeout_ms': 30000}
            message = {'role': 'assistant', 'content': 'Wait for the background fixture.',
                       'reasoning_content': 'Retain the pending native session.',
                       'tool_calls': [{'id': 'fixture-native-poll', 'type': 'function',
                                       'function': {'name': name, 'arguments': json.dumps(args)}}]}
        finish = 'tool_calls' if message.get('tool_calls') else 'stop'
        self.send_response(200)
        if request.get('stream'):
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            delta = dict(message)
            for index, tool in enumerate(delta.get('tool_calls', [])):
                tool['index'] = index
            events = [dict(id='fixture', object='chat.completion.chunk', model=request['model'],
                           choices=[{'index': 0, 'delta': delta, 'finish_reason': None}]),
                      dict(id='fixture', object='chat.completion.chunk', model=request['model'],
                           choices=[{'index': 0, 'delta': {}, 'finish_reason': finish}])]
            for event in events:
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
        else:
            body = json.dumps({'id': 'fixture', 'object': 'chat.completion', 'model': request['model'],
                               'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                               'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}).encode()
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get('RUN_EXTERNAL_CALLS_DOCKER_TESTS') == '1', 'opt-in native Docker test')
class MultiHarnessLoopTests(unittest.TestCase):
    def run_loop(self, harness, *, short_shell=False, slow_solver=False, background=False, short_model=False):
        bridge = json.loads(subprocess.check_output(['docker', 'network', 'inspect', 'bridge'], text=True))[0]['IPAM']['Config'][0]['Gateway']
        model = ThreadingHTTPServer((bridge, 0), LoopBackend)
        solver = ThreadingHTTPServer((bridge, 0), DelayedBackend)
        model.requests, model.harness, model.error = [], harness, None
        model.background = background
        model.failure_delay = 3 if short_model else 0.3
        solver.requests, solver.responses = [], ([SUBMIT, PLAN] if slow_solver or background else [SUBMIT, TIMEOUT, SUBMIT, PLAN])
        solver.final_delay = 8 if background else 5 if slow_solver else 0
        for server in (model, solver):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / 'native_safety_streaming_solver_as_tool_call_checkpoint.json')
        adapter = get_adapter(harness, benchmark_profile=profile, model='deepseek/deepseek-v4-flash', api_key='not-real')
        gateway = adapter.model_gateway()
        gateway['upstream_origin'] = f'http://{bridge}:{model.server_port}'
        identity = 'checkpoint-native-loop-' + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory(prefix='checkpoint-native-loop-') as directory:
                workspace = AgentWorkspace(identity, identity, adapter, artifact_dir=Path(directory))
                try:
                    with patch.object(adapter, 'model_gateway', return_value=gateway), \
                         patch.object(adapter, 'solver_upstream_base', return_value=f'http://{bridge}:{solver.server_port}'), \
                         patch.object(adapter, 'solver_backend', return_value='public'):
                        workspace.start()
                    if short_shell:
                        # Test-only shortened native value; campaign TOML is
                        # unchanged. This isolates the Rust shell timer itself.
                        workspace.write_text_file('/tmp/zeroclaw-pddl-benchmark/config.toml',
                            adapter._benchmark_config_toml().replace('shell_timeout_secs = 60', 'shell_timeout_secs = 3'))
                    if short_model:
                        workspace.write_text_file('/tmp/zeroclaw-pddl-benchmark/config.toml',
                            adapter._benchmark_config_toml().replace('timeout_secs = 1800', 'timeout_secs = 2'))
                    workspace.write_text_file('/workspace/domain.pddl', '(domain bytes)')
                    workspace.write_text_file('/workspace/problem.pddl', '(problem bytes)')
                    if harness == 'zeroclaw':
                        workspace.write_text_file('/workspace/solver_fixture.py',
                            "import subprocess\nprint(subprocess.run(['pddl-solver'], cwd='/workspace', capture_output=True, text=True).stdout)\n")
                    clock = AttemptClock(90)
                    adapter._attempt_clock.clock = clock  # fixture watchdog only
                    workspace.start_model_gateway_monitor(clock)
                    result = adapter.send_task('Run pddl-solver once, then finish. This is a mock infrastructure fixture.',
                                               identity, workspace.container_name,
                                               artifact_dir=Path(directory), instance_id=identity)
                    workspace.stop_model_gateway_monitor()
                    output = '\n'.join(p.read_text(errors='replace') for p in Path(directory).glob('agent_*.log'))
                    self.assertIsNone(model.error, output)
                    terminal = workspace.gateway_terminal_infra_error()
                    checkpoint_evidence = Path(directory) / 'gateway/call_checkpoints.jsonl'
                    self.assertIsNone(terminal, {'output': output, 'checkpoints':
                        checkpoint_evidence.read_text() if terminal and checkpoint_evidence.exists() else None})
                    self.assertIsNone(workspace.gateway_monitor_error(), output)
                    self.assertEqual(len(model.requests), 4 if background else 3, output)
                    self.assertEqual(model.requests[0], model.requests[1], 'retry must preserve exact model request')
                    if short_model:
                        self.assertFalse(json.loads(model.requests[0]).get('stream'), 'fixture must exercise reqwest total deadline')
                    final_context = json.loads(model.requests[-1])['messages']
                    if slow_solver:
                        self.assertIn('Command timed out after 3s and was killed', json.dumps(final_context), output)
                        self.assertNotIn('(move a b)', json.dumps(final_context), output)
                    else:
                        self.assertIn('(move a b)', json.dumps(final_context), output)
                    self.assertNotIn('Request Time Out', json.dumps(final_context), output)
                    ledger = workspace.model_gateway_ledger()
                    committed = [row for row in ledger if row.get('downstream_committed')]
                    self.assertEqual(len(committed), 3 if background else 2, {'ledger': ledger, 'output': output})
                    self.assertEqual(committed[0]['transient_retry_count'], 1)
                    if background:
                        self.assertTrue(any(row.get('external_call_timing_mode') == 'running_wall' for row in ledger), ledger)
                    calls = list((Path(directory) / 'gateway/solver_calls').glob('call-*/outcome.json'))
                    self.assertEqual(len(calls), 1, output)
                    self.assertEqual(json.loads(calls[0].read_text())['action'], 'native_deadline' if slow_solver else 'return',
                        {'output': output, 'solver_outcome': json.loads(calls[0].read_text()),
                         'settlements': (Path(directory) / 'gateway/call_checkpoints.jsonl').read_text(),
                         'clock': clock.snapshot()})
                    self.assertEqual(len(solver.requests), 2 if slow_solver or background else 4, output)
                    self.assertEqual(workspace.validate_state_isolation()['status'], 'pass')
                    print(harness, 'native model→tool→model:', clock.snapshot(),
                          'streaming:', [json.loads(raw).get('stream') for raw in model.requests],
                          'other native calls:', [{k: row.get(k) for k in ('routing_reason', 'routing_class', 'status_code')}
                                                   for row in ledger if not row.get('downstream_committed')], flush=True)
                finally:
                    workspace.cleanup()
        finally:
            for server in (model, solver):
                server.shutdown()
                server.server_close()

    def test_generic_native_loop(self):
        self.run_loop('generic')

    def test_hermes_native_loop(self):
        self.run_loop('hermes')

    def test_nanobot_native_loop(self):
        self.run_loop('nanobot')

    def test_zeroclaw_native_loop(self):
        self.run_loop('zeroclaw')

    def test_zeroclaw_retry_longer_than_native_shell_deadline(self):
        self.run_loop('zeroclaw', short_shell=True)

    def test_zeroclaw_real_native_shell_timeout(self):
        self.run_loop('zeroclaw', short_shell=True, slow_solver=True)

    def test_zeroclaw_model_retry_longer_than_native_reqwest_deadline(self):
        self.run_loop('zeroclaw', short_model=True)

    def test_hermes_native_background_solver_then_model(self):
        self.run_loop('hermes', background=True)

    def test_nanobot_native_background_solver_then_model(self):
        self.run_loop('nanobot', background=True)
