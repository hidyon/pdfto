"""Regression evaluation cases: sample + expectation + scorer (spec 0030).

A case pairs a bundled sample with the metrics that judge its conversion.  The
registry is declarative data; running the conversions lives in ``report.py`` and
the opt-in tests.  Importing this module does **not** pull in docling — only the
lightweight ``app.models`` for the output-format/options types.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Callable

from app.models import ConversionOptions, OutputFormat

from eval import metrics

SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "samples"

# Mirrors scripts/make_sample_pdfs.py::make_table_doc_sample.
EXPECTED_TABLE = [
    ["Product", "Q1", "Q2", "Q3"],
    ["Widget", "100", "120", "140"],
    ["Gadget", "90", "85", "95"],
    ["Gizmo", "60", "75", "80"],
    ["Doohickey", "45", "50", "55"],
]

# Mirrors scripts/make_sample_pdfs.py::make_scanned_sample (distinctive phrases).
SCANNED_TOKENS = ["fox", "lazy dog", "invoice", "12345"]

# Mirrors scripts/make_sample_pdfs.py::make_prose_sample.
PROSE_TOKENS = [
    "PDFto",
    "born-digital",
    "Reykjavik",
    "photosynthesis",
    "42 kilometres",
    "quarterly",
]

# Mirrors scripts/make_sample_pdfs.py::make_complex_table_sample.  Merged-cell
# layout has no well-defined flat positions, so we measure value recall (did
# each datum survive) rather than strict per-position recovery.
COMPLEX_TABLE_VALUES = [
    "Region", "H1 2026", "H2 2026", "Q1", "Q2", "Q3", "Q4",
    "North", "South", "East", "West",
    "120", "135", "150", "160", "90", "95", "100", "110",
    "70", "80", "85", "60", "65", "75",
]

# Mirrors scripts/make_sample_pdfs.py::make_noisy_scan_sample (degraded scan).
NOISY_SCAN_TOKENS = [
    "Monthly", "Statement", "Account", "Anderson",
    "quick", "brown", "fox", "lazy", "dog",
    "Balance", "Total", "payment",
]


@dataclass(frozen=True)
class EvalCase:
    """One regression case: which sample, how to convert it, how to score it."""

    name: str
    sample: pathlib.Path
    options: ConversionOptions
    score: Callable[[str], dict[str, float]]
    notes: str = field(default="")

    def base_options(self) -> ConversionOptions:
        """A fresh copy of this case's options (so variants can override it)."""
        return self.options.model_copy(deep=True)


def _score_table_doc(content: str) -> dict[str, float]:
    rows, cols = metrics.table_shape(content)
    return {
        "cell_recovery": metrics.table_cell_recovery(content, EXPECTED_TABLE),
        "rows": float(rows),
        "cols": float(cols),
    }


def _score_scanned(content: str) -> dict[str, float]:
    return {"token_recall": metrics.token_recall(content, SCANNED_TOKENS)}


def _score_prose(content: str) -> dict[str, float]:
    return {"token_recall": metrics.token_recall(content, PROSE_TOKENS)}


def _score_complex_table(content: str) -> dict[str, float]:
    rows, cols = metrics.table_shape(content)
    return {
        "value_recall": metrics.table_value_recall(content, COMPLEX_TABLE_VALUES),
        "rows": float(rows),
        "cols": float(cols),
    }


def _score_noisy_scan(content: str) -> dict[str, float]:
    return {"token_recall": metrics.token_recall(content, NOISY_SCAN_TOKENS)}


CASES: list[EvalCase] = [
    EvalCase(
        name="table_doc",
        sample=SAMPLES / "table_doc_sample.pdf",
        options=ConversionOptions(
            output_format=OutputFormat.markdown, do_table_structure=True),
        score=_score_table_doc,
        notes="Document-style ruled table; expects full cell recovery (5x4).",
    ),
    EvalCase(
        name="scanned",
        sample=SAMPLES / "scanned_sample.pdf",
        options=ConversionOptions(output_format=OutputFormat.markdown, do_ocr=True),
        score=_score_scanned,
        notes="Image-only page; OCR must recover the known phrases.",
    ),
    EvalCase(
        name="prose",
        sample=SAMPLES / "prose_sample.pdf",
        options=ConversionOptions(output_format=OutputFormat.markdown),
        score=_score_prose,
        notes="Born-digital prose; measures body-text fidelity.",
    ),
    EvalCase(
        name="complex_table",
        sample=SAMPLES / "complex_table_sample.pdf",
        options=ConversionOptions(
            output_format=OutputFormat.markdown, do_table_structure=True),
        score=_score_complex_table,
        notes="Merged-cell header (column/row spans); measures data survival.",
    ),
    EvalCase(
        name="noisy_scan",
        sample=SAMPLES / "noisy_scan_sample.pdf",
        options=ConversionOptions(output_format=OutputFormat.markdown, do_ocr=True),
        score=_score_noisy_scan,
        notes="Degraded scan (skew/blur/noise/low-res); OCR robustness.",
    ),
]

CASES_BY_NAME: dict[str, EvalCase] = {c.name: c for c in CASES}
