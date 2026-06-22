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


def make_table_doc_sample(path: pathlib.Path) -> None:
    """A document-style table (body text + ruled table) docling extracts as a
    real table — used for the table-extraction quality metric (spec 0024).

    Unlike ``table_sample.pdf`` (full grid, no surrounding text), the body
    paragraphs give docling enough document context to classify this as a
    table rather than a picture.
    """
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    data = [
        ["Product", "Q1", "Q2", "Q3"],
        ["Widget", "100", "120", "140"],
        ["Gadget", "90", "85", "95"],
        ["Gizmo", "60", "75", "80"],
        ["Doohickey", "45", "50", "55"],
    ]
    table = Table(data)
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems = [
        Paragraph("Quarterly Sales Report", styles["Title"]),
        Spacer(1, 18),
        Paragraph(
            "The table below summarizes quarterly unit sales by product. "
            "Each row is a product and each column is a fiscal quarter.",
            styles["BodyText"]),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph(
            "Totals exclude returns. Source: internal finance system.",
            styles["BodyText"]),
    ]
    doc.build(elems)


def make_scanned_sample(path: pathlib.Path) -> None:
    """A rasterized, image-only page (no text layer) — requires OCR to read."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1240, 1754), "white")  # ~A4 @150dpi
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        bold = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except OSError:
        font = ImageFont.load_default()
        bold = font
    draw.text((90, 90), "PDFto Scan Test", fill="black", font=bold)
    lines = [
        "This page is a rasterized image with no text layer.",
        "OCR must read these sentences to extract any text.",
        "The quick brown fox jumps over the lazy dog.",
        "Invoice number 12345 dated 2026-06-21.",
    ]
    y = 220
    for line in lines:
        draw.text((90, y), line, fill="black", font=font)
        y += 70
    img.save(path, "PDF", resolution=150)


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    table = SAMPLES / "table_sample.pdf"
    make_table_sample(table)
    print(f"wrote {table}")
    table_doc = SAMPLES / "table_doc_sample.pdf"
    make_table_doc_sample(table_doc)
    print(f"wrote {table_doc}")
    scanned = SAMPLES / "scanned_sample.pdf"
    make_scanned_sample(scanned)
    print(f"wrote {scanned}")


if __name__ == "__main__":
    main()
