"""Unit tests for the background JobManager."""

from __future__ import annotations

import time

from app.db import Database
from app.jobs import JobManager
from app.models import JobStatus, OutputFormat


def _mgr(tmp_path):
    return JobManager(max_workers=1, db=Database(tmp_path / "pdfto.db"))


def _wait(mgr, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = mgr.get(job_id)
        if job and job.status in (JobStatus.succeeded, JobStatus.failed):
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_successful_job_carries_result_fields(tmp_path):
    mgr = _mgr(tmp_path)
    job = mgr.submit("doc1", OutputFormat.markdown,
                     lambda: {"download_url": "/x", "preview": "hi", "truncated": False})
    assert job.status == JobStatus.pending
    done = _wait(mgr, job.id)
    assert done.status == JobStatus.succeeded
    assert done.download_url == "/x"
    assert done.preview == "hi"


def test_failing_work_marks_failed_without_crashing(tmp_path):
    mgr = _mgr(tmp_path)

    def boom():
        raise RuntimeError("kaboom")

    job = mgr.submit("doc1", OutputFormat.markdown, boom)
    done = _wait(mgr, job.id)
    assert done.status == JobStatus.failed
    assert "kaboom" in done.error


def test_unknown_job_is_none(tmp_path):
    mgr = _mgr(tmp_path)
    assert mgr.get("missing") is None
