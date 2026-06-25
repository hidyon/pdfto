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
    names = {c.name for c in cases}
    assert "irs_1040" in names                     # IRS case is always defined
    assert all(n == "irs_1040" or n.startswith("sroie_") for n in names)
    for case in cases:
        scores = case.score("")          # empty output must not raise
        assert scores and all(isinstance(v, float) for v in scores.values())


def test_sroie_tokens_derived_from_key(tmp_path):
    key = tmp_path / "k.json"
    key.write_text(
        '{"company": "BOOK TA .K (TAMAN DAYA) SDN BHD", "date": "25/12/2018",'
        ' "address": "NO.53, JALAN SAGU 18, 81100 JOHOR", "total": "9.00"}',
        encoding="utf-8")
    tokens = ext.sroie_tokens(key)
    # Words >= 3 chars from company/address, plus verbatim date/total.
    assert "TAMAN" in tokens and "JALAN" in tokens and "JOHOR" in tokens
    assert "25/12/2018" in tokens and "9.00" in tokens
    assert "TA" not in tokens          # too short, dropped
    assert tokens == list(dict.fromkeys(tokens))  # de-duplicated, order-stable


def test_count_table_blocks():
    md = "para\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\ntext\n\n| x |\n| - |\n"
    assert ext._count_table_blocks(md) == 2.0
    assert ext._count_table_blocks("no tables here") == 0.0


def test_irs_scorer_counts_tables_and_recall():
    md = "Filing Status and Standard Deduction\n\n| a | b |\n| - | - |\n"
    scores = ext._score_irs_1040(md)
    assert scores["table_blocks"] == 1.0
    assert 0.0 < scores["token_recall"] <= 1.0
