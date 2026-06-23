"""Opt-in end-to-end conversion check on a real sample PDF.

This runs the actual docling pipeline (which downloads ML models), so it is
skipped unless PDFTO_RUN_DOCLING_TESTS=1.  It is a smoke test: it asserts the
pipeline converts the bundled table sample without error and returns non-empty
output.  Strict table-structure assertions are intentionally avoided because
table detection on synthetic PDFs is model-dependent (see spec 0012).
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

RUN = os.environ.get("PDFTO_RUN_DOCLING_TESTS") == "1"
_SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "samples"
SAMPLE = _SAMPLES / "table_sample.pdf"
TABLE_DOC = _SAMPLES / "table_doc_sample.pdf"
SCANNED = _SAMPLES / "scanned_sample.pdf"

# Must match scripts/make_sample_pdfs.py::make_table_doc_sample.
EXPECTED_TABLE = [
    ["Product", "Q1", "Q2", "Q3"],
    ["Widget", "100", "120", "140"],
    ["Gadget", "90", "85", "95"],
    ["Gizmo", "60", "75", "80"],
    ["Doohickey", "45", "50", "55"],
]


def parse_markdown_table(md: str) -> list[list[str]]:
    """Return the first Markdown table as rows of stripped cells.

    The ``|---|`` separator row is dropped; cell whitespace is normalised so
    docling's column padding doesn't affect comparisons.
    """
    rows: list[list[str]] = []
    for line in md.splitlines():
        if "|" not in line:
            if rows:
                break  # table ended
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-:") and c for c in cells):
            continue  # separator row
        rows.append([" ".join(c.split()) for c in cells])
    return rows

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


@pytest.mark.parametrize("fmt", ["markdown", "html", "json", "text"])
def test_table_sample_all_formats(fmt):
    """Every output format exports without error and is well-formed.

    The table sample is classified as a Picture (see spec 0012), so plain-text
    export of this image-only page is legitimately empty — only the structured
    formats are asserted non-empty.
    """
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    result = convert(SAMPLE, ConversionOptions(output_format=OutputFormat(fmt)))
    assert isinstance(result.content, str)
    if fmt == "json":
        json.loads(result.content)              # valid JSON document tree
    elif fmt == "html":
        assert "<" in result.content
    elif fmt == "markdown":
        assert result.content.strip() != ""     # at least the image placeholder
    # text: export_to_text() of an image-only page can be empty; the assertion
    # above (returns a str without raising) is the meaningful check here.


def test_page_range_converts():
    """A page-range restricted conversion runs and returns output."""
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    result = convert(SAMPLE, ConversionOptions(
        output_format=OutputFormat.markdown, page_start=1, page_end=1))
    assert result.content.strip() != ""


def test_table_doc_quality():
    """The document-style table is extracted with full cell recovery.

    Quality metric: parse the Markdown table and assert its shape (4 columns,
    5 data rows incl. header) and a cell-recovery ratio of 1.0 against the
    known expected values.
    """
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    result = convert(TABLE_DOC, ConversionOptions(
        output_format=OutputFormat.markdown, do_table_structure=True))
    table = parse_markdown_table(result.content)

    assert table, "no Markdown table found in output"
    assert len(table) == len(EXPECTED_TABLE), f"row count: {len(table)}"
    assert all(len(r) == 4 for r in table), f"column counts: {[len(r) for r in table]}"

    expected_cells = {(r, c) for r, row in enumerate(EXPECTED_TABLE)
                      for c in range(len(row))}
    found = sum(
        1 for (r, c) in expected_cells
        if r < len(table) and c < len(table[r])
        and table[r][c] == EXPECTED_TABLE[r][c]
    )
    recovery = found / len(expected_cells)
    assert recovery == 1.0, f"cell recovery {recovery:.2f}: got {table}"


def test_html_input_converts(tmp_path):
    """A non-PDF input (HTML) converts to Markdown with its table recovered."""
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    html = tmp_path / "doc.html"
    html.write_text(
        "<html><body><h1>Heading</h1><p>Body text.</p>"
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        "</body></html>",
        encoding="utf-8",
    )
    result = convert(html, ConversionOptions(output_format=OutputFormat.markdown))
    assert "Heading" in result.content
    assert "|" in result.content  # the table survived as a Markdown table


def test_scanned_sample_exists():
    assert SCANNED.is_file()


def test_ocr_reads_scanned_pdf():
    """OCR on an image-only PDF recovers the text; without OCR it does not."""
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    with_ocr = convert(SCANNED, ConversionOptions(
        output_format=OutputFormat.markdown, do_ocr=True))
    text = with_ocr.content.lower()
    assert "fox" in text
    assert "invoice" in text

    without_ocr = convert(SCANNED, ConversionOptions(
        output_format=OutputFormat.markdown, do_ocr=False))
    assert "fox" not in without_ocr.content.lower()
