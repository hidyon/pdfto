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


def test_quality_knobs_forwarded(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_get(**kwargs):
        captured.update(kwargs)
        return _FakeConverter()

    monkeypatch.setattr(conv, "_get_converter", fake_get)
    monkeypatch.setattr(settings, "docling_artifacts", None)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions(
        do_ocr=True, force_full_page_ocr=True,
        do_cell_matching=False, image_scale=3.0))

    assert captured["force_full_page_ocr"] is True
    assert captured["do_cell_matching"] is False
    assert captured["image_scale"] == 3.0


def test_quality_knobs_defaults(tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(conv, "_get_converter",
                        lambda **k: captured.update(k) or _FakeConverter())
    monkeypatch.setattr(settings, "docling_artifacts", None)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions())

    assert captured["force_full_page_ocr"] is False
    assert captured["do_cell_matching"] is True
    assert captured["image_scale"] == 2.0
    assert captured["ocr_confidence_threshold"] is None


def test_ocr_confidence_threshold_forwarded(tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(conv, "_get_converter",
                        lambda **k: captured.update(k) or _FakeConverter())
    monkeypatch.setattr(settings, "docling_artifacts", None)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions(do_ocr=True, ocr_confidence_threshold=0.1))

    assert captured["ocr_confidence_threshold"] == 0.1


def test_get_converter_sets_easyocr_confidence(monkeypatch):
    """_get_converter applies the threshold onto the EasyOCR options.

    docling's DocumentConverter is stubbed so no models load; EasyOcrOptions is
    real, and we capture the pipeline_options handed to PdfFormatOption.
    """
    import docling.document_converter as dc

    captured: dict = {}

    class _StubConverter:
        def __init__(self, format_options=None):
            captured["format_options"] = format_options

    monkeypatch.setattr(dc, "DocumentConverter", _StubConverter)
    conv._get_converter.cache_clear()
    conv._get_converter(
        do_ocr=True, do_table_structure=False, table_mode="accurate",
        generate_images=False, force_full_page_ocr=False,
        ocr_confidence_threshold=0.1)
    conv._get_converter.cache_clear()

    from docling.datamodel.base_models import InputFormat

    fmts = captured["format_options"]
    # The OCR options must reach BOTH pdf and image inputs (image inputs
    # otherwise fall back to docling defaults and ignore the threshold).
    assert InputFormat.PDF in fmts and InputFormat.IMAGE in fmts
    for fmt in (InputFormat.PDF, InputFormat.IMAGE):
        po = fmts[fmt].pipeline_options
        assert po.ocr_options.confidence_threshold == 0.1
        assert po.ocr_options.lang == ["en"]


def test_ocr_confidence_threshold_range_validated():
    import pytest
    from pydantic import ValidationError

    for bad in (-0.1, 1.5):
        with pytest.raises(ValidationError):
            ConversionOptions(ocr_confidence_threshold=bad)
    # In-range and None are accepted.
    assert ConversionOptions(ocr_confidence_threshold=0.0).ocr_confidence_threshold == 0.0
    assert ConversionOptions().ocr_confidence_threshold is None


def test_relativize_asset_links():
    from pathlib import Path

    ad = Path("/tmp/abc123/assets")
    md = f"# Doc\n\n![img]({ad}/img_000.png)\n"
    assert conv._relativize_asset_links(md, ad) == "# Doc\n\n![img](assets/img_000.png)\n"

    html = f'<p>x</p><img src="{ad}/pic.png">'
    assert conv._relativize_asset_links(html, ad) == '<p>x</p><img src="assets/pic.png">'

    # Already-relative content is left untouched.
    rel = "![img](assets/img_000.png)"
    assert conv._relativize_asset_links(rel, ad) == rel
