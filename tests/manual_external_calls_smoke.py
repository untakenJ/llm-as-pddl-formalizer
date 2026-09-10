"""Opt-in live smoke. Never imported by unittest discovery; no sweep outputs."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from agent_formalizer.configuration.config import MODEL_GATEWAY_SCRIPT, ROOT_DIR
from agent_formalizer.external_calls.control import write_json
from agent_formalizer.external_calls.solver import solve
from agent_formalizer.tools.solver.remote_client import solver_failure
from agent_formalizer.util import read_named_secret


def public_solver(output, selected=None):
    fixture = ROOT_DIR / "tests" / "fixtures" / "local_solver"
    domain = (fixture / "tiny_domain.pddl").read_text()
    problem = (fixture / "tiny_problem.pddl").read_text()
    scenarios = [
        ("plan", domain, problem, True),
        ("empty_plan", domain, problem.replace("(:goal (at-b))", "(:goal (at-a))"), True),
        ("unsolvable", domain, problem.replace("(:init (at-a))", "(:init (at-b))").replace("(:goal (at-b))", "(:goal (at-a))"), False),
        ("syntax_error", domain + " invalid trailing token", problem, False),
    ]
    summaries = []
    for name, df, pf, expected in scenarios:
        if selected and name != selected:
            continue
        records = []
        started = time.monotonic()
        try:
            ok, result, charged = solve(df, pf, solver="dual-bfws-ffparser",
                base_url="https://solver.planning.domains:5001", format_failure=solver_failure,
                event=records.append)
            row = {"case": name, "ok": ok, "expected_ok": expected, "result": result,
                   "charged_seconds": charged, "wall_seconds": time.monotonic() - started,
                   "events": records}
        except Exception as exc:
            row = {"case": name, "exception": type(exc).__name__, "reason": str(exc), "events": records}
        write_json(output / f"public-{name}.json", row)
        summary = {k: v for k, v in row.items() if k not in {"events", "result"}}
        summary["final_classification"] = records[-1].get("reason") if records else None
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    return summaries


def deepseek(output):
    # The one real provider request has a tiny completion cap and no automatic
    # retry: recovery semantics were already exercised by the mock tests.
    with tempfile.TemporaryDirectory(prefix="external-calls-key-") as directory:
        key_file = Path(directory) / "key"
        key_file.write_text(read_named_secret("DEEPSEEK_API_KEY", ROOT_DIR / "_private" / ".env"))
        key_file.chmod(0o600)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PDDL_GATEWAY_UPSTREAM_ORIGIN": "https://api.deepseek.com",
            "PDDL_GATEWAY_LISTEN_HOST": "127.0.0.1",
            "PDDL_GATEWAY_PORT": str(port),
            "PDDL_GATEWAY_API_KEY_FILE": str(key_file),
            "PDDL_GATEWAY_PROVIDER": "deepseek",
            "PDDL_GATEWAY_AUTH_MODE": "bearer",
            "PDDL_GATEWAY_ALLOWED_MODELS": '["deepseek-v4-flash"]',
            "PDDL_GATEWAY_ALLOWED_PATH_PREFIXES": '["/v1"]',
            "PDDL_GATEWAY_MAX_MODEL_CALLS": "1",
            "PDDL_GATEWAY_MAX_ACTION_STEPS": "2",
            "PDDL_GATEWAY_MAX_TRANSIENT_RETRIES": "0",
            "PDDL_GATEWAY_RESPONSE_DELIVERY": "native_streaming",
            "PDDL_GATEWAY_CONTROL_FILE": str(output / "model-control.json"),
            "PDDL_GATEWAY_REASONING_PATH": str(output / "provider_reasoning.jsonl"),
            "PDDL_GATEWAY_REASONING_STATUS_PATH": str(output / "reasoning_capture_status.json"),
        }
        with open(output / "model-gateway.log", "w") as log:
            process = subprocess.Popen([sys.executable, str(MODEL_GATEWAY_SCRIPT)], env=env, stdout=log, stderr=log)
            try:
                origin = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("smoke gateway exited during startup")
                    try:
                        with urllib.request.urlopen(origin + "/__benchmark__/health", timeout=1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise RuntimeError("smoke gateway did not become healthy")
                request = urllib.request.Request(origin + "/v1/chat/completions",
                    data=json.dumps({"model": "deepseek-v4-flash",
                        "messages": [{"role": "user", "content": "Reply exactly OK."}],
                        "max_tokens": 64, "thinking": {"type": "disabled"}, "stream": True,
                        "stream_options": {"include_usage": True}}).encode(),
                    headers={"Content-Type": "application/json", "Authorization": "Bearer benchmark-placeholder"})
                chunks = []
                with urllib.request.urlopen(request, timeout=120) as response:
                    stream = response.read().decode()
                (output / "deepseek-stream.txt").write_text(stream)
                for line in stream.splitlines():
                    if line.startswith("data:") and line[5:].strip() != "[DONE]":
                        chunks.append(json.loads(line[5:]))
                with urllib.request.urlopen(origin + "/__benchmark__/ledger", timeout=5) as response:
                    ledger = json.load(response)
                write_json(output / "model-ledger.json", ledger)
                with urllib.request.urlopen(origin + "/__benchmark__/status", timeout=5) as response:
                    status = json.load(response)
                write_json(output / "model-status.json", status)
                content = "".join(choice.get("delta", {}).get("content") or "" for chunk in chunks for choice in chunk.get("choices", []))
                summary = {"case": "deepseek_streaming", "content": content,
                    "done_marker": "[DONE]" in stream, "sse_chunks": len(chunks),
                    "usage": [c["usage"] for c in chunks if c.get("usage")],
                    "logical_model_calls": status.get("request_attempts"),
                    "physical_model_calls": status.get("upstream_attempts")}
                write_json(output / "deepseek-summary.json", summary)
                print(json.dumps(summary), flush=True)
                return summary
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-solver", action="store_true")
    parser.add_argument("--deepseek", action="store_true")
    parser.add_argument("--solver-case", choices=["plan", "empty_plan", "unsolvable", "syntax_error"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    if args.public_solver:
        summaries = public_solver(args.output, args.solver_case)
        expected_classes = {"plan": "solver_plan", "empty_plan": "solver_empty_plan", "unsolvable": "solver_unsolvable", "syntax_error": "solver_input_error"}
        if not all(row.get("final_classification") == expected_classes[row["case"]] and "exception" not in row for row in summaries):
            raise SystemExit("public solver smoke classifications did not match expectations; inspect evidence")
    if args.deepseek:
        deepseek(args.output)
