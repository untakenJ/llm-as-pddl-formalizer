"""Lossless text/accounting and observational equivalence of passive evidence."""
import asyncio
import importlib.util
import json
import hashlib
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from agent_formalizer.results import native_audit
from agent_formalizer.results.provider_reasoning import ProviderReasoningRecorder, token_accounting
from agent_formalizer.claws.openclaw import _sanitize_content_block, _session_entry_to_steps


class FullTraceTests(unittest.TestCase):
    def test_host_only_sink_records_full_text_and_distrusts_client_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            control = root / 'control'; control.mkdir()
            evidence = root / 'evidence'
            collector = native_audit.Collector(control, evidence)
            try:
                text = 'long code 中文\n' * 10000
                with patch.object(native_audit, 'AUDIT_SOCKET', str(control / 'native-audit.sock')), \
                     patch.object(native_audit, '_snapshot', return_value=[
                         {'path':'../../outside.py','sha256':'../../escape','text':text}]), \
                     patch.object(native_audit.os, 'write') as errors:
                    native_audit.record('tool_result', snapshot=True, result={'stdout':text})
                    errors.assert_not_called()
                rows = [json.loads(line) for line in (evidence / 'native_tools.jsonl').read_text().splitlines()]
                self.assertEqual(rows[-1]['result']['stdout'],text)
                change = rows[-1]['file_changes'][0]
                self.assertEqual(change['content_file'],'files/'+hashlib.sha256(text.encode()).hexdigest())
                self.assertEqual((evidence / change['content_file']).read_text(),text)
                self.assertEqual(list(control.iterdir()),[control / 'native-audit.sock'])
                self.assertFalse((root / 'outside.py').exists())
                # The socket is append-only: an invalid read/history request
                # yields no historical model/tool/file content.
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
                    channel.settimeout(5); channel.connect(str(control / 'native-audit.sock'))
                    channel.sendall(b'{"read":"history"}\n')
                    self.assertEqual(channel.recv(1024),b'')
                self.assertEqual(json.loads((evidence / 'capture_status.json').read_text())['errors'],1)
            finally:
                collector.close()

    def test_native_capture_failure_is_visible_without_replacing_result(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(native_audit,'AUDIT_SOCKET',str(Path(temp)/'absent.sock')), \
                 patch.object(native_audit.os,'write') as diagnostic:
                @native_audit.capture
                def tool(): return 'native output'
                self.assertEqual(tool(),'native output')
                self.assertTrue(any(b'BENCHMARK_FULL_TRACE_ERROR' in call.args[1]
                                    for call in diagnostic.call_args_list))

    def test_large_model_text_tool_args_thinking_and_usage_survive(self):
        text = "完整文本\n" * 40000
        payload = {"candidates": [{"content": {"parts": [
            {"thought": True, "text": text}, {"text": text},
            {"functionCall": {"name": "write", "args": {"content": text}}},
            {"thoughtSignature": "opaque-secret"}]}}],
            "usageMetadata": {"promptTokenCount": 1000, "cachedContentTokenCount": 100,
                              "candidatesTokenCount": 200, "thoughtsTokenCount": 300}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recorder = ProviderReasoningRecorder("google-vertex", root / "thoughts.jsonl", root / "status.json",
                                                 full_trace_path=root / "full.jsonl")
            context = {"response_id": "a", "physical_attempt": 1, "model": "gemini-3.1-flash-lite"}
            recorder.capture_payload(payload, context=context)
            # Cumulative usage repeated by stream events must not be added twice.
            recorder.capture_payload({"usageMetadata": payload["usageMetadata"]}, context=context)
            recorder.record_boundary(context=context, response_complete=True, downstream_state="delivered")
            rows = [json.loads(line) for line in (root / "full.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["payload"]["candidates"][0]["content"]["parts"][0]["text"], text)
            self.assertNotIn("opaque-secret", (root / "full.jsonl").read_text())
            accounting = rows[-1]["token_accounting"]
            self.assertEqual(accounting["output_tokens_including_thinking"], 500)
            self.assertAlmostEqual(accounting["estimated_cost_usd"], (900 * .25 + 100 * .025 + 500 * 1.5) / 1e6)
            self.assertEqual(recorder.status()["write_errors"], 0)

    def test_openai_reasoning_subset_not_double_counted(self):
        accounting = token_accounting({"usage": {"prompt_tokens": 1000, "completion_tokens": 500,
            "prompt_tokens_details": {"cached_tokens": 100}, "completion_tokens_details": {"reasoning_tokens": 300}}},
            "google-vertex/gemini-3.1-flash-lite")
        self.assertEqual(accounting["output_tokens_including_thinking"], 500)
        self.assertEqual(accounting["thinking_tokens"], 300)

    def test_missing_usage_or_unknown_price_not_zero(self):
        self.assertIsNone(token_accounting({"choices": []}, "gemini-3.1-flash-lite"))
        self.assertIsNone(token_accounting({"usage": {"prompt_tokens": 1}}, "gemini-3.1-flash-lite")["estimated_cost_usd"])
        self.assertIsNone(token_accounting({"usage": {"prompt_tokens": 1, "completion_tokens": 1}}, "unpriced")["estimated_cost_usd"])

    def test_openclaw_thinking_not_truncated(self):
        value = "reason " * 2000
        self.assertEqual(_sanitize_content_block({"thinking": value})["thinking"], value)

    def test_native_outputs_without_next_model_request_and_generator_protocol(self):
        records = []
        with patch.object(native_audit, "record", side_effect=lambda event, **kw: records.append((event, kw))):
            result = {"stdout": "long output" * 10000}
            @native_audit.capture
            def sync():
                return result
            @native_audit.capture
            async def asynchronous():
                return result
            @native_audit.capture
            def generator():
                sent = yield result
                return sent
            self.assertIs(sync(), result)
            self.assertIs(asyncio.run(asynchronous()), result)
            iterator = generator()
            self.assertIs(next(iterator), result)
            with self.assertRaises(StopIteration) as done:
                iterator.send("native return")
            self.assertEqual(done.exception.value, "native return")
            self.assertEqual(sum(event == "tool_result" for event, _ in records), 3)
            self.assertEqual(sum(event == "tool_progress" for event, _ in records), 1)

    def test_native_exception_identity_preserved(self):
        failure = RuntimeError("native error")
        @native_audit.capture
        def function():
            raise failure
        with patch.object(native_audit, "record") as recorder:
            with self.assertRaises(RuntimeError) as caught:
                function()
            self.assertIs(caught.exception, failure)
            self.assertEqual(recorder.call_args.args[0], "tool_exception")

    def test_api_trace_resume_and_interrupted_history(self):
        source = Path(__file__).resolve().parents[1] / 'source/llm-as-formalizer-api.py'
        spec = importlib.util.spec_from_file_location('full_trace_api_test', source)
        module = importlib.util.module_from_spec(spec)
        with patch('env_loader.load_project_dotenv'):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / 'data/textual_barman/fixture'
            data.mkdir(parents=True)
            (data / 'p01_domain.txt').write_text('tiny domain')
            (data / 'p01_problem.txt').write_text('tiny problem')
            with patch.object(module, 'ROOT_DIR', str(root)), patch.object(module, 'respond_with_tools',
                    return_value=json.dumps({'domain file':'domain bytes','problem file':'problem bytes'})) as call:
                args = dict(provider='google-vertex',client=None,domain='barman',model='gemini-3.1-flash-lite',data='fixture',
                            problem_numbers=[1],out_dir_root=str(root/'output'),resume=True)
                module.run_gpt_batch(**args)
                module.run_gpt_batch(**args)
                self.assertEqual(call.call_count,1)
                trace = next((root/'output').rglob('*_trace.jsonl'))
                old_trace = trace.read_bytes()
                trace.write_text('interrupted trace\n')
                module.run_gpt_batch(**args)
                self.assertEqual(call.call_count,2)
                history = list((trace.parent/'execution_history').glob('*/*_trace.jsonl'))
                self.assertEqual(len(history),1)
                self.assertEqual(history[0].read_text(),'interrupted trace\n')
                self.assertTrue((trace.parent/'api_completion.json').is_file())


if __name__ == "__main__":
    unittest.main()
