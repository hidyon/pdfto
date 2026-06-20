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
        # Maximum number of files accepted in one batch request.
        self.max_batch_files = int(os.environ.get("PDFTO_MAX_BATCH_FILES", "20"))
        # Number of characters returned inline in conversion previews.
        self.preview_chars = int(os.environ.get("PDFTO_PREVIEW_CHARS", "4000"))
        # Maximum number of conversions running concurrently.
        self.max_workers = int(os.environ.get("PDFTO_MAX_WORKERS", "2"))
        # How long uploads/outputs/finished jobs are kept before deletion.
        self.ttl_minutes = int(os.environ.get("PDFTO_TTL_MINUTES", "60"))
        # How often the background cleaner runs.
        self.sweep_interval_seconds = int(
            os.environ.get("PDFTO_SWEEP_INTERVAL_SECONDS", "300")
        )
        # Local directory holding pre-downloaded docling models (baked into the
        # Docker image). When unset, docling uses its default cache.
        self.docling_artifacts = os.environ.get("PDFTO_DOCLING_ARTIFACTS") or None
        # Logging.
        self.log_level = os.environ.get("PDFTO_LOG_LEVEL", "INFO").upper()
        self.log_format = os.environ.get("PDFTO_LOG_FORMAT", "text").lower()
        # API key auth (opt-in): comma-separated keys. Empty = auth disabled.
        self.api_keys = {
            k.strip() for k in os.environ.get("PDFTO_API_KEYS", "").split(",")
            if k.strip()
        }
        # Rate limiting (requests per window). 0 disables.
        self.rate_limit = int(os.environ.get("PDFTO_RATE_LIMIT", "60"))
        self.rate_window_seconds = int(
            os.environ.get("PDFTO_RATE_WINDOW_SECONDS", "60")
        )
        # Webhooks (job completion callbacks).
        self.webhook_secret = os.environ.get("PDFTO_WEBHOOK_SECRET") or None
        self.webhook_timeout = int(os.environ.get("PDFTO_WEBHOOK_TIMEOUT", "10"))
        self.webhook_allowed_hosts = {
            h.strip() for h in os.environ.get("PDFTO_WEBHOOK_ALLOWED_HOSTS", "").split(",")
            if h.strip()
        }

    @property
    def webhooks_signed(self) -> bool:
        return bool(self.webhook_secret)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_keys)

    @property
    def rate_limit_enabled(self) -> bool:
        return self.rate_limit > 0

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def ttl_seconds(self) -> float:
        return self.ttl_minutes * 60

    @property
    def cleanup_enabled(self) -> bool:
        return self.ttl_minutes > 0


settings = Settings()
