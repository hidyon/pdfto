"""Generate showcase documents and their conversions, for product intros.

Builds two realistic samples under docs/examples/ and converts them with
docling so the outputs can be shown as before/after material:

1. ``showcase.pdf``  — a rich, multi-page report (headings, intro text, bullet
   list, an embedded bar-chart image and two tables) → Markdown / JSON / HTML /
   text.  Markdown/HTML use *referenced* images, written under ``assets/``.
2. ``showcase_ocr.pdf`` — an image-only (scanned) page with no text layer →
   converted both WITH and WITHOUT OCR to demonstrate text recovery.

Requires reportlab + Pillow (inputs) and docling (conversion); all dev-only.

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
    Image, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "docs" / "examples"

_REVENUE = [
    ["Product", "Q1", "Q2", "Q3", "YoY"],
    ["Widget", "100", "120", "140", "+18%"],
    ["Gadget", "90", "85", "95", "+6%"],
    ["Gizmo", "60", "75", "80", "+33%"],
    ["Doohickey", "45", "50", "48", "-4%"],
]
_REGIONS = [
    ["Region", "Revenue", "Customers", "Share"],
    ["North America", "$1.2M", "320", "41%"],
    ["Europe", "$0.9M", "210", "31%"],
    ["Asia Pacific", "$0.7M", "180", "24%"],
    ["Other", "$0.1M", "40", "4%"],
]


def _table(data):
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def make_chart_png(path: pathlib.Path) -> None:
    """A simple bar chart (Q3 by product) so the report has a real figure."""
    from PIL import Image as PImage, ImageDraw, ImageFont
    W, H = 760, 360
    img = PImage.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except OSError:
        font = bold = ImageFont.load_default()
    d.text((24, 16), "Q3 Units by Product", fill="black", font=bold)
    bars = [("Widget", 140), ("Gadget", 95), ("Gizmo", 80), ("Doohickey", 48)]
    base_y, max_h, x = 300, 220, 70
    scale = max_h / max(v for _, v in bars)
    for label, value in bars:
        h = int(value * scale)
        d.rectangle([x, base_y - h, x + 110, base_y], fill=(79, 140, 255))
        d.text((x, base_y + 8), label, fill="black", font=font)
        d.text((x + 30, base_y - h - 26), str(value), fill="black", font=font)
        x += 165
    d.line([60, base_y, W - 30, base_y], fill="black", width=2)
    img.save(path, "PNG")


def build_rich_pdf(path: pathlib.Path, chart: pathlib.Path) -> None:
    styles = getSampleStyleSheet()
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14)
    body = ParagraphStyle("Body", parent=styles["BodyText"], alignment=TA_LEFT,
                          spaceAfter=8, leading=15)

    bullets = ListFlowable([
        ListItem(Paragraph("Total revenue grew 12% quarter over quarter.", body)),
        ListItem(Paragraph("Widget remained the top performer across all regions.", body)),
        ListItem(Paragraph("Doohickey dipped slightly and needs attention.", body)),
    ], bulletType="bullet", leftIndent=18)

    steps = ListFlowable([
        ListItem(Paragraph("Expand Gizmo distribution in Asia Pacific.", body)),
        ListItem(Paragraph("Refresh the Doohickey lineup for Q4.", body)),
        ListItem(Paragraph("Pilot a loyalty program in North America.", body)),
    ], bulletType="bullet", leftIndent=18)

    elems = [
        Paragraph("Northwind Analytics — Q3 Product Report", styles["Title"]),
        Spacer(1, 10),
        Paragraph(
            "This report summarizes product performance for the third quarter. "
            "It is provided as a sample document to demonstrate how PDFto converts "
            "headings, paragraphs, lists, figures and tables into clean, structured "
            "output across multiple pages.", body),
        Paragraph("Highlights", h2),
        bullets,
        Paragraph("Q3 Units by Product", h2),
        Image(str(chart), width=380, height=180),
        Paragraph("Quarterly Revenue by Product", h2),
        Paragraph(
            "The table below lists unit sales by product and fiscal quarter, "
            "with year-over-year growth in the final column.", body),
        Spacer(1, 8),
        _table(_REVENUE),
        PageBreak(),
        Paragraph("Regional Breakdown", h2),
        Paragraph(
            "Revenue, active customers and revenue share by region for the quarter.",
            body),
        Spacer(1, 8),
        _table(_REGIONS),
        Paragraph("Next Steps", h2),
        steps,
        Spacer(1, 10),
        Paragraph(
            "Figures are illustrative. Source: internal finance system (sample data).",
            body),
    ]
    SimpleDocTemplate(str(path), pagesize=A4,
                      title="Northwind Q3 Product Report").build(elems)


def build_ocr_pdf(path: pathlib.Path) -> None:
    """An image-only invoice (no text layer) — OCR is required to read it."""
    from PIL import Image as PImage, ImageDraw, ImageFont
    img = PImage.new("RGB", (1240, 1754), "white")  # ~A4 @150dpi
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
    except OSError:
        font = bold = ImageFont.load_default()
    d.text((90, 80), "ACME Supplies — Invoice", fill="black", font=bold)
    lines = [
        "Invoice number: 12345",
        "Date: 2026-06-21",
        "Bill to: Northwind Analytics",
        "",
        "Item                 Qty     Price",
        "Widgets               10    $100.00",
        "Gadgets                5     $45.00",
        "Shipping               1     $12.50",
        "",
        "Total due:                  $157.50",
        "",
        "Thank you for your business.",
    ]
    y = 220
    for line in lines:
        d.text((90, y), line, fill="black", font=font)
        y += 64
    img.save(path, "PDF", resolution=150)


def convert_rich(pdf: pathlib.Path) -> None:
    from app.converter import convert
    from app.models import ConversionOptions, ImageMode, OutputFormat

    assets_dir = EXAMPLES / "assets"
    assets_dir.mkdir(exist_ok=True)
    jobs = [
        (OutputFormat.markdown, "md", ImageMode.referenced),
        (OutputFormat.html, "html", ImageMode.referenced),
        (OutputFormat.json, "json", ImageMode.placeholder),
        (OutputFormat.text, "txt", ImageMode.placeholder),
    ]
    for fmt, ext, image_mode in jobs:
        result = convert(pdf, ConversionOptions(
            output_format=fmt, do_table_structure=True, image_mode=image_mode))
        content = result.content
        if fmt is OutputFormat.json:
            content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        # Referenced images already link as relative assets/<name> (the core
        # handles this; see app/converter._relativize_asset_links).
        (pdf.with_suffix(f".{ext}")).write_text(content, encoding="utf-8")
        for name, data in result.assets.items():
            (assets_dir / name).write_bytes(data)
        print(f"wrote {pdf.with_suffix(f'.{ext}').name}  "
              f"({len(content)} chars, {len(result.assets)} asset(s))")


def convert_ocr(pdf: pathlib.Path) -> None:
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    with_ocr = convert(pdf, ConversionOptions(
        output_format=OutputFormat.text, do_ocr=True, ocr_languages=["en"]))
    (pdf.with_suffix(".ocr.txt")).write_text(with_ocr.content, encoding="utf-8")
    print(f"wrote {pdf.with_suffix('.ocr.txt').name}  ({len(with_ocr.content)} chars)")

    no_ocr = convert(pdf, ConversionOptions(
        output_format=OutputFormat.text, do_ocr=False))
    (pdf.with_suffix(".no-ocr.txt")).write_text(no_ocr.content, encoding="utf-8")
    print(f"wrote {pdf.with_suffix('.no-ocr.txt').name}  "
          f"({len(no_ocr.content)} chars — empty without OCR)")


def main() -> None:
    import tempfile

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    (EXAMPLES / "assets").mkdir(exist_ok=True)
    # The chart is an intermediate used to build the PDF; keep it out of the
    # committed assets/ dir (which holds only docling-extracted images).
    with tempfile.TemporaryDirectory() as td:
        chart = pathlib.Path(td) / "q3-units.png"
        make_chart_png(chart)
        rich = EXAMPLES / "showcase.pdf"
        build_rich_pdf(rich, chart)
        print(f"wrote {rich}")
        convert_rich(rich)

    ocr = EXAMPLES / "showcase_ocr.pdf"
    build_ocr_pdf(ocr)
    print(f"wrote {ocr}")
    convert_ocr(ocr)


if __name__ == "__main__":
    main()
