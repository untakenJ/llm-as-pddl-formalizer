"""Provider-neutral data contracts for infrastructure diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ProviderResponseSnapshot:
    event_type: str
    provider: str
    model: str | None
    status_code: int | None
    headers: Mapping[str, str]
    body: bytes | None
    body_sha256: str | None
    body_original_bytes: int
    body_truncated: bool
    error_type: str | None
    error_message: str | None
    routing_class: str | None
    routing_reason: str | None
    retryable: bool | None
    retry_after_ms: int | None
    duration_ms: float | None
    observed_at: str
    correlation: Mapping[str, Any]


@dataclass(frozen=True)
class DiagnosticProjection:
    normalized: Mapping[str, Any]
    provider_payload: Mapping[str, Any]
    raw_payload: Mapping[str, Any] | None = None


class ProviderDiagnosticHandler(Protocol):
    handler_id: str
    provider_id: str

    def project(
        self, snapshot: ProviderResponseSnapshot
    ) -> DiagnosticProjection:
        ...

