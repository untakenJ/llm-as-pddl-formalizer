"""Load project-local ``.env`` files (``python-dotenv``).

Looks for ``_private/.env`` and ``_private/gemini.env`` under the repo root.
Existing shell environment variables are not overwritten (``override=False``).

Gemini in this repo uses **Gemini Enterprise Agent Platform** only (ADC)::

    GOOGLE_GENAI_USE_ENTERPRISE=true
    GOOGLE_CLOUD_PROJECT=your-project-id
    GOOGLE_CLOUD_LOCATION=global

Authenticate with ``gcloud auth application-default login`` or
``GOOGLE_APPLICATION_CREDENTIALS``.
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
    for name in (".env", "gemini.env"):
        path = private / name
        if path.is_file():
            load_dotenv(path, override=False)
            loaded_any = True

    # If project/location are set but the enterprise flag is missing, enable it.
    if os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip() and not os.environ.get(
        "GOOGLE_GENAI_USE_ENTERPRISE", ""
    ).strip():
        os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"

    _dotenv_loaded = True
    return loaded_any
