"""Background conversion jobs.

A small, single-process job runner: conversions are submitted to a
``ThreadPoolExecutor`` and tracked in an in-memory index keyed by job id.
Clients submit a job and poll :func:`JobManager.get` for its status.

This module is deliberately decoupled from the conversion core: callers pass a
``work`` callable that performs the actual conversion and returns the fields to
attach to a successful job.  Any exception it raises is captured and turns the
job ``failed`` (its message becomes ``Job.error``), so a bad conversion never
crashes the worker thread or the process.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Callable, Optional

from .logging_config import request_id_var
from .models import Job, JobStatus, OutputFormat

logger = logging.getLogger("pdfto.jobs")

# A unit of work returns the fields to merge into the job on success.
Work = Callable[[], dict]


class JobManager:
    """Thread-safe registry and executor for conversion jobs."""

    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def submit(self, document_id: str, output_format: OutputFormat,
               work: Work) -> Job:
        """Register a job and schedule *work* to run in the background."""

        now = time.time()
        job = Job(
            id=uuid.uuid4().hex,
            document_id=document_id,
            status=JobStatus.pending,
            output_format=output_format,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.id] = job
        # Capture the originating request id so the worker thread's logs can be
        # correlated back to the request that started the job.
        rid = request_id_var.get()
        logger.info("job submitted", extra={"job_id": job.id,
                                             "document_id": document_id})
        self._executor.submit(self._run, job.id, work, rid)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            updated = job.model_copy(update={**fields, "updated_at": time.time()})
            self._jobs[job_id] = updated

    def _run(self, job_id: str, work: Work, request_id: str = "-") -> None:
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

    def cleanup_expired(self, ttl_seconds: float) -> list[str]:
        """Drop finished jobs whose last update is older than *ttl_seconds*.

        Only terminal jobs (``succeeded``/``failed``) are eligible; in-flight
        jobs keep a recent ``updated_at`` and are left alone.
        """

        now = time.time()
        terminal = (JobStatus.succeeded, JobStatus.failed)
        with self._lock:
            expired = [
                jid for jid, job in self._jobs.items()
                if job.status in terminal and now - job.updated_at > ttl_seconds
            ]
            for jid in expired:
                del self._jobs[jid]
        return expired

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
