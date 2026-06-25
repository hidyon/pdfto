"""Eval cases backed by real internet documents (spec 0030 §9).

These probe PDFto's limits on genuine documents.  The sample files are fetched
on demand by ``scripts/fetch_external_samples.py`` into ``samples/external/``
and are **not committed**; :func:`external_cases` returns only the cases whose
files are present, so everything degrades gracefully when nothing is fetched.

Include them in a report run with::

    python scripts/fetch_external_samples.py
    python -m eval.report --include-external
"""

from __future__ import annotations

import pathlib

from app.models import ConversionOptions, OutputFormat

from eval import metrics
from eval.cases import EvalCase

EXTERNAL = pathlib.Path(__file__).resolve().parents[1] / "samples" / "external"

# Known phrases present in a U.S. Form 1040 (ground truth by inspection).
IRS_1040_TOKENS = [
    "Filing Status", "Standard Deduction", "Adjusted gross income",
    "taxable income", "Qualified dividends", "Federal income tax",
    "Earned income credit", "Refund", "Amount You Owe", "Dependents",
]

# Ground-truth key fields for the SROIE receipt (from sroie000.key.json),
# broken into tokens robust to OCR spacing.
SROIE_TOKENS = [
    "BOOK", "TAMAN", "DAYA", "SDN", "BHD", "JALAN", "SAGU",
    "JOHOR", "81100", "25/12/2018", "9.00", "TOTAL",
]


def _count_table_blocks(md: str) -> float:
    """Number of contiguous Markdown table blocks (rows containing '|')."""
    blocks, in_block = 0, False
    for line in md.splitlines():
        if "|" in line:
            if not in_block:
                blocks += 1
                in_block = True
        else:
            in_block = False
    return float(blocks)


def _score_irs_1040(content: str) -> dict[str, float]:
    return {
        "token_recall": metrics.token_recall(content, IRS_1040_TOKENS),
        "table_blocks": _count_table_blocks(content),
    }


def _score_sroie(content: str) -> dict[str, float]:
    return {"token_recall": metrics.token_recall(content, SROIE_TOKENS)}


def _all_external() -> list[EvalCase]:
    return [
        EvalCase(
            name="irs_1040",
            sample=EXTERNAL / "f1040.pdf",
            options=ConversionOptions(
                output_format=OutputFormat.markdown, do_table_structure=True,
                page_start=1, page_end=2),
            score=_score_irs_1040,
            notes="Real complex tax form (born-digital); text vs table-structure.",
        ),
        EvalCase(
            name="sroie_receipt",
            sample=EXTERNAL / "sroie000.jpg",
            options=ConversionOptions(output_format=OutputFormat.markdown, do_ocr=True),
            score=_score_sroie,
            notes="Real photographed receipt (ICDAR SROIE); hard OCR case.",
        ),
    ]


def external_cases() -> list[EvalCase]:
    """Return the external cases whose sample files have been fetched."""
    return [c for c in _all_external() if c.sample.is_file()]
