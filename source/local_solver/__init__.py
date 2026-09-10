"""Lightweight, planning.domains-compatible local solver backend."""

from __future__ import annotations

PUBLIC_SOLVER_BASE_URL = "https://solver.planning.domains:5001"
LOCAL_SOLVER_HOST_BASE_URL = "http://127.0.0.1:8769"
LOCAL_SOLVER_CONTAINER_BASE_URL = "http://host.docker.internal:8769"
DEFAULT_IMAGE = "pddl-local-solver:planutils-v1"
DEFAULT_SOLVER_BACKEND = "local"
SUPPORTED_BACKENDS = frozenset({"public", "local", "public_then_local"})


def base_urls_for_backend(backend: str) -> tuple[str, str]:
    """Return ``(host_url, container_sidecar_url)`` for a named backend."""
    if backend in {"public", "public_then_local"}:
        return PUBLIC_SOLVER_BASE_URL, PUBLIC_SOLVER_BASE_URL
    if backend == "local":
        return LOCAL_SOLVER_HOST_BASE_URL, LOCAL_SOLVER_CONTAINER_BASE_URL
    raise ValueError(
        f"unsupported solver backend {backend!r}; expected one of "
        + ", ".join(sorted(SUPPORTED_BACKENDS))
    )


def fallback_url_for_backend(backend: str, *, containerized: bool = False) -> str | None:
    """Local fallback is opt-in; existing public/local modes never switch."""
    base_urls_for_backend(backend)  # Reject unknown modes, not silent public-only.
    if backend == "public_then_local":
        return LOCAL_SOLVER_CONTAINER_BASE_URL if containerized else LOCAL_SOLVER_HOST_BASE_URL
    return None


__all__ = [
    "DEFAULT_IMAGE",
    "DEFAULT_SOLVER_BACKEND",
    "LOCAL_SOLVER_CONTAINER_BASE_URL",
    "LOCAL_SOLVER_HOST_BASE_URL",
    "PUBLIC_SOLVER_BASE_URL",
    "SUPPORTED_BACKENDS",
    "base_urls_for_backend",
    "fallback_url_for_backend",
]
