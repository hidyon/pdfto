"""Generate a showcase document and its conversions, for product intros.

Builds a realistic one-page PDF (headings, intro text, a bullet list and a
ruled table) under docs/examples/, then converts it with docling into Markdown
/ JSON / HTML / plain text so the outputs can be shown as before/after samples.

Requires reportlab (PDF) and docling (conversion); both are dev-only.

Usage:
    python scripts/make_showcase.py
"""

import json
import pathlib

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "docs" / "examples"


def build_pdf(path: pathlib.Path) -> None:
    styles = getSampleStyleSheet()
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14)
    body = ParagraphStyle("Body", parent=styles["BodyText"], alignment=TA_LEFT,
                          spaceAfter=8, leading=15)

    data = [
        ["Product", "Q1", "Q2", "Q3", "YoY"],
        ["Widget", "100", "120", "140", "+18%"],
        ["Gadget", "90", "85", "95", "+6%"],
        ["Gizmo", "60", "75", "80", "+33%"],
        ["Doohickey", "45", "50", "48", "-4%"],
    ]
    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    bullets = ListFlowable(
        [
            ListItem(Paragraph("Total revenue grew 12% quarter over quarter.", body)),
            ListItem(Paragraph("Widget remained the top performer across all regions.", body)),
            ListItem(Paragraph("Doohickey dipped slightly and needs attention.", body)),
        ],
        bulletType="bullet", leftIndent=18,
    )

    elems = [
        Paragraph("Northwind Analytics — Q3 Product Report", styles["Title"]),
        Spacer(1, 10),
        Paragraph(
            "This report summarizes product performance for the third quarter. "
            "It is provided as a sample document to demonstrate how PDFto converts "
            "headings, paragraphs, lists and tables into clean, structured output.",
            body),
        Paragraph("Highlights", h2),
        bullets,
        Paragraph("Quarterly Revenue by Product", h2),
        Paragraph(
            "The table below lists unit sales by product and fiscal quarter, "
            "with year-over-year growth in the final column.", body),
        Spacer(1, 8),
        table,
        Spacer(1, 12),
        Paragraph(
            "Figures are illustrative. Source: internal finance system (sample data).",
            body),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, title="Northwind Q3 Product Report").build(elems)


def convert_all(pdf: pathlib.Path) -> None:
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    for fmt, ext in [(OutputFormat.markdown, "md"), (OutputFormat.json, "json"),
                     (OutputFormat.html, "html"), (OutputFormat.text, "txt")]:
        result = convert(pdf, ConversionOptions(output_format=fmt,
                                                do_table_structure=True))
        out = pdf.with_suffix(f".{ext}")
        content = result.content
        if fmt is OutputFormat.json:
            # Pretty-print for readability in the example.
            content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        out.write_text(content, encoding="utf-8")
        print(f"wrote {out}  ({len(content)} chars)")


def main() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    pdf = EXAMPLES / "showcase.pdf"
    build_pdf(pdf)
    print(f"wrote {pdf}")
    convert_all(pdf)


if __name__ == "__main__":
    main()
