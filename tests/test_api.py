"""End-to-end tests of the REST API with the conversion core mocked.

We mock :func:`app.converter.convert` so the API contract (upload → questions →
convert → download) is verified without pulling in docling's heavy ML models.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.converter import ConversionError, ConvertedDocument
from app.jobs import JobManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate storage and a fresh single-worker job manager for each test.
    from app.storage import Storage
    monkeypatch.setattr(main, "storage", Storage(tmp_path))
    monkeypatch.setattr(main, "jobs", JobManager(max_workers=1))

    def fake_convert(pdf_path, options, image_dir=None):
        return ConvertedDocument(
            content=f"# Converted\nformat={options.output_format.value}",
            output_format=options.output_format,
            suggested_extension={"markdown": "md", "html": "html",
                                 "json": "json", "text": "txt"}[options.output_format.value],
        )

    monkeypatch.setattr(main, "convert", fake_convert)
    return TestClient(main.app)


def _wait_for_job(client, job_id, timeout=5.0):
    """Poll a job until it leaves pending/running, like a real client would."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/jobs/{job_id}")
        assert r.status_code == 200, r.text
        job = r.json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_rejects_non_pdf(client):
    r = client.post("/api/v1/documents",
                    files={"file": ("a.txt", b"not a pdf", "text/plain")})
    assert r.status_code in (415, 400)


def test_full_flow(client, text_pdf):
    # 1. upload
    r = client.post("/api/v1/documents",
                    files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    doc_id = body["id"]
    assert body["analysis"]["page_count"] == 2
    assert any(q["id"] == "output_format" for q in body["questions"])

    # 2. start conversion -> a job, not the result
    r = client.post(f"/api/v1/documents/{doc_id}/convert",
                    json={"output_format": "markdown"})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] in ("pending", "running", "succeeded")
    assert job["output_format"] == "markdown"

    # 3. poll until finished
    job = _wait_for_job(client, job["id"])
    assert job["status"] == "succeeded"
    assert "# Converted" in job["preview"]
    assert job["download_url"].endswith("format=markdown")

    # 4. download
    r = client.get(job["download_url"])
    assert r.status_code == 200
    assert b"# Converted" in r.content


def test_failed_conversion_marks_job_failed(client, text_pdf, monkeypatch):
    def boom(pdf_path, options, image_dir=None):
        raise ConversionError("boom: bad pdf")
    monkeypatch.setattr(main, "convert", boom)

    r = client.post("/api/v1/documents",
                    files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = r.json()["id"]
    r = client.post(f"/api/v1/documents/{doc_id}/convert", json={})
    assert r.status_code == 202
    job = _wait_for_job(client, r.json()["id"])
    assert job["status"] == "failed"
    assert "boom" in job["error"]


def test_unknown_job_404(client):
    r = client.get("/api/v1/jobs/nope")
    assert r.status_code == 404


def test_request_id_header_present_and_echoed(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Request-ID")

    r2 = client.get("/api/health", headers={"X-Request-ID": "my-trace-1"})
    assert r2.headers.get("X-Request-ID") == "my-trace-1"


def test_unhandled_error_returns_clean_500(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(main.storage, "get", boom)

    # Let the app's exception handler produce the response instead of TestClient
    # re-raising the error.
    raw = TestClient(main.app, raise_server_exceptions=False)
    r = raw.get("/api/v1/documents/anything")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "internal server error"
    assert body["request_id"]
    assert "kaboom" not in r.text  # internals are not leaked
    assert r.headers.get("X-Request-ID")


def test_download_before_convert_404(client, text_pdf):
    r = client.post("/api/v1/documents",
                    files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = r.json()["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/download?format=markdown")
    assert r.status_code == 404


def test_oneshot_convert(client, text_pdf):
    r = client.post("/api/v1/convert?output_format=text",
                    files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    assert b"format=text" in r.content


def test_unknown_document_404(client):
    r = client.post("/api/v1/documents/does-not-exist/convert", json={})
    assert r.status_code == 404
