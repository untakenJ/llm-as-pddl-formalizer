"""Frozen output-budget policy shared by adapters, the gateway and API baselines.

No provider calls or registry reads take place at import time. This module also
runs as a standalone, standard-library-only module in the model sidecar.
"""
from __future__ import annotations

from copy import deepcopy
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit

POLICY_ID = "model-output-v1"
REGISTRY_PATH = Path(__file__).resolve().parent.parent / "configs/model_capabilities.json"


class OutputBudgetInputError(ValueError):
    """A real input rejection, not grounds to invalidate/resample an answer."""
    def __init__(self, status, payload):
        super().__init__(f"Output-budget input rejected (HTTP {status})")
        self.status = status
        self.payload = payload


def validate_selection(value):
    if isinstance(value, str) and value in {"native", "model_max"}:
        return value
    if type(value) is int and value > 0:
        return value
    raise ValueError("max_output_tokens must be 'native', 'model_max', or a positive integer")


def validate_registry(raw):
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "models", "aliases"}:
        raise ValueError("model capabilities require schema_version, models and aliases")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Unsupported model capabilities schema")
    if not isinstance(raw["models"], dict) or not isinstance(raw["aliases"], dict):
        raise ValueError("models and aliases must be objects")
    required = {"context_window_tokens", "max_output_tokens", "context_handling", "output_accounting", "source_url", "verified_at"}
    for model, row in raw["models"].items():
        if not isinstance(model, str) or "/" not in model or not isinstance(row, dict) or set(row) != required:
            raise ValueError(f"Invalid capability entry: {model}")
        if type(row["context_window_tokens"]) is not int or row["context_window_tokens"] < 2:
            raise ValueError(f"Invalid context window: {model}")
        cap = row["max_output_tokens"]
        if cap != "remaining_context" and (type(cap) is not int or cap <= 0):
            raise ValueError(f"Invalid output limit: {model}")
        if row["context_handling"] not in ("provider_enforced", "vllm_tokenize"):
            raise ValueError(f"Unsupported context accounting: {model}")
        if cap == "remaining_context" and row["context_handling"] != "vllm_tokenize":
            raise ValueError("remaining_context requires authoritative vLLM tokenization")
        if row["output_accounting"] not in ("includes_reasoning", "provider_defined"):
            raise ValueError(f"Invalid output accounting: {model}")
        if not all(isinstance(row[k], str) and row[k] for k in ("source_url", "verified_at")):
            raise ValueError(f"Capability evidence is required: {model}")
    for alias, target in raw["aliases"].items():
        if not isinstance(alias, str) or "/" not in alias or alias in raw["models"] or not isinstance(target, str) or target not in raw["models"]:
            raise ValueError(f"Invalid explicit model alias: {alias}")
    return deepcopy(raw)


def load_registry(path=REGISTRY_PATH):
    return validate_registry(json.loads(Path(path).read_text()))


def resolve_output_policy(model, selection, registry=None):
    validate_selection(selection)
    if not isinstance(model, str) or "/" not in model:
        raise ValueError("Output policy requires an exact provider/model route")
    if selection == "native":
        return None
    registry = load_registry() if registry is None else validate_registry(registry)
    canonical = registry["aliases"].get(model, model)
    if canonical not in registry["models"]:
        raise ValueError(f"No verified model capabilities for {model!r}; add an exact registry entry or select 'native'")
    row = registry["models"][canonical]
    cap = row["max_output_tokens"]
    if type(selection) is int and type(cap) is int and selection > cap:
        raise ValueError(f"Requested output limit {selection} exceeds {model} limit {cap}")
    # Only selected semantic fields enter run identity, never unrelated rows,
    # documentary URLs, verification dates or filesystem paths.
    return {
        "policy_id": POLICY_ID, "model": model, "selection": selection,
        "context_window_tokens": row["context_window_tokens"],
        "max_output_tokens": cap if selection == "model_max" else selection,
        "context_handling": row["context_handling"],
        "output_accounting": row["output_accounting"],
    }


def validate_policy(policy):
    fields = {"policy_id", "model", "selection", "context_window_tokens", "max_output_tokens", "context_handling", "output_accounting"}
    if not isinstance(policy, dict) or set(policy) != fields or policy["policy_id"] != POLICY_ID:
        raise ValueError("Invalid frozen model output policy")
    validate_selection(policy["selection"])
    if policy["selection"] == "native":
        raise ValueError("Native policy must be omitted, not materialized")
    if type(policy["selection"]) is int and policy["selection"] != policy["max_output_tokens"]:
        raise ValueError("Frozen numeric output selection must match its limit")
    if not isinstance(policy["model"], str):
        raise ValueError("Frozen policy model must be a string")
    row = {k: policy[k] for k in ("context_window_tokens", "max_output_tokens", "context_handling", "output_accounting")}
    validate_registry({"schema_version": 1, "models": {policy["model"]: {**row, "source_url": "frozen", "verified_at": "frozen"}}, "aliases": {}})
    return policy


def native_output_hint(policy, *, fallback=8192):
    """For context-limited models, keep native packing reserve distinct from cap.

    The gateway replaces this carrier hint using the server's exact token count;
    it is NOT an 8192-token generation ceiling. Reserving the entire context as
    output inside a native compactor would leave no space for any input.
    """
    if not policy:
        return None
    cap = policy["max_output_tokens"]
    return cap if type(cap) is int else min(fallback, policy["context_window_tokens"] // 2)


def apply_output_policy(payload, policy, api_path, *, input_tokens=None, deployment_context=None):
    """Return a modified copy and a small, secret-free audit record.

    Cloud APIs without a verified tokenization path retain their authoritative
    context validation; this function NEVER pretends a character estimate is an
    exact token count, truncates input, or retries an input/context error.
    """
    validate_policy(policy)
    result = deepcopy(payload)
    cap = policy["max_output_tokens"]
    audit = {"policy_id": POLICY_ID, "configured_max_output_tokens": cap,
             "context_handling": policy["context_handling"]}
    if policy["context_handling"] == "vllm_tokenize":
        if type(input_tokens) is not int or input_tokens < 0 or type(deployment_context) is not int:
            raise ValueError("Authoritative input count and deployment context are required")
        if deployment_context < policy["context_window_tokens"]:
            raise ValueError("Deployed context window is smaller than the frozen experiment requires")
        remaining = policy["context_window_tokens"] - input_tokens
        if remaining <= 0:
            raise OutputBudgetInputError(400, {"error": {"type": "context_length_exceeded",
                "message": "Input exhausts the frozen model context window"}})
        cap = remaining if cap == "remaining_context" else min(cap, remaining)
        audit.update(input_tokens=input_tokens, remaining_context_tokens=remaining,
                     deployment_context_tokens=deployment_context)
    if type(cap) is not int or cap <= 0:
        raise ValueError("No usable output budget")
    if api_path.rstrip("/").endswith((":generateContent", ":streamGenerateContent")):
        config = result.setdefault("generationConfig", {})
        if not isinstance(config, dict):
            raise ValueError("generationConfig must be an object")
        audit["requested_max_output_tokens"] = config.get("maxOutputTokens")
        config["maxOutputTokens"] = cap
        field = "generationConfig.maxOutputTokens"
    else:
        audit["requested_token_fields"] = {k: result[k] for k in ("max_tokens", "max_completion_tokens", "max_output_tokens") if k in result}
        if api_path.rstrip("/").endswith("/responses"):
            field = "max_output_tokens"
        elif api_path.rstrip("/").endswith("/messages"):
            field = "max_tokens"
        else:
            name = str(result.get("model", "")).split("/")[-1]
            provider = policy["model"].split("/", 1)[0]
            completion_field = (provider not in {"google-vertex", "google", "gemini", "deepseek"}
                                and ("max_completion_tokens" in result or name.startswith(("gpt-5", "o1", "o3", "o4"))))
            field = "max_completion_tokens" if completion_field else "max_tokens"
        for key in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
            result.pop(key, None)
        result[field] = cap
    audit.update(effective_max_output_tokens=cap, parameter=field)
    return result, audit


def vllm_count_tokens(origin, payload, *, headers=None, timeout=60):
    """Use the actual inference server's tokenizer and chat template, no weights.

    A single request-boundary operation, never a streaming-event hook. Caller
    owns transient recovery. No response bodies (potential secrets) in errors.
    """
    url = urlsplit(str(origin))
    connection_cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise ValueError("Invalid vLLM origin")
    allowed = {"model", "messages", "tools", "chat_template", "chat_template_kwargs", "add_generation_prompt", "continue_final_message", "add_special_tokens"}
    request = {k: deepcopy(v) for k, v in payload.items() if k in allowed}
    # /tokenize has no top-level tool_choice field. Keep schemas even for
    # tool_choice=none: vLLM retains them by default. Non-default parser or
    # exclude-tools settings require deployment validation (see configs guide).
    template_kwargs = deepcopy(payload.get("chat_template_kwargs") or {})
    for field in ("documents", "reasoning_effort"):
        if field in payload:
            template_kwargs[field] = payload[field]
    if payload.get("reasoning_effort") is not None and "enable_thinking" not in template_kwargs:
        template_kwargs["enable_thinking"] = payload["reasoning_effort"] != "none"
    if template_kwargs:
        request["chat_template_kwargs"] = template_kwargs
    request["add_generation_prompt"] = payload.get("add_generation_prompt", True)
    request["return_token_strs"] = False
    prefix = url.path.rstrip("/")
    if prefix.endswith("/v1"):
        prefix = prefix[:-3]
    conn = connection_cls(url.hostname, url.port, timeout=timeout)
    try:
        conn.request("POST", prefix + "/tokenize", json.dumps(request).encode(),
                     {**(headers or {}), "Content-Type": "application/json"})
        response = conn.getresponse()
        data = response.read(32 * 1024 * 1024)
        if response.status in {408, 429, 500, 502, 503, 504}:
            raise ConnectionResetError(f"vLLM tokenization transient HTTP {response.status}")
        if response.status in {400, 422}:
            try:
                rejection = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                rejection = {"error": {"type": "invalid_request_error", "message": data.decode('utf-8', errors='replace')}}
            raise OutputBudgetInputError(response.status, rejection)
        if response.status != 200:
            raise ValueError(f"vLLM /tokenize required by output policy returned HTTP {response.status}")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("vLLM /tokenize response must be an object")
        count, context = value.get("count"), value.get("max_model_len")
        if type(count) is not int or count < 0 or type(context) is not int or context <= 0:
            raise ValueError("vLLM /tokenize did not return count and max_model_len")
        return count, context
    finally:
        conn.close()
