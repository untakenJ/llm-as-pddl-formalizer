"""Explicit built-in handler registry; no directory scanning or dynamic code."""

from __future__ import annotations

from .providers.deepseek import DeepSeekDiagnosticHandlerV1
from .providers.generic_http import GenericHttpDiagnosticHandlerV1
from .providers.google_vertex import GoogleVertexDiagnosticHandlerV1


GENERIC_HANDLER_ID = "builtin:generic_http@1"

HANDLER_FACTORIES = {
    GENERIC_HANDLER_ID: GenericHttpDiagnosticHandlerV1,
    "builtin:google_vertex@1": GoogleVertexDiagnosticHandlerV1,
    "builtin:deepseek@1": DeepSeekDiagnosticHandlerV1,
}

DEFAULT_HANDLER_IDS = {
    "google_vertex": "builtin:google_vertex@1",
    "gemini": "builtin:google_vertex@1",
    "deepseek": "builtin:deepseek@1",
}


def canonical_provider_id(provider: str) -> str:
    value = str(provider or "unknown").strip().lower().replace("-", "_")
    if value in {"google", "google_vertex"}:
        return "google_vertex"
    return value or "unknown"


def resolve_handler_id(
    provider: str,
    configured_handler_id: str | None = None,
) -> str:
    if configured_handler_id is not None:
        if configured_handler_id not in HANDLER_FACTORIES:
            raise ValueError(
                f"unknown provider diagnostic handler: {configured_handler_id}"
            )
        return configured_handler_id
    return DEFAULT_HANDLER_IDS.get(canonical_provider_id(provider), GENERIC_HANDLER_ID)


def create_handler(handler_id: str):
    try:
        factory = HANDLER_FACTORIES[handler_id]
    except KeyError as exc:
        raise ValueError(f"unknown provider diagnostic handler: {handler_id}") from exc
    return factory()

