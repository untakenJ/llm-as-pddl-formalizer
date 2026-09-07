#!/usr/bin/env python3
"""Execute one Planutils package using its installed service manifest.

This file runs *inside* a long-lived, resource-limited Planutils worker
container.  It deliberately imports Planutils' package registry instead of
duplicating solver command lines.  The generic materialization mirrors the
``tasks.run.package`` path in AI-Planning/planning-as-a-service while avoiding
the Flask/Celery/Redis/MySQL service stack.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _packages() -> dict[str, Any]:
    from planutils.package_installation import PACKAGES

    return PACKAGES


def _service_manifest(package: str, service: str = "solve") -> dict[str, Any]:
    packages = _packages()
    if package not in packages:
        raise ValueError(f"Planutils package is not installed: {package}")
    try:
        manifest = packages[package]["endpoint"]["services"][service]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"Planutils package {package!r} has no {service!r} service"
        ) from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"invalid Planutils service manifest for {package}/{service}")
    return manifest


def _write_argument_files(
    request: dict[str, Any], manifest: dict[str, Any], directory: Path
) -> tuple[str, dict[str, Any]]:
    call = str(manifest["call"])
    materialized: dict[str, Any] = {}
    for row in manifest.get("args", []):
        name = row["name"]
        arg_type = row["type"]
        if name in request:
            value = request[name]
        elif "default" in row:
            value = row["default"]
        else:
            raise ValueError(f"missing required Planutils argument: {name}")
        if arg_type == "file":
            if not isinstance(value, str):
                raise ValueError(f"Planutils file argument {name!r} must be text")
            (directory / name).write_text(value, encoding="utf-8")
            replacement = name
            materialized[name] = {"type": "file", "bytes": len(value.encode())}
        else:
            replacement = str(value)
            materialized[name] = {"type": arg_type, "value": replacement}
        call = call.replace("{%s}" % name, replacement)
    return call, materialized


def _output_spec(manifest: dict[str, Any]) -> tuple[str, str]:
    value = manifest.get("return", {})
    if not isinstance(value, dict):
        raise ValueError("Planutils service return manifest must be an object")
    pattern = value.get("files", value.get("file"))
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("Planutils service return manifest has no file glob")
    output_type = value.get("type", "generic")
    return pattern, str(output_type)


def _read_outputs(directory: Path, pattern: str, output_type: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for raw_path in glob.glob(str(directory / pattern)):
        path = Path(raw_path)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        output[path.name] = json.loads(text) if output_type == "json" else text
    return output


def _terminate_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run_package(request: dict[str, Any]) -> dict[str, Any]:
    package = request.get("solver", "dual-bfws-ffparser")
    timeout_seconds = float(request.get("timeout_seconds", 60))
    if not isinstance(package, str) or not package:
        raise ValueError("solver must be a non-empty package name")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    manifest = _service_manifest(package)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="pddl-local-solver-") as raw_directory:
        directory = Path(raw_directory)
        call, arguments = _write_argument_files(request, manifest, directory)
        tokens = shlex.split(call)
        if not tokens:
            raise ValueError("Planutils service manifest produced an empty command")
        command = ["planutils", "run", tokens[0], "--", *tokens[1:]]
        rendered_call = (
            f"timeout {timeout_seconds:g} "
            + " ".join(shlex.quote(token) for token in command)
        )
        proc = subprocess.Popen(
            command,
            cwd=directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(proc)
            stdout, stderr = proc.communicate()

        pattern, output_type = _output_spec(manifest)
        output = _read_outputs(directory, pattern, output_type)
        result = {
            "stdout": stdout,
            "stderr": stderr,
            "call": rendered_call,
            "output": output,
            "output_type": output_type,
            "local_backend": {
                "schema_version": 1,
                "runner": "planutils-manifest-v1",
                "package": package,
                "process_returncode": proc.returncode,
                "timed_out": timed_out,
                "timeout_seconds": timeout_seconds,
                "duration_seconds": round(time.monotonic() - started, 6),
                "arguments": arguments,
                "output_glob": pattern,
            },
        }
        if timed_out and not result["stdout"]:
            result["stdout"] = "Request Time Out"
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args(argv)
    if args.describe:
        packages = _packages()
        installed = sorted(
            package
            for package, value in packages.items()
            if isinstance(value, dict)
            and "solve" in value.get("endpoint", {}).get("services", {})
        )
        print(json.dumps({"installed_solver_packages": installed}))
        return 0
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        print(json.dumps({"ok": True, "result": run_package(request)}))
        return 0
    except Exception as exc:  # noqa: BLE001 - process boundary diagnostic
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
