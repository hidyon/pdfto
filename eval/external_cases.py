"""Eval cases backed by real internet documents (spec 0030 §9, spec 0031 §9).

These probe PDFto's limits on genuine documents.  The sample files are fetched
on demand by ``scripts/fetch_external_samples.py`` into ``samples/external/``
and are **not committed**; :func:`external_cases` returns only the cases whose
files are present, so everything degrades gracefully when nothing is fetched.

Several SROIE receipts are registered (not just one) so we can check whether an
OCR improvement *generalizes* across real photographed scans.  Each receipt's
ground-truth tokens are derived from its own ``*.key.json`` file, so the cases
stay honest and need no hand-curated expectations.

Include them in a report run with::

    python scripts/fetch_external_samples.py
    python -m eval.report --include-external
"""

from __future__ import annotations

import json
import pathlib
import re

from app.models import ConversionOptions, OutputFormat

from eval import metrics
from eval.cases import EvalCase

EXTERNAL = pathlib.Path(__file__).resolve().parents[1] / "samples" / "external"

SROIE_IDS = ["000", "001", "002", "003", "004", "005"]

# Known phrases present in a U.S. Form 1040 (ground truth by inspection).
IRS_1040_TOKENS = [
    "Filing Status", "Standard Deduction", "Adjusted gross income",
    "taxable income", "Qualified dividends", "Federal income tax",
    "Earned income credit", "Refund", "Amount You Owe", "Dependents",
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


def sroie_tokens(key_path: pathlib.Path) -> list[str]:
    """Ground-truth tokens for a SROIE receipt, derived from its key file.

    Company/address are split into words (length >= 3); date/total are kept
    verbatim.  Returns a de-duplicated, order-stable token list.
    """
    data = json.loads(key_path.read_text(encoding="utf-8"))
    tokens: list[str] = []
    for field in ("company", "address"):
        for word in re.split(r"[^0-9A-Za-z]+", data.get(field, "")):
            if len(word) >= 3 and word not in tokens:
                tokens.append(word)
    for field in ("date", "total"):
        value = str(data.get(field, "")).strip()
        if value and value not in tokens:
            tokens.append(value)
    return tokens


def _make_sroie_scorer(tokens: list[str]):
    def score(content: str) -> dict[str, float]:
        return {"token_recall": metrics.token_recall(content, tokens)}
    return score


def _all_external() -> list[EvalCase]:
    cases: list[EvalCase] = [
        EvalCase(
            name="irs_1040",
            sample=EXTERNAL / "f1040.pdf",
            options=ConversionOptions(
                output_format=OutputFormat.markdown, do_table_structure=True,
                page_start=1, page_end=2),
            score=_score_irs_1040,
            notes="Real complex tax form (born-digital); text vs table-structure.",
        ),
    ]
    # One case per SROIE receipt whose image AND ground-truth key are present
    # (tokens are derived from the key file, so both are required to define it).
    for rid in SROIE_IDS:
        img = EXTERNAL / f"sroie{rid}.jpg"
        key = EXTERNAL / f"sroie{rid}.key.json"
        if not (img.is_file() and key.is_file()):
            continue
        cases.append(EvalCase(
            name=f"sroie_{rid}",
            sample=img,
            options=ConversionOptions(output_format=OutputFormat.markdown, do_ocr=True),
            score=_make_sroie_scorer(sroie_tokens(key)),
            notes="Real photographed receipt (ICDAR SROIE); hard OCR case.",
        ))
    return cases


def external_cases() -> list[EvalCase]:
    """Return the external cases whose sample files have been fetched."""
    return [c for c in _all_external() if c.sample.is_file()]
