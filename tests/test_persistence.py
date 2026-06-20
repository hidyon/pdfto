"""Tests that state survives 'restarts' (re-opening the same database)."""

from __future__ import annotations

import time

from app.db import Database
from app.jobs import JobManager
from app.models import DocumentAnalysis, JobStatus, OutputFormat
from app.storage import Storage

PDF = b"%PDF-1.4 minimal"


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        page_count=2, has_extractable_text=True, likely_scanned=False,
        has_images=False, encrypted=False, file_size_bytes=len(PDF),
    )


def test_document_survives_reopen(tmp_path):
    s1 = Storage(tmp_path)
    rec = s1.create_document("doc.pdf", PDF, _analysis())
    s1.add_output(rec.id, "# hi", OutputFormat.markdown, "md")

    # Simulate a restart: a brand new Storage over the same directory/db.
    s2 = Storage(tmp_path)
    again = s2.get(rec.id)
    assert again is not None
    assert again.filename == "doc.pdf"
    assert again.analysis.page_count == 2
    out = s2.get_output(rec.id, "markdown")
    assert out is not None and out.filename == "doc.md"


def test_finished_job_survives_reopen(tmp_path):
    store = Storage(tmp_path)
    mgr1 = JobManager(max_workers=1, db=store.db)
    job = mgr1.submit("doc", OutputFormat.markdown, lambda: {"preview": "done"})
    deadline = time.time() + 3
    while time.time() < deadline and mgr1.get(job.id).status != JobStatus.succeeded:
        time.sleep(0.01)
    assert mgr1.get(job.id).status == JobStatus.succeeded

    # Re-open over the same db file.
    store2 = Storage(tmp_path)
    mgr2 = JobManager(max_workers=1, db=store2.db)
    again = mgr2.get(job.id)
    assert again is not None
    assert again.status == JobStatus.succeeded
    assert again.preview == "done"


def test_interrupted_jobs_recovered_to_failed(tmp_path):
    store = Storage(tmp_path)
    # Insert a job stuck in 'running' as if the process had died mid-conversion.
    now = time.time()
    store.db.execute(
        "INSERT INTO jobs (id, document_id, status, output_format, created_at,"
        " updated_at, truncated) VALUES ('j1', 'd1', 'running', 'markdown', ?, ?, 0)",
        (now, now),
    )
    # Starting a JobManager over this db recovers it.
    mgr = JobManager(max_workers=1, db=store.db)
    job = mgr.get("j1")
    assert job.status == JobStatus.failed
    assert "interrupted" in job.error
