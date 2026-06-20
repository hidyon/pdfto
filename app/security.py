"""API key extraction and in-memory rate limiting.

Both are opt-in and applied by middleware in :mod:`app.main` to ``/api/v1/*``
only.  The rate limiter is a simple fixed-window counter keyed by identity
(API key when auth is on, otherwise client IP); state is per-process, matching
the single-instance execution model.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Optional


def extract_api_key(headers) -> Optional[str]:
    """Return the API key from ``X-API-Key`` or ``Authorization: Bearer``."""
    key = headers.get("x-api-key")
    if key:
        return key.strip()
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


class RateLimiter:
    """Fixed-window request counter, keyed by an opaque identity string."""

    def __init__(self) -> None:
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def check(self, identity: str, limit: int, window: float) -> tuple[bool, int]:
        """Record a hit; return (allowed, retry_after_seconds).

        ``limit <= 0`` disables limiting (always allowed).
        """
        if limit <= 0:
            return True, 0
        now = time.time()
        with self._lock:
            start, count = self._hits.get(identity, (now, 0))
            if now - start >= window:
                start, count = now, 0
            count += 1
            self._hits[identity] = (start, count)
            if count > limit:
                retry_after = int(window - (now - start)) + 1
                return False, retry_after
        return True, 0
