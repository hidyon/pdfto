"""Tests for webhook delivery, signing, and URL validation."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from app import jobs as jobs_module
from app import main
from app.config import settings
from app.jobs import JobManager
from app.models import OutputFormat
from app.security import RateLimiter
from app.storage import Storage
from app.webhooks import check_url, deliver, sign


# -- check_url -------------------------------------------------------------- #
def test_check_url_accepts_http_and_https():
    assert check_url("http://example.com/hook") is None
    assert check_url("https://example.com/hook") is None


def test_check_url_rejects_other_schemes():
    assert check_url("file:///etc/passwd") is not None
    assert check_url("ftp://example.com") is not None


def test_check_url_host_allowlist():
    allowed = {"example.com"}
    assert check_url("https://example.com/h", allowed) is None
    assert check_url("https://api.example.com/h", allowed) is None  # suffix
    assert check_url("https://evil.test/h", allowed) is not None


def test_sign_is_stable():
    assert sign(b"body", "secret") == sign(b"body", "secret")
    assert sign(b"body", "secret") != sign(b"body", "other")


# -- deliver against a real local server ------------------------------------ #
class _Capture(BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _Capture.received = {
            "body": body,
            "signature": self.headers.get("X-PDFTO-Signature"),
            "content_type": self.headers.get("Content-Type"),
        }
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def webhook_server():
    server = HTTPServer(("127.0.0.1", 0), _Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Capture.received = {}
    yield f"http://127.0.0.1:{server.server_port}/hook"
    server.shutdown()


def test_deliver_posts_signed_payload(webhook_server):
    ok = deliver(webhook_server, {"event": "job.succeeded", "job": {"id": "1"}},
                 secret="s3cret", timeout=5)
    assert ok
    rec = _Capture.received
    assert rec["content_type"] == "application/json"
    assert json.loads(rec["body"])["event"] == "job.succeeded"
    assert rec["signature"] == "sha256=" + sign(rec["body"], "s3cret")


def test_deliver_unreachable_returns_false_without_raising():
    # Nothing listening on this port.
    assert deliver("http://127.0.0.1:9/hook", {"x": 1}, timeout=1) is False


# -- job triggers delivery -------------------------------------------------- #
def test_job_completion_calls_deliver(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(jobs_module, "deliver",
                        lambda url, payload, **kw: calls.append((url, payload)) or True)

    store = Storage(tmp_path)
    mgr = JobManager(max_workers=1, db=store.db)
    job = mgr.submit("doc", OutputFormat.markdown, lambda: {"preview": "ok"},
                     callback_url="http://example.com/hook")
    deadline = time.time() + 3
    while time.time() < deadline and not calls:
        time.sleep(0.01)
    assert calls, "deliver was not called"
    url, payload = calls[0]
    assert url == "http://example.com/hook"
    assert payload["event"] == "job.succeeded"
    assert payload["job"]["id"] == job.id


# -- API validation --------------------------------------------------------- #
def test_convert_rejects_bad_callback_url(tmp_path, monkeypatch, text_pdf):
    store = Storage(tmp_path)
    monkeypatch.setattr(main, "storage", store)
    monkeypatch.setattr(main, "jobs", JobManager(max_workers=1, db=store.db))
    monkeypatch.setattr(main, "rate_limiter", RateLimiter())
    client = TestClient(main.app)

    up = client.post("/api/v1/documents",
                     files={"file": ("d.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    r = client.post(f"/api/v1/documents/{doc_id}/convert?callback_url=ftp://x",
                    json={})
    assert r.status_code == 422
