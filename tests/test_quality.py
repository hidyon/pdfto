"""Opt-in end-to-end conversion check on a real sample PDF.

This runs the actual docling pipeline (which downloads ML models), so it is
skipped unless PDFTO_RUN_DOCLING_TESTS=1.  It is a smoke test: it asserts the
pipeline converts the bundled table sample without error and returns non-empty
output.  Strict table-structure assertions are intentionally avoided because
table detection on synthetic PDFs is model-dependent (see spec 0012).
"""

from __future__ import annotations

import os
import pathlib

import pytest

RUN = os.environ.get("PDFTO_RUN_DOCLING_TESTS") == "1"
SAMPLE = pathlib.Path(__file__).resolve().parents[1] / "samples" / "table_sample.pdf"

pytestmark = pytest.mark.skipif(
    not RUN, reason="set PDFTO_RUN_DOCLING_TESTS=1 to run real docling conversions"
)


def test_sample_pdf_exists():
    assert SAMPLE.is_file()


@pytest.mark.parametrize("table_mode", ["accurate", "fast"])
def test_table_sample_converts(table_mode):
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat, TableMode

    opts = ConversionOptions(
        output_format=OutputFormat.markdown,
        do_ocr=True,
        do_table_structure=True,
        table_mode=TableMode(table_mode),
    )
    result = convert(SAMPLE, opts)
    assert isinstance(result.content, str)
    assert result.content.strip() != ""
