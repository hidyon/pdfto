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
