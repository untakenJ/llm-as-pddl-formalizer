"""Load project-local ``.env`` files (``python-dotenv``).

Looks for ``_private/.env`` and ``_private/gemini.env`` under the repo root.
Project env files override inherited shell values, matching
``agent_formalizer.util.load_private_secrets``.

Gemini in this repo uses **Gemini Enterprise Agent Platform / Vertex** via a
Google Cloud API key::

    GOOGLE_CLOUD_API_KEY=your-cloud-api-key
    GOOGLE_CLOUD_PROJECT=your-project-id
    GOOGLE_CLOUD_LOCATION=global
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

_dotenv_loaded = False


def load_project_dotenv() -> bool:
    """Load gitignored env files from ``_private/``. Returns True if any file loaded."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return True

    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    loaded_any = False
    private = ROOT_DIR / "_private"
    # Load legacy gemini.env first, then .env, so _private/.env remains the
    # highest-priority project credential source.
    for name in ("gemini.env", ".env"):
        path = private / name
        if path.is_file():
            load_dotenv(path, override=True)
            loaded_any = True

    # If project/location are set but the enterprise flag is missing, enable it.
    if os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip() and not os.environ.get(
        "GOOGLE_GENAI_USE_ENTERPRISE", ""
    ).strip():
        os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"

    _dotenv_loaded = True
    return loaded_any
