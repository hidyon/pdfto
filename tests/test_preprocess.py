"""Tests for OCR image preprocessing (spec 0032).

The preprocessing function itself runs real OpenCV on a tiny synthetic image
(no ML models), and the converter wiring is checked with docling stubbed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app import converter as conv
from app.config import settings
from app.models import ConversionOptions
from app.preprocess import PreprocessError, preprocess_image_for_ocr


def _make_image(path: Path, size=(40, 60)) -> None:
    import cv2

    img = np.full((size[1], size[0]), 200, dtype=np.uint8)
    cv2.rectangle(img, (5, 5), (30, 20), 0, -1)  # a dark block to survive binarize
    cv2.imwrite(str(path), img)


def test_preprocess_upscales_and_binarizes(tmp_path):
    src = tmp_path / "scan.png"
    _make_image(src, size=(40, 60))
    out = preprocess_image_for_ocr(src, tmp_path / "pp")

    import cv2

    assert out.is_file() and out != src
    res = cv2.imread(str(out), cv2.IMREAD_GRAYSCALE)
    assert res.shape == (120, 80)                    # 2x upscale of (60,40)
    assert set(np.unique(res)).issubset({0, 255})    # adaptive threshold output
    # The source is untouched.
    assert cv2.imread(str(src), cv2.IMREAD_GRAYSCALE).shape == (60, 40)


def test_preprocess_unreadable_raises(tmp_path):
    bad = tmp_path / "notimage.png"
    bad.write_bytes(b"not a real image")
    with pytest.raises(PreprocessError):
        preprocess_image_for_ocr(bad, tmp_path / "pp")


# ---- converter wiring -------------------------------------------------------

class _FakeDoc:
    def export_to_markdown(self, image_mode=None):
        return "md-out"


class _FakeResult:
    document = _FakeDoc()


def _capture_convert_source(monkeypatch, src: Path, options: ConversionOptions):
    """Return the path string docling was asked to convert."""
    seen: dict = {}

    class _FakeConverter:
        def convert(self, source, **kw):
            seen["source"] = source
            return _FakeResult()

    monkeypatch.setattr(conv, "_get_converter", lambda **k: _FakeConverter())
    monkeypatch.setattr(settings, "docling_artifacts", None)
    conv.convert(src, options)
    return seen["source"]


def test_image_preprocessed_before_ocr(tmp_path, monkeypatch):
    src = tmp_path / "receipt.png"
    _make_image(src)
    source = _capture_convert_source(
        monkeypatch, src, ConversionOptions(do_ocr=True, ocr_preprocess=True))
    assert source.endswith("_pp.png")            # docling got the preprocessed file
    assert source != str(src)


def test_no_preprocess_when_disabled(tmp_path, monkeypatch):
    src = tmp_path / "receipt.png"
    _make_image(src)
    source = _capture_convert_source(
        monkeypatch, src, ConversionOptions(do_ocr=True, ocr_preprocess=False))
    assert source == str(src)


def test_no_preprocess_without_ocr(tmp_path, monkeypatch):
    src = tmp_path / "receipt.png"
    _make_image(src)
    source = _capture_convert_source(
        monkeypatch, src, ConversionOptions(do_ocr=False, ocr_preprocess=True))
    assert source == str(src)


def test_no_preprocess_for_non_image(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    source = _capture_convert_source(
        monkeypatch, pdf, ConversionOptions(do_ocr=True, ocr_preprocess=True))
    assert source == str(pdf)                     # PDFs are not preprocessed
