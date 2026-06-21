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
import time
import urllib.request
import uuid
from threading import Event, Thread
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


class WebhookDispatcher:
    """Persisted, retrying webhook delivery backed by SQLite.

    A completed job's notification is recorded in ``webhook_deliveries`` and
    attempted immediately; failures are retried with exponential backoff by a
    background sweep thread, so a briefly-unavailable receiver doesn't lose the
    notification (and deliveries survive a restart).
    """

    def __init__(self, db, *, secret: Optional[str] = None, timeout: float = 10,
                 max_attempts: int = 5, base_seconds: float = 10,
                 sweep_seconds: float = 30) -> None:
        self._db = db
        self._secret = secret
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._base = base_seconds
        self._interval = sweep_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    # -- public ------------------------------------------------------------- #
    def enqueue(self, job, url: str) -> str:
        """Record a delivery for *job* to *url* and attempt it once now."""
        event = "job.succeeded" if job.status.value == "succeeded" else "job.failed"
        payload = json.dumps({"event": event, "job": job.model_dump()},
                             ensure_ascii=False, default=str)
        now = time.time()
        delivery_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO webhook_deliveries (id, job_id, url, event, payload,"
            " status, attempts, max_attempts, next_attempt_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)",
            (delivery_id, job.id, url, event, payload, self._max_attempts, now, now, now),
        )
        row = self._db.query_one(
            "SELECT * FROM webhook_deliveries WHERE id = ?", (delivery_id,)
        )
        self._attempt(row)
        return delivery_id

    def sweep_once(self) -> int:
        """Attempt all due pending deliveries; return how many were tried."""
        now = time.time()
        rows = self._db.query(
            "SELECT * FROM webhook_deliveries WHERE status = 'pending'"
            " AND (next_attempt_at IS NULL OR next_attempt_at <= ?)",
            (now,),
        )
        for row in rows:
            try:
                self._attempt(row)
            except Exception:  # noqa: BLE001 - keep sweeping other deliveries
                logger.exception("webhook sweep failed", extra={"id": row["id"]})
        return len(rows)

    def list_for_job(self, job_id: str) -> list[dict]:
        rows = self._db.query(
            "SELECT * FROM webhook_deliveries WHERE job_id = ? ORDER BY created_at",
            (job_id,),
        )
        return [dict(r) for r in rows]

    # -- internals ---------------------------------------------------------- #
    def _attempt(self, row) -> None:
        attempts = row["attempts"] + 1
        ok = deliver(row["url"], json.loads(row["payload"]),
                     secret=self._secret, timeout=self._timeout)
        now = time.time()
        if ok:
            self._db.execute(
                "UPDATE webhook_deliveries SET status='delivered', attempts=?,"
                " next_attempt_at=NULL, last_error=NULL, updated_at=? WHERE id=?",
                (attempts, now, row["id"]),
            )
            return
        if attempts >= row["max_attempts"]:
            self._db.execute(
                "UPDATE webhook_deliveries SET status='failed', attempts=?,"
                " next_attempt_at=NULL, last_error=?, updated_at=? WHERE id=?",
                (attempts, "delivery failed", now, row["id"]),
            )
            return
        delay = self._base * (2 ** (attempts - 1))
        self._db.execute(
            "UPDATE webhook_deliveries SET status='pending', attempts=?,"
            " next_attempt_at=?, last_error=?, updated_at=? WHERE id=?",
            (attempts, now + delay, "delivery failed", now, row["id"]),
        )

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.sweep_once()
            except Exception:  # noqa: BLE001
                logger.exception("webhook dispatcher loop error")

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="pdfto-webhooks", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
