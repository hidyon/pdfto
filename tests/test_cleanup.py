"""Tests for TTL-based cleanup of documents and jobs."""

from __future__ import annotations

import time

from app.cleanup import PeriodicCleaner
from app.jobs import JobManager
from app.models import DocumentAnalysis, JobStatus, OutputFormat
from app.storage import Storage

PDF = b"%PDF-1.4 minimal"


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        page_count=1, has_extractable_text=True, likely_scanned=False,
        has_images=False, encrypted=False, file_size_bytes=len(PDF),
    )


def test_storage_removes_expired_keeps_fresh(tmp_path):
    s = Storage(tmp_path)
    old = s.create_document("old.pdf", PDF, _analysis())
    fresh = s.create_document("new.pdf", PDF, _analysis())
    # Age the first document well past the TTL.
    old.created_at = time.time() - 1000

    removed = s.cleanup_expired(ttl_seconds=60)

    assert old.id in removed
    assert s.get(old.id) is None
    assert not s.doc_dir(old.id).exists()
    assert s.get(fresh.id) is not None


def test_storage_removes_orphan_directories(tmp_path):
    s = Storage(tmp_path)
    orphan = tmp_path / "orphan"
    orphan.mkdir()
    (orphan / "source.pdf").write_bytes(PDF)
    # Make the orphan look old.
    old_time = time.time() - 1000
    import os
    os.utime(orphan, (old_time, old_time))

    removed = s.cleanup_expired(ttl_seconds=60)

    assert "orphan" in removed
    assert not orphan.exists()


def test_jobs_remove_expired_terminal_only():
    mgr = JobManager(max_workers=1)
    done = mgr.submit("doc", OutputFormat.markdown, lambda: {"preview": "ok"})
    # Wait for it to finish, then age it.
    deadline = time.time() + 3
    while time.time() < deadline and mgr.get(done.id).status != JobStatus.succeeded:
        time.sleep(0.01)
    assert mgr.get(done.id).status == JobStatus.succeeded
    mgr._jobs[done.id] = mgr.get(done.id).model_copy(
        update={"updated_at": time.time() - 1000}
    )

    removed = mgr.cleanup_expired(ttl_seconds=60)
    assert done.id in removed
    assert mgr.get(done.id) is None


def test_periodic_cleaner_sweep_once(tmp_path):
    s = Storage(tmp_path)
    mgr = JobManager(max_workers=1)
    old = s.create_document("old.pdf", PDF, _analysis())
    old.created_at = time.time() - 1000

    cleaner = PeriodicCleaner(s, mgr, ttl_seconds=60, interval_seconds=999)
    result = cleaner.sweep_once()

    assert old.id in result["documents"]
    assert s.get(old.id) is None
