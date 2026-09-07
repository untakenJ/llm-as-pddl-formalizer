"""DeepSeek OpenAI-compatible provider diagnostic projection."""

from __future__ import annotations

from ..types import DiagnosticProjection, ProviderResponseSnapshot
from .generic_http import decode_json_object


_REQUEST_ID_HEADERS = (
    "x-request-id",
    "request-id",
    "x-ds-request-id",
)


def _request_id(headers) -> str | None:
    for name in _REQUEST_ID_HEADERS:
        value = headers.get(name)
        if value:
            return value
    return None


class DeepSeekDiagnosticHandlerV1:
    handler_id = "builtin:deepseek@1"
    provider_id = "deepseek"

    def project(
        self, snapshot: ProviderResponseSnapshot
    ) -> DiagnosticProjection:
        payload = decode_json_object(snapshot.body)
        error = payload.get("error")
        if not isinstance(error, dict):
            error = {}
        return DiagnosticProjection(
            normalized={
                "request_id": _request_id(snapshot.headers),
                "provider_error_type": error.get("type"),
                "provider_error_code": error.get("code"),
            },
            provider_payload={
                "error_type": error.get("type"),
                "error_code": error.get("code"),
                "message": error.get("message"),
                "param": error.get("param"),
                "safe_response_headers": dict(snapshot.headers),
                "unrecognized_response_json": payload if payload and not error else None,
            },
        )

