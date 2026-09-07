"""Google Vertex / Gemini provider diagnostic projection."""

from __future__ import annotations

from ..types import DiagnosticProjection, ProviderResponseSnapshot
from .generic_http import decode_json_object


_REQUEST_ID_HEADERS = (
    "x-goog-request-id",
    "x-google-request-id",
    "x-request-id",
    "request-id",
    "x-cloud-trace-context",
)


def _request_id(headers) -> str | None:
    for name in _REQUEST_ID_HEADERS:
        value = headers.get(name)
        if value:
            return value
    return None


class GoogleVertexDiagnosticHandlerV1:
    handler_id = "builtin:google_vertex@1"
    provider_id = "google_vertex"

    def project(
        self, snapshot: ProviderResponseSnapshot
    ) -> DiagnosticProjection:
        payload = decode_json_object(snapshot.body)
        error = payload.get("error")
        if not isinstance(error, dict):
            error = {}
        details = error.get("details")
        if not isinstance(details, list):
            details = []
        detail_types = [
            item.get("@type")
            for item in details
            if isinstance(item, dict) and isinstance(item.get("@type"), str)
        ]
        return DiagnosticProjection(
            normalized={
                "request_id": _request_id(snapshot.headers),
                "provider_error_code": error.get("code"),
                "provider_error_status": error.get("status"),
            },
            provider_payload={
                "error_code": error.get("code"),
                "error_status": error.get("status"),
                "message": error.get("message"),
                "details": details,
                "detail_types": detail_types,
                "safe_response_headers": dict(snapshot.headers),
                "unrecognized_response_json": payload if payload and not error else None,
            },
        )

