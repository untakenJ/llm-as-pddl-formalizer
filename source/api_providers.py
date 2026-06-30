"""LLM API backends for the *-api formalizer/planner scripts.

- **OpenAI**: Responses API (``client.responses.create``) with optional hosted tools.
- **Gemini**: Google GenAI SDK on **Gemini Enterprise Agent Platform** (ADC) with
  JSON-schema structured output.

Gemini credentials (``_private/.env`` via ``env_loader``, or shell env):

- ``GOOGLE_GENAI_USE_ENTERPRISE=true``
- ``GOOGLE_CLOUD_PROJECT``
- ``GOOGLE_CLOUD_LOCATION`` (e.g. ``global``)
- Application Default Credentials (``gcloud auth application-default login`` or
  ``GOOGLE_APPLICATION_CREDENTIALS``)

OpenAI: ``_private/key.txt``

All Gemini access (formalizer-api, planner-api, and the Antigravity
Interactions API / remote sandbox) uses **Gemini Enterprise via ADC only** --
no Developer API key (``key_gemini.txt`` / ``GEMINI_API_KEY`` are not used).
"""

from __future__ import annotations

import datetime
import json
import os
import time

from openai import OpenAI

from env_loader import load_project_dotenv

load_project_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GEMINI_PROVIDER = "gemini-enterprise"

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


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def gemini_enterprise_enabled() -> bool:
    """True when Gemini Enterprise Agent Platform env is configured."""
    return _truthy_env("GOOGLE_GENAI_USE_ENTERPRISE")


def require_gemini_enterprise_config() -> None:
    """Exit with a clear message if Enterprise env is incomplete."""
    missing = []
    if not gemini_enterprise_enabled():
        missing.append("GOOGLE_GENAI_USE_ENTERPRISE=true")
    if not os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        missing.append("GOOGLE_CLOUD_PROJECT")
    if not os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip():
        missing.append("GOOGLE_CLOUD_LOCATION")
    if missing:
        raise SystemExit(
            "Gemini Enterprise configuration incomplete. Set in _private/.env or "
            "the shell:\n  " + "\n  ".join(missing) + "\n"
            "Then authenticate: gcloud auth application-default login"
        )


def sanitize_model_name(model: str) -> str:
    """Filesystem-safe model label (for output paths and run_solver/run_val)."""
    return model.replace("/", "__").replace(":", "_").replace(" ", "_")


def build_gemini_client():
    """Construct a ``google.genai.Client`` for Gemini Enterprise (ADC).

    Pins ``api_version="v1"`` for ``generate_content`` (formalizer-api /
    planner-api). For the Antigravity Interactions API use
    :func:`build_gemini_interactions_client` instead (it must stay on the
    Enterprise default ``v1beta1``).
    """
    from google import genai
    from google.genai.types import HttpOptions

    require_gemini_enterprise_config()
    return genai.Client(http_options=HttpOptions(api_version="v1"))


def build_gemini_interactions_client():
    """Construct a ``google.genai.Client`` for the Antigravity Interactions API
    on **Gemini Enterprise Agent Platform** (ADC).

    Unlike :func:`build_gemini_client`, this does *not* pin ``api_version``:
    the Interactions API and the Antigravity remote sandbox are served on the
    Enterprise default (``v1beta1``); pinning ``v1`` returns 404 for
    ``interactions``. Authentication uses Application Default Credentials
    (``gcloud auth application-default login`` or
    ``GOOGLE_APPLICATION_CREDENTIALS``), not a Developer API key.
    """
    from google import genai

    require_gemini_enterprise_config()
    return genai.Client()


def build_provider_client(model: str) -> tuple[str, object]:
    """Return ``(provider_name, client)`` where provider is ``openai`` or ``gemini-enterprise``."""
    if is_gemini_model(model):
        return GEMINI_PROVIDER, build_gemini_client()
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


def generate_gemini_json(
    client,
    model: str,
    prompt: str,
    schema: dict,
    *,
    tracer=None,
) -> str:
    """Generate JSON matching ``schema`` via Gemini Enterprise."""
    from google.genai import types

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    request_log = {
        "model": model,
        "provider": GEMINI_PROVIDER,
        "backend": "gemini-enterprise",
        "response_mime_type": "application/json",
        "response_json_schema": schema,
        "prompt_chars": len(prompt),
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
        "location": os.environ.get("GOOGLE_CLOUD_LOCATION"),
    }
    if tracer:
        tracer.emit("request", round=0, provider=GEMINI_PROVIDER, kwargs=request_log)

    t0 = time.monotonic()
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as e:
        if tracer:
            tracer.emit(
                "api_error",
                round=0,
                provider=GEMINI_PROVIDER,
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                error_type=type(e).__name__,
                error_message=str(e),
            )
        raise

    elapsed_ms = (time.monotonic() - t0) * 1000.0
    if tracer:
        tracer.emit(
            "response",
            round=0,
            provider=GEMINI_PROVIDER,
            elapsed_ms=elapsed_ms,
            response=_serialize_response(resp),
        )

    text = resp.text
    if not text:
        rejection = _gemini_rejection_details(resp)
        message = _format_gemini_rejection_message(rejection)
        print(message, flush=True)
        if tracer:
            tracer.emit("gemini_rejection", provider=GEMINI_PROVIDER, **rejection)
        raise RuntimeError(message)
    return text


def _respond_gemini(client, model, input_items, text_format, tracer=None) -> str:
    prompt = _prompt_from_input_items(input_items)
    return generate_gemini_json(
        client, model, prompt, text_format["schema"], tracer=tracer
    )


def respond_with_tools(provider: str, client, model, input_items, text_format,
                       tools=None, tool_executors=None, tool_choice="auto",
                       max_tool_rounds=8, tracer=None) -> str:
    if provider == GEMINI_PROVIDER or provider == "gemini":
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
