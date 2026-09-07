"""LLM API backends for the *-api formalizer/planner scripts.

- **OpenAI**: Responses API (``client.responses.create``) with optional hosted tools.
- **Gemini**: Google GenAI SDK on **Gemini Enterprise Agent Platform / Vertex**
  with a Google Cloud API key and JSON-schema structured output.
- **DeepSeek**: OpenAI-compatible Chat Completions API with JSON output. The
  complete response object, including any provider-returned
  ``reasoning_content``, is retained in the trace.

Gemini credentials (``_private/.env`` via ``env_loader``, or shell env):

- ``GOOGLE_CLOUD_API_KEY``
- ``GOOGLE_CLOUD_PROJECT``
- ``GOOGLE_CLOUD_LOCATION`` (e.g. ``global``)

OpenAI: ``_private/key.txt``

DeepSeek: ``DEEPSEEK_API_KEY`` from ``_private/.env`` or the shell.

The Gemini formalizer/planner API path uses **Gemini Enterprise / Vertex via
``GOOGLE_CLOUD_API_KEY``** -- no Developer API key (``key_gemini.txt`` /
``GEMINI_API_KEY``). The Antigravity Interactions API is project-scoped and
uses Vertex ADC (``GOOGLE_APPLICATION_CREDENTIALS`` or existing ADC) plus
``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_CLOUD_LOCATION``.
"""

from __future__ import annotations

import datetime
import errno
import http.client
import json
import os
import re
import socket
import ssl
import time
from email.utils import parsedate_to_datetime

from openai import OpenAI
import requests

from env_loader import load_project_dotenv

load_project_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GEMINI_PROVIDER = "google-vertex"
GEMINI_BACKEND = "google-vertex-api-key"
GEMINI_INTERACTIONS_BACKEND = "google-developer-api-key"
GEMINI_API_KEY_ENV = "GOOGLE_CLOUD_API_KEY"

DEEPSEEK_PROVIDER = "deepseek"
DEEPSEEK_BACKEND = "deepseek-chat-completions"
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

LOGITS_PROVIDER = "logits"
LOGITS_BACKEND = "logits-public-rest-openai-adapter"
LOGITS_API_KEY_ENV = "LOGITS_API_KEY"

# The standalone API pipelines own this policy independently of agent_formalizer.
# SDK retries are disabled for their clients so every application-visible
# attempt and delay can be recorded in the per-problem trace.
DIRECT_API_TRANSIENT_POLICY_ID = "external-transient-v2"
DIRECT_API_MAX_TRANSIENT_RETRIES = 5
DIRECT_API_TRANSIENT_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)
DIRECT_API_MAX_RETRY_AFTER_SECONDS = 60.0
DIRECT_API_RETRYABLE_HTTP_STATUSES = frozenset(
    {408, 429, 502, 503, 504, 520, 521, 522, 523, 524, 525, 529}
)

# Backwards-compatible names for callers that used the earlier 429-only helper.
RATE_LIMIT_MAX_ATTEMPTS = DIRECT_API_MAX_TRANSIENT_RETRIES + 1
RATE_LIMIT_BACKOFF_SECONDS = DIRECT_API_TRANSIENT_BACKOFF_SECONDS

_TRANSIENT_500_CODES = frozenset(
    {
        "INTERNAL",
        "INTERNAL_ERROR",
        "INTERNAL_SERVER_ERROR",
        "SERVER_ERROR",
        "TEMPORARILY_UNAVAILABLE",
    }
)
_TRANSIENT_PROVIDER_STATUSES = frozenset(
    {
        "DEADLINE_EXCEEDED",
        "RATE_LIMIT",
        "RATE_LIMITED",
        "RESOURCE_EXHAUSTED",
        "SERVICE_UNAVAILABLE",
        "TOO_MANY_REQUESTS",
        "UNAVAILABLE",
    }
)

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
    "gemini-3.7-flash",
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

DEEPSEEK_API_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]

API_MODELS = OPENAI_API_MODELS + GEMINI_API_MODELS + DEEPSEEK_API_MODELS

REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5", "deepseek-v4")

OPENAI_TOOLS = [
    {"type": "web_search"},
    {"type": "code_interpreter", "container": {"type": "auto"}},
]

OPENAI_TOOL_EXECUTORS: dict = {}


def is_gemini_model(model: str) -> bool:
    return model.startswith("gemini-") or model in GEMINI_API_MODELS


def is_deepseek_model(model: str) -> bool:
    return model.startswith("deepseek-") or model in DEEPSEEK_API_MODELS


def is_logits_model(model: str) -> bool:
    """Logits model availability is dynamic; require an explicit provider id."""
    return model.startswith("logits/") and len(model.split("/", 1)[1]) > 0


def validate_api_model(model: str) -> str:
    if model in API_MODELS or is_logits_model(model):
        return model
    raise ValueError(
        f"Unsupported API model {model!r}. Use a known model name or an explicit "
        "dynamic Logits route such as logits/Qwen/Qwen3.5-4B."
    )


def is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in REASONING_PREFIXES)


def default_tools_for_model(model: str) -> tuple[list | None, dict | None]:
    """Return hosted tools only for models served by OpenAI Responses."""
    if is_gemini_model(model) or is_deepseek_model(model) or is_logits_model(model):
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


def require_gemini_vertex_api_key_config() -> dict[str, str]:
    """Return Vertex API-key config, or exit with a clear message if incomplete."""
    api_key = os.environ.get(GEMINI_API_KEY_ENV, "").strip()
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("GCLOUD_PROJECT", "").strip()
    )
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip()

    missing = []
    if not api_key:
        missing.append(GEMINI_API_KEY_ENV)
    if not project:
        missing.append("GOOGLE_CLOUD_PROJECT")
    if not location:
        missing.append("GOOGLE_CLOUD_LOCATION")
    if missing:
        raise SystemExit(
            "Gemini Vertex API-key configuration incomplete. Set in _private/.env "
            "or the shell:\n  " + "\n  ".join(missing) + "\n"
            "This path uses a Google Cloud API key; no browser login or "
            "credential JSON is required."
        )
    return {"api_key": api_key, "project": project, "location": location}


def require_deepseek_api_key_config() -> dict[str, str]:
    """Return the explicitly named DeepSeek credential without logging it."""
    api_key = os.environ.get(DEEPSEEK_API_KEY_ENV, "").strip()
    if not api_key:
        raise SystemExit(
            f"DeepSeek API key not found. Set {DEEPSEEK_API_KEY_ENV} in "
            "_private/.env or the shell."
        )
    return {"api_key": api_key}


def require_logits_api_key_config() -> dict[str, str]:
    """Return the explicitly named Logits credential without logging it."""
    api_key = os.environ.get(LOGITS_API_KEY_ENV, "").strip()
    if not api_key:
        raise SystemExit(
            f"Logits API key not found. Set {LOGITS_API_KEY_ENV} in "
            "_private/.env or the shell."
        )
    return {"api_key": api_key}


def require_gemini_vertex_project_config() -> dict[str, str]:
    """Return Vertex project/location config for ADC-backed clients."""
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("GCLOUD_PROJECT", "").strip()
    )
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip()

    missing = []
    if not project:
        missing.append("GOOGLE_CLOUD_PROJECT")
    if not location:
        missing.append("GOOGLE_CLOUD_LOCATION")
    if missing:
        raise SystemExit(
            "Gemini Vertex project configuration incomplete. Set in "
            "_private/.env or the shell:\n  "
            + "\n  ".join(missing)
            + "\n"
            "The Antigravity Interactions API is project-scoped and uses "
            "Vertex ADC; configure GOOGLE_APPLICATION_CREDENTIALS or existing "
            "application-default credentials."
        )
    return {"project": project, "location": location}


def sanitize_model_name(model: str) -> str:
    """Filesystem-safe model label (for output paths and run_solver/run_val)."""
    return model.replace("/", "__").replace(":", "_").replace(" ", "_")


def build_gemini_client():
    """Construct a Vertex ``google.genai.Client`` using ``GOOGLE_CLOUD_API_KEY``.

    Pins ``api_version="v1"`` for ``generate_content`` (formalizer-api /
    planner-api). For the Antigravity Interactions API use
    :func:`build_gemini_interactions_client` instead (it must stay on the
    Enterprise default ``v1beta1``).
    """
    from google import genai
    from google.genai.types import HttpOptions, HttpRetryOptions

    cfg = require_gemini_vertex_api_key_config()
    return genai.Client(
        api_key=cfg["api_key"],
        vertexai=True,
        http_options=HttpOptions(
            api_version="v1",
            retry_options=HttpRetryOptions(attempts=1),
        ),
    )


def build_deepseek_client():
    """Construct the OpenAI-compatible DeepSeek client with SDK retries off."""
    cfg = require_deepseek_api_key_config()
    return OpenAI(
        api_key=cfg["api_key"],
        base_url=DEEPSEEK_BASE_URL,
        max_retries=0,
    )


def build_logits_client(model: str):
    """Build the direct public-REST client used by the API-only pipelines."""
    import atexit

    from agent_formalizer.config import LOGITS_MODEL_ASSETS_ROOT
    from agent_formalizer.logits_openai_bridge import JsonlLedger, LogitsChatBackend

    cfg = require_logits_api_key_config()
    upstream_model = model.split("/", 1)[1]
    client = LogitsChatBackend(
        model=upstream_model,
        api_key=cfg["api_key"],
        ledger=JsonlLedger(None),
        assets_root=LOGITS_MODEL_ASSETS_ROOT,
        origin=os.environ.get("LOGITS_BASE_URL", "https://api.logits.dev"),
    )
    atexit.register(client.close)
    return client


def require_gemini_developer_api_key_config() -> dict[str, str]:
    """Return a Gemini Developer API key for the Antigravity Interactions API.

    Reads ``GOOGLE_CLOUD_API_KEY`` first (this repo's convention), then the
    SDK-standard ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``. The key must be valid
    for the Generative Language API (``generativelanguage.googleapis.com``).
    """
    api_key = (
        os.environ.get(GEMINI_API_KEY_ENV, "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    if not api_key:
        raise SystemExit(
            "Gemini Developer API key not found. Set one of the following in "
            "_private/.env or the shell:\n  "
            f"{GEMINI_API_KEY_ENV}\n  GEMINI_API_KEY\n  GOOGLE_API_KEY\n"
            "The Antigravity Interactions API (Developer API path) authenticates "
            "with an API key valid for generativelanguage.googleapis.com."
        )
    return {"api_key": api_key}


def build_gemini_interactions_client():
    """Construct a ``google.genai.Client`` for the Antigravity Interactions API
    on the **Gemini Developer API** (``generativelanguage.googleapis.com``)
    using a Gemini API key.

    Passing ``vertexai=False`` explicitly forces the Developer API backend
    regardless of ``GOOGLE_GENAI_USE_ENTERPRISE`` / ``GOOGLE_GENAI_USE_VERTEXAI``
    in the environment (the SDK only consults those env vars when ``vertexai``
    is left unset). The SDK then serves the managed Antigravity agent at
    ``v1beta/interactions`` and authenticates with the ``x-goog-api-key``
    header. Project/location must not be passed here -- they are mutually
    exclusive with an API key in the client initializer.
    """
    from google import genai

    cfg = require_gemini_developer_api_key_config()
    return genai.Client(api_key=cfg["api_key"], vertexai=False)


def build_provider_client(model: str) -> tuple[str, object]:
    """Return the standalone API provider name and its configured client."""
    if is_gemini_model(model):
        return GEMINI_PROVIDER, build_gemini_client()
    if is_deepseek_model(model):
        return DEEPSEEK_PROVIDER, build_deepseek_client()
    if is_logits_model(model):
        return LOGITS_PROVIDER, build_logits_client(model)
    return "openai", OpenAI(api_key=_read_key_file("key.txt"), max_retries=0)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def direct_api_transient_policy() -> dict:
    """Return the secret-free, versioned retry policy recorded in traces."""
    return {
        "id": DIRECT_API_TRANSIENT_POLICY_ID,
        "max_retries": DIRECT_API_MAX_TRANSIENT_RETRIES,
        "backoff_seconds": list(DIRECT_API_TRANSIENT_BACKOFF_SECONDS),
        "max_retry_after_seconds": DIRECT_API_MAX_RETRY_AFTER_SECONDS,
        "retryable_http_statuses": sorted(DIRECT_API_RETRYABLE_HTTP_STATUSES),
    }


def _coerce_http_status(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if 100 <= value <= 599 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if 100 <= number <= 599 else None
    enum_value = getattr(value, "value", None)
    if enum_value is not value:
        return _coerce_http_status(enum_value)
    return None


def _exception_http_status(exc: BaseException) -> int | None:
    for value in (getattr(exc, "status_code", None), getattr(exc, "code", None)):
        status = _coerce_http_status(value)
        if status is not None:
            return status
    response = getattr(exc, "response", None)
    if response is not None:
        for value in (
            getattr(response, "status_code", None),
            getattr(response, "status", None),
        ):
            status = _coerce_http_status(value)
            if status is not None:
                return status
    # Some SDK wrappers discard structured attributes but retain a leading
    # HTTP status. Keep this narrow so arbitrary numbers in messages do not
    # change routing.
    match = re.match(r"^\s*(\d{3})\b", str(exc))
    return _coerce_http_status(match.group(1)) if match else None


def _structured_error_tokens(value) -> set[str]:
    tokens: set[str] = set()

    def visit(item):
        if isinstance(item, dict):
            for key, nested in item.items():
                if str(key).lower() in {"code", "reason", "status", "type"}:
                    tokens.add(str(nested).strip().upper())
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return {token for token in tokens if token}


def _exception_provider_tokens(exc: BaseException) -> set[str]:
    tokens = set()
    for attr in ("status", "reason", "type"):
        value = getattr(exc, attr, None)
        if value is not None:
            tokens.add(str(value).strip().upper())
    for attr in ("details", "body"):
        tokens.update(_structured_error_tokens(getattr(exc, attr, None)))

    # Compatibility fallback for exception wrappers without structured fields.
    upper = str(exc).upper()
    for token in _TRANSIENT_PROVIDER_STATUSES:
        if re.search(rf"\b{re.escape(token)}\b", upper):
            tokens.add(token)
    if "QUOTA EXCEEDED" in upper:
        tokens.add("RESOURCE_EXHAUSTED")
    return tokens


def _exception_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_retryable_transport_error(exc: BaseException) -> bool:
    chain = tuple(_exception_chain(exc))
    if any(
        isinstance(item, (ssl.SSLCertVerificationError, requests.exceptions.SSLError))
        or "certificate verify failed" in str(item).lower()
        for item in chain
    ):
        return False

    standard_types = (
        ConnectionError,
        TimeoutError,
        socket.gaierror,
        socket.timeout,
        http.client.RemoteDisconnected,
        http.client.IncompleteRead,
        http.client.BadStatusLine,
        http.client.LineTooLong,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    )
    retryable_errnos = {
        errno.ECONNABORTED,
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.EHOSTUNREACH,
        errno.ENETDOWN,
        errno.ENETUNREACH,
        errno.EPIPE,
        errno.ETIMEDOUT,
    }
    transport_class_names = {
        "ConnectError",
        "ConnectTimeout",
        "NetworkError",
        "PoolTimeout",
        "ReadError",
        "ReadTimeout",
        "RemoteProtocolError",
        "TimeoutException",
        "TransportError",
        "WriteError",
        "WriteTimeout",
    }
    for item in chain:
        if isinstance(item, standard_types):
            return True
        if isinstance(item, ssl.SSLError):
            return True
        if isinstance(item, OSError) and item.errno in retryable_errnos:
            return True
        if any(
            cls.__module__.split(".", 1)[0] in {"httpx", "httpcore"}
            and cls.__name__ in transport_class_names
            for cls in type(item).__mro__
        ):
            return True
    return False


def classify_direct_api_error(exc: BaseException) -> dict:
    """Classify an API exception without depending on agent_formalizer.

    Structured HTTP/provider fields take precedence. Text is only a fallback
    for SDK wrappers that discard those fields.
    """
    status = _exception_http_status(exc)
    provider_tokens = _exception_provider_tokens(exc)
    provider_status = next(
        (
            token
            for token in sorted(provider_tokens)
            if token and _coerce_http_status(token) is None
        ),
        None,
    )

    if status is not None:
        if status in DIRECT_API_RETRYABLE_HTTP_STATUSES:
            return {
                "retryable": True,
                "reason": f"upstream_http_{status}",
                "http_status": status,
                "provider_status": provider_status,
            }
        if status == 500 and provider_tokens & _TRANSIENT_500_CODES:
            return {
                "retryable": True,
                "reason": "upstream_structured_internal_error",
                "http_status": status,
                "provider_status": provider_status,
            }
        return {
            "retryable": False,
            "reason": f"upstream_http_{status}",
            "http_status": status,
            "provider_status": provider_status,
        }

    transient_provider = provider_tokens & _TRANSIENT_PROVIDER_STATUSES
    if transient_provider:
        provider_status = sorted(transient_provider)[0]
        return {
            "retryable": True,
            "reason": f"upstream_provider_{provider_status.lower()}",
            "http_status": None,
            "provider_status": provider_status,
        }
    if _is_retryable_transport_error(exc):
        return {
            "retryable": True,
            "reason": "upstream_transport_error",
            "http_status": None,
            "provider_status": provider_status,
        }
    return {
        "retryable": False,
        "reason": "non_retryable_api_error",
        "http_status": None,
        "provider_status": provider_status,
    }


def is_rate_limit_error(exc: BaseException) -> bool:
    """Backward-compatible predicate for 429/quota-style rate limits."""
    status = _exception_http_status(exc)
    tokens = _exception_provider_tokens(exc)
    return status == 429 or bool(
        tokens
        & {
            "RATE_LIMIT",
            "RATE_LIMITED",
            "RESOURCE_EXHAUSTED",
            "TOO_MANY_REQUESTS",
        }
    )


def _retry_headers(exc: BaseException):
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    return headers or getattr(exc, "headers", None)


def _retry_delay_seconds(
    exc: BaseException,
    retry_index: int,
    backoff_seconds: tuple[float, ...],
    max_retry_after_seconds: float,
) -> tuple[float, str]:
    headers = _retry_headers(exc)
    raw = (
        headers.get("Retry-After") or headers.get("retry-after")
        if headers is not None
        else None
    )
    parsed: float | None = None
    if raw:
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            try:
                parsed = parsedate_to_datetime(raw).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                parsed = None
    if parsed is not None:
        return (
            round(max(0.0, min(max_retry_after_seconds, parsed)), 6),
            "retry_after",
        )
    index = min(retry_index, len(backoff_seconds) - 1)
    return backoff_seconds[index], "fixed_backoff"


def call_with_transient_retry(
    fn,
    *,
    tracer=None,
    provider: str = "",
    max_attempts: int = DIRECT_API_MAX_TRANSIENT_RETRIES + 1,
    backoff_seconds: tuple[float, ...] = DIRECT_API_TRANSIENT_BACKOFF_SECONDS,
    max_retry_after_seconds: float = DIRECT_API_MAX_RETRY_AFTER_SECONDS,
):
    """Call ``fn`` with bounded transparent retries for external transients."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if not backoff_seconds or any(delay < 0 for delay in backoff_seconds):
        raise ValueError("backoff_seconds must be non-empty and non-negative")
    if max_retry_after_seconds < 0:
        raise ValueError("max_retry_after_seconds must be non-negative")

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        try:
            result = fn()
        except Exception as exc:
            classification = classify_direct_api_error(exc)
            will_retry = classification["retryable"] and attempt < max_attempts
            delay = None
            delay_source = None
            if will_retry:
                delay, delay_source = _retry_delay_seconds(
                    exc,
                    attempt - 1,
                    backoff_seconds,
                    max_retry_after_seconds,
                )
            routing_class = (
                "transparent_transient"
                if will_retry
                else (
                    "terminal_infrastructure"
                    if classification["retryable"]
                    else "api_error"
                )
            )
            routing_reason = (
                "provider_transient_exhausted"
                if classification["retryable"] and not will_retry
                else classification["reason"]
            )
            if tracer:
                tracer.emit(
                    "api_attempt",
                    provider=provider,
                    policy_id=DIRECT_API_TRANSIENT_POLICY_ID,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    outcome="error",
                    duration_ms=round((time.monotonic() - started) * 1000.0, 3),
                    error_type=type(exc).__name__,
                    http_status=classification["http_status"],
                    provider_status=classification["provider_status"],
                    routing_class=routing_class,
                    routing_reason=routing_reason,
                    last_error_reason=classification["reason"],
                    will_retry=will_retry,
                    retry_delay_seconds=delay,
                    retry_delay_source=delay_source,
                )
            if not will_retry:
                raise
            print(
                f"[{provider or 'api'}] transient {classification['reason']}; "
                f"retry {attempt}/{max_attempts} after {delay:g}s",
                flush=True,
            )
            time.sleep(delay)
        else:
            if tracer:
                tracer.emit(
                    "api_attempt",
                    provider=provider,
                    policy_id=DIRECT_API_TRANSIENT_POLICY_ID,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    outcome="success",
                    duration_ms=round((time.monotonic() - started) * 1000.0, 3),
                    routing_class="upstream_success",
                    routing_reason="upstream_success",
                    will_retry=False,
                )
            return result
    raise AssertionError("unreachable")


def call_with_rate_limit_retry(
    fn,
    *,
    tracer=None,
    provider: str = "",
    max_attempts: int = RATE_LIMIT_MAX_ATTEMPTS,
    backoff_seconds: tuple[float, ...] = RATE_LIMIT_BACKOFF_SECONDS,
):
    """Compatibility wrapper; new code should use transient retry."""
    return call_with_transient_retry(
        fn,
        tracer=tracer,
        provider=provider,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
    )


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
            resp = call_with_transient_retry(
                lambda: client.responses.create(**kwargs),
                tracer=tracer,
                provider="openai",
            )
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
        "backend": GEMINI_BACKEND,
        "api_key_env": GEMINI_API_KEY_ENV,
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
        resp = call_with_transient_retry(
            lambda: client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            ),
            tracer=tracer,
            provider=GEMINI_PROVIDER,
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


def generate_deepseek_json(
    client,
    model: str,
    input_items: list,
    schema: dict,
    *,
    tracer=None,
) -> str:
    """Generate a JSON object through DeepSeek Chat Completions.

    DeepSeek's JSON mode requires the prompt to explicitly request JSON. It
    does not currently enforce arbitrary JSON Schema server-side, so the
    schema is included verbatim in the system instruction and the caller
    performs the existing parse/key checks.
    """
    json_instruction = (
        "Return exactly one valid JSON object and no other text. Do not use "
        "Markdown fences. The JSON object must conform to this JSON Schema:\n"
        + json.dumps(schema, ensure_ascii=False, sort_keys=True)
    )
    messages = [{"role": "system", "content": json_instruction}, *input_items]
    request = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if tracer:
        tracer.emit(
            "request",
            round=0,
            provider=DEEPSEEK_PROVIDER,
            backend=DEEPSEEK_BACKEND,
            api_key_env=DEEPSEEK_API_KEY_ENV,
            kwargs=request,
        )

    t0 = time.monotonic()
    try:
        resp = call_with_transient_retry(
            lambda: client.chat.completions.create(**request),
            tracer=tracer,
            provider=DEEPSEEK_PROVIDER,
        )
    except Exception as e:
        if tracer:
            tracer.emit(
                "api_error",
                round=0,
                provider=DEEPSEEK_PROVIDER,
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
            provider=DEEPSEEK_PROVIDER,
            elapsed_ms=elapsed_ms,
            response=_serialize_response(resp),
        )

    choices = getattr(resp, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    text = getattr(message, "content", None) if message is not None else None
    if not text:
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        raise RuntimeError(
            "DeepSeek returned empty JSON content "
            f"(finish_reason={finish_reason or 'UNKNOWN'})"
        )
    return text


def _respond_deepseek(client, model, input_items, text_format, tracer=None) -> str:
    return generate_deepseek_json(
        client,
        model,
        input_items,
        text_format["schema"],
        tracer=tracer,
    )


def generate_logits_json(
    client,
    model: str,
    input_items: list,
    schema: dict,
    *,
    tracer=None,
) -> str:
    """Generate schema-checked JSON through the public Logits REST protocol."""
    upstream_model = model.split("/", 1)[1]
    json_instruction = (
        "Return exactly one valid JSON object and no other text. Do not use "
        "Markdown fences. The JSON object must conform to this JSON Schema:\n"
        + json.dumps(schema, ensure_ascii=False, sort_keys=True)
    )
    request = {
        "model": upstream_model,
        "messages": [{"role": "system", "content": json_instruction}, *input_items],
        "response_format": {"type": "json_object"},
        "logits_json_schema": schema,
    }
    if tracer:
        tracer.emit(
            "request",
            round=0,
            provider=LOGITS_PROVIDER,
            backend=LOGITS_BACKEND,
            api_key_env=LOGITS_API_KEY_ENV,
            kwargs=request,
        )
    started = time.monotonic()
    try:
        response = call_with_transient_retry(
            lambda: client.chat_completion(request),
            tracer=tracer,
            provider=LOGITS_PROVIDER,
        )
    except Exception as exc:
        if tracer:
            tracer.emit(
                "api_error",
                round=0,
                provider=LOGITS_PROVIDER,
                elapsed_ms=(time.monotonic() - started) * 1000.0,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        raise
    if tracer:
        tracer.emit(
            "response",
            round=0,
            provider=LOGITS_PROVIDER,
            elapsed_ms=(time.monotonic() - started) * 1000.0,
            response=response,
        )
    choices = response.get("choices") if isinstance(response, dict) else None
    message = choices[0].get("message") if choices else None
    text = message.get("content") if isinstance(message, dict) else None
    if not text:
        finish_reason = choices[0].get("finish_reason") if choices else None
        raise RuntimeError(
            "Logits returned empty JSON content "
            f"(finish_reason={finish_reason or 'UNKNOWN'})"
        )
    return text


def _respond_logits(client, model, input_items, text_format, tracer=None) -> str:
    return generate_logits_json(
        client,
        model,
        input_items,
        text_format["schema"],
        tracer=tracer,
    )


def respond_with_tools(provider: str, client, model, input_items, text_format,
                       tools=None, tool_executors=None, tool_choice="auto",
                       max_tool_rounds=8, tracer=None) -> str:
    if provider == GEMINI_PROVIDER or provider == "gemini":
        if tools:
            # OpenAI-hosted tools are not available on the Gemini path.
            pass
        return _respond_gemini(client, model, input_items, text_format, tracer=tracer)
    if provider == DEEPSEEK_PROVIDER:
        if tools:
            raise ValueError("DeepSeek Direct API baseline does not use hosted tools")
        return _respond_deepseek(
            client, model, input_items, text_format, tracer=tracer
        )
    if provider == LOGITS_PROVIDER:
        if tools:
            raise ValueError("Logits Direct API baseline does not use hosted tools")
        return _respond_logits(
            client, model, input_items, text_format, tracer=tracer
        )
    return _respond_openai(
        client, model, input_items, text_format,
        tools=tools, tool_executors=tool_executors,
        tool_choice=tool_choice, max_tool_rounds=max_tool_rounds,
        tracer=tracer,
    )
