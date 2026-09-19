"""CPU-only API/local-model integration; all provider and evaluator IO is fake."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import OpenAI

from api_providers import (build_provider_client, default_tools_for_model, sanitize_model_name,
                           validate_api_model)
from remote_execution import api, checkpoints
from remote_execution.benchmark import required_service_preflight, run
from remote_execution.protocol import private_json, read_json, validate_job
from test_remote_execution import TemporaryCase, ROOT
import test_remote_execution as remote_fixture


MODEL = "self-hosted/Qwen/example-bf16"
GOOD = json.dumps({"domain file": "(define (domain test))", "problem file": "(define (problem test))"})


def response(content=GOOD):
    return {"id": "test", "object": "chat.completion", "created": 1, "model": "Qwen/example-bf16",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content,
                         "reasoning_content": "Check all facts before writing."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26,
                      "completion_tokens_details": {"reasoning_tokens": 4}}}


class ApiTests(TemporaryCase):
    def setUp(self):
        super().setUp()
        self.spec = {"schema_version": 1, "job_id": "api", "release_id": "a" * 64, "kind": "api_cell",
                     "parameters": {"model": MODEL, "domain": "barman", "dataset": "Heavily_Templated_Barman-100",
                                    "indices": [1, 2], "operational_config": "op.json", "services": ["model", "solver"],
                                    "solver_backend": "local"}}
        self.formalizer = api.load_formalizer(ROOT)
        self.formalizer.ROOT_DIR = str(self.workspace)
        folder = self.workspace / "data/textual_barman/Heavily_Templated_Barman-100"
        folder.mkdir(parents=True)
        for problem in ("p01", "p02"):
            for suffix in ("domain", "problem"):
                (folder / f"{problem}_{suffix}.txt").write_text("Independent task " + problem + suffix)
        self.output = self.root / "output"
        self.requests = []

    def client(self, contents=(GOOD,), statuses=()):
        bodies = iter(contents)
        errors = iter(statuses)
        def handler(request):
            self.requests.append(json.loads(request.content))
            status = next(errors, 200)
            if status != 200:
                return httpx.Response(status, json={"error": {"message": "test failure", "type": "rate_limit"}})
            return httpx.Response(200, json=response(next(bodies)))
        client = OpenAI(api_key="test-private-key", base_url="http://test.invalid/v1", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        return client

    def run_case(self, client, problem="p01"):
        return api.run_case(self.formalizer, "self-hosted", client, self.spec, self.workspace, self.output, problem)

    def test_self_hosted_build_is_explicit_no_openai_fallback(self):
        self.assertEqual(validate_api_model(MODEL), MODEL)
        self.assertEqual(default_tools_for_model(MODEL), (None, None))
        with patch("api_providers.OpenAI") as constructor:
            provider, _ = build_provider_client(MODEL, api_key="private", provider_options={"base_url": "http://localhost:8000/v1"})
            self.assertEqual(provider, "self-hosted")
            constructor.assert_called_once_with(api_key="private", base_url="http://localhost:8000/v1", max_retries=0)
        for url in ("", "http://user:pass@localhost/v1", "http://localhost/v1?key=bad", "http://localhost/v2"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                build_provider_client(MODEL, api_key="private", provider_options={"base_url": url})

    def test_response_retry_reasoning_tokens_and_resume(self):
        with patch("api_providers.time.sleep"):
            execution, record = self.run_case(self.client(statuses=(429, 200)))
        self.assertTrue(record["generation_success"])
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0], self.requests[1])
        self.assertEqual(self.requests[1]["model"], "Qwen/example-bf16")
        self.assertEqual(self.requests[1]["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", self.requests[1])
        trace = next(execution.glob("*_trace.jsonl")).read_text()
        self.assertIn("reasoning_content", trace)
        self.assertIn("reasoning_tokens", trace)
        self.assertNotIn("test-private-key", trace)
        before = record["files"]
        self.assertEqual(self.run_case(self.client(contents=()))[1]["files"], before)
        self.assertEqual(len(self.requests), 2)

    def test_output_budget_input_rejection_is_not_resampled(self):
        from agent_formalizer.configuration.model_capabilities import OutputBudgetInputError
        with patch.object(self.formalizer, 'run_formalizer_gpt', side_effect=OutputBudgetInputError(400, {'error': 'context exhausted'})) as generate:
            execution, record = self.run_case(self.client())
            self.assertTrue(record['attempt_valid'])
            self.assertFalse(record['generation_success'])
            self.assertEqual(self.run_case(self.client())[0], execution)
            generate.assert_called_once()

    def test_valid_bad_and_empty_outputs_are_not_resampled(self):
        for i, content in enumerate(("bad JSON", None), 1):
            with self.subTest(content=content):
                problem = f"p{i:02d}"
                execution, record = self.run_case(self.client((content,)), problem)
                self.assertTrue(record["attempt_valid"])
                self.assertFalse(record["generation_success"])
                self.assertEqual(self.run_case(self.client(contents=()), problem)[0], execution)
        self.assertEqual(len(self.requests), 2)

    def test_exhausted_transient_and_interrupted_attempt_can_resume(self):
        with patch("api_providers.time.sleep"):
            self.assertIsNone(self.run_case(self.client(statuses=(503,) * 6)))
        case = api.case_directory(self.output, self.spec["parameters"], "p01")
        self.assertEqual(len(list(case.rglob("infra_invalid.json"))), 1)
        (case / "executions/execution-000002").mkdir()  # Interrupted, never committed.
        execution, _ = self.run_case(self.client())
        self.assertEqual(execution.name, "execution-000003")

    def test_missing_message_is_invalid_but_explicit_vertex_refusal_is_valid(self):
        with patch("test_remote_api.response", return_value={"id": "test", "choices": []}):
            self.assertIsNone(self.run_case(self.client()))
        spec = deepcopy(self.spec); spec["parameters"].update(model="gemini-3.1-flash-lite", services=["solver"])
        result = SimpleNamespace(text=None, prompt_feedback=None,
            candidates=[SimpleNamespace(finish_reason="SAFETY", safety_ratings=[], citation_metadata=None, content=None)],
            model_dump=lambda **_: {"candidates": [{"finish_reason": "SAFETY"}]})
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: result))
        execution, record = api.run_case(self.formalizer, "google-vertex", client, spec, self.workspace, self.output, "p01")
        self.assertTrue(record["attempt_valid"])
        self.assertFalse(record["generation_success"])
        self.assertIsNotNone(api.selected_case(execution.parents[1]))

    def test_input_drift_or_trace_corruption_refuses_resume(self):
        execution, _ = self.run_case(self.client())
        changed = deepcopy(self.spec); changed["parameters"]["solver_backend"] = "public"
        with self.assertRaisesRegex(ValueError, "identity"):
            api.run_case(self.formalizer, "self-hosted", self.client(), changed, self.workspace, self.output, "p01")
        next(execution.glob("*_trace.jsonl")).write_text("corrupted")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            self.run_case(self.client())

    def test_separate_eval_workers_and_non_overwriting_generations(self):
        selected = {"p01": self.run_case(self.client())}
        with patch("run_solver.run_solver_batch") as solver, patch("run_val.validate_plan_batch") as val:
            evaluation = api.evaluate(self.spec, self.output, selected, 1, {"solver_workers": 2, "val_workers": 3})
            self.assertEqual(solver.call_args.kwargs["workers"], 2)
            self.assertEqual(solver.call_args.kwargs["solver_backend"], "local")
            self.assertEqual(val.call_args.kwargs["workers"], 3)
            copied = next(evaluation.rglob("*_df.pddl"))
            self.assertEqual(copied.read_text(), "(define (domain test))")
            api.evaluate(self.spec, self.output, selected, 2, {"solver_workers": 1, "val_workers": 1})
            self.assertEqual(copied.read_text(), "(define (domain test))")
        import run_solver, run_val
        self.assertEqual(run_solver._model_output_name(MODEL), sanitize_model_name(MODEL))
        self.assertEqual(run_val._model_output_name(MODEL), sanitize_model_name(MODEL))

    def test_api_protocol_does_not_accept_agent_fields_or_unsafe_model_paths(self):
        validate_job(self.spec)
        for field, value in (("harness", "minimum"), ("model", "self-hosted/../bad"), ("solver_backend", "magic")):
            bad = deepcopy(self.spec); bad["parameters"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_job(bad)

    def test_external_provider_generation_preserves_native_protocols(self):
        cases = (("deepseek-v4-flash", "deepseek"), ("gpt-4o-mini", "openai"),
                 ("gemini-3.1-flash-lite", "google-vertex"))
        for model, provider in cases:
            with self.subTest(model=model):
                spec = deepcopy(self.spec)
                spec["parameters"].update(model=model, services=["solver"])
                if provider == "deepseek":
                    client = self.client()
                else:
                    raw = {"text": GOOD, "usage": {"input_tokens": 17, "output_tokens": 9}}
                    result = SimpleNamespace(output_text=GOOD, output=[], text=GOOD,
                                             model_dump=lambda **_: raw)
                    client = SimpleNamespace(
                        responses=SimpleNamespace(create=lambda **_: result),
                        models=SimpleNamespace(generate_content=lambda **_: result))
                execution, record = api.run_case(self.formalizer, provider, client, spec,
                                                 self.workspace, self.output, "p01")
                self.assertTrue(record["generation_success"])
                events = [json.loads(line) for line in next(execution.glob("*_trace.jsonl")).read_text().splitlines()]
                self.assertEqual(next(row for row in events if row["event"] == "request")["provider"], provider)
                self.assertIsNotNone(api.selected_case(execution.parents[1]))
                self.assertEqual(api.model_route(model), provider + "/" + model)

    def test_explicit_node_secrets_used_for_external_clients(self):
        with patch("api_providers.OpenAI") as sdk, patch("api_providers._read_key_file", side_effect=AssertionError):
            build_provider_client("gpt-4o-mini", api_key="node-openai")
            sdk.assert_called_with(api_key="node-openai", max_retries=0)
            build_provider_client("deepseek-v4-flash", api_key="node-deepseek")
            sdk.assert_called_with(api_key="node-deepseek", base_url="https://api.deepseek.com/v1", max_retries=0)
        with patch("google.genai.Client") as sdk, \
             patch("api_providers.require_gemini_vertex_api_key_config", side_effect=AssertionError):
            build_provider_client("gemini-3.1-flash-lite", api_key="node-vertex")
            self.assertTrue(sdk.call_args.kwargs["vertexai"])
            self.assertEqual(sdk.call_args.kwargs["api_key"], "node-vertex")

    def test_external_models_do_not_require_local_model_service_or_gpu(self):
        for model in ("google-vertex/gemini-3.1-flash-lite", "deepseek/deepseek-v4-flash", "openai/gpt-4o-mini"):
            spec = deepcopy(self.spec); spec["parameters"]["services"] = []
            with patch("remote_execution.benchmark.service_preflight", return_value={}) as health:
                required_service_preflight(model, "public", spec, {"services": {}},
                                           {"credential": {"secrets_env_file": "unused"}}, self.root, 1)
                self.assertEqual(health.call_args.args[1], [])
        spec = deepcopy(self.spec); spec["parameters"]["services"] = []
        with self.assertRaisesRegex(ValueError, "model service"):
            required_service_preflight(MODEL, "public", spec, {}, {}, self.root, 1)


class ApiBridgeTests(TemporaryCase):
    fixture = remote_fixture.BenchmarkBridgeTests.fixture

    def test_remote_entry_uses_standalone_profile_independent_pipeline(self):
        spec, directory, _, _ = self.fixture()
        spec["kind"] = "api_cell"
        p = spec["parameters"]
        for field in ("harness", "benchmark_profile", "resolved_config_sha256"):
            p.pop(field)
        p.update(model="deepseek-v4-flash", solver_backend="local")
        (self.workspace / "source/llm-as-formalizer-api.py").write_text("# frozen standalone entrypoint")
        (self.root / "runner.env").write_text("DEEPSEEK_API_KEY=test-node-private-key\n")
        with patch("remote_execution.benchmark.service_preflight", return_value={}), \
             patch("remote_execution.api.load_formalizer"), \
             patch("api_providers.build_provider_client", return_value=("deepseek", object())), \
             patch("remote_execution.api.run_case", return_value=None), \
             patch("remote_execution.api.evaluate", return_value=directory / "output/evaluation-1"):
            self.assertEqual(run(spec, self.config, self.workspace, directory, 1), 2)
        provenance = read_json(directory / "evidence/configuration-1.json")
        self.assertEqual(provenance["api_condition"], "direct-api-no-tools-v1")
        self.assertNotIn("resolved_config_sha256", provenance)
        self.assertNotIn("test-node-private-key", json.dumps(read_json(directory / "output/cell-summary-1.json")))
