"""Periodic background cleanup of expired documents and jobs.

A small daemon thread that, every ``interval`` seconds, asks the storage and
job manager to drop anything older than the TTL.  Kept dependency-free (stdlib
``threading`` only); the single-shot :meth:`PeriodicCleaner.sweep_once` is the
unit of work and is directly testable.
"""

from __future__ import annotations

import logging
from threading import Event, Thread

from .jobs import JobManager
from .storage import Storage

logger = logging.getLogger("pdfto.cleanup")


class PeriodicCleaner:
    """Runs :meth:`sweep_once` on a fixed interval in a daemon thread."""

    def __init__(self, storage: Storage, jobs: JobManager, ttl_seconds: float,
                 interval_seconds: float) -> None:
        self._storage = storage
        self._jobs = jobs
        self._ttl = ttl_seconds
        self._interval = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def sweep_once(self) -> dict[str, list[str]]:
        """Run one cleanup pass; never raises.

        Storage and job cleanup are independent: a failure in one does not skip
        the other.  Returns what was removed, for logging/testing.
        """

        result: dict[str, list[str]] = {"documents": [], "jobs": []}
        try:
            result["documents"] = self._storage.cleanup_expired(self._ttl)
        except Exception:  # noqa: BLE001
            logger.exception("document cleanup failed")
        try:
            result["jobs"] = self._jobs.cleanup_expired(self._ttl)
        except Exception:  # noqa: BLE001
            logger.exception("job cleanup failed")
        if result["documents"] or result["jobs"]:
            logger.info("cleanup removed %d documents, %d jobs",
                        len(result["documents"]), len(result["jobs"]))
        return result

    def _loop(self) -> None:
        # Wait first so we don't sweep immediately on startup.
        while not self._stop.wait(self._interval):
            self.sweep_once()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="pdfto-cleaner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
