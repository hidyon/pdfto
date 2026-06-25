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
]

CASES_BY_NAME: dict[str, EvalCase] = {c.name: c for c in CASES}
