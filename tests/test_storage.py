"""Storage behaviour for multi-format sources (extension preservation)."""

from __future__ import annotations

from app.models import DocumentAnalysis
from app.storage import Storage

DATA = b"binary-source-bytes"


def _analysis() -> DocumentAnalysis:
    return DocumentAnalysis(
        page_count=1, has_extractable_text=True, likely_scanned=False,
        has_images=False, encrypted=False, file_size_bytes=len(DATA),
    )


def test_source_saved_with_real_extension(tmp_path):
    store = Storage(tmp_path)
    rec = store.create_document("slides.pptx", DATA, _analysis())
    assert rec.source_path.name == "source.pptx"
    assert rec.source_path.read_bytes() == DATA
    # Survives a reopen and round-trips the path.
    again = Storage(tmp_path).get(rec.id)
    assert again is not None and again.source_path.name == "source.pptx"


def test_pdf_default_extension(tmp_path):
    store = Storage(tmp_path)
    rec = store.create_document("doc.pdf", DATA, _analysis())
    assert rec.source_path.name == "source.pdf"


def test_missing_extension_defaults_to_pdf(tmp_path):
    store = Storage(tmp_path)
    rec = store.create_document("noext", DATA, _analysis())
    assert rec.source_path.name == "source.pdf"
