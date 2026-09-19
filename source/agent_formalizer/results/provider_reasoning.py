"""Provider reasoning extraction and separate complete readable-output audit.

This module is mounted beside ``model_gateway.py`` in the gateway sidecar.  It
reasoning sink only extracts fields whose provider wire semantics identify
readable reasoning/thinking. Its separate full-trace sink preserves model/tool
text and usage without changing responses delivered to the harness. Neither
sink infers whether the harness parsed or exposed a captured field.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1

# Standard on-demand Vertex Global pricing, verified 2026-09-10. Costs are
# estimates, not billing data; cached tokens are a subset of input tokens and
# OpenAI reasoning tokens are a subset of completion tokens.
GEMINI_FLASH_LITE_PRICING = {
    "model": "gemini-3.1-flash-lite", "currency": "USD", "region": "global",
    "input_per_million": 0.25, "cached_input_per_million": 0.025,
    "output_including_thinking_per_million": 1.50,
    "verified_date": "2026-09-10",
    "source": "https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing",
}


def token_accounting(payload: Any, model: str = "") -> dict[str, Any] | None:
    """Normalize an authoritative usage snapshot, without inventing missing data."""
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usageMetadata") or payload.get("usage_metadata")
    gemini = isinstance(usage, dict)
    if not gemini:
        usage = payload.get("usage")
    if not isinstance(usage, dict) or not usage:
        nested = payload.get("response")
        return token_accounting(nested, model) if isinstance(nested, dict) else None

    def count(*keys, default=None):
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return default

    if gemini:
        input_tokens = count("promptTokenCount", "prompt_token_count")
        cached = count("cachedContentTokenCount", "cached_content_token_count", default=0)
        thinking = count("thoughtsTokenCount", "thoughts_token_count", default=0)
        visible = count("candidatesTokenCount", "candidates_token_count")
        total = count("totalTokenCount", "total_token_count")
        zero_output_derived = (
            visible is None
            and input_tokens is not None
            and total == input_tokens
            and thinking == 0
            and count("toolUsePromptTokenCount", "tool_use_prompt_token_count", default=0) == 0
        )
        if zero_output_derived:
            visible = 0
        output = None if visible is None else visible + thinking
    else:
        input_tokens = count("prompt_tokens", "input_tokens")
        output = count("completion_tokens", "output_tokens")
        total = count("total_tokens")
        zero_output_derived = (
            output is None
            and input_tokens is not None
            and total == input_tokens
        )
        if zero_output_derived:
            output = 0
        input_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        output_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
        cached = input_details.get("cached_tokens", 0)
        thinking = output_details.get("reasoning_tokens")
    result = {
        "input_tokens": input_tokens, "cached_input_tokens": cached,
        "output_tokens_including_thinking": output, "thinking_tokens": thinking,
        "provider_usage": usage, "estimated_cost_usd": None,
        "cost_status": "usage_incomplete_or_model_unpriced",
        "zero_output_derived_from_complete_totals": zero_output_derived,
    }
    resolved_model = model or str(payload.get("modelVersion") or payload.get("model_version") or payload.get("model") or "")
    if ("gemini-3.1-flash-lite" in resolved_model and input_tokens is not None
            and output is not None and isinstance(cached, int)
            and not isinstance(cached, bool) and 0 <= cached <= input_tokens):
        rates = GEMINI_FLASH_LITE_PRICING
        result.update({
            "estimated_cost_usd": ((input_tokens - cached) * rates["input_per_million"]
                                   + cached * rates["cached_input_per_million"]
                                   + output * rates["output_including_thinking_per_million"]) / 1_000_000,
            "cost_status": "estimated_vertex_global_standard_on_demand",
            "pricing": dict(rates),
        })
    return result


def readable_audit_payload(value: Any) -> Any:
    """Keep complete message/tool text; omit credentials and opaque replay blobs.

    This is a separate evidence surface, never the content-free call ledger.
    No HTTP headers or process environment are accepted by this interface.
    """
    if isinstance(value, dict):
        excluded = {"thoughtsignature", "thinking_signature", "thinkingsignature",
                    "textsignature", "encrypted_content", "openclawreasoningreplay",
                    "authorization", "x-goog-api-key", "api_key", "apikey"}
        return {key: ("<opaque-or-secret-field-omitted>" if key.lower() in excluded
                      else readable_audit_payload(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [readable_audit_payload(item) for item in value]
    return value

_PROVIDER_ALIASES = {
    "google": "gemini",
    "google-vertex": "gemini",
}

_EXTRACTOR_IDS = {
    "self-hosted": ["openai-compatible-reasoning-content-v1", "vllm-chat-reasoning-v1"],
    "deepseek": [
        "openai-compatible-reasoning-content-v1",
        "deepseek-responses-reasoning-text-v1",
    ],
    "gemini": [
        "openai-compatible-reasoning-content-v1",
        "gemini-generate-content-thought-part-v1",
        "gemini-interactions-thought-summary-v1",
    ],
}


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalized_reasoning_provider(provider: str) -> str:
    value = str(provider or "").strip().lower()
    return _PROVIDER_ALIASES.get(value, value)


def reasoning_capture_capability(provider: str) -> dict[str, Any]:
    normalized = normalized_reasoning_provider(provider)
    extractors = list(_EXTRACTOR_IDS.get(normalized, []))
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": str(provider or "unknown"),
        "normalized_provider": normalized or "unknown",
        "support": "implemented" if extractors else "not_implemented",
        "extractor_ids": extractors,
        "captures": "provider_response_readable_reasoning_only",
        "agent_visibility": "not_inferred_or_modified",
    }


def _walk_dicts(value: Any, path: str = "$") -> Iterable[tuple[str, dict]]:
    if isinstance(value, dict):
        yield path, value
        for key, nested in value.items():
            yield from _walk_dicts(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk_dicts(nested, f"{path}[{index}]")


def _readable_values(value: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        if value:
            yield path, value
        return
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text:
            yield f"{path}.text", text
        return
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if isinstance(item, str) and item:
            yield item_path, item
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text:
                yield f"{item_path}.text", text


def _explicit_reasoning_fields(payload: Any) -> list[dict[str, str]]:
    """Extract explicit readable fields shared by compatible transports."""
    result: list[dict[str, str]] = []
    for path, item in _walk_dicts(payload):
        for key in ("reasoning_content", "reasoningContent"):
            if key not in item:
                continue
            for source_path, text in _readable_values(item[key], f"{path}.{key}"):
                result.append(
                    {
                        "extractor_id": "openai-compatible-reasoning-content-v1",
                        "source_path": source_path,
                        "text": text,
                    }
                )
    return result


def _deepseek_reasoning(payload: Any) -> list[dict[str, str]]:
    result = _explicit_reasoning_fields(payload)
    if not isinstance(payload, dict):
        return result

    event_type = str(payload.get("type") or "")
    if event_type == "response.reasoning_text.delta":
        delta = payload.get("delta")
        if isinstance(delta, str) and delta:
            result.append(
                {
                    "extractor_id": "deepseek-responses-reasoning-text-v1",
                    "source_path": "$.delta",
                    "text": delta,
                }
            )

    # A streamed ``response.completed`` event may contain a complete nested
    # response after all deltas. Only inspect a top-level non-stream response
    # here so faithful delta capture is not duplicated.
    output = payload.get("output")
    if isinstance(output, list):
        for output_index, item in enumerate(output):
            if not isinstance(item, dict) or item.get("type") != "reasoning":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_index, part in enumerate(content):
                if (
                    not isinstance(part, dict)
                    or part.get("type") != "reasoning_text"
                ):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    result.append(
                        {
                            "extractor_id": (
                                "deepseek-responses-reasoning-text-v1"
                            ),
                            "source_path": (
                                f"$.output[{output_index}].content"
                                f"[{content_index}].text"
                            ),
                            "text": text,
                        }
                    )
    return result


def _gemini_reasoning(payload: Any) -> list[dict[str, str]]:
    result = _explicit_reasoning_fields(payload)
    for path, item in _walk_dicts(payload):
        if item.get("thought") is True:
            text = item.get("text")
            if isinstance(text, str) and text:
                result.append(
                    {
                        "extractor_id": "gemini-generate-content-thought-part-v1",
                        "source_path": f"{path}.text",
                        "text": text,
                    }
                )

    if not isinstance(payload, dict):
        return result

    steps = payload.get("steps")
    if isinstance(steps, list):
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("type") != "thought":
                continue
            for source_path, text in _readable_values(
                step.get("summary"), f"$.steps[{step_index}].summary"
            ):
                result.append(
                    {
                        "extractor_id": "gemini-interactions-thought-summary-v1",
                        "source_path": source_path,
                        "text": text,
                    }
                )

    step = payload.get("step")
    if isinstance(step, dict) and step.get("type") == "thought":
        for source_path, text in _readable_values(
            step.get("summary"), "$.step.summary"
        ):
            result.append(
                {
                    "extractor_id": "gemini-interactions-thought-summary-v1",
                    "source_path": source_path,
                    "text": text,
                }
            )

    delta = payload.get("delta")
    if isinstance(delta, dict) and delta.get("type") == "thought_summary":
        for source_path, text in _readable_values(
            delta.get("content"), "$.delta.content"
        ):
            result.append(
                {
                    "extractor_id": "gemini-interactions-thought-summary-v1",
                    "source_path": source_path,
                    "text": text,
                }
            )
    return result


def _self_hosted_reasoning(payload: Any) -> list[dict[str, str]]:
    # vLLM documents reasoning in choices[].message/delta; older releases use
    # reasoning_content. Never infer arbitrary nested fields to be reasoning.
    # https://docs.vllm.ai/en/latest/features/reasoning_outputs/
    result = _explicit_reasoning_fields(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
        return result
    for index, choice in enumerate(payload["choices"]):
        if not isinstance(choice, dict):
            continue
        for key in ("message", "delta"):
            message = choice.get(key)
            if isinstance(message, dict) and isinstance(message.get("reasoning"), str) and message["reasoning"]:
                result.append({"extractor_id": "vllm-chat-reasoning-v1",
                               "source_path": f"$.choices[{index}].{key}.reasoning", "text": message["reasoning"]})
    return result


_PROVIDER_EXTRACTORS = {
    "self-hosted": _self_hosted_reasoning,
    "deepseek": _deepseek_reasoning,
    "gemini": _gemini_reasoning,
}


def extract_reasoning_fragments(provider: str, payload: Any) -> list[dict[str, str]]:
    """Return exact readable fragments and their response JSON locations."""
    normalized = normalized_reasoning_provider(provider)
    extractor = _PROVIDER_EXTRACTORS.get(normalized)
    if extractor is None:
        return []
    candidates = extractor(payload)

    # Extractors can overlap on compatibility payloads. Preserve the first
    # semantic classification while removing exact path/text duplicates.
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        identity = (candidate["source_path"], candidate["text"])
        if identity in seen:
            continue
        seen.add(identity)
        result.append(candidate)
    return result


class ProviderReasoningRecorder:
    """Append reasoning fragments and maintain a content-free health record."""

    def __init__(
        self,
        provider: str,
        records_path: str | Path | None,
        status_path: str | Path | None,
        *,
        full_trace_path: str | Path | None = None,
    ):
        self.capability = reasoning_capture_capability(provider)
        self.records_path = Path(records_path) if records_path else None
        self.status_path = Path(status_path) if status_path else None
        self.full_trace_path = Path(full_trace_path) if full_trace_path else None
        self._full_records = 0
        self._full_stream = None
        self._last_status_write = 0.0
        self._usage_by_response: dict[tuple[str, Any], dict] = {}
        self._lock = threading.Lock()
        self._fragments = 0
        self._characters = 0
        self._utf8_bytes = 0
        self._boundaries = 0
        self._write_errors = 0
        self._capture_errors = 0
        self._last_error_type: str | None = None
        self._response_fragments: dict[str, tuple[int, int]] = {}
        with self._lock:
            self._write_status_locked()

    @property
    def enabled(self) -> bool:
        return (
            self.capability["support"] == "implemented"
            and self.records_path is not None
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict[str, Any]:
        return {
            **self.capability,
            "persistence": (
                "enabled"
                if self.enabled
                else "not_configured"
                if self.capability["support"] == "implemented"
                else "not_implemented"
            ),
            "records_file": self.records_path.name if self.records_path else None,
            "fragments_captured": self._fragments,
            "characters_captured": self._characters,
            "utf8_bytes_captured": self._utf8_bytes,
            "response_boundaries": self._boundaries,
            "responses_with_reasoning": len(self._response_fragments),
            "write_errors": self._write_errors,
            "capture_errors": self._capture_errors,
            "last_error_type": self._last_error_type,
            "full_trace_file": self.full_trace_path.name if self.full_trace_path else None,
            "full_trace_records": self._full_records,
            "updated_at": _now(),
        }

    def _record_write_error_locked(self, exc: BaseException) -> None:
        self._write_errors += 1
        self._last_error_type = type(exc).__name__

    def record_capture_error(self, exc: BaseException) -> dict[str, int]:
        """Record an extractor/observer failure without affecting delivery."""
        with self._lock:
            write_errors_before = self._write_errors
            self._capture_errors += 1
            self._last_error_type = type(exc).__name__
            self._write_status_locked()
            return {
                "capture_errors": 1,
                "write_errors": self._write_errors - write_errors_before,
            }

    def _write_status_locked(self, *, force: bool = True) -> None:
        if self.status_path is None:
            return
        now = time.monotonic()
        if not force and now - self._last_status_write < 0.25:
            return
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.parent.chmod(0o700)
            # AgentWorkspace pre-creates this host-owned file. Updating it in
            # place preserves ownership when the sidecar itself runs as root,
            # so the benchmark runner can later collect the 0600 artifact.
            self.status_path.write_text(
                json.dumps(self._status_locked(), ensure_ascii=False, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            self.status_path.chmod(0o600)
            self._last_status_write = now
        except OSError as exc:
            self._record_write_error_locked(exc)

    def _append_locked(self, record: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            self.records_path.parent.mkdir(parents=True, exist_ok=True)
            self.records_path.parent.chmod(0o700)
            with self.records_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.records_path.chmod(0o600)
            return True
        except OSError as exc:
            self._record_write_error_locked(exc)
            return False

    @staticmethod
    def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "response_id",
            "logical_call_index",
            "physical_attempt",
            "model",
            "api_path",
            "streaming",
            "payload_sequence",
        }
        return {key: context.get(key) for key in allowed if key in context}

    def _append_full_locked(self, record: dict) -> None:
        if self.full_trace_path is None:
            return
        try:
            if self._full_stream is None:
                self.full_trace_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._full_stream = self.full_trace_path.open("a", encoding="utf-8", buffering=1)
                self.full_trace_path.chmod(0o600)
            self._full_stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._full_records += 1
        except OSError as exc:
            self._record_write_error_locked(exc)

    def capture_request(self, payload: Any, *, context: dict[str, Any]) -> None:
        with self._lock:
            self._append_full_locked({
                "schema_version": 1, "record_type": "harness_request",
                "captured_at": _now(), **self._safe_context(context),
                "payload": readable_audit_payload(payload),
            })

    def capture_payload(
        self, payload: Any, *, context: dict[str, Any]
    ) -> dict[str, int]:
        try:
            fragments = extract_reasoning_fragments(
                self.capability["normalized_provider"], payload
            )
        except Exception as exc:
            return self.record_capture_error(exc)
        written = 0
        characters = 0
        utf8_bytes = 0
        response_id = str(context.get("response_id") or "unknown")
        with self._lock:
            errors_before = self._write_errors
            self._append_full_locked({
                "schema_version": 1, "record_type": "provider_payload",
                "captured_at": _now(), **self._safe_context(context),
                "provider": self.capability["provider"],
                "payload": readable_audit_payload(payload),
            })
            accounting = token_accounting(payload, str(context.get("model") or ""))
            if accounting is not None:
                # Streaming usage is normally cumulative: retain the last
                # snapshot for this physical attempt, never sum its chunks.
                self._usage_by_response[(response_id, context.get("physical_attempt"))] = accounting
            for fragment in fragments:
                text = fragment["text"]
                encoded = text.encode("utf-8")
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "reasoning_fragment",
                    "captured_at": _now(),
                    "provider": self.capability["provider"],
                    "normalized_provider": self.capability["normalized_provider"],
                    **self._safe_context(context),
                    "extractor_id": fragment["extractor_id"],
                    "source_path": fragment["source_path"],
                    "text": text,
                    "text_characters": len(text),
                    "text_utf8_bytes": len(encoded),
                    "text_sha256": hashlib.sha256(encoded).hexdigest(),
                    "agent_visibility": "not_inferred_by_gateway",
                }
                if not self._append_locked(record):
                    continue
                written += 1
                characters += len(text)
                utf8_bytes += len(encoded)
            if written:
                self._fragments += written
                self._characters += characters
                self._utf8_bytes += utf8_bytes
                old_fragments, old_characters = self._response_fragments.get(
                    response_id, (0, 0)
                )
                self._response_fragments[response_id] = (
                    old_fragments + written,
                    old_characters + characters,
                )
            self._write_status_locked(force=False)
            return {
                "fragments": written,
                "characters": characters,
                "utf8_bytes": utf8_bytes,
                "write_errors": self._write_errors - errors_before,
            }

    def record_boundary(
        self,
        *,
        context: dict[str, Any],
        response_complete: bool,
        downstream_state: str,
    ) -> dict[str, int]:
        if self.capability["support"] != "implemented" and self.full_trace_path is None:
            return {"write_errors": 0}
        response_id = str(context.get("response_id") or "unknown")
        with self._lock:
            errors_before = self._write_errors
            fragments, characters = self._response_fragments.get(response_id, (0, 0))
            record = {
                "schema_version": SCHEMA_VERSION,
                "record_type": "response_boundary",
                "captured_at": _now(),
                "provider": self.capability["provider"],
                "normalized_provider": self.capability["normalized_provider"],
                **self._safe_context(context),
                "response_complete": bool(response_complete),
                "downstream_state": downstream_state,
                "reasoning_fragments": fragments,
                "reasoning_characters": characters,
                "agent_visibility": "not_inferred_by_gateway",
            }
            self._append_full_locked({
                **record,
                "token_accounting": self._usage_by_response.pop(
                    (response_id, context.get("physical_attempt")), None),
                "accounting_scope": "physical_attempt_not_logical_call",
            })
            if self._append_locked(record):
                self._boundaries += 1
            self._write_status_locked()
            return {"write_errors": self._write_errors - errors_before}

    def close(self) -> None:
        with self._lock:
            if self._full_stream is not None:
                self._full_stream.close()
                self._full_stream = None

    def __del__(self):
        stream = getattr(self, "_full_stream", None)
        if stream is not None:
            stream.close()
