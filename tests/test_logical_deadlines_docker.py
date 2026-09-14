"""Real native watchdogs + Docker freeze; only fake HTTP services, no API keys."""
import ipaddress
import json
import os
from pathlib import Path
import shlex
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
from agent_formalizer.configuration.config import MODEL_GATEWAY_HOST, MODEL_GATEWAY_PORT
from agent_formalizer.timing.deadline_integration import ENVIRONMENT_KEYS
from agent_formalizer.workspace import AgentWorkspace
from test_external_calls_gateway import Backend, SUBMIT, TIMEOUT, PLAN


class DelayedBackend(Backend):
    def do_POST(self):
        if len(self.server.responses) == 1:
            time.sleep(self.server.final_delay)
        super().do_POST()


class ModelBackend(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.calls += 1
        first_failure = self.server.retry and self.server.calls == 1
        time.sleep(3 if first_failure else self.server.final_delay)
        if first_failure:
            body = b'{"error":{"type":"rate_limit_error"}}'
            self.send_response(429)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            self.wfile.write(b'data: {"choices":[{"index":0,"delta":{"content":"hello"}}]}\n\n')
            self.wfile.flush()
            time.sleep(0.25)
            self.wfile.write(b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get("RUN_EXTERNAL_CALLS_DOCKER_TESTS") == "1", "opt-in real Docker/native runtime test")
class NativeDeadlineDockerTests(unittest.TestCase):
    def test_python_checkpoint_native_outer_timeouts(self):
        for harness in ('generic', 'nanobot', 'hermes'):
            for retry in (True, False):
                with self.subTest(harness=harness, retry=retry):
                    self.run_solver(harness, retry=retry, final_delay=0 if retry else 6,
                                    native_only=True,
                                    profile_name='native_safety_streaming_solver_as_tool_call_checkpoint.json')

    def test_python_checkpoint_background_waits(self):
        for harness in ('nanobot', 'hermes'):
            with self.subTest(harness=harness):
                self.run_solver(harness, native_path='background',
                                profile_name='native_safety_streaming_solver_as_tool_call_checkpoint.json')

    def test_python_checkpoint_model_retries_and_native_read_timeouts(self):
        for harness in ('generic', 'nanobot', 'hermes'):
            for retry in (True, False):
                with self.subTest(harness=harness, retry=retry):
                    self.run_model(retry=retry, final_delay=0 if retry else 2,
                                   asynchronous=harness == 'nanobot', harness_name=harness,
                                   profile_name='native_safety_streaming_solver_as_tool_call_checkpoint.json')

    def test_python_checkpoint_hidden_retries(self):
        for harness in ('generic', 'nanobot', 'hermes'):
            with self.subTest(harness=harness):
                self.run_solver(harness, profile_name='native_safety_streaming_solver_as_tool_call_checkpoint.json')

    def test_python_checkpoint_genuine_timeouts(self):
        for harness in ('generic', 'nanobot', 'hermes'):
            with self.subTest(harness=harness):
                self.run_solver(harness, final_delay=5, retry=False, profile_name='native_safety_streaming_solver_as_tool_call_checkpoint.json')

    def run_solver(self, harness, *, final_delay=0, retry=True, native_path=None, native_only=False, profile_name="native_safety_streaming_solver_as_tool_logical_deadline.json"):
        bridge = json.loads(subprocess.check_output(["docker", "network", "inspect", "bridge"], text=True))[0]["IPAM"]["Config"][0]["Gateway"]
        self.assertTrue(ipaddress.ip_address(bridge).is_private)
        backend = ThreadingHTTPServer((bridge, 0), DelayedBackend)
        backend.responses = [SUBMIT, TIMEOUT, SUBMIT, PLAN] if retry else [SUBMIT, PLAN]
        backend.requests = []
        backend.final_delay = final_delay
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / profile_name)
        adapter = get_adapter(harness, benchmark_profile=profile, model="openai/gpt-4o-mini", api_key="test-not-real")
        identity = "logical-native-test-" + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory(prefix="logical-native-evidence-") as directory:
                workspace = AgentWorkspace(identity, identity, adapter, artifact_dir=Path(directory))
                with patch.object(adapter, "solver_upstream_base", return_value=f"http://{bridge}:{backend.server_port}"), patch.object(adapter, "solver_backend", return_value="public"):
                    try:
                        workspace.start()
                        workspace.write_text_file("/workspace/domain.pddl", "(domain bytes)")
                        workspace.write_text_file("/workspace/problem.pddl", "(problem bytes)")
                        clock = AttemptClock(30)
                        workspace.start_model_gateway_monitor(clock)
                        command = "cd /workspace && timeout 4 pddl-solver; echo NATIVE_EXIT=$?"
                        if native_only:
                            command = "cd /workspace && pddl-solver; echo NATIVE_EXIT=$?"
                        if harness == "generic":
                            code = f"import sys; sys.path.insert(0, {str(adapter.runtime_repo)!r}); from ga import code_run; print(list(code_run({command!r}, code_type='bash', timeout=5, cwd='/workspace', code_cwd='/workspace')))"
                        elif harness == "nanobot":
                            code = f"import asyncio; from nanobot.agent.tools.shell import ExecTool; print(asyncio.run(ExecTool(working_dir='/workspace', allowed_env_keys={list(ENVIRONMENT_KEYS)!r}).execute(command={command!r}, timeout=5)))"
                        elif harness == "openclaw":
                            options = {"command": command, "workdir": "/workspace", "env": {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/root"}, "timeoutSec": 5, "maxOutput": 10000, "pendingMaxOutput": 10000, "warnings": []}
                            code = f"import {{m as run}} from '/usr/lib/node_modules/openclaw/dist/bash-tools.exec-runtime-Cdq-HAHC.js'; const task=await run({json.dumps(options)}); console.log(JSON.stringify(await task.promise));"
                        else:
                            code = f"import subprocess; from tools.environments.local import LocalEnvironment; e=LocalEnvironment(cwd='/workspace'); p=subprocess.Popen({command!r}, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True); print(e._wait_for_process(p, timeout=5))"
                        if native_path == 'background' and harness == 'hermes':
                            code = f"import os; from tools.process_registry import ProcessRegistry; r=ProcessRegistry(); s=r.spawn_local({command!r}, cwd='/workspace', env_vars=dict(os.environ)); print(r.wait(s.id, timeout=5))"
                        elif native_path == 'background' and harness == 'nanobot':
                            code = f"""import asyncio, os
from nanobot.agent.tools.exec_session import ExecSessionManager, WriteStdinTool
async def run():
    manager=ExecSessionManager()
    key, first=await manager.start(command={command!r}, cwd='/workspace', env=dict(os.environ),
        timeout=5, shell_program=None, login=False, yield_time_ms=0, max_output_chars=10000)
    assert not first.done, first
    print(await WriteStdinTool(manager=manager)._wait_for_output(session_id=key, chars=None,
        close_stdin=False, terminate=False, wait_for='NATIVE_EXIT', wait_timeout_ms=5000,
        max_output_chars=10000))
asyncio.run(run())
"""
                        runtime = "node --input-type=module -e" if harness == "openclaw" else f"{shlex.quote(str(adapter.runtime_python))} -c"
                        result = workspace.run_in_container(f"{runtime} {shlex.quote(code)}", timeout=25)
                        workspace.stop_model_gateway_monitor()
                        self.assertIsNone(workspace.gateway_monitor_error(), result.stdout + result.stderr)
                        self.assertIsNone(workspace.gateway_terminal_infra_error(), result.stdout + result.stderr)
                        self.assertEqual(result.exit_code, 0, result.stdout + result.stderr)
                        outcome = json.loads((Path(directory) / "gateway/solver_calls/call-0001/outcome.json").read_text())
                        if final_delay:
                            if not native_only:
                                self.assertIn("NATIVE_EXIT=124", result.stdout)
                            self.assertNotIn("(move a b)", result.stdout)
                            self.assertEqual(outcome["action"], "native_deadline")
                        else:
                            timing_file = "call_checkpoints.jsonl" if "call_checkpoint" in profile_name else "logical_time.jsonl"
                            self.assertIn("(move a b)", result.stdout, {"stdout": result.stdout, "stderr": result.stderr, "clock": clock.snapshot(), "outcome": outcome, "settlements": (Path(directory) / "gateway" / timing_file).read_text()})
                            self.assertIn("NATIVE_EXIT=0", result.stdout)
                            self.assertNotIn("[Timeout Error]", result.stdout)
                            self.assertEqual(outcome["action"], "return")
                            if retry:
                                self.assertGreaterEqual(clock.snapshot()["infra_pause_seconds"], 5)
                        isolation = workspace.validate_state_isolation()
                        self.assertEqual(isolation.get("status"), "pass", isolation)
                    finally:
                        workspace.cleanup()
        finally:
            backend.shutdown()
            backend.server_close()

    def test_generic_hidden_retry_longer_than_both_native_deadlines(self):
        self.run_solver("generic")

    def test_generic_genuine_native_deadline_still_fires(self):
        self.run_solver("generic", final_delay=5, retry=False)

    def test_nanobot_hidden_retry(self):
        self.run_solver("nanobot")

    def test_hermes_hidden_retry(self):
        self.run_solver("hermes")

    def test_openclaw_hidden_retry(self):
        self.run_solver("openclaw")

    def test_openclaw_genuine_native_deadline(self):
        self.run_solver("openclaw", final_delay=5, retry=False)

    def run_model(self, *, retry, final_delay=0, asynchronous=False, openclaw=False, harness_name=None, profile_name="native_safety_streaming_solver_as_tool_logical_deadline.json"):
        bridge = json.loads(subprocess.check_output(["docker", "network", "inspect", "bridge"], text=True))[0]["IPAM"]["Config"][0]["Gateway"]
        backend = ThreadingHTTPServer((bridge, 0), ModelBackend)
        backend.calls, backend.retry, backend.final_delay = 0, retry, final_delay
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / profile_name)
        adapter = get_adapter(harness_name or ("openclaw" if openclaw else "nanobot" if asynchronous else "generic"), benchmark_profile=profile, model="openai/gpt-4o-mini", api_key="test-not-real")
        gateway = adapter.model_gateway()
        gateway["upstream_origin"] = f"http://{bridge}:{backend.server_port}"
        identity = "logical-model-test-" + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory(prefix="logical-model-evidence-") as directory:
                workspace = AgentWorkspace(identity, identity, adapter, artifact_dir=Path(directory))
                try:
                    with patch.object(adapter, "model_gateway", return_value=gateway):
                        workspace.start()
                    clock = AttemptClock(30)
                    workspace.start_model_gateway_monitor(clock)
                    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "mock test"}], "stream": True}
                    url = f"http://{MODEL_GATEWAY_HOST}:{MODEL_GATEWAY_PORT}/v1/chat/completions"
                    if openclaw:
                        code = f"""import OpenAI from '/usr/lib/node_modules/openclaw/node_modules/openai/index.mjs';
const client = new OpenAI({{apiKey:'not-real', baseURL:{json.dumps(url.rsplit('/', 2)[0])}, timeout:1000, maxRetries:0}});
try {{
  const stream = await client.chat.completions.create({json.dumps(payload)});
  for await (const chunk of stream) console.log(JSON.stringify(chunk));
  console.log('MODEL_SUCCESS');
}} catch (e) {{
  if (e instanceof OpenAI.APIConnectionTimeoutError) console.log('NATIVE_READ_TIMEOUT');
  else throw e;
}}
"""
                    elif asynchronous:
                        code = f"""import asyncio, httpx
async def run():
    try:
        async with httpx.AsyncClient(timeout=1, trust_env=False) as c:
            async with c.stream('POST', {url!r}, json={payload!r}) as r:
                async for line in r.aiter_lines():
                    print(line, flush=True)
        print('MODEL_SUCCESS')
    except httpx.ReadTimeout:
        print('NATIVE_READ_TIMEOUT')
asyncio.run(run())
"""
                    else:
                        code = f"""import requests
try:
    r=requests.post({url!r}, json={payload!r}, stream=True, timeout=(5, 1))
    for line in r.iter_lines(chunk_size=1):
        print(line.decode(), flush=True)
    print('MODEL_SUCCESS')
except requests.exceptions.Timeout:
    print('NATIVE_READ_TIMEOUT')
"""
                    runtime = "node --input-type=module -e" if openclaw else f"{shlex.quote(str(adapter.runtime_python))} -c"
                    result = workspace.run_in_container(f"{runtime} {shlex.quote(code)}", timeout=20)
                    workspace.stop_model_gateway_monitor()
                    self.assertIsNone(workspace.gateway_monitor_error(), result.stdout + result.stderr)
                    self.assertIsNone(workspace.gateway_terminal_infra_error(), result.stdout + result.stderr)
                    self.assertEqual(result.exit_code, 0, result.stdout + result.stderr)
                    ledger = workspace.model_gateway_ledger()
                    self.assertEqual(len(ledger), 1, {"ledger": ledger, "output": result.stdout, "status": workspace.model_gateway_stats()})
                    entry = ledger[0]
                    if final_delay:
                        self.assertIn("NATIVE_READ_TIMEOUT", result.stdout)
                        self.assertNotIn("hello", result.stdout)
                        self.assertTrue(entry["native_deadline"], entry)
                    else:
                        self.assertIn("MODEL_SUCCESS", result.stdout)
                        self.assertIn("hello", result.stdout)
                        self.assertTrue(entry["downstream_committed"])
                        self.assertEqual(entry["transient_retry_count"], 1)
                        self.assertGreater(entry["infra_pause_seconds"], 3)
                        self.assertLess(entry["accepted_call_seconds"], 1)
                    self.assertEqual(backend.calls, 2 if retry else 1)
                finally:
                    workspace.cleanup()
        finally:
            backend.shutdown()
            backend.server_close()

    def test_model_first_failed_request_and_retry_excluded(self):
        self.run_model(retry=True)

    def test_model_genuine_native_read_timeout(self):
        self.run_model(retry=False, final_delay=3)

    def test_model_async_read_hidden_retry(self):
        self.run_model(retry=True, asynchronous=True)

    def test_openclaw_model_hidden_retry(self):
        self.run_model(retry=True, openclaw=True)

    def test_openclaw_model_genuine_timeout(self):
        self.run_model(retry=False, final_delay=3, openclaw=True)


@unittest.skipUnless(os.environ.get("RUN_EXTERNAL_CALLS_DOCKER_TESTS") == "1", "opt-in real Docker/native runtime test")
class CallCheckpointDockerTests(unittest.TestCase):
    run_solver = NativeDeadlineDockerTests.run_solver
    run_model = NativeDeadlineDockerTests.run_model
    profile_name = "native_safety_streaming_solver_as_tool_call_checkpoint.json"

    def test_native_exec_default_background_yield_then_model(self):
        """Actual default 10 s yield, actual process poll and SDK; healthy solver."""
        bridge = json.loads(subprocess.check_output(["docker", "network", "inspect", "bridge"], text=True))[0]["IPAM"]["Config"][0]["Gateway"]
        model = ThreadingHTTPServer((bridge, 0), ModelBackend)
        solver = ThreadingHTTPServer((bridge, 0), DelayedBackend)
        model.calls, model.retry, model.final_delay = 0, False, 0
        solver.requests, solver.responses, solver.final_delay = [], [SUBMIT, PLAN], 13
        for server in (model, solver):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / self.profile_name)
        adapter = get_adapter("openclaw", benchmark_profile=profile, model="openai/gpt-4o-mini", api_key="not-real")
        gateway = adapter.model_gateway()
        gateway["upstream_origin"] = f"http://{bridge}:{model.server_port}"
        identity = "checkpoint-background-test-" + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory(prefix="checkpoint-background-evidence-") as directory:
                workspace = AgentWorkspace(identity, identity, adapter, artifact_dir=Path(directory))
                try:
                    with patch.object(adapter, "model_gateway", return_value=gateway), \
                         patch.object(adapter, "solver_upstream_base", return_value=f"http://{bridge}:{solver.server_port}"), \
                         patch.object(adapter, "solver_backend", return_value="public"):
                        workspace.start()
                    workspace.write_text_file("/workspace/domain.pddl", "(domain bytes)")
                    workspace.write_text_file("/workspace/problem.pddl", "(problem bytes)")
                    clock = AttemptClock(40)
                    workspace.start_model_gateway_monitor(clock)
                    code = """
import {r as createExecTool, t as createProcessTool} from '/usr/lib/node_modules/openclaw/dist/bash-tools-Bvyb7cWG.js';
import OpenAI from '/usr/lib/node_modules/openclaw/node_modules/openai/index.mjs';
import deadlines from '/opt/benchmark-deadlines/node-checkpoints.cjs';
const runDeadline=deadlines.setTimeout(()=>{throw new Error('native run timeout')},35000);
const exec=createExecTool({host:'gateway',security:'full',ask:'off'});
const process=createProcessTool();
const start=Date.now();
// Neither background nor yieldMs is specified by the agent.
const initial=await exec.execute('exec-1',{command:'cd /workspace && pddl-solver',timeout:30});
const yieldElapsed=Date.now()-start;
if(initial.details.status!=='running') throw new Error(JSON.stringify(initial));
const client=new OpenAI({apiKey:'not-real',baseURL:'http://model-gateway:8766/v1',maxRetries:0});
const answers=await Promise.all([1,2].map(async index=>{
  const stream=await client.chat.completions.create({model:'gpt-4o-mini',stream:true,
  messages:[{role:'user',content:JSON.stringify({index,initial})}]});
  let answer=''; for await(const chunk of stream) answer+=chunk.choices[0]?.delta?.content??'';
  return answer;
}));
let final;
do { final=await process.execute('poll-1',{action:'poll',sessionId:initial.details.sessionId,timeout:1000}); }
while(final.details.status==='running');
console.log(JSON.stringify({yieldElapsed,elapsed:Date.now()-start,answers,initial,final}));
deadlines.clearTimeout(runDeadline);
"""
                    result = workspace.run_in_container("node --input-type=module -e " + shlex.quote(code), timeout=40)
                    workspace.stop_model_gateway_monitor()
                    self.assertIsNone(workspace.gateway_terminal_infra_error(), result.stdout + result.stderr)
                    self.assertIsNone(workspace.gateway_monitor_error(), result.stdout + result.stderr)
                    self.assertEqual(result.exit_code, 0, result.stdout + result.stderr)
                    value = json.loads(result.stdout)
                    self.assertGreater(value["yieldElapsed"], 9900)
                    self.assertLess(value["yieldElapsed"], 12500)
                    self.assertEqual(value["answers"], ["hello", "hello"])
                    self.assertIn("(move a b)", json.dumps(value["final"]))
                    self.assertEqual(model.calls, 2)
                    self.assertEqual(len(solver.requests), 2)
                    ledger = workspace.model_gateway_ledger()
                    self.assertEqual(len({row["timing_control_call_id"] for row in ledger}), 2)
                    self.assertTrue(all(row["external_call_timing_mode"] == "running_wall" for row in ledger))
                    solver_request = json.loads((Path(directory) / "gateway/solver_calls/call-0001/request.json").read_text())
                    self.assertIn("timing_control_call_id", solver_request)
                    self.assertLess(clock.snapshot()["infra_pause_seconds"], 1)
                    print("native background checkpoint:", {"wall_ms": value["elapsed"], "yield_ms": value["yieldElapsed"], "clock": clock.snapshot()})
                finally:
                    workspace.cleanup()
        finally:
            for server in (model, solver):
                server.shutdown()
                server.server_close()

    def test_model_retry_same_native_continuation(self):
        self.run_model(retry=True, openclaw=True, profile_name=self.profile_name)

    def test_model_real_timeout_still_cancels(self):
        self.run_model(retry=False, final_delay=3, openclaw=True, profile_name=self.profile_name)

    def test_solver_retry_nested_native_timers(self):
        self.run_solver("openclaw", profile_name=self.profile_name)

    def test_solver_real_timeout_still_cancels(self):
        self.run_solver("openclaw", retry=False, final_delay=5, profile_name=self.profile_name)

    def test_native_loop_stream_then_solver_retains_business_context(self):
        """Exercise the actual overlaid Agent loop, not just its HTTP SDK."""
        class LoopBackend(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.server.requests.append(raw)
                number = len(self.server.requests)
                if number == 1:
                    time.sleep(3)
                    self.send_response(429)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b'{}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def send(delta, finish=None):
                    event = {"id": "fixture", "object": "chat.completion.chunk", "model": "gpt-4o-mini",
                             "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())

                send({"role": "assistant"})
                if number == 2:
                    for _ in range(10000):
                        send({"content": "x"})
                    send({"tool_calls": [{"index": 0, "id": "fixed-solver-call", "type": "function",
                                          "function": {"name": "solve", "arguments": "{}"}}]})
                    send({}, "tool_calls")
                else:
                    send({"content": "done"})
                    send({}, "stop")
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()

            def log_message(self, *args):
                pass

        bridge = json.loads(subprocess.check_output(["docker", "network", "inspect", "bridge"], text=True))[0]["IPAM"]["Config"][0]["Gateway"]
        model = ThreadingHTTPServer((bridge, 0), LoopBackend)
        solver = ThreadingHTTPServer((bridge, 0), Backend)
        model.requests, solver.requests = [], []
        solver.responses = [SUBMIT, TIMEOUT, SUBMIT, PLAN]
        for server in (model, solver):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        profile = load_benchmark_profile(HISTORICAL_PROFILES_DIR / self.profile_name)
        adapter = get_adapter("openclaw", benchmark_profile=profile, model="openai/gpt-4o-mini", api_key="not-real")
        gateway = adapter.model_gateway()
        gateway["upstream_origin"] = f"http://{bridge}:{model.server_port}"
        identity = "checkpoint-loop-test-" + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory(prefix="checkpoint-loop-evidence-") as directory:
                workspace = AgentWorkspace(identity, identity, adapter, artifact_dir=Path(directory))
                try:
                    with patch.object(adapter, "model_gateway", return_value=gateway), \
                         patch.object(adapter, "solver_upstream_base", return_value=f"http://{bridge}:{solver.server_port}"), \
                         patch.object(adapter, "solver_backend", return_value="public"):
                        workspace.start()
                    clock = AttemptClock(45)
                    workspace.start_model_gateway_monitor(clock)
                    code = """
import {vt as Agent} from '/usr/lib/node_modules/openclaw/dist/proxy-72wW6ush.js';
import {i as streamSimple} from '/usr/lib/node_modules/openclaw/dist/stream-iBy3TeLb.js';
import deadlines from '/opt/benchmark-deadlines/node-checkpoints.cjs';
let executions=0;
const model={id:'gpt-4o-mini',name:'fixture',api:'openai-completions',provider:'openai',
baseUrl:'http://model-gateway:8766/v1',reasoning:false,input:['text'],contextWindow:128000,maxTokens:16384,
cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};
const agent=new Agent({streamFn:streamSimple,getApiKey:async()=>'not-real', initialState:{model,
tools:[{name:'solve',description:'Fixture solver',parameters:{type:'object',properties:{},additionalProperties:false},
execute:async()=>{executions++; const r=await fetch('http://solver-gateway:8768/solve',
{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({domain:'(domain bytes)',problem:'(problem bytes)'})});
const result=await r.json(); return {content:[{type:'text',text:JSON.stringify(result)}],details:{}};}}]}});
const deadline=deadlines.setTimeout(()=>agent.abort(),30000);
const started=Date.now(); await agent.prompt('Use solve once, then finish.'); deadlines.clearTimeout(deadline);
console.log(JSON.stringify({executions,elapsed:Date.now()-started,messages:agent.state.messages}));
"""
                    result = workspace.run_in_container("node --input-type=module -e " + shlex.quote(code), timeout=45)
                    workspace.stop_model_gateway_monitor()
                    self.assertIsNone(workspace.gateway_monitor_error(), result.stdout + result.stderr)
                    self.assertIsNone(workspace.gateway_terminal_infra_error(), result.stdout + result.stderr)
                    self.assertEqual(result.exit_code, 0, result.stdout + result.stderr)
                    value = json.loads(result.stdout)
                    self.assertEqual(value["executions"], 1, {"elapsed": value["elapsed"], "messages": [
                        {"role": m["role"], "stopReason": m.get("stopReason"), "errorMessage": m.get("errorMessage")}
                        for m in value["messages"]]})
                    self.assertEqual([m["role"] for m in value["messages"]], ["user", "assistant", "toolResult", "assistant"])
                    self.assertIn("done", json.dumps(value["messages"][-1]))
                    self.assertNotIn("Request Time Out", json.dumps(value["messages"]))
                    self.assertEqual(model.requests[0], model.requests[1])
                    self.assertEqual(len(model.requests), 3)
                    self.assertEqual(solver.requests[0][1], solver.requests[2][1])
                    ledger = workspace.model_gateway_ledger()
                    self.assertEqual(len(ledger), 2)
                    self.assertEqual([e["action"] for e in ledger[0]["checkpoint_events"]], ["checkpoint", "rollback", "commit"])
                    self.assertGreater(value["elapsed"], 8000)
                    from agent_formalizer.results.optional_evidence import collect_full_trace_evidence
                    audit = collect_full_trace_evidence(Path(directory), 'openclaw', workspace.container_name)
                    self.assertEqual(audit['native_collection'], 'host_stream', audit)
                    self.assertNotEqual(workspace.run_in_container('test -e /tmp/benchmark-full-trace').exit_code, 0)
                    self.assertEqual(audit['native_events'].get('tool_result'), 1, audit)
                    self.assertEqual(audit['parse_errors'], 0, audit)
                    self.assertIn('(move a b)', (Path(directory) / 'native_audit/native_tools.jsonl').read_text())
                    print("native checkpoint loop:", {"physical_ms": value["elapsed"], "active_seconds": clock.snapshot()["active_duration_seconds"], "stream_events": 10000})
                finally:
                    workspace.cleanup()
        finally:
            for server in (model, solver):
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
