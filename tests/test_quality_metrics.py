"""Default (mocked, docling-free) tests for the quality-measurement foundation.

Covers the pure metric functions, the case registry's integrity, and the A/B
runner's wiring (with ``convert`` patched) — see spec 0030.  These run in the
default ``pytest`` because they touch no ML models.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from eval import metrics
from eval.cases import CASES, CASES_BY_NAME, EXPECTED_TABLE
from eval import report


# ---- metrics: parse_markdown_table -----------------------------------------

GOOD_TABLE_MD = """\
# Title

| Product | Q1 | Q2 |
| --- | --- | --- |
| Widget | 100 | 120 |
| Gadget | 90 | 85 |

trailing text
"""


def test_parse_markdown_table_drops_separator_and_normalises():
    rows = metrics.parse_markdown_table(GOOD_TABLE_MD)
    assert rows == [
        ["Product", "Q1", "Q2"],
        ["Widget", "100", "120"],
        ["Gadget", "90", "85"],
    ]


def test_parse_markdown_table_none_present():
    assert metrics.parse_markdown_table("no table here\njust prose") == []


def test_table_shape():
    assert metrics.table_shape(GOOD_TABLE_MD) == (3, 3)
    assert metrics.table_shape("no table") == (0, 0)


# ---- metrics: table_cell_recovery ------------------------------------------

def test_cell_recovery_perfect():
    md = (
        "| Product | Q1 | Q2 | Q3 |\n| - | - | - | - |\n"
        + "\n".join("| " + " | ".join(r) + " |" for r in EXPECTED_TABLE[1:])
    )
    assert metrics.table_cell_recovery(md, EXPECTED_TABLE) == 1.0


def test_cell_recovery_partial_and_missing():
    # Only the header row is present → 4 of 20 expected cells.
    md = "| Product | Q1 | Q2 | Q3 |\n| - | - | - | - |\n"
    assert metrics.table_cell_recovery(md, EXPECTED_TABLE) == pytest.approx(4 / 20)
    # No table at all → 0.0.
    assert metrics.table_cell_recovery("nothing", EXPECTED_TABLE) == 0.0


def test_cell_recovery_rejects_empty_expectation():
    with pytest.raises(ValueError):
        metrics.table_cell_recovery("x", [])


# ---- metrics: table_value_recall -------------------------------------------

def test_table_value_recall_is_position_agnostic():
    # Same values as GOOD_TABLE_MD but order/position differs — still recalled.
    assert metrics.table_value_recall(GOOD_TABLE_MD, ["Widget", "85", "Q2"]) == 1.0
    assert metrics.table_value_recall(GOOD_TABLE_MD, ["Widget", "absent"]) == 0.5
    assert metrics.table_value_recall("no table", ["x"]) == 0.0


def test_table_value_recall_rejects_empty():
    with pytest.raises(ValueError):
        metrics.table_value_recall("x", [])


# ---- metrics: token_recall -------------------------------------------------

def test_token_recall_case_insensitive_substring():
    text = "The quick brown FOX. Invoice 12345."
    assert metrics.token_recall(text, ["fox", "invoice", "12345"]) == 1.0
    assert metrics.token_recall(text, ["fox", "missing"]) == 0.5


def test_token_recall_rejects_empty_tokens():
    with pytest.raises(ValueError):
        metrics.token_recall("x", [])


# ---- case registry integrity -----------------------------------------------

def test_case_registry_is_consistent():
    assert CASES, "no cases registered"
    assert set(CASES_BY_NAME) == {c.name for c in CASES}
    assert len(CASES_BY_NAME) == len(CASES), "duplicate case names"


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_case_sample_exists_and_scores(case):
    assert case.sample.is_file(), f"missing sample for {case.name}"
    # Every scorer returns a dict of floats and tolerates empty output.
    scores = case.score("")
    assert scores and all(isinstance(v, float) for v in scores.values())


def test_base_options_is_an_independent_copy():
    case = CASES[0]
    a = case.base_options()
    a.image_scale = 3.5
    assert case.options.image_scale != 3.5  # mutating the copy left the case intact


# ---- A/B runner wiring (convert patched) -----------------------------------

def test_run_applies_variants_and_scores():
    """run() converts each case under each variant; verify wiring without docling."""
    table_doc = CASES_BY_NAME["table_doc"]
    perfect_md = (
        "| Product | Q1 | Q2 | Q3 |\n| - | - | - | - |\n"
        + "\n".join("| " + " | ".join(r) + " |" for r in EXPECTED_TABLE[1:])
    )

    seen: list[bool] = []

    class _Result:
        content = perfect_md

    def fake_convert(path, opts):
        seen.append(opts.do_cell_matching)  # record the knob the variant set
        return _Result()

    with patch("app.converter.convert", side_effect=fake_convert):
        results = report.run([table_doc], ["baseline", "no_cell_match"])

    assert [r.variant for r in results] == ["baseline", "no_cell_match"]
    assert seen == [True, False]  # no_cell_match flipped the knob
    assert all(r.scores["cell_recovery"] == 1.0 for r in results)


def test_unknown_variant_raises():
    with pytest.raises(KeyError):
        report._apply_variant(CASES[0], "does_not_exist")


def test_format_compare_shows_delta():
    results = [
        report.CaseResult("c", "baseline", {"token_recall": 0.5}),
        report.CaseResult("c", "force_ocr", {"token_recall": 0.9}),
    ]
    out = report.format_compare(results, "baseline", "force_ocr")
    assert "+0.400" in out
    assert "force_ocr - baseline" in out
