"""Conservative fallback for unknown or malformed provider responses."""

from __future__ import annotations

import json

from ..types import DiagnosticProjection, ProviderResponseSnapshot


def decode_json_object(body: bytes | None) -> dict:
    if not body:
        return {}
    try:
        value = json.loads(body.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


class GenericHttpDiagnosticHandlerV1:
    handler_id = "builtin:generic_http@1"
    provider_id = "*"

    def project(
        self, snapshot: ProviderResponseSnapshot
    ) -> DiagnosticProjection:
        payload = decode_json_object(snapshot.body)
        provider_payload = {
            "content_type": snapshot.headers.get("content-type"),
            "response_json": payload or None,
            "response_text": (
                snapshot.body.decode("utf-8", errors="replace")
                if snapshot.body and not payload
                else None
            ),
            "safe_response_headers": dict(snapshot.headers),
        }
        return DiagnosticProjection(
            normalized={},
            provider_payload=provider_payload,
        )

