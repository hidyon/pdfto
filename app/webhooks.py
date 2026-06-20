"""Deliver job-completion notifications to a caller-supplied URL.

Standard library only.  Delivery is best-effort and synchronous (called from
the conversion worker thread): a single attempt with a timeout, and any failure
is logged rather than raised so it never affects the job's outcome.

SSRF is mitigated by :func:`check_url`: only http/https is allowed, and an
optional host allowlist further restricts where notifications may be sent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("pdfto.webhooks")


def check_url(url: str, allowed_hosts: set[str] | None = None) -> Optional[str]:
    """Validate a callback URL; return an error message, or ``None`` if OK."""
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return "invalid callback_url"
    if parsed.scheme not in ("http", "https"):
        return "callback_url must be http or https"
    if not parsed.hostname:
        return "callback_url has no host"
    if allowed_hosts:
        host = parsed.hostname
        ok = any(host == h or host.endswith("." + h) for h in allowed_hosts)
        if not ok:
            return "callback_url host is not allowed"
    return None


def sign(body: bytes, secret: str) -> str:
    """Return the hex HMAC-SHA256 of *body* under *secret*."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def deliver(url: str, payload: dict, *, secret: Optional[str] = None,
            timeout: float = 10) -> bool:
    """POST *payload* as JSON to *url*; return True on a 2xx response."""
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "pdfto-webhook"}
    if secret:
        headers["X-PDFTO-Signature"] = "sha256=" + sign(body, secret)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= resp.status < 300
        logger.info("webhook delivered", extra={"url": url, "ok": ok})
        return ok
    except Exception as exc:  # noqa: BLE001 - never propagate delivery errors
        logger.warning("webhook delivery failed: %s", exc, extra={"url": url})
        return False
