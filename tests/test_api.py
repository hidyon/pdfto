"""End-to-end tests of the REST API with the conversion core mocked.

We mock :func:`app.converter.convert` so the API contract (upload → questions →
convert → download) is verified without pulling in docling's heavy ML models.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.converter import ConvertedDocument
from app.models import OutputFormat


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate storage to a temp dir for each test.
    from app.storage import Storage
    monkeypatch.setattr(main, "storage", Storage(tmp_path))

    def fake_convert(pdf_path, options, image_dir=None):
        return ConvertedDocument(
            content=f"# Converted\nformat={options.output_format.value}",
            output_format=options.output_format,
            suggested_extension={"markdown": "md", "html": "html",
                                 "json": "json", "text": "txt"}[options.output_format.value],
        )

    monkeypatch.setattr(main, "convert", fake_convert)
    return TestClient(main.app)


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

    # 2. convert
    r = client.post(f"/api/v1/documents/{doc_id}/convert",
                    json={"output_format": "markdown"})
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["output_format"] == "markdown"
    assert "# Converted" in result["preview"]
    assert result["download_url"].endswith("format=markdown")

    # 3. download
    r = client.get(result["download_url"])
    assert r.status_code == 200
    assert b"# Converted" in r.content


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
