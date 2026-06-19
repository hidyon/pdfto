"""Runtime configuration, read from the environment."""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Application settings with environment overrides.

    Attributes are read once at import time; override via environment variables
    prefixed with ``PDFTO_``.
    """

    def __init__(self) -> None:
        self.data_dir = Path(os.environ.get("PDFTO_DATA_DIR", "data"))
        self.max_upload_mb = int(os.environ.get("PDFTO_MAX_UPLOAD_MB", "50"))
        # Number of characters returned inline in conversion previews.
        self.preview_chars = int(os.environ.get("PDFTO_PREVIEW_CHARS", "4000"))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
