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


def make_complex_table_sample(path: pathlib.Path) -> None:
    """A table with merged cells: a two-row header with column-group spans.

    Harder than ``table_doc_sample`` — docling must cope with a header that
    spans columns ("H1 2026" over Q1/Q2) and rows ("Region" over both header
    rows).  Used by the quality foundation (spec 0030) to measure how much of
    the data survives a spanned layout.  Keep the values in sync with
    ``eval/cases.py::COMPLEX_TABLE_VALUES``.
    """
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    data = [
        ["Region", "H1 2026", "", "H2 2026", ""],
        ["", "Q1", "Q2", "Q3", "Q4"],
        ["North", "120", "135", "150", "160"],
        ["South", "90", "95", "100", "110"],
        ["East", "70", "80", "85", "90"],
        ["West", "60", "65", "70", "75"],
    ]
    table = Table(data)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("BACKGROUND", (0, 0), (-1, 1), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("SPAN", (0, 0), (0, 1)),   # "Region" spans the two header rows
        ("SPAN", (1, 0), (2, 0)),   # "H1 2026" spans Q1+Q2
        ("SPAN", (3, 0), (4, 0)),   # "H2 2026" spans Q3+Q4
    ]))
    elems = [
        Paragraph("Regional Revenue by Half-Year", styles["Title"]),
        Spacer(1, 18),
        Paragraph(
            "Revenue in thousands of USD. The header groups quarters into "
            "halves; each region reports four quarterly figures.",
            styles["BodyText"]),
        Spacer(1, 12),
        table,
    ]
    doc.build(elems)


def make_noisy_scan_sample(path: pathlib.Path) -> None:
    """A degraded, real-world-like scan: skew + blur + noise + low resolution.

    Unlike ``scanned_sample`` (a crisp rasterization), this simulates a poor
    photocopy/phone scan so OCR is genuinely stressed.  The text is known, so
    ``token_recall`` reports how robust OCR is to degradation (spec 0030).  Keep
    the wording in sync with ``eval/cases.py::NOISY_SCAN_TOKENS``.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

    w, h = 1240, 1754  # ~A4 @150dpi
    img = Image.new("L", (w, h), 255)  # grayscale, like a scan
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        bold = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except OSError:
        font = ImageFont.load_default()
        bold = font
    draw.text((90, 90), "Monthly Statement", fill=0, font=bold)
    lines = [
        "Account holder Jane Anderson",
        "The quick brown fox jumps over the lazy dog.",
        "Balance carried forward from the previous period.",
        "Total amount due before the payment deadline.",
    ]
    y = 230
    for line in lines:
        draw.text((90, y), line, fill=0, font=font)
        y += 75

    # Degrade: skew, blur, additive Gaussian noise, then a resolution round-trip.
    img = img.rotate(-2.3, fillcolor=255, resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(1.1))
    noise = Image.effect_noise((w, h), 26)            # zero-mean Gaussian noise
    img = ImageChops.add(img, noise, scale=1.0, offset=-20)
    img = img.resize((w // 2, h // 2)).resize((w, h))  # low-res round-trip
    img.convert("RGB").save(path, "PDF", resolution=110)


def make_prose_sample(path: pathlib.Path) -> None:
    """A born-digital prose page with distinctive tokens for body-text fidelity.

    Used by the quality-measurement foundation (spec 0030): ``token_recall``
    checks how many of the known phrases survive conversion.  The wording here
    must stay in sync with ``eval/cases.py::PROSE_TOKENS``.
    """
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    elems = [
        Paragraph("PDFto Prose Fidelity Sample", styles["Title"]),
        Spacer(1, 18),
        Paragraph(
            "This is a born-digital document used to measure body-text "
            "fidelity. It is not a scan, so no OCR is required to read it.",
            styles["BodyText"]),
        Spacer(1, 12),
        Paragraph(
            "The capital of Iceland is Reykjavik. Photosynthesis converts "
            "light into chemical energy. The trail is 42 kilometres long.",
            styles["BodyText"]),
        Spacer(1, 12),
        Paragraph(
            "The quarterly figures are summarized elsewhere; this page only "
            "exercises plain paragraph extraction.",
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
    prose = SAMPLES / "prose_sample.pdf"
    make_prose_sample(prose)
    print(f"wrote {prose}")
    complex_table = SAMPLES / "complex_table_sample.pdf"
    make_complex_table_sample(complex_table)
    print(f"wrote {complex_table}")
    noisy = SAMPLES / "noisy_scan_sample.pdf"
    make_noisy_scan_sample(noisy)
    print(f"wrote {noisy}")


if __name__ == "__main__":
    main()
