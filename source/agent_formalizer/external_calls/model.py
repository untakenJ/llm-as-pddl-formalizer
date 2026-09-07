"""Compatibility policy for the existing external-transient-v2 model gateway."""

import errno
import http.client
import json
import socket
import ssl

from .retry import Action, Decision

TRANSIENT_500_CODES = frozenset({
    "internal_error", "overloaded", "server_error", "service_unavailable", "temporarily_unavailable",
})


def structured_error_codes(body: bytes) -> set[str]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return set()
    codes = set()

    def visit(item):
        if isinstance(item, dict):
            for key, nested in item.items():
                if key.lower() in {"code", "error_code", "reason", "type"} and isinstance(nested, str):
                    codes.add(nested.strip().lower())
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
    visit(value)
    return codes


def classify_response(status: int, body: bytes, retryable_statuses) -> Decision:
    if status in retryable_statuses:
        return Decision(Action.RETRY, f"upstream_http_{status}")
    if status == 500 and structured_error_codes(body) & TRANSIENT_500_CODES:
        return Decision(Action.RETRY, "upstream_structured_internal_error")
    return Decision(Action.RETURN, "upstream_response")


def retryable_transport(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return False
    return isinstance(exc, (
        ConnectionError, TimeoutError, socket.gaierror, socket.timeout,
        http.client.RemoteDisconnected, http.client.IncompleteRead,
        http.client.BadStatusLine, http.client.LineTooLong,
    )) or (
        isinstance(exc, ssl.SSLError) and "certificate verify failed" not in str(exc).lower()
    ) or (isinstance(exc, OSError) and exc.errno in {
        errno.ECONNABORTED, errno.ECONNREFUSED, errno.ECONNRESET, errno.EHOSTUNREACH,
        errno.ENETDOWN, errno.ENETUNREACH, errno.EPIPE, errno.ETIMEDOUT,
    })
