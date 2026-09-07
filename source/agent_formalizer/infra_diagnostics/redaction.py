"""Common redaction applied after provider-specific projection."""

from __future__ import annotations

import re
from typing import Any, Mapping


_SENSITIVE_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-goog-api-key",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
}
_SAFE_HEADER_NAMES = {
    "content-type",
    "content-encoding",
    "date",
    "request-id",
    "retry-after",
    "server",
    "x-cloud-trace-context",
    "x-envoy-upstream-service-time",
    "x-goog-request-id",
    "x-google-request-id",
    "x-request-id",
}
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/=]+")
_KEY_QUERY = re.compile(r"(?i)([?&](?:key|api_key|access_token)=)[^&\s]+")
_KEY_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)"
    r"\b\s*[:=]\s*[\"']?)[^\"'\s,;&]+"
)


def safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        if (
            name in _SAFE_HEADER_NAMES
            or name.startswith("x-ratelimit-")
            or name.startswith("ratelimit-")
        ):
            result[name] = redact_text(str(raw_value))
    return result


def redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _KEY_QUERY.sub(r"\1[REDACTED]", value)
    return _KEY_ASSIGNMENT.sub(r"\1[REDACTED]", value)


def redact(value: Any, *, path: str = "$") -> tuple[Any, list[str]]:
    redacted_paths: list[str] = []

    def visit(item: Any, current: str) -> Any:
        if isinstance(item, dict):
            result = {}
            for key, nested in item.items():
                key_text = str(key)
                nested_path = f"{current}.{key_text}"
                if key_text.lower() in _SENSITIVE_KEYS:
                    result[key_text] = "[REDACTED]"
                    redacted_paths.append(nested_path)
                else:
                    result[key_text] = visit(nested, nested_path)
            return result
        if isinstance(item, list):
            return [visit(nested, f"{current}[{index}]") for index, nested in enumerate(item)]
        if isinstance(item, tuple):
            return [visit(nested, f"{current}[{index}]") for index, nested in enumerate(item)]
        if isinstance(item, str):
            cleaned = redact_text(item)
            if cleaned != item:
                redacted_paths.append(current)
            return cleaned
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return redact_text(str(item))

    return visit(value, path), redacted_paths
