#!/usr/bin/env python3
"""Fixed-loop runtime for the benchmark-owned Minimum Formalizer Agent.

The control model receives only conversation messages. It never receives a
tool schema and never reads or writes workspace files. This runtime parses each
assistant response, optionally obtains one fixed solver observation before each
reflection, and writes only the final parsed PDDL pair to the official delivery
paths.

The module deliberately uses only the Python standard library so the pinned
benchmark base image is its complete execution runtime.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator


RESPONSE_FIELDS = frozenset({"reasoning", "domain_file", "problem_file"})


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _iter_json_objects(text: str) -> Iterator[dict[str, Any]]:
    decoder = json.JSONDecoder()
    index = text.find("{")
    while index >= 0:
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(value, dict):
                yield value
        index = text.find("{", index + 1)


def parse_response(text: str) -> dict[str, str]:
    """Parse the exact three-field response contract from one model reply."""
    errors: list[str] = []
    for value in _iter_json_objects(text):
        if set(value) != RESPONSE_FIELDS:
            errors.append(
                "JSON object fields were "
                + repr(sorted(value))
                + "; expected "
                + repr(sorted(RESPONSE_FIELDS))
            )
            continue
        if not all(isinstance(value[field], str) for field in RESPONSE_FIELDS):
            errors.append("all response fields must be strings")
            continue
        if not value["reasoning"].strip():
            errors.append("reasoning must be a non-empty string")
            continue
        return {field: value[field] for field in RESPONSE_FIELDS}
    detail = "; ".join(errors[-3:]) if errors else "no JSON object was found"
    raise ValueError(f"response did not satisfy the minimum-agent contract: {detail}")


def _assistant_content(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for item in message:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
    raise ValueError("chat completion did not contain string assistant content")


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            # This placeholder is removed by the benchmark gateway, which
            # injects the real credential from its private sidecar.
            "Authorization": "Bearer benchmark-gateway-placeholder",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {status} from {url}: {raw[:4000]}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"non-JSON HTTP {status} response from {url}: {raw[:4000]}"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"HTTP {status} response must be a JSON object")
    return status, value


def _chat_completion(
    config: dict[str, Any], messages: list[dict[str, str]]
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    url = config["api_base"].rstrip("/") + "/chat/completions"
    _, response = _post_json(
        url,
        {
            "model": config["model"],
            "messages": messages,
            "stream": False,
        },
        timeout_seconds=float(config.get("request_timeout_seconds", 600)),
    )
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("chat completion response is missing choices[0]")
    first = choices[0]
    if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
        raise ValueError("chat completion response is missing choices[0].message")
    content = _assistant_content(first["message"].get("content"))
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return content, usage, response


def _solver_feedback(
    config: dict[str, Any],
    parsed: dict[str, str],
    reflection_index: int,
) -> tuple[str, dict[str, Any]]:
    solver = config["solver_feedback"]
    gateway = config["solver_gateway"].rstrip("/")
    url = gateway + "/solve"
    payload = {
        "domain": parsed["domain_file"],
        "problem": parsed["problem_file"],
        "solver": solver["solver"],
    }
    try:
        status, response = _post_json(
            url,
            payload,
            timeout_seconds=float(config.get("solver_timeout_seconds", 600)),
        )
        record = {
            "event": "fixed_solver_call",
            "reflection_index": reflection_index,
            "timestamp": _now(),
            "solver": solver["solver"],
            "http_status": status,
            "ok": bool(response.get("ok")),
            "input": {
                "domain_file": parsed["domain_file"],
                "problem_file": parsed["problem_file"],
                "domain_sha256": _sha256_text(parsed["domain_file"]),
                "problem_sha256": _sha256_text(parsed["problem_file"]),
            },
            "response": response,
        }
    except Exception as exc:  # solver failure remains model-visible feedback
        record = {
            "event": "fixed_solver_call",
            "reflection_index": reflection_index,
            "timestamp": _now(),
            "solver": solver["solver"],
            "http_status": None,
            "ok": False,
            "input": {
                "domain_file": parsed["domain_file"],
                "problem_file": parsed["problem_file"],
                "domain_sha256": _sha256_text(parsed["domain_file"]),
                "problem_sha256": _sha256_text(parsed["problem_file"]),
            },
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    rendered = json.dumps(
        {
            key: value
            for key, value in record.items()
            if key not in {"event", "timestamp", "input"}
        },
        indent=2,
        ensure_ascii=False,
    )
    limit = int(solver["max_chars"])
    if len(rendered) > limit:
        removed = len(rendered) - limit
        rendered = rendered[:limit] + f"\n... solver feedback truncated by {removed} chars"
        record["feedback_truncated_chars"] = removed
    feedback = (
        f"<solver_feedback reflection=\"{reflection_index}\">\n"
        f"{rendered}\n"
        "</solver_feedback>"
    )
    record["conversation_feedback"] = feedback
    return feedback, record


def _usage_totals(events: list[dict[str, Any]]) -> dict[str, int]:
    result = {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "total": 0,
        "reasoningTokens": 0,
    }
    for event in events:
        if event.get("event") != "model_call":
            continue
        usage = event.get("usage") or {}
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        prompt_details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        cached = int(prompt_details.get("cached_tokens", 0) or 0)
        reasoning = int(completion_details.get("reasoning_tokens", 0) or 0)
        result["input"] += max(0, prompt - cached)
        result["cacheRead"] += cached
        result["output"] += completion
        result["reasoningTokens"] += reasoning
        result["total"] += int(
            usage.get("total_tokens", prompt + completion) or prompt + completion
        )
    return result


def _render_template(template: str, config: dict[str, Any], **extra: Any) -> str:
    values = {
        "reflection_count": int(config["reflection_count"]),
        "solver_feedback_enabled": str(
            bool(config["solver_feedback"]["enabled"])
        ).lower(),
        **extra,
    }
    return template.format(**values)


def _validate_output_path(value: str, output_root: str = "/workspace") -> Path:
    path = Path(value)
    workspace = Path(output_root).resolve()
    try:
        path.resolve().relative_to(workspace)
    except ValueError as exc:
        raise ValueError(
            f"official output must remain under configured output root: {path}"
        ) from exc
    if path.parent.resolve() != workspace:
        raise ValueError(
            f"official output must be a direct child of configured output root: {path}"
        )
    return path


def execute(config: dict[str, Any]) -> dict[str, Any]:
    """Execute one initial generation and exactly n fixed reflection calls."""
    transcript_path = Path(config["transcript_path"])
    output_root = config.get("output_root", "/workspace")
    if "output_root" in config:
        domain_path = _validate_output_path(config["domain_output_path"], output_root)
        problem_path = _validate_output_path(config["problem_output_path"], output_root)
    else:  # Backward-compatible container/default contract and test patch point.
        domain_path = _validate_output_path(config["domain_output_path"])
        problem_path = _validate_output_path(config["problem_output_path"])
    if "output_root" in config:
        Path(output_root).mkdir(parents=True, exist_ok=True)
    for path in (domain_path, problem_path):
        path.unlink(missing_ok=True)

    transcript: dict[str, Any] = {
        "schema_version": 1,
        "adapter": "minimum",
        "status": "running",
        "started_at": _now(),
        "model": config["model"],
        "wire_protocol": "openai_chat_completions",
        "reflection_count_requested": int(config["reflection_count"]),
        "solver_feedback": copy.deepcopy(config["solver_feedback"]),
        "events": [],
        "messages": [],
    }
    messages: list[dict[str, str]] = [
        {"role": "user", "content": config["initial_prompt"]}
    ]
    latest: dict[str, str] | None = None

    def save() -> None:
        transcript["messages"] = copy.deepcopy(messages)
        transcript["usage"] = _usage_totals(transcript["events"])
        transcript["model_calls_completed"] = sum(
            event.get("event") == "model_call" for event in transcript["events"]
        )
        transcript["fixed_solver_calls_completed"] = sum(
            event.get("event") == "fixed_solver_call"
            for event in transcript["events"]
        )
        _atomic_json(transcript_path, transcript)

    try:
        total_calls = int(config["reflection_count"]) + 1
        for call_index in range(1, total_calls + 1):
            phase = "initial" if call_index == 1 else "reflection"
            reflection_index = max(0, call_index - 1)
            if reflection_index:
                user_parts: list[str] = []
                if bool(config["solver_feedback"]["enabled"]):
                    assert latest is not None
                    feedback, solver_event = _solver_feedback(
                        config, latest, reflection_index
                    )
                    transcript["events"].append(solver_event)
                    user_parts.append(feedback)
                user_parts.append(
                    _render_template(
                        config["reflection_prompt"],
                        config,
                        reflection_index=reflection_index,
                    )
                )
                messages.append({"role": "user", "content": "\n\n".join(user_parts)})
                save()

            request_messages = copy.deepcopy(messages)
            content, usage, provider_response = _chat_completion(config, messages)
            parsed = parse_response(content)
            event = {
                "event": "model_call",
                "logical_call_index": call_index,
                "phase": phase,
                "reflection_index": reflection_index,
                "timestamp": _now(),
                "request_messages": request_messages,
                "response_text": content,
                "response_sha256": _sha256_text(content),
                "parsed": parsed,
                "usage": usage,
                "provider_response": provider_response,
            }
            transcript["events"].append(event)
            messages.append({"role": "assistant", "content": content})
            latest = parsed
            save()

        assert latest is not None
        try:
            _atomic_text(domain_path, latest["domain_file"])
            _atomic_text(problem_path, latest["problem_file"])
        except Exception:
            domain_path.unlink(missing_ok=True)
            problem_path.unlink(missing_ok=True)
            raise

        transcript["status"] = "ok"
        transcript["finished_at"] = _now()
        transcript["final_response_logical_call_index"] = total_calls
        transcript["official_delivery"] = {
            "domain_path": str(domain_path),
            "problem_path": str(problem_path),
            "domain_sha256": _sha256_text(latest["domain_file"]),
            "problem_sha256": _sha256_text(latest["problem_file"]),
            "source": "last_parsed_model_response",
        }
        save()
        return transcript
    except Exception as exc:
        transcript["status"] = "failed"
        transcript["finished_at"] = _now()
        transcript["error_type"] = type(exc).__name__
        transcript["error"] = str(exc)
        save()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    transcript = execute(config)
    print(
        json.dumps(
            {
                "status": transcript["status"],
                "model_calls": transcript["model_calls_completed"],
                "fixed_solver_calls": transcript["fixed_solver_calls_completed"],
                "transcript_path": config["transcript_path"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
