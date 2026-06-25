"""Pure scoring functions for conversion quality (spec 0030).

These operate purely on output strings and known expectations — no docling, no
app runtime — so they are fast and covered by the default (mocked) test suite.
Each metric returns a value that is easy to read and to A/B compare.
"""

from __future__ import annotations

__all__ = [
    "parse_markdown_table",
    "table_shape",
    "table_cell_recovery",
    "token_recall",
]


def parse_markdown_table(md: str) -> list[list[str]]:
    """Return the first Markdown table in *md* as rows of stripped cells.

    The ``|---|`` separator row is dropped and cell whitespace is normalised so
    column padding does not affect comparisons.  Returns ``[]`` if no table is
    found.
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


def table_shape(md: str) -> tuple[int, int]:
    """Return ``(rows, cols)`` of the first Markdown table in *md*.

    ``cols`` is the most common per-row cell count (robust to a stray ragged
    row).  Returns ``(0, 0)`` when no table is present.
    """
    table = parse_markdown_table(md)
    if not table:
        return (0, 0)
    widths = [len(r) for r in table]
    cols = max(set(widths), key=widths.count)
    return (len(table), cols)


def table_cell_recovery(md: str, expected_rows: list[list[str]]) -> float:
    """Fraction of expected table cells recovered at the same position+value.

    Compares the first Markdown table in *md* cell-by-cell against
    *expected_rows*.  Returns 0.0..1.0 (1.0 = every expected cell present and
    exactly equal).  ``expected_rows`` must be non-empty.
    """
    total = sum(len(row) for row in expected_rows)
    if total == 0:
        raise ValueError("expected_rows must contain at least one cell")
    table = parse_markdown_table(md)
    found = 0
    for r, row in enumerate(expected_rows):
        for c, want in enumerate(row):
            if r < len(table) and c < len(table[r]) and table[r][c] == want:
                found += 1
    return found / total


def token_recall(text: str, tokens: list[str]) -> float:
    """Fraction of *tokens* that appear in *text* (case-insensitive substring).

    Used for OCR and body-text fidelity: how many of the known phrases survived
    the conversion.  Returns 0.0..1.0.  ``tokens`` must be non-empty.
    """
    if not tokens:
        raise ValueError("tokens must contain at least one token")
    hay = text.lower()
    found = sum(1 for t in tokens if t.lower() in hay)
    return found / len(tokens)
