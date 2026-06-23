"""Verify converter wiring (e.g. artifacts_path) without loading docling models.

We replace ``_get_converter`` with a fake that records the arguments it was
called with, so we can assert the configured artifacts path is forwarded.
"""

from __future__ import annotations

from app import converter as conv
from app.config import settings
from app.models import ConversionOptions, OutputFormat


class _FakeDoc:
    def export_to_markdown(self, image_mode=None):
        return "md-out"


class _FakeResult:
    document = _FakeDoc()


class _FakeConverter:
    def convert(self, src, **kw):
        return _FakeResult()


def test_convert_forwards_artifacts_path(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_get(**kwargs):
        captured.update(kwargs)
        return _FakeConverter()

    monkeypatch.setattr(conv, "_get_converter", fake_get)
    monkeypatch.setattr(settings, "docling_artifacts", "/opt/docling/models")

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    result = conv.convert(pdf, ConversionOptions(output_format=OutputFormat.markdown))

    assert captured["artifacts_path"] == "/opt/docling/models"
    assert result.content == "md-out"


def test_convert_forwards_ocr_languages(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_get(**kwargs):
        captured.update(kwargs)
        return _FakeConverter()

    monkeypatch.setattr(conv, "_get_converter", fake_get)
    monkeypatch.setattr(settings, "docling_artifacts", None)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions(do_ocr=True, ocr_languages=["ja", "en"]))

    assert captured["ocr_languages"] == ("ja", "en")


def test_convert_forwards_easyocr_models(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_get(**kwargs):
        captured.update(kwargs)
        return _FakeConverter()

    monkeypatch.setattr(conv, "_get_converter", fake_get)
    monkeypatch.setattr(settings, "easyocr_models", "/opt/easyocr-models")

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions(do_ocr=True, ocr_languages=["en"]))

    assert captured["easyocr_models"] == "/opt/easyocr-models"


def test_convert_artifacts_path_none_by_default(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_get(**kwargs):
        captured.update(kwargs)
        return _FakeConverter()

    monkeypatch.setattr(conv, "_get_converter", fake_get)
    monkeypatch.setattr(settings, "docling_artifacts", None)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions())

    assert captured["artifacts_path"] is None


class _CapturingConverter:
    """Records the kwargs passed to ``convert`` (e.g. page_range)."""

    def __init__(self, sink):
        self._sink = sink

    def convert(self, src, **kw):
        self._sink.update(kw)
        return _FakeResult()


def _convert_capturing(monkeypatch, path, options):
    convert_kwargs: dict = {}
    monkeypatch.setattr(conv, "_get_converter",
                        lambda **k: _CapturingConverter(convert_kwargs))
    monkeypatch.setattr(settings, "docling_artifacts", None)
    conv.convert(path, options)
    return convert_kwargs


def test_page_range_applied_for_pdf(tmp_path, monkeypatch):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    kw = _convert_capturing(monkeypatch, pdf,
                            ConversionOptions(page_start=2, page_end=5))
    assert kw["page_range"] == (2, 5)


def test_page_range_ignored_for_non_pdf(tmp_path, monkeypatch):
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"PK\x03\x04")  # zip magic; never actually parsed (fake)
    kw = _convert_capturing(monkeypatch, docx,
                            ConversionOptions(page_start=2, page_end=5))
    assert "page_range" not in kw
