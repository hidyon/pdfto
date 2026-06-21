"""Generate the verification sample PDFs under samples/ (dev tool).

Requires reportlab (``pip install reportlab``); not needed at runtime since the
generated PDFs are committed.

Usage:
    python scripts/make_sample_pdfs.py
"""

import pathlib

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "samples"


def make_table_sample(path: pathlib.Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    data = [
        ["Product", "Q1", "Q2", "Q3"],
        ["Widget", "100", "120", "140"],
        ["Gadget", "90", "85", "95"],
        ["Gizmo", "60", "75", "80"],
    ]
    table = Table(data)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
    ]))
    elems = [
        Paragraph("Quarterly Sales Report", styles["Title"]),
        Spacer(1, 18),
        table,
    ]
    doc.build(elems)


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    out = SAMPLES / "table_sample.pdf"
    make_table_sample(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
