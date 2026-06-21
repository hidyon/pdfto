"""Tests for persisted, retrying webhook delivery (WebhookDispatcher)."""

from __future__ import annotations

import time

from app import webhooks
from app.db import Database
from app.models import Job, JobStatus, OutputFormat


def _job(job_id="j1", status=JobStatus.succeeded) -> Job:
    now = time.time()
    return Job(id=job_id, document_id="d1", status=status,
               output_format=OutputFormat.markdown, created_at=now, updated_at=now,
               preview="ok")


def _make(tmp_path, max_attempts=3, base=10):
    db = Database(tmp_path / "pdfto.db")
    disp = webhooks.WebhookDispatcher(db, max_attempts=max_attempts,
                                      base_seconds=base, sweep_seconds=999)
    return db, disp


def test_enqueue_delivers_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(webhooks, "deliver", lambda *a, **k: True)
    _, disp = _make(tmp_path)
    disp.enqueue(_job(), "http://example.com/hook")
    row = disp.list_for_job("j1")[0]
    assert row["status"] == "delivered"
    assert row["attempts"] == 1


def test_failure_schedules_retry_then_succeeds(tmp_path, monkeypatch):
    state = {"ok": False}
    monkeypatch.setattr(webhooks, "deliver", lambda *a, **k: state["ok"])
    db, disp = _make(tmp_path)
    disp.enqueue(_job(), "http://example.com/hook")

    row = disp.list_for_job("j1")[0]
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["next_attempt_at"] > time.time()

    # Make it due and let the next attempt succeed.
    db.execute("UPDATE webhook_deliveries SET next_attempt_at=? WHERE id=?",
               (time.time() - 1, row["id"]))
    state["ok"] = True
    assert disp.sweep_once() == 1
    assert disp.list_for_job("j1")[0]["status"] == "delivered"


def test_exhausts_to_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(webhooks, "deliver", lambda *a, **k: False)
    db, disp = _make(tmp_path, max_attempts=2)
    disp.enqueue(_job(), "http://example.com/hook")  # attempt 1 -> pending
    row = disp.list_for_job("j1")[0]
    db.execute("UPDATE webhook_deliveries SET next_attempt_at=? WHERE id=?",
               (time.time() - 1, row["id"]))
    disp.sweep_once()  # attempt 2 -> failed
    final = disp.list_for_job("j1")[0]
    assert final["status"] == "failed"
    assert final["attempts"] == 2


def test_deliveries_persist_across_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(webhooks, "deliver", lambda *a, **k: False)
    _, disp = _make(tmp_path)
    disp.enqueue(_job(), "http://example.com/hook")

    # Reopen the same DB as a fresh dispatcher (restart-equivalent).
    db2 = Database(tmp_path / "pdfto.db")
    disp2 = webhooks.WebhookDispatcher(db2, max_attempts=3, base_seconds=10,
                                       sweep_seconds=999)
    rows = disp2.list_for_job("j1")
    assert rows and rows[0]["status"] == "pending"

    db2.execute("UPDATE webhook_deliveries SET next_attempt_at=? WHERE id=?",
                (time.time() - 1, rows[0]["id"]))
    monkeypatch.setattr(webhooks, "deliver", lambda *a, **k: True)
    assert disp2.sweep_once() == 1
    assert disp2.list_for_job("j1")[0]["status"] == "delivered"
