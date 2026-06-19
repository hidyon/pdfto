"""Tests for the lightweight PDF analysis."""

from __future__ import annotations

from tempfile import NamedTemporaryFile

from app.analysis import analyze_pdf


def _analyze(data: bytes):
    with NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(data)
        tmp.flush()
        return analyze_pdf(tmp.name)


def test_counts_pages_and_detects_text(text_pdf):
    a = _analyze(text_pdf)
    assert a.page_count == 2
    assert a.has_extractable_text is True
    assert a.likely_scanned is False
    assert a.file_size_bytes > 0


def test_detects_likely_scanned(scanned_pdf):
    a = _analyze(scanned_pdf)
    assert a.page_count == 2
    assert a.likely_scanned is True
