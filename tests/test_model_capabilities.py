"""Output-budget conditions: no live model, solver, or remote-node calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agent_formalizer.claws import get_adapter
from agent_formalizer.configuration.benchmark_profile import BenchmarkProfile, DEFAULT_BENCHMARK_PROFILE, load_benchmark_profile, with_google_vertex_project
from agent_formalizer.configuration.model_capabilities import (
    apply_output_policy, load_registry, native_output_hint, resolve_output_policy,
    validate_policy, validate_registry, validate_selection, vllm_count_tokens, OutputBudgetInputError,
)
from api_providers import generate_deepseek_json, generate_gemini_json, _apply_output_budget
from profile_fixtures import HISTORICAL_PROFILES_DIR
from remote_execution.api import load_formalizer
from sweep_agent_pipeline import _freeze_study_profile

ROOT = Path(__file__).resolve().parents[1]
GEMINI = "google-vertex/gemini-3.1-flash-lite"
QWEN = "self-hosted/Qwen/Qwen3.8-27B"
ALIBABA_QWEN = "alibaba/qwen3.8-27b"


class ModelCapabilitiesTests(unittest.TestCase):
    def test_default_is_model_max_only_named_defaults_change(self):
        profile = DEFAULT_BENCHMARK_PROFILE
        self.assertEqual(profile.raw['condition_profile']['overrides']['generation'], {'max_output_tokens': 'model_max'})
        self.assertEqual(profile.default_model, GEMINI)
        for harness in ('openclaw', 'hermes', 'generic', 'nanobot', 'zeroclaw'):
            resolved = profile.resolve(harness)
            self.assertEqual(resolved.output_token_policy['max_output_tokens'], 65536)
            self.assertEqual(resolved.solver_backend, 'local')
            self.assertEqual(resolved.generation_overrides, {'output_token_policy': resolved.output_token_policy})

    def test_strict_selection_and_registry(self):
        for value in (True, False, 0, -1, 1.5, '65536', 'max', None, {}, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_selection(value)
        for value in ('native', 'model_max', 1, 65536):
            self.assertEqual(validate_selection(value), value)
        for field, value in (('context_window_tokens', True), ('max_output_tokens', 0),
                             ('context_handling', []), ('output_accounting', []), ('source_url', '')):
            raw = load_registry()
            raw['models'][GEMINI][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_registry(raw)
        raw = load_registry()
        raw['aliases']['test/alias'] = []
        with self.assertRaises(ValueError):
            validate_registry(raw)

    def test_unknown_and_excessive_limits_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'No verified'):
            resolve_output_policy('unknown/model', 'model_max')
        self.assertIsNone(resolve_output_policy('unknown/model', 'native'))
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            resolve_output_policy(GEMINI, 65537)
        numeric = resolve_output_policy(GEMINI, 1024)
        self.assertEqual(numeric['max_output_tokens'], 1024)
        numeric['max_output_tokens'] = 2048
        with self.assertRaises(ValueError):
            validate_policy(numeric)

    def test_alibaba_qwen_uses_verified_model_studio_limits(self):
        policy = resolve_output_policy(ALIBABA_QWEN, 'model_max')
        self.assertEqual(policy['context_window_tokens'], 1_000_000)
        self.assertEqual(policy['max_output_tokens'], 131_072)
        request, audit = apply_output_policy(
            {'model': 'qwen3.8-27b', 'messages': [], 'max_tokens': 8192, 'max_output_tokens': 1024},
            policy,
            '/compatible-mode/v1/chat/completions',
        )
        self.assertEqual(request['max_completion_tokens'], 131_072)
        self.assertNotIn('max_tokens', request)
        self.assertNotIn('max_output_tokens', request)
        self.assertEqual(audit['parameter'], 'max_completion_tokens')

    def test_alias_and_qwen_context_are_not_fixed_output_262144(self):
        self.assertEqual(resolve_output_policy('gemini/gemini-3.1-flash-lite', 'model_max')['max_output_tokens'], 65536)
        policy = resolve_output_policy(QWEN, 'model_max')
        self.assertEqual(policy['max_output_tokens'], 'remaining_context')
        self.assertEqual(native_output_hint(policy), 8192)
        request = {'model': 'Qwen/Qwen3.8-27B', 'messages': [{'role': 'user', 'content': 'facts'}], 'max_tokens': 8192}
        bounded, audit = apply_output_policy(request, policy, '/v1/chat/completions', input_tokens=10000, deployment_context=262144)
        self.assertEqual(bounded['max_tokens'], 252144)
        self.assertEqual(bounded['messages'], request['messages'])
        self.assertEqual(request['max_tokens'], 8192)
        self.assertEqual(audit['remaining_context_tokens'], 252144)

    def test_remaining_context_is_enforced_without_guessing_or_input_truncation(self):
        policy = resolve_output_policy(QWEN, 4096)
        out, audit = apply_output_policy({'messages': []}, policy, '/v1/chat/completions', input_tokens=262044, deployment_context=262144)
        self.assertEqual(out['max_tokens'], 100)
        for count, context in ((262144, 262144), (100, 131072), (None, 262144), (True, 262144)):
            with self.subTest(count=count, context=context), self.assertRaises(ValueError):
                apply_output_policy({}, policy, '/v1/chat/completions', input_tokens=count, deployment_context=context)

    def test_cloud_parameter_mapping_and_content_preservation(self):
        policy = resolve_output_policy(GEMINI, 'model_max')
        for path, field in (('/v1/chat/completions', 'max_tokens'), ('/v1/responses', 'max_output_tokens'), ('/v1/messages', 'max_tokens')):
            request = {'model': 'test', 'messages': [{'role': 'user', 'content': 'unchanged'}], 'tools': [{'name': 'test'}], 'max_tokens': 8192, 'max_output_tokens': 1024}
            out, audit = apply_output_policy(request, policy, path)
            self.assertEqual(out[field], 65536)
            self.assertEqual(out['messages'], request['messages'])
            self.assertEqual(out['tools'], request['tools'])
            self.assertEqual(set(out) & {'max_tokens', 'max_completion_tokens', 'max_output_tokens'}, {field})
            self.assertEqual(audit['effective_max_output_tokens'], 65536)
        out, _ = apply_output_policy({'max_completion_tokens': 99}, policy, '/v1/chat/completions')
        self.assertEqual(out, {'max_tokens': 65536})  # Vertex-compatible API's documented field.
        openai_policy = {**policy, 'model': 'openai/test-model'}
        out, _ = apply_output_policy({'max_completion_tokens': 99}, openai_policy, '/v1/chat/completions')
        self.assertEqual(out['max_completion_tokens'], 65536)
        out, _ = apply_output_policy({'contents': ['x'], 'generationConfig': {'topP': .7}}, policy, '/v1/models/test:streamGenerateContent')
        self.assertEqual(out, {'contents': ['x'], 'generationConfig': {'topP': .7, 'maxOutputTokens': 65536}})

    def test_old_profiles_omit_policy_and_never_read_registry(self):
        for path in HISTORICAL_PROFILES_DIR.glob('*.json'):
            profile = load_benchmark_profile(path)
            harness = 'minimum' if 'minimum' in path.stem else 'openclaw'
            with patch('agent_formalizer.configuration.model_capabilities.load_registry', side_effect=AssertionError('must not read')):
                resolved = profile.resolve(harness)
                self.assertIsNone(resolved.output_token_policy)
                self.assertNotIn('output_token_policy', resolved.raw['resolved'])
                self.assertNotIn('output_token_policy', resolved.generation_overrides)
                self.assertEqual(profile.frozen_raw(), profile.raw)

    def test_frozen_registry_resume_and_unrelated_entries_do_not_change_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            frozen = _freeze_study_profile(DEFAULT_BENCHMARK_PROFILE, Path(tmp))
            before = frozen.resolve('openclaw').sha256
            changed = deepcopy(frozen.raw)
            changed['model_capabilities']['models'][QWEN]['context_window_tokens'] = 500000
            changed['model_capabilities']['models'][GEMINI]['source_url'] = 'https://example.org/documentary-only'
            self.assertEqual(BenchmarkProfile(frozen.path, changed).resolve('openclaw').sha256, before)
            changed['model_capabilities']['models'][GEMINI]['max_output_tokens'] = 60000
            self.assertNotEqual(BenchmarkProfile(frozen.path, changed).resolve('openclaw').sha256, before)
            with patch('agent_formalizer.configuration.model_capabilities.load_registry', side_effect=AssertionError('live drift')):
                self.assertEqual(frozen.resolve('openclaw').sha256, before)

    def test_five_adapters_write_native_limit_fields(self):
        profile = with_google_vertex_project(DEFAULT_BENCHMARK_PROFILE, 'test-project')
        adapters = {name: get_adapter(name, benchmark_profile=profile) for name in ('openclaw', 'hermes', 'generic', 'nanobot', 'zeroclaw')}
        self.assertEqual(adapters['nanobot']._benchmark_config()['agents']['defaults']['maxTokens'], 65536)
        self.assertEqual(adapters['hermes']._benchmark_config()['model']['max_tokens'], 65536)
        self.assertIn("'max_tokens': 65536", adapters['generic']._mykey_source())
        zero = tomllib.loads(adapters['zeroclaw']._benchmark_config_toml())
        self.assertEqual(zero['providers']['models']['custom']['benchmark']['max_tokens'], 65536)
        self.assertEqual(adapters['openclaw']._gateway_provider_config()['models'][0]['maxTokens'], 65536)
        for adapter in adapters.values():
            self.assertEqual(adapter.resolved_config.generation_overrides['output_token_policy']['max_output_tokens'], 65536)

    def test_minimum_inherits_same_gateway_output_policy(self):
        old = load_benchmark_profile(HISTORICAL_PROFILES_DIR / 'native_safety_streaming_minimum_agent.json')
        raw = deepcopy(old.raw)
        raw['condition_profile']['overrides']['generation'] = {'max_output_tokens': 'model_max'}
        resolved = BenchmarkProfile(old.path, raw).resolve('minimum', model=GEMINI)
        self.assertEqual(resolved.generation_overrides['output_token_policy']['max_output_tokens'], 65536)

    def test_api_output_caps_and_native_compatibility(self):
        policy = resolve_output_policy(GEMINI, 'model_max')
        request = {'messages': []}
        self.assertIs(_apply_output_budget(request, None, '/v1/chat/completions'), request)
        tracer = Mock()
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text='{}', candidates=[])
        generate_gemini_json(client, 'gemini-3.1-flash-lite', 'prompt', {'type': 'object'}, tracer=tracer, output_token_policy=policy, stream=False)
        self.assertEqual(client.models.generate_content.call_args.kwargs['config'].max_output_tokens, 65536)
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
        deepseek = resolve_output_policy('deepseek/deepseek-v4-flash', 'model_max')
        generate_deepseek_json(client, 'deepseek-v4-flash', [], {}, output_token_policy=deepseek, stream=False)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'], 393216)
        qwen = resolve_output_policy(QWEN, 'model_max')
        with patch('agent_formalizer.configuration.model_capabilities.vllm_count_tokens', return_value=(500, 262144)) as count:
            generate_deepseek_json(client, QWEN, [], {}, provider='self-hosted', output_token_policy=qwen, stream=False)
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'], 261644)
        self.assertIn('Return exactly one valid JSON', count.call_args.args[1]['messages'][0]['content'])

    def test_api_cell_freezes_before_calls_and_rejects_mixing(self):
        formalizer = load_formalizer(ROOT)
        policy = resolve_output_policy(GEMINI, 'model_max')
        with tempfile.TemporaryDirectory() as tmp:
            cell = Path(tmp) / 'cell'
            formalizer._freeze_api_output_policy(cell, policy)
            formalizer._freeze_api_output_policy(cell, policy)
            with self.assertRaises(ValueError):
                formalizer._freeze_api_output_policy(cell, None)
            legacy = Path(tmp) / 'legacy'
            legacy.mkdir()
            (legacy / 'trace.jsonl').write_text('incomplete legacy trace')
            with self.assertRaises(ValueError):
                formalizer._freeze_api_output_policy(legacy, policy)

    def test_registry_is_not_part_of_implementation_hash(self):
        from agent_formalizer.orchestrator import _adapter_code_sha256
        with patch('agent_formalizer.orchestrator.file_manifest', return_value=[]) as manifest:
            _adapter_code_sha256()
        paths = manifest.call_args.args[0]
        self.assertTrue(any(path.name == 'model_capabilities.py' for path in paths))
        self.assertFalse(any(path.name == 'model_capabilities.json' for path in paths))

    def test_remote_api_policy_validated_and_bound_to_model(self):
        from remote_execution.protocol import validate_job
        spec = {'schema_version': 1, 'job_id': 'budget-test', 'release_id': 'a' * 64, 'kind': 'api_cell',
                'parameters': {'model': QWEN, 'domain': 'barman', 'dataset': 'Heavily_Templated_Barman-100',
                               'indices': [1], 'operational_config': 'op.json', 'solver_backend': 'local', 'services': ['model', 'solver'],
                               'output_token_policy': resolve_output_policy(QWEN, 'model_max')}}
        self.assertEqual(validate_job(spec), spec)
        spec['parameters']['output_token_policy']['model'] = GEMINI
        with self.assertRaisesRegex(ValueError, 'different model'):
            validate_job(spec)

    def test_remote_model_output_preflight_rejects_small_context_and_hidden_ceiling(self):
        from remote_execution.benchmark import required_service_preflight
        policy = resolve_output_policy(QWEN, 'model_max')
        provenance = {key: 'test' for key in ('model_revision', 'tokenizer_revision', 'server_version', 'dtype', 'quantization', 'chat_template_sha256', 'tool_call_parser', 'reasoning_parser')}
        provenance.update(max_model_len=262144, generation_config='vllm')
        node = {'services': {'model': {'provenance': provenance}}}
        health = {'model': {'health': {'data': [{'id': QWEN.split('/', 1)[1], 'max_model_len': 262144}]}}}
        spec = {'parameters': {'services': ['model']}}
        op = {'credential': {'secrets_env_file': 'unused'}}
        with patch('remote_execution.benchmark.service_preflight', return_value=health):
            required_service_preflight(QWEN, 'public', spec, node, op, Path('/unused'), 1, policy)
            provenance['generation_config'] = 'auto'
            with self.assertRaisesRegex(ValueError, 'hidden generation-config ceilings'):
                required_service_preflight(QWEN, 'public', spec, node, op, Path('/unused'), 1, policy)
            provenance['generation_config'] = 'vllm'
            provenance['max_model_len'] = 32768
            with self.assertRaisesRegex(ValueError, 'smaller'):
                required_service_preflight(QWEN, 'public', spec, node, op, Path('/unused'), 1, policy)

    def test_tokenizer_is_server_side_and_preserves_template_inputs(self):
        connection = Mock()
        connection.getresponse.return_value = SimpleNamespace(status=200, read=lambda n: b'{"count":123,"max_model_len":262144}')
        request = {'model': 'Qwen/Qwen3.8-27B', 'messages': [{'role': 'assistant', 'content': 'x'}], 'tools': [], 'chat_template_kwargs': {'enable_thinking': True}, 'temperature': .9, 'max_tokens': 8192}
        with patch('agent_formalizer.configuration.model_capabilities.http.client.HTTPConnection', return_value=connection):
            self.assertEqual(vllm_count_tokens('http://localhost:8000/v1', request), (123, 262144))
        args = connection.request.call_args.args
        self.assertEqual(args[:2], ('POST', '/tokenize'))
        sent = json.loads(args[2])
        self.assertEqual(sent['messages'], request['messages'])
        self.assertEqual(sent['chat_template_kwargs'], request['chat_template_kwargs'])
        self.assertNotIn('max_tokens', sent)
        self.assertNotIn('temperature', sent)
        connection.close.assert_called_once()

    def test_tokenizer_errors_are_not_silently_ignored(self):
        for status, exc in ((429, ConnectionResetError), (503, ConnectionResetError), (401, ValueError), (404, ValueError), (400, OutputBudgetInputError), (422, OutputBudgetInputError)):
            connection = Mock()
            connection.getresponse.return_value = SimpleNamespace(status=status, read=lambda n: b'{}')
            with patch('agent_formalizer.configuration.model_capabilities.http.client.HTTPConnection', return_value=connection):
                with self.subTest(status=status), self.assertRaises(exc):
                    vllm_count_tokens('http://localhost:8000', {'messages': []})

    def test_tokenizer_keeps_tool_schemas_and_explicit_reasoning_template_settings(self):
        connection = Mock()
        connection.getresponse.return_value = SimpleNamespace(status=200, read=lambda n: b'{"count":123,"max_model_len":262144}')
        payload = {'messages': [], 'tools': [{'type': 'function', 'function': {'name': 'test'}}],
                   'tool_choice': 'none', 'reasoning_effort': 'none',
                   'chat_template_kwargs': {'enable_thinking': True}}
        with patch('agent_formalizer.configuration.model_capabilities.http.client.HTTPConnection', return_value=connection):
            vllm_count_tokens('http://localhost:8000/v1', payload)
        sent = json.loads(connection.request.call_args.args[2])
        self.assertEqual(sent['tools'], payload['tools'])
        self.assertNotIn('tool_choice', sent)  # Not part of /tokenize schema.
        self.assertEqual(sent['chat_template_kwargs'], {'reasoning_effort': 'none', 'enable_thinking': True})


if __name__ == '__main__':
    unittest.main()
