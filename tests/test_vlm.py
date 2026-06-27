"""Tests for the VLM pipeline wiring (spec 0034), docling models never loaded.

``DocumentConverter`` and the VLM pipeline class are real imports, but no model
is downloaded: we stub ``DocumentConverter`` to capture the format options, so
these run in the default suite.
"""

from __future__ import annotations

import pytest

from app import converter as conv
from app.config import settings
from app.models import ConversionOptions, OutputFormat


class _FakeDoc:
    def export_to_markdown(self, image_mode=None):
        return "vlm-md"


class _FakeResult:
    document = _FakeDoc()


def _stub_document_converter(monkeypatch):
    """Stub docling.document_converter.DocumentConverter; capture format_options."""
    import docling.document_converter as dc

    captured: dict = {}

    class _Stub:
        def __init__(self, format_options=None):
            captured["format_options"] = format_options

        def convert(self, source, **kw):
            captured["source"] = source
            return _FakeResult()

    monkeypatch.setattr(dc, "DocumentConverter", _Stub)
    return captured


def test_vlm_converter_uses_vlm_pipeline_local(monkeypatch):
    from docling.datamodel.base_models import InputFormat
    from docling.pipeline.vlm_pipeline import VlmPipeline

    captured = _stub_document_converter(monkeypatch)
    conv._get_vlm_converter.cache_clear()
    conv._get_vlm_converter(model="granite_docling", api_url=None, api_key=None,
                            api_model=None, timeout=300)
    conv._get_vlm_converter.cache_clear()

    fmts = captured["format_options"]
    assert InputFormat.PDF in fmts and InputFormat.IMAGE in fmts
    for fmt in (InputFormat.PDF, InputFormat.IMAGE):
        assert fmts[fmt].pipeline_cls is VlmPipeline
    # A local run does not enable remote services.
    assert fmts[InputFormat.PDF].pipeline_options.enable_remote_services is False


def test_vlm_converter_api_mode(monkeypatch):
    from docling.datamodel.base_models import InputFormat

    captured = _stub_document_converter(monkeypatch)
    conv._get_vlm_converter.cache_clear()
    conv._get_vlm_converter(
        model="granite_docling", api_url="https://vlm.example/v1/chat/completions",
        api_key="secret", api_model="some-vlm", timeout=99)
    conv._get_vlm_converter.cache_clear()

    po = captured["format_options"][InputFormat.PDF].pipeline_options
    assert po.enable_remote_services is True
    assert str(po.vlm_options.url).startswith("https://vlm.example")
    assert po.vlm_options.headers.get("Authorization") == "Bearer secret"


def test_vlm_unknown_model_raises(monkeypatch):
    _stub_document_converter(monkeypatch)
    conv._get_vlm_converter.cache_clear()
    with pytest.raises(conv.ConversionError):
        conv._get_vlm_converter(model="nope", api_url=None, api_key=None,
                                api_model=None, timeout=300)
    conv._get_vlm_converter.cache_clear()


def test_convert_routes_to_vlm_when_use_vlm(tmp_path, monkeypatch):
    """convert() uses the VLM converter (and not the standard one) when use_vlm."""
    called: dict = {}

    class _FakeConverter:
        def convert(self, source, **kw):
            return _FakeResult()

    def fake_vlm(**kwargs):
        called["vlm"] = kwargs
        return _FakeConverter()

    def fake_std(**kwargs):
        called["std"] = kwargs
        return _FakeConverter()

    monkeypatch.setattr(conv, "_get_vlm_converter", fake_vlm)
    monkeypatch.setattr(conv, "_get_converter", fake_std)
    monkeypatch.setattr(settings, "vlm_model", "granite_docling")

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = conv.convert(pdf, ConversionOptions(
        output_format=OutputFormat.markdown, use_vlm=True))

    assert out.content == "vlm-md"
    assert "vlm" in called and "std" not in called      # routed to VLM only
    assert called["vlm"]["model"] == "granite_docling"


def test_convert_uses_standard_pipeline_by_default(tmp_path, monkeypatch):
    called: dict = {}

    class _StdConv:
        def convert(self, source, **kw):
            return _FakeResult()

    def fake_vlm(**k):
        called["vlm"] = k
        return _StdConv()

    def fake_std(**k):
        called["std"] = k
        return _StdConv()

    monkeypatch.setattr(conv, "_get_vlm_converter", fake_vlm)
    monkeypatch.setattr(conv, "_get_converter", fake_std)
    monkeypatch.setattr(settings, "docling_artifacts", None)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    conv.convert(pdf, ConversionOptions())
    assert "std" in called and "vlm" not in called
