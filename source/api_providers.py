"""LLM API backends for the *-api formalizer/planner scripts.

- **OpenAI**: Responses API (``client.responses.create``) with optional hosted tools.
- **Gemini**: Google GenAI SDK (``google.genai``) with JSON-schema structured output.

API keys (under ``_private/``, gitignored):

- OpenAI: ``key.txt`` (existing)
- Gemini: ``key_gemini.txt`` (new), or env ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``
"""

from __future__ import annotations

import datetime
import json
import os
import time

from openai import OpenAI

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OPENAI_API_MODELS = [
    "gpt-3.5-turbo",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.1",
    "gpt-5.1-mini",
    "gpt-5.2",
    "gpt-5.2-mini",
    "gpt-5.3",
    "gpt-5.3-mini",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-5.5-mini",
]

GEMINI_API_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

API_MODELS = OPENAI_API_MODELS + GEMINI_API_MODELS

REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")

OPENAI_TOOLS = [
    {"type": "web_search"},
    {"type": "code_interpreter", "container": {"type": "auto"}},
]

OPENAI_TOOL_EXECUTORS: dict = {}


def is_gemini_model(model: str) -> bool:
    return model.startswith("gemini-") or model in GEMINI_API_MODELS


def is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in REASONING_PREFIXES)


def default_tools_for_model(model: str) -> tuple[list | None, dict | None]:
    """Return ``(tools, tool_executors)`` for OpenAI models; ``(None, None)`` for Gemini."""
    if is_gemini_model(model):
        return None, None
    executors = OPENAI_TOOL_EXECUTORS or None
    return OPENAI_TOOLS, executors


def _read_key_file(filename: str) -> str:
    path = os.path.join(ROOT_DIR, "_private", filename)
    if not os.path.exists(path):
        raise SystemExit(
            f"API key file not found: {path}\n"
            f"Create it with your key (one line, no quotes)."
        )
    return open(path).read().strip()


def read_gemini_api_key() -> str:
    gemini_path = os.path.join(ROOT_DIR, "_private", "key_gemini.txt")
    if os.path.exists(gemini_path):
        return open(gemini_path).read().strip()
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    raise SystemExit(
        "Gemini API key not found. Create _private/key_gemini.txt "
        "or set GEMINI_API_KEY / GOOGLE_API_KEY."
    )


def build_provider_client(model: str) -> tuple[str, object]:
    """Return ``(provider_name, client)`` where provider is ``openai`` or ``gemini``."""
    if is_gemini_model(model):
        from google import genai

        return "gemini", genai.Client(api_key=read_gemini_api_key())
    return "openai", OpenAI(api_key=_read_key_file("key.txt"))


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _serialize_response(resp) -> dict:
    if hasattr(resp, "model_dump"):
        return resp.model_dump(mode="json", exclude_none=True)
    if hasattr(resp, "to_dict"):
        return resp.to_dict()
    return {"_repr": repr(resp)}


class Tracer:
    """Append-only JSONL writer. No-ops when ``path`` is None."""

    def __init__(self, path):
        self.path = path
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._fp = open(path, "w", buffering=1)
        else:
            self._fp = None

    def emit(self, event: str, **fields):
        if self._fp is None:
            return
        rec = {"event": event, "ts": _now(), **fields}
        self._fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def close(self):
        if self._fp is not None:
            self._fp.close()
            self._fp = None


def _prompt_from_input_items(input_items: list) -> str:
    parts = []
    for item in input_items:
        role = item.get("role", "user")
        content = item.get("content", "")
        if role == "user":
            parts.append(content)
        else:
            parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def _respond_openai(client, model, input_items, text_format, tools=None, tool_executors=None,
                    tool_choice="auto", max_tool_rounds=8, tracer=None) -> str:
    def _create(input_payload, round_idx, previous_response_id=None):
        kwargs = {
            "model": model,
            "input": input_payload,
            "text": {"format": text_format},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id
        if is_reasoning_model(model):
            kwargs["reasoning"] = {"summary": "auto"}

        if tracer:
            tracer.emit("request", round=round_idx, provider="openai", kwargs=kwargs)
        t0 = time.monotonic()
        try:
            resp = client.responses.create(**kwargs)
        except Exception as e:
            if tracer:
                tracer.emit("api_error", round=round_idx, provider="openai",
                            elapsed_ms=(time.monotonic() - t0) * 1000.0,
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        if tracer:
            tracer.emit("response", round=round_idx, provider="openai",
                        elapsed_ms=elapsed_ms,
                        response=_serialize_response(resp))
        return resp

    response = _create(input_items, round_idx=0)

    for round_idx in range(1, max_tool_rounds + 1):
        function_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]

        if not function_calls:
            return response.output_text

        followup_input = []
        for fc in function_calls:
            fn_name = fc.name
            args_for_log = fc.arguments
            duration_ms = 0.0
            try:
                fn_args = json.loads(fc.arguments or "{}")
                args_for_log = fn_args
            except json.JSONDecodeError as e:
                tool_result = {"error": f"Invalid JSON arguments: {e}"}
            else:
                if tool_executors and fn_name in tool_executors:
                    t0 = time.monotonic()
                    try:
                        tool_result = tool_executors[fn_name](**fn_args)
                    except Exception as e:
                        tool_result = {"error": f"Tool '{fn_name}' raised: {e}"}
                    duration_ms = (time.monotonic() - t0) * 1000.0
                else:
                    tool_result = {"error": f"No executor registered for tool '{fn_name}'"}

            if tracer:
                tracer.emit("tool_exec", round=round_idx, provider="openai",
                            name=fn_name, arguments=args_for_log,
                            result=tool_result, duration_ms=duration_ms,
                            call_id=fc.call_id)

            followup_input.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": tool_result if isinstance(tool_result, str) else json.dumps(tool_result),
            })

        response = _create(followup_input, round_idx=round_idx, previous_response_id=response.id)

    raise RuntimeError(f"Tool-calling loop exceeded max_tool_rounds={max_tool_rounds}")


def _gemini_rejection_details(resp) -> dict:
    """Extract why Gemini returned no usable text (finish_reason, safety, etc.)."""
    details: dict = {}
    prompt_feedback = getattr(resp, "prompt_feedback", None)
    if prompt_feedback is not None:
        details["prompt_feedback"] = (
            prompt_feedback.model_dump(mode="json", exclude_none=True)
            if hasattr(prompt_feedback, "model_dump")
            else str(prompt_feedback)
        )

    candidates = getattr(resp, "candidates", None) or []
    if not candidates:
        details["candidates"] = 0
        return details

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if finish_reason is not None:
        details["finish_reason"] = str(finish_reason).split(".")[-1]

    safety_ratings = getattr(candidate, "safety_ratings", None)
    if safety_ratings:
        details["safety_ratings"] = [
            r.model_dump(mode="json", exclude_none=True)
            if hasattr(r, "model_dump")
            else str(r)
            for r in safety_ratings
        ]

    citation_metadata = getattr(candidate, "citation_metadata", None)
    if citation_metadata is not None:
        details["citation_metadata"] = (
            citation_metadata.model_dump(mode="json", exclude_none=True)
            if hasattr(citation_metadata, "model_dump")
            else str(citation_metadata)
        )

    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if parts:
        partial_chars = sum(len(getattr(p, "text", "") or "") for p in parts)
        if partial_chars:
            details["partial_text_chars"] = partial_chars

    return details


def _format_gemini_rejection_message(details: dict) -> str:
    finish_reason = details.get("finish_reason", "UNKNOWN")
    parts = [f"Gemini returned empty text (finish_reason={finish_reason})"]
    if finish_reason == "RECITATION":
        parts.append("model output matched copyrighted/training material")
    elif finish_reason == "SAFETY":
        parts.append("response blocked by safety filters")
    if details.get("safety_ratings"):
        parts.append(f"safety_ratings={details['safety_ratings']}")
    if details.get("prompt_feedback"):
        parts.append(f"prompt_feedback={details['prompt_feedback']}")
    if details.get("citation_metadata"):
        parts.append(f"citation_metadata={details['citation_metadata']}")
    if details.get("partial_text_chars"):
        parts.append(f"partial_text_chars={details['partial_text_chars']}")
    if details.get("candidates") == 0:
        parts.append("no candidates returned")
    return "; ".join(parts)


def _respond_gemini(client, model, input_items, text_format, tracer=None) -> str:
    from google.genai import types

    prompt = _prompt_from_input_items(input_items)
    schema = text_format["schema"]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    request_log = {
        "model": model,
        "provider": "gemini",
        "response_mime_type": "application/json",
        "response_json_schema": schema,
        "prompt_chars": len(prompt),
    }
    if tracer:
        tracer.emit("request", round=0, provider="gemini", kwargs=request_log)

    t0 = time.monotonic()
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as e:
        if tracer:
            tracer.emit("api_error", round=0, provider="gemini",
                        elapsed_ms=(time.monotonic() - t0) * 1000.0,
                        error_type=type(e).__name__,
                        error_message=str(e))
        raise

    elapsed_ms = (time.monotonic() - t0) * 1000.0
    if tracer:
        tracer.emit("response", round=0, provider="gemini",
                    elapsed_ms=elapsed_ms,
                    response=_serialize_response(resp))

    text = resp.text
    if not text:
        rejection = _gemini_rejection_details(resp)
        message = _format_gemini_rejection_message(rejection)
        print(message, flush=True)
        if tracer:
            tracer.emit("gemini_rejection", provider="gemini", **rejection)
        raise RuntimeError(message)
    return text


def respond_with_tools(provider: str, client, model, input_items, text_format,
                       tools=None, tool_executors=None, tool_choice="auto",
                       max_tool_rounds=8, tracer=None) -> str:
    if provider == "gemini":
        if tools:
            # OpenAI-hosted tools are not available on the Gemini path.
            pass
        return _respond_gemini(client, model, input_items, text_format, tracer=tracer)
    return _respond_openai(
        client, model, input_items, text_format,
        tools=tools, tool_executors=tool_executors,
        tool_choice=tool_choice, max_tool_rounds=max_tool_rounds,
        tracer=tracer,
    )
