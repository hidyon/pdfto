"""Default tests for the gated external eval cases (spec 0030 §9).

No network and no docling: only that the registry degrades gracefully and the
scorers are well-formed.  The real conversions are run manually after
``scripts/fetch_external_samples.py`` (see eval/external_cases.py).
"""

from __future__ import annotations

from eval import external_cases as ext


def test_external_cases_only_returns_present_files():
    # Whatever is/ isn't fetched, every returned case must have its file.
    for case in ext.external_cases():
        assert case.sample.is_file()


def test_all_external_definitions_are_wellformed():
    cases = ext._all_external()
    assert {c.name for c in cases} == {"irs_1040", "sroie_receipt"}
    for case in cases:
        scores = case.score("")          # empty output must not raise
        assert scores and all(isinstance(v, float) for v in scores.values())


def test_count_table_blocks():
    md = "para\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\ntext\n\n| x |\n| - |\n"
    assert ext._count_table_blocks(md) == 2.0
    assert ext._count_table_blocks("no tables here") == 0.0


def test_irs_scorer_counts_tables_and_recall():
    md = "Filing Status and Standard Deduction\n\n| a | b |\n| - | - |\n"
    scores = ext._score_irs_1040(md)
    assert scores["table_blocks"] == 1.0
    assert 0.0 < scores["token_recall"] <= 1.0
