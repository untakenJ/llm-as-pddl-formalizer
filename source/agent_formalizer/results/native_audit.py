"""Passive native tool evidence, independent of retry/timer decisions.

Version-checked runtime overlays call this collector at the native tool-return
boundary, BEFORE subsequent history compression. Original values, exceptions,
generator yields, concurrency and context budgets remain unchanged. The sink
is attempt-private and is collected even when there is no next model request.
"""
from __future__ import annotations

import ast
import dataclasses
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import threading
import time
import uuid

AUDIT_SOCKET = "/run/benchmark-deadlines/native-audit.sock"
_lock = threading.RLock()
_seen: dict[str, str] = {}


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()
                if str(k).lower() not in {"api_key", "authorization", "x-goog-api-key"}}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    return {"unserialized_type": type(value).__name__}


def _snapshot():
    # Do not crawl harness HOME, /proc, credentials, runtimes or symlink targets.
    # Workspace text files plus direct /tmp auxiliary programs are task content.
    paths = []
    if Path("/workspace").is_dir():
        for directory, dirs, files in os.walk("/workspace", followlinks=False):
            dirs[:] = [d for d in dirs if not Path(directory, d).is_symlink()]
            paths.extend(Path(directory, name) for name in files)
    paths.extend(p for p in Path("/tmp").iterdir()
                 if p.suffix in {".py", ".pddl", ".sh", ".txt"})
    changed = []
    for path in paths:
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            # O_NOFOLLOW closes the lstat/open symlink race.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    continue
                data = stream.read()
            digest = hashlib.sha256(data).hexdigest()
            if _seen.get(str(path)) == digest:
                continue
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                changed.append({"path": str(path), "sha256": digest, "bytes": len(data),
                                "content_status": "binary_not_human_readable"})
            else:
                changed.append({"path": str(path), "sha256": digest, "bytes": len(data),
                                "text": data.decode("utf-8")})
            _seen[str(path)] = digest
        except FileNotFoundError:
            changed.append({"path": str(path), "content_status": "disappeared_during_snapshot"})
        except OSError as exc:
            changed.append({"path": str(path), "content_status": type(exc).__name__})
    return changed


def record(event: str, *, snapshot=False, **fields):
    """Best-effort evidence only; errors are visible, never substitute tool results."""
    try:
        with _lock:
            value = {"schema_version": 1, "event": event, "physical_time": time.time(),
                     "pid": os.getpid(), **_jsonable(fields)}
            if snapshot:
                value["file_changes"] = _snapshot()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(5)
                channel.connect(AUDIT_SOCKET)
                channel.sendall((json.dumps(value, ensure_ascii=False) + "\n").encode())
                ack = b""
                while len(ack) < 3:
                    fragment = channel.recv(3 - len(ack))
                    if not fragment:
                        break
                    ack += fragment
                if ack != b"ok\n":
                    raise OSError("native audit not acknowledged")
    except Exception as exc:
        _seen.clear()  # A later successful boundary must resend lost snapshots.
        # Content-free fail-visible diagnostic, not an agent tool response.
        try:
            os.write(2, ("BENCHMARK_FULL_TRACE_ERROR " + type(exc).__name__ + "\n").encode())
        except OSError:
            pass


class Collector:
    """Host-only append sink; its API never returns historical content.

    Only the socket is in the native control mount. Evidence and snapshots are
    not mounted into the agent, so observing clipped results does not give it
    an extra memory/context-recovery channel. Client paths are metadata only;
    all written filenames are host-computed content hashes.
    """
    def __init__(self, control_directory: Path, evidence_directory: Path):
        self.root = Path(evidence_directory)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.lock = threading.Lock()
        self.errors = 0
        self.records = 0
        self.socket_path = Path(control_directory) / "native-audit.sock"
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    self.connection.settimeout(5)
                    value = json.loads(self.rfile.readline())
                    owner.append(value)
                    self.wfile.write(b"ok\n")
                except Exception as exc:
                    with owner.lock:
                        owner.errors += 1
                        owner._status(type(exc).__name__)

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        fd = os.open(control_directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.server = Server(f"/proc/self/fd/{fd}/native-audit.sock", Handler)
        finally:
            os.close(fd)
        self.socket_path.chmod(0o666)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval":0.05}, daemon=True)
        self.thread.start()
        self.append({"schema_version":1,"event":"collector_ready","storage":"host_only"})

    def _status(self, error=None):
        path = self.root / "capture_status.json"
        path.write_text(json.dumps({"records":self.records,"errors":self.errors,
                                    "last_error_type":error,"storage":"host_only"}) + "\n")
        path.chmod(0o600)

    def append(self, value):
        if not isinstance(value, dict) or not isinstance(value.get("event"), str):
            raise ValueError("invalid native audit event")
        with self.lock:
            for change in value.get("file_changes", []):
                if "text" not in change:
                    continue
                text = change.pop("text")
                if not isinstance(text, str):
                    raise ValueError("invalid text snapshot")
                data = text.encode("utf-8")
                digest = hashlib.sha256(data).hexdigest()
                blob = self.root / "files" / digest
                blob.parent.mkdir(exist_ok=True, mode=0o700)
                if not blob.exists():
                    blob.write_bytes(data)
                    blob.chmod(0o600)
                change.update(sha256=digest,bytes=len(data),content_file="files/" + digest)
            path = self.root / "native_tools.jsonl"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            path.chmod(0o600)
            self.records += 1
            self._status()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def capture(function):
    signature = inspect.signature(function)

    def start(args, kwargs):
        call_id = uuid.uuid4().hex
        bound = signature.bind_partial(*args, **kwargs).arguments
        arguments = {k: v for k, v in bound.items() if k not in
                     {"self", "agent", "spec", "execute", "stop_signal", "myprint"}}
        record("tool_start", call_id=call_id, tool=function.__qualname__, arguments=arguments)
        return call_id

    def end(call_id, result):
        record("tool_result", snapshot=True, call_id=call_id,
               tool=function.__qualname__, result=result)

    def error(call_id, exc):
        record("tool_exception", snapshot=True, call_id=call_id,
               tool=function.__qualname__, error_type=type(exc).__name__, error=str(exc))

    if inspect.iscoroutinefunction(function):
        @functools.wraps(function)
        async def asynchronous(*args, **kwargs):
            call_id = start(args, kwargs)
            try:
                result = await function(*args, **kwargs)
                end(call_id, result)
                return result
            except BaseException as exc:
                error(call_id, exc)
                raise
        return asynchronous
    if inspect.isgeneratorfunction(function):
        class Observed:
            def __init__(self, iterator, call_id):
                self.iterator, self.call_id = iterator, call_id
            def __iter__(self):
                return self
            def observed(self, method, *args):
                value = method(*args)
                record("tool_progress", call_id=self.call_id, result=value)
                return value
            def __next__(self):
                return self.observed(next, self.iterator)
            def send(self, value):
                return self.observed(self.iterator.send, value)
            def throw(self, *args):
                return self.observed(self.iterator.throw, *args)
            def close(self):
                return self.iterator.close()
        @functools.wraps(function)
        def generator(*args, **kwargs):
            call_id = start(args, kwargs)
            try:
                # yield-from preserves send/throw/close and StopIteration.value.
                result = yield from Observed(function(*args, **kwargs), call_id)
                end(call_id, result)
                return result
            except BaseException as exc:
                error(call_id, exc)
                raise
        return generator
    @functools.wraps(function)
    def synchronous(*args, **kwargs):
        call_id = start(args, kwargs)
        try:
            result = function(*args, **kwargs)
            end(call_id, result)
            return result
        except BaseException as exc:
            error(call_id, exc)
            raise
    return synchronous


def instrument_python(tree, module):
    targets = {
        "nanobot.agent.tools.registry": {"execute"},
        "nanobot.agent.runner": {"_run_tool"},
        "agent.tool_executor": {"_run_agent_tool_execution_middleware"},
        "ga": {"code_run", "do_code_run", "do_file_read", "do_file_write", "do_file_patch"},
    }
    selected = targets.get(module, set())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in selected:
            node.decorator_list.append(ast.parse("__import__('native_audit').capture", mode="eval").body)
            found.add(node.name)
        # Generic's native code_run retains stdout before smart_format clips it.
        if module == "ga" and isinstance(node, ast.FunctionDef) and node.name == "code_run":
            class RawOutput(ast.NodeTransformer):
                def visit_Assign(self, item):
                    if any(isinstance(t, ast.Name) and t.id == "stdout_str" for t in item.targets):
                        return [item, ast.parse("__import__('native_audit').record('raw_process_output', stdout=stdout_str, source='ga.code_run')").body[0]]
                    return self.generic_visit(item)
            RawOutput().visit(node)
    if found != selected:
        raise RuntimeError(f"native audit source drift: {module}: {found} != {selected}")
    if module == "agent.tool_executor":
        class BeforeHistory(ast.NodeTransformer):
            count = 0
            def visit_Assign(self, node):
                calls = [item for item in ast.walk(node.value) if isinstance(item, ast.Call)
                         and isinstance(item.func, ast.Name) and item.func.id == "maybe_persist_tool_result"]
                if calls:
                    if len(calls) != 1:
                        raise RuntimeError("ambiguous Hermes history persistence call")
                    keywords = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
                    self.count += 1
                    call = ast.parse("__import__('native_audit').record('tool_result', snapshot=True, "
                                     f"tool={keywords['tool_name']}, call_id={keywords['tool_use_id']}, result=function_result)").body[0]
                    return [call, node]
                return self.generic_visit(node)
        rewrite = BeforeHistory()
        tree = rewrite.visit(tree)
        if rewrite.count != 2:
            raise RuntimeError(f"Hermes audit history boundary drift: {rewrite.count}")
    return tree


# Node uses the same record vocabulary. Files are content-addressed and native
# return objects are observed without cloning/replacing them on the data path.
NODE_SOURCE = r'''
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const net = require('node:net');
const seen = new Map();
function files() {
  const paths = [];
  function walk(dir) { for (const e of fs.readdirSync(dir, {withFileTypes:true})) {
    const p = path.join(dir,e.name); if(e.isDirectory()) walk(p); else if(e.isFile()) paths.push(p);
  }}
  if(fs.existsSync('/workspace')) walk('/workspace');
  for(const e of fs.readdirSync('/tmp',{withFileTypes:true}))
    if(e.isFile() && /\.(py|pddl|sh|txt)$/.test(e.name)) paths.push('/tmp/'+e.name);
  const changed=[];
  for(const p of paths) { try {
    const fd=fs.openSync(p, fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
    let data; try { if(!fs.fstatSync(fd).isFile()) continue; data=fs.readFileSync(fd); } finally { fs.closeSync(fd); }
    const hash=crypto.createHash('sha256').update(data).digest('hex');
    if(seen.get(p)===hash) continue;
    const text=data.toString('utf8');
    if(Buffer.from(text,'utf8').equals(data)) {
      changed.push({path:p,sha256:hash,bytes:data.length,text});
    } else changed.push({path:p,sha256:hash,bytes:data.length,content_status:'binary_not_human_readable'});
    seen.set(p,hash);
  } catch(e) {changed.push({path:p,content_status:e.code||e.name});}}
  return changed;
}
function record(event, fields={}, snapshot=false) { try {
  const value={schema_version:1,event,physical_time:Date.now()/1000,pid:process.pid,...fields};
  if(snapshot) value.file_changes=files();
  const bytes=JSON.stringify(value)+'\n';
  const channel=net.createConnection('/run/benchmark-deadlines/native-audit.sock');
  let ack='',failed=false;
  function failure(name) { if(!failed) {failed=true;seen.clear();process.stderr.write('BENCHMARK_FULL_TRACE_ERROR '+name+'\n');} }
  channel.setTimeout(5000);
  channel.on('connect',()=>channel.write(bytes));
  channel.on('data',data=>{ack+=data.toString();if(ack==='ok\n')channel.end();else if(ack.length>=3)channel.destroy(new Error('native audit acknowledgement'));});
  channel.on('timeout',()=>channel.destroy(new Error('native audit timeout')));
  channel.on('error',e=>failure(e.name));
  channel.on('close',()=>{if(ack!=='ok\n')failure('IncompleteAcknowledgement');});
} catch(e) { seen.clear();process.stderr.write('BENCHMARK_FULL_TRACE_ERROR '+e.name+'\n'); }}
module.exports={record};
'''


def instrument_zeroclaw(source: str) -> str:
    marker = "    // Emit the terminal ToolResult immediately after this call completes so"
    if source.count(marker) != 1:
        raise RuntimeError("ZeroClaw native audit source drift")
    capture = r'''
    // Passive benchmark sink, independent of history/event-channel delivery.
    if let Ok(out) = &outcome {
        use std::io::{Write, Read};
        static AUDIT_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
        let _audit_lock = AUDIT_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let saved = (|| -> std::io::Result<()> {
            let mut file = std::os::unix::net::UnixStream::connect("/run/benchmark-deadlines/native-audit.sock")?;
            file.set_write_timeout(Some(std::time::Duration::from_secs(5)))?;
            file.set_read_timeout(Some(std::time::Duration::from_secs(5)))?;
            fn snapshot(dir: &std::path::Path, recurse: bool,
                        changed: &mut Vec<serde_json::Value>) -> std::io::Result<()> {
                use sha2::{Digest, Sha256};
                for entry in std::fs::read_dir(dir)? {
                    let entry = entry?;
                    let kind = entry.file_type()?;
                    let path = entry.path();
                    if kind.is_dir() && recurse { snapshot(&path,true,changed)?; }
                    else if kind.is_file() && (recurse || matches!(path.extension().and_then(|s|s.to_str()),Some("py"|"pddl"|"sh"|"txt"))) {
                        if let Ok(data) = std::fs::read(&path) {
                            if let Ok(text) = std::str::from_utf8(&data) {
                                let hash = format!("{:x}",Sha256::digest(&data));
                                changed.push(serde_json::json!({"path":path,"sha256":hash,"bytes":data.len(),"text":text}));
                            }
                        }
                    }
                }
                Ok(())
            }
            let mut changed=Vec::new();
            snapshot(std::path::Path::new("/workspace"),true,&mut changed)?;
            snapshot(std::path::Path::new("/tmp"),false,&mut changed)?;
            let record = serde_json::json!({"schema_version":1,"event":"tool_result",
                "call_id":event_call_id,"tool":call_name,"arguments":call_arguments,
                "result":out.output,"success":out.success,"error":out.error_reason,
                "structured_output":out.output_data,
                "file_changes":changed,
                "physical_time":std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs_f64()});
            writeln!(file,"{}",record)?;
            let mut ack=[0u8;3]; file.read_exact(&mut ack)?;
            if &ack != b"ok\n" { return Err(std::io::Error::other("native audit not acknowledged")); }
            Ok(())
        })();
        if let Err(error) = saved { eprintln!("BENCHMARK_FULL_TRACE_ERROR {:?}",error.kind()); }
    }
'''
    signature_start = source.index("pub(crate) async fn execute_one_tool(")
    signature_end = source.index("    // Serialize arguments once", signature_start)
    signature = source[signature_start:signature_end]
    # Observe the returned outcome outside the original function so early
    # unavailable/unknown/denied-tool returns are not silently lost either.
    wrapper = signature + r'''
    let audit_arguments = call_arguments.clone();
    let outcome = execute_one_tool_unobserved(call_name, call_arguments, tool_call_id,
        dispatch, meta, observer, cancellation_token, receipt_generator, event_tx).await;
    let call_arguments = audit_arguments;
    let event_call_id = tool_call_id.map(str::to_string).unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
''' + capture + '\n    outcome\n}\n\n'
    original = source[signature_start:].replace(
        'pub(crate) async fn execute_one_tool(', 'async fn execute_one_tool_unobserved(', 1)
    return source[:signature_start] + wrapper + original
