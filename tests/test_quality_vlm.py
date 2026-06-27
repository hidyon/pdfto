"""Opt-in real VLM conversion check (downloads a vision-language model).

The VLM pipeline loads a multi-hundred-MB model and runs it on the page images,
which is far heavier than the standard OCR tests, so it is gated behind its own
flag ``PDFTO_RUN_VLM_TESTS=1`` (separate from PDFTO_RUN_DOCLING_TESTS).  The
default ``pytest`` run never touches it; wiring is covered by test_vlm.py.
"""

from __future__ import annotations

import os
import pathlib

import pytest

RUN_VLM = os.environ.get("PDFTO_RUN_VLM_TESTS") == "1"
_SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "samples"

pytestmark = pytest.mark.skipif(
    not RUN_VLM, reason="set PDFTO_RUN_VLM_TESTS=1 to run the real VLM pipeline")


def test_vlm_converts_scanned_sample():
    """The local VLM pipeline converts a scanned PDF to non-empty text."""
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    result = convert(_SAMPLES / "scanned_sample.pdf", ConversionOptions(
        output_format=OutputFormat.markdown, use_vlm=True))
    assert isinstance(result.content, str)
    assert result.content.strip() != ""
