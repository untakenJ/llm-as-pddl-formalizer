"""Explicit OpenAI-compatible execution-node model origin (e.g. vLLM).

This is routing only: no prompt rewriting, hidden sampling defaults or retries.
The selected credential profile supplies the origin; model identity stays in
the benchmark profile. No ambient OPENAI_BASE_URL is consumed.
"""

from urllib.parse import urlsplit


def api_base(provider_options: dict | None) -> str:
    options = (provider_options or {}).get("self_hosted", {})
    if not isinstance(options, dict) or set(options) != {"base_url"}:
        raise ValueError("self-hosted requires self_hosted.base_url in its credential profile")
    value = options["base_url"]
    if not isinstance(value, str):
        raise ValueError("self_hosted.base_url must be a URL")
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path.rstrip("/") != "/v1"):
        raise ValueError("self_hosted.base_url must be an HTTP(S) /v1 origin without credentials")
    return value.rstrip("/")
