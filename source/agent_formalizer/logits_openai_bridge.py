#!/usr/bin/env python3
"""OpenAI Chat Completions compatibility for the Logits sampling REST API.

This is the permanent form of the adapter validated by campaign
``20260823-131746``.  Provider availability is discovered from Logits at
runtime; this module does not keep a static supported-model list.  Wire-format
details that genuinely vary by model family live in an explicit convention
registry.  Qwen3.5 is the first registered convention, and additional model
families can be added without changing provider or harness routing.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


DEFAULT_LOGITS_ORIGIN = "https://api.logits.dev"
LOGITS_PROTOCOL_VERSION = "0.21.0"
MAX_REQUEST_BYTES = 16 * 1024 * 1024
DEFAULT_MODEL_ASSETS_ROOT = (
    Path(__file__).resolve().parents[2]
    / ".cache"
    / "harness-runtimes"
    / "logits-bridge"
    / "models"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def upstream_model_id(model: str) -> str:
    """Return the explicit Logits model id without imposing a model list."""
    value = str(model).strip()
    if value.startswith("logits/"):
        value = value.split("/", 1)[1]
    if not value:
        raise ValueError(
            "Logits models must use an explicit provider model id, for example "
            "logits/Qwen/Qwen3.5-4B"
        )
    return value


class UpstreamError(RuntimeError):
    def __init__(self, status: int, detail: str, *, retry_after: str | None = None):
        super().__init__(detail)
        self.status = status
        self.status_code = status
        self.detail = detail
        self.retry_after = retry_after


class ModelOutputError(RuntimeError):
    """The sampled output did not satisfy the requested response convention."""


class JsonlLedger:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **fields: Any) -> None:
        if not self.path:
            return
        row = {"event": event, "ts": utc_now(), **fields}
        encoded = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with self.lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)


@dataclass(frozen=True)
class ModelConvention:
    id: str
    model_pattern: re.Pattern[str]
    tokenizer_revision: str
    chat_template_sha256: str
    render_kwargs: dict[str, Any]
    response_parser: Callable[[str, list[dict[str, Any]]], tuple[str, str, list[dict[str, Any]]]]

    def matches(self, model: str) -> bool:
        return bool(self.model_pattern.fullmatch(model))

    def asset_dir(self, model: str, root: Path) -> Path:
        return root / model.replace("/", "--") / self.tokenizer_revision


_MODEL_CONVENTIONS: list[ModelConvention] = []


def register_model_convention(convention: ModelConvention) -> None:
    """Register a model-family convention; newest registrations take priority."""
    if any(item.id == convention.id for item in _MODEL_CONVENTIONS):
        raise ValueError(f"duplicate Logits model convention: {convention.id}")
    _MODEL_CONVENTIONS.insert(0, convention)


def resolve_model_convention(model: str) -> ModelConvention:
    resolved = upstream_model_id(model)
    for convention in _MODEL_CONVENTIONS:
        if convention.matches(resolved):
            return convention
    raise ValueError(
        f"Logits currently advertises model {resolved!r}, but this benchmark has "
        "no audited chat/tool convention for its model family. Add and validate "
        "a ModelConvention instead of treating it as Qwen3.5."
    )


def normalize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and item.get("type") in {
                "text",
                "input_text",
                "output_text",
            }:
                pieces.append(str(item.get("text", "")))
        return "\n".join(pieces)
    return str(content)


def normalize_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    system_parts: list[str] = []
    normalized: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, dict):
            raise ValueError("every message must be an object")
        role = str(raw.get("role", ""))
        content = normalize_content(raw.get("content"))
        if role in {"system", "developer"}:
            system_parts.append(content)
            continue
        if role not in {"user", "assistant", "tool"}:
            raise ValueError(f"unsupported message role: {role}")
        row: dict[str, Any] = {"role": role, "content": content}
        if role == "assistant":
            if isinstance(raw.get("reasoning_content"), str):
                row["reasoning_content"] = raw["reasoning_content"]
            calls = []
            for call in raw.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function", call)
                if not isinstance(function, dict) or not function.get("name"):
                    continue
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                calls.append(
                    {
                        "function": {
                            "name": str(function["name"]),
                            "arguments": arguments if isinstance(arguments, dict) else {},
                        }
                    }
                )
            if calls:
                row["tool_calls"] = calls
        if role == "tool":
            if raw.get("tool_call_id") is not None:
                row["tool_call_id"] = str(raw["tool_call_id"])
            if raw.get("name") is not None:
                row["name"] = str(raw["name"])
        normalized.append(row)
    if system_parts:
        normalized.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})
    if not any(row["role"] == "user" for row in normalized):
        raise ValueError("messages contain no user message")
    return normalized


def sampling_params_from_request(body: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "temperature": float(body.get("temperature", 1.0)),
        "top_k": int(body.get("top_k", -1)),
        "top_p": float(body.get("top_p", 1.0)),
    }
    max_tokens = body.get("max_completion_tokens", body.get("max_tokens"))
    if max_tokens is not None:
        params["max_tokens"] = int(max_tokens)
    if body.get("seed") is not None:
        params["seed"] = int(body["seed"])
    stop = body.get("stop")
    if isinstance(stop, str) or (
        isinstance(stop, list) and all(isinstance(item, str) for item in stop)
    ):
        params["stop"] = stop
    return params


TOOL_BLOCK_RE = re.compile(
    r"<tool_call>\s*<function=([^>\s]+)>\s*(.*?)\s*</function>\s*</tool_call>",
    re.S,
)
PARAM_RE = re.compile(r"<parameter=([^>]+)>\s*(.*?)\s*</parameter>", re.S)


def _schema_for_tool(tools: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for tool in tools:
        function = tool.get("function", {}) if isinstance(tool, dict) else {}
        if function.get("name") == name:
            params = function.get("parameters", {})
            return params if isinstance(params, dict) else {}
    return {}


def _coerce_argument(raw: str, schema: dict[str, Any]) -> Any:
    value = raw.strip()
    expected = schema.get("type")
    if expected == "string" or not expected:
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        if expected == "integer":
            return int(value)
        if expected == "number":
            return float(value)
        if expected == "boolean" and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        return value


def parse_qwen35_response(
    raw: str, tools: list[dict[str, Any]]
) -> tuple[str, str, list[dict[str, Any]]]:
    text = raw.replace("<|im_end|>", "").strip()
    reasoning = ""
    answer = text
    if "</think>" in text:
        reasoning, answer = text.split("</think>", 1)
        reasoning = reasoning.removeprefix("<think>").strip()
    elif text.startswith("<think>"):
        answer = text.removeprefix("<think>").strip()
    calls: list[dict[str, Any]] = []
    for index, match in enumerate(TOOL_BLOCK_RE.finditer(answer)):
        name = match.group(1)
        properties = _schema_for_tool(tools, name).get("properties", {})
        arguments: dict[str, Any] = {}
        for param in PARAM_RE.finditer(match.group(2)):
            key = param.group(1).strip()
            schema = properties.get(key, {}) if isinstance(properties, dict) else {}
            arguments[key] = _coerce_argument(
                param.group(2), schema if isinstance(schema, dict) else {}
            )
        calls.append(
            {
                "index": index,
                "id": f"call_{secrets.token_hex(12)}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(
                        arguments, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            }
        )
    return reasoning, TOOL_BLOCK_RE.sub("", answer).strip(), calls


register_model_convention(
    ModelConvention(
        id="qwen3.5-chat-tools-v1",
        model_pattern=re.compile(r"Qwen/Qwen3\.5-[A-Za-z0-9._-]+"),
        tokenizer_revision="851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
        chat_template_sha256=(
            "a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715"
        ),
        render_kwargs={"enable_thinking": True},
        response_parser=parse_qwen35_response,
    )
)


def load_tokenizer(
    model: str,
    convention: ModelConvention,
    *,
    assets_root: Path = DEFAULT_MODEL_ASSETS_ROOT,
):
    """Load only locked local tokenizer assets; benchmark runs never download."""
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Logits support requires the locked logits bridge runtime; run "
            "source/agent_formalizer/install_harnesses.sh logits"
        ) from exc
    asset_dir = convention.asset_dir(model, Path(assets_root))
    if not asset_dir.is_dir():
        raise RuntimeError(
            f"locked tokenizer assets are missing for {model}: {asset_dir}. "
            "Run source/agent_formalizer/install_harnesses.sh logits."
        )
    tokenizer = AutoTokenizer.from_pretrained(asset_dir, local_files_only=True)
    template_sha = hashlib.sha256((tokenizer.chat_template or "").encode()).hexdigest()
    if template_sha != convention.chat_template_sha256:
        raise RuntimeError(
            f"unexpected {model} chat template sha256: {template_sha}"
        )
    return tokenizer


class LogitsRestSampler:
    """Small direct client for the public protocol, including HTTP 410 recovery."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        ledger: JsonlLedger,
        origin: str = DEFAULT_LOGITS_ORIGIN,
        http_client=None,
    ):
        self.model = upstream_model_id(model)
        self.api_key = api_key
        self.ledger = ledger
        if http_client is None:
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("Logits REST transport requires httpx") from exc
            http_client = httpx.Client(
                base_url=origin.rstrip("/"),
                headers={"X-API-Key": api_key},
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
            )
        self.http = http_client
        self.origin = origin.rstrip("/")
        self.seq_lock = threading.Lock()
        self.sample_lock = threading.Lock()
        self.session_lock = threading.RLock()
        self.closed = threading.Event()
        self.seq_id = 0
        self.session_generation = 0
        self.session_id = ""
        self.sampling_session_id = ""
        self._initialize()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="logits-session-heartbeat",
            daemon=True,
        )
        self.heartbeat_thread.start()

    def _json_response(self, response, path: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise UpstreamError(
                response.status_code,
                f"Logits {path} returned HTTP {response.status_code}: {response.text[:2000]}",
                retry_after=response.headers.get("retry-after"),
            )
        try:
            value = response.json()
        except ValueError as exc:
            raise UpstreamError(502, f"Logits {path} returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise UpstreamError(502, f"Logits {path} returned a non-object JSON value")
        return value

    def _post(
        self, path: str, body: dict[str, Any], *, timeout: float = 60.0
    ) -> dict[str, Any]:
        try:
            response = self.http.post(path, json=body, timeout=timeout)
        except Exception as exc:
            name = type(exc).__name__
            if "Timeout" in name:
                raise UpstreamError(504, f"Logits {path} timed out") from exc
            raise UpstreamError(503, f"Logits {path} transport failure: {name}") from exc
        return self._json_response(response, path)

    def _initialize(self) -> None:
        response = self.http.get("/api/v1/get_server_capabilities", timeout=30.0)
        capabilities = self._json_response(response, "/api/v1/get_server_capabilities")
        supported = sorted(
            {
                row.get("model_name")
                for row in capabilities.get("supported_models", [])
                if isinstance(row, dict) and row.get("model_name")
            }
        )
        if self.model not in supported:
            raise RuntimeError(
                f"{self.model} is not in the authenticated Logits capabilities; "
                f"advertised models: {supported}"
            )
        self._renew_session("bridge_start")
        self.ledger.emit(
            "bridge_ready",
            model=self.model,
            logits_origin=self.origin,
            protocol_version=LOGITS_PROTOCOL_VERSION,
            supported_models=supported,
            session_generation=self.session_generation,
        )

    def _renew_session(self, reason: str) -> None:
        with self.session_lock:
            session = self._post(
                "/api/v1/create_session",
                {
                    "tags": ["pddl-formalizer", "per-attempt-gateway"],
                    "user_metadata": {
                        "adapter": "logits-rest-openai-v1",
                        "model": self.model,
                    },
                    "sdk_version": LOGITS_PROTOCOL_VERSION,
                    "type": "create_session",
                },
            )
            session_id = str(session["session_id"])
            sampling = self._post(
                "/api/v1/create_sampling_session",
                {
                    "session_id": session_id,
                    "sampling_session_seq_id": 0,
                    "base_model": self.model,
                    "type": "create_sampling_session",
                },
            )
            self.session_id = session_id
            self.sampling_session_id = str(sampling["sampling_session_id"])
            self.session_generation += 1
            with self.seq_lock:
                self.seq_id = 0
            self.ledger.emit(
                "session_ready",
                reason=reason,
                session_generation=self.session_generation,
            )

    def _heartbeat_loop(self) -> None:
        while not self.closed.wait(30.0):
            try:
                self._post(
                    "/api/v1/session_heartbeat",
                    {"session_id": self.session_id, "type": "session_heartbeat"},
                    timeout=30.0,
                )
            except UpstreamError as exc:
                if exc.status == 410:
                    with self.sample_lock:
                        self._renew_session("heartbeat_http_410")
                else:
                    self.ledger.emit("heartbeat_error", error_message=str(exc))
            except Exception as exc:
                if not self.closed.is_set():
                    self.ledger.emit("heartbeat_error", error_message=str(exc))

    def _next_seq_id(self) -> int:
        with self.seq_lock:
            value = self.seq_id
            self.seq_id += 1
            return value

    def _sample_once(
        self, prompt_tokens: list[int], sampling_params: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        seq_id = self._next_seq_id()
        future = self._post(
            "/api/v1/asample",
            {
                "num_samples": 1,
                "prompt": {
                    "chunks": [{"type": "encoded_text", "tokens": prompt_tokens}]
                },
                "sampling_params": sampling_params,
                "sampling_session_id": self.sampling_session_id,
                "seq_id": seq_id,
                "prompt_logprobs": False,
                "topk_prompt_logprobs": 0,
                "type": "sample",
            },
        )
        request_id = future.get("request_id")
        if not request_id:
            raise UpstreamError(502, "Logits asample omitted request_id")
        deadline = time.monotonic() + 1800.0
        iteration = 0
        while time.monotonic() < deadline:
            try:
                response = self.http.post(
                    "/api/v1/retrieve_future",
                    json={"request_id": request_id, "allow_metadata_only": False},
                    headers={
                        "X-Tinker-Request-Type": "Sample",
                        "X-Tinker-Request-Iteration": str(iteration),
                    },
                    timeout=60.0,
                )
            except Exception as exc:
                if "Timeout" in type(exc).__name__:
                    iteration += 1
                    continue
                raise UpstreamError(
                    503,
                    f"Logits retrieve transport failure: {type(exc).__name__}",
                ) from exc
            if response.status_code == 408:
                iteration += 1
                continue
            payload = self._json_response(response, "/api/v1/retrieve_future")
            if payload.get("type") == "try_again":
                retry_after = response.headers.get("retry-after")
                try:
                    delay = min(float(retry_after), 10.0) if retry_after else 1.0
                except ValueError:
                    delay = 1.0
                time.sleep(max(0.0, delay))
                iteration += 1
                continue
            if "error" in payload:
                raise UpstreamError(502, f"Logits sample failed: {payload['error']}")
            if not isinstance(payload.get("sequences"), list) or not payload["sequences"]:
                raise UpstreamError(502, "Logits sample response omitted sequences")
            return payload, seq_id
        raise UpstreamError(504, f"Logits sample timed out after 1800s: {request_id}")

    def sample(
        self, prompt_tokens: list[int], sampling_params: dict[str, Any]
    ) -> tuple[dict[str, Any], int, int]:
        started = time.monotonic()
        with self.sample_lock:
            recoveries = 0
            while True:
                try:
                    payload, seq_id = self._sample_once(prompt_tokens, sampling_params)
                    return payload, seq_id, int((time.monotonic() - started) * 1000)
                except UpstreamError as exc:
                    if exc.status != 410:
                        raise
                    recoveries += 1
                    self.ledger.emit(
                        "session_expired",
                        source="sample",
                        recovery_index=recoveries,
                        error_message=exc.detail,
                    )
                    self._renew_session("sample_http_410")
                    self.ledger.emit(
                        "logical_sample_replayed", recovery_index=recoveries
                    )

    def close(self) -> None:
        self.closed.set()
        close = getattr(self.http, "close", None)
        if callable(close):
            close()


def validate_structured_value(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    checks = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected in checks and not checks[expected]:
        raise ValueError(f"{path} must have type {expected}")
    if expected == "object":
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise ValueError(f"{path} is missing required keys: {missing}")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ValueError(f"{path} has unexpected keys: {extras}")
        for key, child in value.items():
            child_schema = properties.get(key) if isinstance(properties, dict) else None
            if isinstance(child_schema, dict):
                validate_structured_value(child, child_schema, f"{path}.{key}")
    if expected == "array" and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            validate_structured_value(child, schema["items"], f"{path}[{index}]")


def _structured_json(
    answer: str, calls: list[dict[str, Any]], schema: dict[str, Any]
) -> str:
    value: Any = None
    for call in calls:
        if call.get("function", {}).get("name") == "submit_json_response":
            value = json.loads(call["function"]["arguments"])
            break
    if value is None:
        candidate = answer.strip()
        if candidate.startswith("```json") and candidate.endswith("```"):
            candidate = candidate[7:-3].strip()
        value = json.loads(candidate)
    validate_structured_value(value, schema)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class LogitsChatBackend:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        ledger: JsonlLedger,
        assets_root: Path = DEFAULT_MODEL_ASSETS_ROOT,
        origin: str = DEFAULT_LOGITS_ORIGIN,
        tokenizer=None,
        sampler: LogitsRestSampler | None = None,
    ):
        self.model = upstream_model_id(model)
        self.convention = resolve_model_convention(self.model)
        self.tokenizer = tokenizer or load_tokenizer(
            self.model, self.convention, assets_root=assets_root
        )
        self.ledger = ledger
        self.sampler = sampler or LogitsRestSampler(
            model=self.model, api_key=api_key, ledger=ledger, origin=origin
        )

    def chat_completion(self, body: dict[str, Any]) -> dict[str, Any]:
        requested_model = str(body.get("model", ""))
        if upstream_model_id(requested_model) != self.model:
            raise ValueError(f"unsupported model for this fixed route: {requested_model}")
        messages = normalize_messages(body.get("messages"))
        tools = body.get("tools") or []
        if not isinstance(tools, list):
            raise ValueError("tools must be an array")
        structured_schema = body.get("logits_json_schema")
        render_tools = tools
        if structured_schema is not None:
            if not isinstance(structured_schema, dict):
                raise ValueError("logits_json_schema must be an object")
            if tools:
                raise ValueError("logits_json_schema cannot be combined with external tools")
            render_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "submit_json_response",
                        "description": "Submit the final response exactly once.",
                        "parameters": structured_schema,
                    },
                }
            ]
            instruction = (
                "For the final answer, you MUST call submit_json_response exactly "
                "once with arguments satisfying its schema."
            )
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n\n" + instruction
            else:
                messages.insert(0, {"role": "system", "content": instruction})
        rendered = self.tokenizer.apply_chat_template(
            messages,
            tools=render_tools or None,
            tokenize=False,
            add_generation_prompt=True,
            **self.convention.render_kwargs,
        )
        prompt_tokens = self.tokenizer.encode(rendered, add_special_tokens=False)
        response, seq_id, upstream_duration_ms = self.sampler.sample(
            prompt_tokens, sampling_params_from_request(body)
        )
        sequence = response["sequences"][0]
        completion_tokens = sequence.get("tokens", [])
        raw = self.tokenizer.decode(completion_tokens, skip_special_tokens=False)
        reasoning, content, calls = self.convention.response_parser(raw, render_tools)
        if structured_schema is not None:
            try:
                content = _structured_json(content, calls, structured_schema)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ModelOutputError(
                    f"Logits structured response validation failed: {exc}"
                ) from exc
            calls = []
        message: dict[str, Any] = {"role": "assistant", "content": content or None}
        if reasoning:
            message["reasoning_content"] = reasoning
        if calls:
            message["tool_calls"] = [
                {key: value for key, value in call.items() if key != "index"}
                for call in calls
            ]
        payload = {
            "id": f"chatcmpl-logits-{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": requested_model,
            "system_fingerprint": f"logits-rest-openai-v1:{self.convention.id}",
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if calls else "stop",
                    "logprobs": None,
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt_tokens),
                "completion_tokens": len(completion_tokens),
                "total_tokens": len(prompt_tokens) + len(completion_tokens),
            },
        }
        self.ledger.emit(
            "chat_completion",
            model=self.model,
            convention=self.convention.id,
            prompt_tokens=len(prompt_tokens),
            completion_tokens=len(completion_tokens),
            finish_reason=payload["choices"][0]["finish_reason"],
            tool_calls=len(calls),
            logits_stop_reason=sequence.get("stop_reason"),
            sampling_seq_id=seq_id,
            upstream_duration_ms=upstream_duration_ms,
        )
        return payload

    def close(self) -> None:
        self.sampler.close()


def sse_from_completion(payload: dict[str, Any]) -> bytes:
    choice = payload["choices"][0]
    message = choice["message"]
    base = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "system_fingerprint": payload["system_fingerprint"],
    }
    delta = {key: value for key, value in message.items() if value is not None}
    content = {
        **base,
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }
    finish = {
        **base,
        "choices": [
            {"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}
        ],
        "usage": payload["usage"],
    }
    return (
        "data: "
        + json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        + "\n\ndata: "
        + json.dumps(finish, ensure_ascii=False, separators=(",", ":"))
        + "\n\ndata: [DONE]\n\n"
    ).encode()


class BridgeService:
    def __init__(self, backend: LogitsChatBackend, api_key: str, ledger: JsonlLedger):
        self.backend = backend
        self.api_key = api_key
        self.ledger = ledger

    def handler_class(self):
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "LogitsOpenAIBridge/2"
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _authorized(self) -> bool:
                bearer = self.headers.get("Authorization", "")
                x_api_key = self.headers.get("X-API-Key", "")
                supplied = bearer[7:] if bearer.lower().startswith("bearer ") else x_api_key
                return bool(supplied) and secrets.compare_digest(supplied, service.api_key)

            def _write(self, status: int, payload: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
                self.close_connection = True

            def _json(self, status: int, value: dict[str, Any]) -> None:
                self._write(
                    status,
                    json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(),
                    "application/json",
                )

            def _error(self, status: int, message: str, kind: str) -> None:
                self._json(
                    status,
                    {"error": {"message": message, "type": kind, "code": status}},
                )

            def do_GET(self) -> None:
                if self.path == "/healthz":
                    self._json(
                        200,
                        {
                            "status": "ok",
                            "model": service.backend.model,
                            "convention": service.backend.convention.id,
                        },
                    )
                    return
                if not self._authorized():
                    self._error(401, "invalid bridge credential", "authentication_error")
                    return
                if self.path.rstrip("/") == "/v1/models":
                    self._json(
                        200,
                        {
                            "object": "list",
                            "data": [
                                {
                                    "id": service.backend.model,
                                    "object": "model",
                                    "created": int(time.time()),
                                    "owned_by": "logits",
                                }
                            ],
                        },
                    )
                    return
                self._error(404, "route not found", "not_found")

            def do_POST(self) -> None:
                if not self._authorized():
                    self._error(401, "invalid bridge credential", "authentication_error")
                    return
                if self.path.rstrip("/") != "/v1/chat/completions":
                    self._error(404, "route not found", "not_found")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > MAX_REQUEST_BYTES:
                        raise ValueError("invalid request Content-Length")
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError("request body must be an object")
                    payload = service.backend.chat_completion(body)
                    if body.get("stream") is True:
                        self._write(200, sse_from_completion(payload), "text/event-stream")
                    else:
                        self._json(200, payload)
                except ValueError as exc:
                    self._error(400, str(exc), "invalid_request_error")
                except ModelOutputError as exc:
                    self._error(422, str(exc), "invalid_model_output")
                except UpstreamError as exc:
                    status = exc.status if exc.status in {408, 429, 502, 503, 504, 529} else 502
                    self._error(status, exc.detail, "upstream_error")
                except Exception as exc:
                    service.ledger.emit(
                        "internal_error",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                    self._error(500, f"bridge internal error: {type(exc).__name__}", "bridge_internal_error")

        return Handler


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_bridge_server(
    *,
    bind: str,
    port: int,
    model: str,
    api_key: str,
    ledger_path: Path | None,
    assets_root: Path = DEFAULT_MODEL_ASSETS_ROOT,
    origin: str = DEFAULT_LOGITS_ORIGIN,
) -> tuple[ReusableThreadingHTTPServer, LogitsChatBackend, threading.Thread]:
    ledger = JsonlLedger(ledger_path)
    backend = LogitsChatBackend(
        model=model,
        api_key=api_key,
        ledger=ledger,
        assets_root=assets_root,
        origin=origin,
    )
    service = BridgeService(backend, api_key, ledger)
    server = ReusableThreadingHTTPServer((bind, int(port)), service.handler_class())
    thread = threading.Thread(target=server.serve_forever, name="logits-bridge", daemon=True)
    thread.start()
    ledger.emit(
        "listener_ready",
        listener=f"http://{bind}:{port}",
        model=backend.model,
        convention=backend.convention.id,
    )
    return server, backend, thread
