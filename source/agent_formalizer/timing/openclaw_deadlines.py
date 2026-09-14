"""Version-bound, read-only OpenClaw source overlays for logical deadlines.

Only the loader sees transformed source. Never edits the installed runtime.
The existing runtime lock plus explicit source-pattern checks fail closed.
"""
from pathlib import Path
import hashlib
import json
import re

PATTERNS = (
    "dist/selection-BfRwHcjH.js", "dist/supervisor-Dcv60Rew.js",
    "dist/attempt.model-diagnostic-events-*.js", "dist/agent-runner.runtime-*.js",
    "dist/fetch-timeout-*.js", "dist/bash-tools.exec-runtime-*.js",
    "node_modules/openai/client.mjs", "node_modules/openai/client.js",
)


def sources(root, *, checkpoint=False):
    result = []
    for pattern in (*PATTERNS, *(("dist/proxy-72wW6ush.js",) if checkpoint else ())):
        found = list(Path(root).glob(pattern))
        if len(found) != 1:
            raise RuntimeError(f"OpenClaw deadline runtime source mismatch: {pattern}")
        result.append(found[0])
    return result


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(f"OpenClaw deadline source drift: {old}")
    return source.replace(old, new)


def transform(path, *, checkpoint=False):
    source = path.read_text()
    count = 0
    if checkpoint and path.name.startswith("proxy-"):
        source = replace_one(source,
            "const result = await prepared.tool.execute(prepared.toolCall.id, prepared.args, signal, (partialResult) => {",
            "const result = await prepared.tool.execute(prepared.toolCall.id, prepared.args, signal, (partialResult) => {\n"
            "__benchmarkAudit.record('tool_progress', {call_id:prepared.toolCall.id, tool:prepared.toolCall.name, result:partialResult});")
        source = replace_one(source, "\tlet result = executed.result;",
            "\t__benchmarkAudit.record('tool_result', {call_id:prepared.toolCall.id, tool:prepared.toolCall.name, arguments:prepared.args, result:executed.result, is_error:executed.isError}, true);\n\tlet result = executed.result;")
        source = "import __benchmarkAudit from '/opt/benchmark-deadlines/native-audit.cjs';\n" + source
        # Preserve the exact pending native continuation, including tool calls
        # already chosen by the model. No transcript replay or new prompt.
        for name, args, context in (
            ("streamAssistantResponse", "context, config, signal, emit, streamFn, runtime", "context"),
            ("executeToolCalls", "currentContext, assistantMessage, config, signal, emit", "currentContext"),
            ("executePreparedToolCall", "prepared, signal, emit", None),
        ):
            signature = f"async function {name}({args}) {{"
            guard = f"__benchmarkDeadlineRuntime.watchContext({context})" if context else "__benchmarkDeadlineRuntime.enterTool()"
            wrapper = (f"{signature}\nconst release = {guard};\n"
                       f"try {{ return await __checkpoint_{name}({args}); }} finally {{ release(); }}\n}}\n"
                       f"async function __checkpoint_{name}({args}) {{")
            source = replace_one(source, signature, wrapper)
    # Register only cancellation watchdogs, never an ordinary sleep/yield or
    # cleanup/logging timer: a due sleep must not cancel an unrelated API call.
    if path.name.startswith("selection-"):
        start = source.index("function streamWithIdleTimeout(")
        end = source.index("//#endregion", start)
        block, changes = re.subn(r"(?<![\w.])setTimeout\(", "__benchmarkSetTimeout(", source[start:end])
        if changes != 2:
            raise RuntimeError("OpenClaw idle watchdog source drift")
        source = source[:start] + block + source[end:]
        source = replace_one(source, "abortTimer = setTimeout(", "abortTimer = __benchmarkSetTimeout(")
        count = changes + 1
    elif path.name.startswith("supervisor-"):
        for variable, expected in (("timeoutTimer", 1), ("noOutputTimer", 2)):
            old = variable + " = setTimeout("
            if source.count(old) != expected:
                raise RuntimeError("OpenClaw supervisor watchdog source drift")
            source = source.replace(old, variable + " = __benchmarkSetTimeout(")
            count += expected
    else:
        variable = (
            "timeoutHandle" if path.name.startswith("attempt.model-") else
            "timeoutId" if path.name.startswith(("agent-runner.runtime-", "fetch-timeout-")) else
            "timeout" if path.name in {"client.js", "client.mjs"} else None
        )
        if variable:
            source = replace_one(source, variable + " = setTimeout(", variable + " = __benchmarkSetTimeout(")
            count = 1
    source = re.sub(r"(?<![\w.])clearTimeout\(", "__benchmarkClearTimeout(", source)
    if path.name.startswith("supervisor-"):
        # These performance readings only calculate/check native deadlines;
        # Date.now-based process registry timestamps remain physical.
        source = source.replace("performance.now()", "__benchmarkNowMs()")
    if path.name.startswith("selection-"):
        source = replace_one(source, "let runAbortDeadlineAtMs = Date.now() + params.timeoutMs;", "let runAbortDeadlineAtMs = __benchmarkNowMs() + params.timeoutMs;")
        source = replace_one(source, "runAbortDeadlineAtMs = Date.now() + Math.max(1, delayMs);", "runAbortDeadlineAtMs = __benchmarkNowMs() + Math.max(1, delayMs);")
        source = replace_one(source, "Math.max(Date.now(), runAbortDeadlineAtMs - 500)", "Math.max(__benchmarkNowMs(), runAbortDeadlineAtMs - 500)")
        source = replace_one(source, "deadlineAtMs: completionRequiredAsyncDeadlineAtMs,", "now: __benchmarkNowMs, deadlineAtMs: completionRequiredAsyncDeadlineAtMs,")
        source = replace_one(source, "deadlineAtMs: Date.now()\n", "now: __benchmarkNowMs, deadlineAtMs: __benchmarkNowMs()\n")
    if path.name.startswith("bash-tools.exec-runtime-"):
        source = replace_one(source, "const shellRuntimeEnv = {\n\t\t...opts.env,", "const shellRuntimeEnv = {\n\t\t...opts.env,\n\t\t...__benchmarkRuntimeEnvironment(),")
    names = "setTimeout: __benchmarkSetTimeout, clearTimeout: __benchmarkClearTimeout, nowMs: __benchmarkNowMs, runtimeEnvironment: __benchmarkRuntimeEnvironment"
    runtime = "/opt/benchmark-deadlines/" + ("node-checkpoints.cjs" if checkpoint else "node-deadlines.cjs")
    if path.name == "client.js":
        prefix = f'const {{{names}}} = require({json.dumps(runtime)});\n'
    else:
        prefix = f'import __benchmarkDeadlineRuntime from {json.dumps(runtime)};\nconst {{{names}}} = __benchmarkDeadlineRuntime;\n'
    return prefix + source, count


def build(root, bundle, *, checkpoint=False):
    manifest = []
    mapping = {}
    for path in sources(root, checkpoint=checkpoint):
        transformed, count = transform(path, checkpoint=checkpoint)
        relative = path.relative_to(root)
        target = "overlay-" + hashlib.sha256(str(relative).encode()).hexdigest()[:16] + path.suffix
        destination = bundle / target
        if not destination.exists():
            import uuid
            temporary = bundle / (target + "." + uuid.uuid4().hex)
            temporary.write_text(transformed)
            temporary.replace(destination)
        mapping[(Path("/usr/lib/node_modules/openclaw") / relative).as_uri()] = target
        manifest.append({"source": str(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "overlay_sha256": hashlib.sha256(transformed.encode()).hexdigest(), "timer_sites": count})
    if not (bundle / "node-overlays.json").exists():
        # Per-bundle content is deterministic. Publish the complete map last.
        import uuid
        temporary = bundle / ("node-overlays." + uuid.uuid4().hex + ".json")
        temporary.write_text(json.dumps(mapping, sort_keys=True))
        temporary.replace(bundle / "node-overlays.json")
    return manifest
