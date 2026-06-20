"""Background conversion jobs, persisted in SQLite.

Conversions are submitted to a ``ThreadPoolExecutor`` and tracked in the shared
:class:`~app.db.Database`, so job state survives process restarts.  Jobs that
were still ``pending``/``running`` when the process died are recovered to
``failed`` on startup (their worker threads are gone).

The module stays decoupled from the conversion core: callers pass a ``work``
callable that performs the conversion and returns the fields to attach to a
successful job.  Any exception it raises turns the job ``failed`` (its message
becomes ``Job.error``) instead of crashing the worker.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from .config import settings
from .db import Database
from .logging_config import request_id_var
from .models import Job, JobStatus, OutputFormat
from .webhooks import deliver

logger = logging.getLogger("pdfto.jobs")

# A unit of work returns the fields to merge into the job on success.
Work = Callable[[], dict]

# Columns a job update is allowed to touch.
_UPDATABLE = {"status", "output_format", "download_url", "filename",
              "preview", "truncated", "error"}


def _row_to_job(row) -> Job:
    return Job(
        id=row["id"],
        document_id=row["document_id"],
        status=JobStatus(row["status"]),
        output_format=OutputFormat(row["output_format"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        download_url=row["download_url"],
        filename=row["filename"],
        preview=row["preview"],
        truncated=bool(row["truncated"]),
        error=row["error"],
    )


class JobManager:
    """Executor + SQLite-backed registry for conversion jobs."""

    def __init__(self, max_workers: int, db: Database) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._db = db
        self.recover_interrupted()

    def recover_interrupted(self) -> int:
        """Mark jobs left running by a previous process as failed."""
        rows = self._db.query(
            "SELECT id FROM jobs WHERE status IN ('pending', 'running')"
        )
        if rows:
            self._db.execute(
                "UPDATE jobs SET status = 'failed', error = 'interrupted by restart',"
                " updated_at = ? WHERE status IN ('pending', 'running')",
                (time.time(),),
            )
            logger.warning("recovered %d interrupted jobs", len(rows))
        return len(rows)

    def submit(self, document_id: str, output_format: OutputFormat,
               work: Work, callback_url: Optional[str] = None) -> Job:
        """Register a job and schedule *work* to run in the background.

        If *callback_url* is given, a completion webhook is POSTed there once
        the job finishes (best-effort; failures are logged, not raised).
        """

        now = time.time()
        job = Job(
            id=uuid.uuid4().hex,
            document_id=document_id,
            status=JobStatus.pending,
            output_format=output_format,
            created_at=now,
            updated_at=now,
        )
        self._db.execute(
            "INSERT INTO jobs (id, document_id, status, output_format,"
            " created_at, updated_at, truncated) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (job.id, document_id, job.status.value, output_format.value, now, now),
        )
        rid = request_id_var.get()
        logger.info("job submitted", extra={"job_id": job.id,
                                             "document_id": document_id})
        self._executor.submit(self._run, job.id, work, rid, callback_url)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        row = self._db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return _row_to_job(row) if row is not None else None

    def _update(self, job_id: str, **fields) -> None:
        sets = ["updated_at = ?"]
        params: list = [time.time()]
        for key, value in fields.items():
            if key not in _UPDATABLE:
                continue
            if isinstance(value, JobStatus):
                value = value.value
            if isinstance(value, OutputFormat):
                value = value.value
            if isinstance(value, bool):
                value = int(value)
            sets.append(f"{key} = ?")
            params.append(value)
        params.append(job_id)
        self._db.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", tuple(params))

    def _run(self, job_id: str, work: Work, request_id: str = "-",
             callback_url: Optional[str] = None) -> None:
        request_id_var.set(request_id)
        started = time.perf_counter()
        self._update(job_id, status=JobStatus.running)
        try:
            result = work() or {}
            self._update(job_id, status=JobStatus.succeeded, **result)
            logger.info("job succeeded", extra={
                "job_id": job_id, "status": "succeeded",
                "duration_ms": round((time.perf_counter() - started) * 1000)})
        except Exception as exc:  # noqa: BLE001 - never let a job kill the worker
            self._update(job_id, status=JobStatus.failed, error=str(exc))
            logger.exception("job failed", extra={
                "job_id": job_id, "status": "failed",
                "duration_ms": round((time.perf_counter() - started) * 1000)})

        if callback_url:
            self._notify(job_id, callback_url)

    def _notify(self, job_id: str, callback_url: str) -> None:
        """Deliver a completion webhook; never affects the job outcome."""
        job = self.get(job_id)
        if job is None:
            return
        event = "job.succeeded" if job.status is JobStatus.succeeded else "job.failed"
        deliver(
            callback_url,
            {"event": event, "job": job.model_dump()},
            secret=settings.webhook_secret,
            timeout=settings.webhook_timeout,
        )

    def cleanup_expired(self, ttl_seconds: float) -> list[str]:
        """Drop finished jobs whose last update is older than *ttl_seconds*."""
        now = time.time()
        rows = self._db.query(
            "SELECT id FROM jobs WHERE status IN ('succeeded', 'failed')"
            " AND ? - updated_at > ?",
            (now, ttl_seconds),
        )
        ids = [row["id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            self._db.execute(
                f"DELETE FROM jobs WHERE id IN ({placeholders})", tuple(ids)
            )
        return ids

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
