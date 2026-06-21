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
    # Isolate storage and a fresh single-worker job manager for each test,
    # sharing one SQLite database.
    from app.security import RateLimiter
    from app.storage import Storage
    from app.webhooks import WebhookDispatcher
    store = Storage(tmp_path)
    monkeypatch.setattr(main, "storage", store)
    dispatcher = WebhookDispatcher(store.db, max_attempts=3, base_seconds=10,
                                   sweep_seconds=999)
    monkeypatch.setattr(main, "webhook_dispatcher", dispatcher)
    monkeypatch.setattr(main, "jobs",
                        JobManager(max_workers=1, db=store.db, dispatcher=dispatcher))
    monkeypatch.setattr(main, "rate_limiter", RateLimiter())

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


def test_list_documents(client, text_pdf):
    ids = []
    for name in ("a.pdf", "b.pdf"):
        r = client.post("/api/v1/documents",
                        files={"file": (name, text_pdf, "application/pdf")})
        ids.append(r.json()["id"])
    listing = client.get("/api/v1/documents").json()
    listed_ids = {d["id"] for d in listing}
    assert set(ids) <= listed_ids
    assert all({"id", "filename", "created_at", "page_count"} <= d.keys()
               for d in listing)


def test_list_jobs_and_status_filter(client, text_pdf):
    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    job = client.post(f"/api/v1/documents/{doc_id}/convert", json={})
    job_id = job.json()["id"]
    _wait_for_job(client, job_id)

    all_jobs = client.get("/api/v1/jobs").json()
    assert any(j["id"] == job_id for j in all_jobs)

    succeeded = client.get("/api/v1/jobs?status=succeeded").json()
    assert any(j["id"] == job_id for j in succeeded)
    assert all(j["status"] == "succeeded" for j in succeeded)

    failed = client.get("/api/v1/jobs?status=failed").json()
    assert all(j["id"] != job_id for j in failed)


def test_listing_validates_limit(client):
    assert client.get("/api/v1/documents?limit=0").status_code == 422
    assert client.get("/api/v1/documents?limit=201").status_code == 422
    assert client.get("/api/v1/jobs?offset=-1").status_code == 422


def test_llm_postprocess_applied(client, text_pdf, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "key")
    monkeypatch.setattr(main.llm, "transform",
                        lambda content, instruction, **kw: f"LLM[{instruction}]")

    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    job = client.post(f"/api/v1/documents/{doc_id}/convert",
                      json={"output_format": "markdown", "llm_instruction": "summarize"})
    final = _wait_for_job(client, job.json()["id"])
    assert final["status"] == "succeeded"
    assert final["preview"] == "LLM[summarize]"


def test_llm_failure_marks_job_failed(client, text_pdf, monkeypatch):
    from app.config import settings
    from app.llm import LLMError
    monkeypatch.setattr(settings, "anthropic_api_key", "key")

    def boom(content, instruction, **kw):
        raise LLMError("llm down")
    monkeypatch.setattr(main.llm, "transform", boom)

    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    job = client.post(f"/api/v1/documents/{doc_id}/convert",
                      json={"llm_instruction": "summarize"})
    final = _wait_for_job(client, job.json()["id"])
    assert final["status"] == "failed"
    assert "llm down" in final["error"]


def test_llm_ignored_when_disabled(client, text_pdf, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    # transform must NOT be called when disabled.
    monkeypatch.setattr(main.llm, "transform",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))

    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    job = client.post(f"/api/v1/documents/{doc_id}/convert",
                      json={"llm_instruction": "summarize"})
    final = _wait_for_job(client, job.json()["id"])
    assert final["status"] == "succeeded"
    assert "# Converted" in final["preview"]


def test_batch_convert_flow(client, text_pdf):
    files = [
        ("files", ("a.pdf", text_pdf, "application/pdf")),
        ("files", ("b.pdf", text_pdf, "application/pdf")),
    ]
    r = client.post("/api/v1/batches?output_format=markdown", files=files)
    assert r.status_code == 202, r.text
    batch = r.json()
    assert batch["count"] == 2
    assert len(batch["items"]) == 2
    assert all(item["job_id"] and item["document_id"] for item in batch["items"])

    # Each job finishes and its document is downloadable.
    for item in batch["items"]:
        job = _wait_for_job(client, item["job_id"])
        assert job["status"] == "succeeded"
        d = client.get(f"/api/v1/documents/{item['document_id']}/download?format=markdown")
        assert d.status_code == 200

    # Aggregate status endpoint.
    g = client.get(f"/api/v1/batches/{batch['id']}")
    assert g.status_code == 200
    agg = g.json()
    assert agg["count"] == 2
    assert {i["status"] for i in agg["items"]} == {"succeeded"}


def test_batch_unknown_404(client):
    assert client.get("/api/v1/batches/nope").status_code == 404


def test_batch_rejects_too_many_files(client, text_pdf, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_batch_files", 1)
    files = [
        ("files", ("a.pdf", text_pdf, "application/pdf")),
        ("files", ("b.pdf", text_pdf, "application/pdf")),
    ]
    r = client.post("/api/v1/batches", files=files)
    assert r.status_code == 422


def test_batch_rejects_non_pdf(client, text_pdf):
    files = [
        ("files", ("a.pdf", text_pdf, "application/pdf")),
        ("files", ("b.txt", b"not a pdf", "text/plain")),
    ]
    r = client.post("/api/v1/batches", files=files)
    assert r.status_code in (400, 415)


def test_referenced_images_assets_and_zip(client, text_pdf, monkeypatch):
    # Fake a referenced-mode conversion that produces an image asset.
    def fake_convert(pdf_path, options, image_dir=None):
        return ConvertedDocument(
            content="# Doc\n\n![img](assets/img_000.png)\n",
            output_format=options.output_format,
            suggested_extension="md",
            assets={"img_000.png": b"PNGBYTES"},
        )
    monkeypatch.setattr(main, "convert", fake_convert)

    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    job = client.post(f"/api/v1/documents/{doc_id}/convert",
                      json={"output_format": "markdown", "image_mode": "referenced"})
    _wait_for_job(client, job.json()["id"])

    # Asset is served.
    a = client.get(f"/api/v1/documents/{doc_id}/assets/img_000.png")
    assert a.status_code == 200
    assert a.content == b"PNGBYTES"

    # Path traversal is rejected.
    bad = client.get(f"/api/v1/documents/{doc_id}/assets/..%2Fsource.pdf")
    assert bad.status_code in (400, 404)

    # Zip bundle contains the output and the asset.
    import io
    import zipfile
    z = client.get(f"/api/v1/documents/{doc_id}/download?format=markdown&bundle=zip")
    assert z.status_code == 200
    assert z.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "doc.md" in names
    assert "assets/img_000.png" in names


def test_webhook_delivery_recorded(client, text_pdf, monkeypatch):
    from app import webhooks
    monkeypatch.setattr(webhooks, "deliver", lambda *a, **k: True)

    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    job = client.post(
        f"/api/v1/documents/{doc_id}/convert?callback_url=https://example.com/hook",
        json={"output_format": "markdown"})
    job_id = job.json()["id"]
    _wait_for_job(client, job_id)

    r = client.get(f"/api/v1/jobs/{job_id}/deliveries")
    assert r.status_code == 200
    deliveries = r.json()
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "delivered"
    assert deliveries[0]["url"] == "https://example.com/hook"


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


def test_convert_accepts_ocr_languages(client, text_pdf):
    up = client.post("/api/v1/documents",
                     files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    doc_id = up.json()["id"]
    r = client.post(f"/api/v1/documents/{doc_id}/convert",
                    json={"do_ocr": True, "ocr_languages": ["ja", "en"]})
    assert r.status_code == 202, r.text


def test_oneshot_accepts_ocr_languages(client, text_pdf):
    r = client.post("/api/v1/convert?output_format=markdown&ocr_languages=ja&ocr_languages=en",
                    files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    assert r.status_code == 200, r.text


def test_oneshot_accepts_table_mode(client, text_pdf):
    r = client.post("/api/v1/convert?table_mode=fast",
                    files={"file": ("doc.pdf", text_pdf, "application/pdf")})
    assert r.status_code == 200, r.text


def test_batch_accepts_table_mode(client, text_pdf):
    files = [("files", ("a.pdf", text_pdf, "application/pdf"))]
    r = client.post("/api/v1/batches?table_mode=accurate", files=files)
    assert r.status_code == 202, r.text


def test_unknown_document_404(client):
    r = client.post("/api/v1/documents/does-not-exist/convert", json={})
    assert r.status_code == 404
