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


def build_docx(path: pathlib.Path) -> None:
    """A small Word document (heading, paragraph, bullet list, table)."""
    from docx import Document

    doc = Document()
    doc.add_heading("Project Kickoff Notes", level=1)
    doc.add_paragraph(
        "A short Word document used to show that PDFto converts .docx files, "
        "not only PDFs.")
    doc.add_heading("Agenda", level=2)
    for item in ("Scope and goals", "Timeline and milestones", "Owners and risks"):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Milestones", level=2)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Phase", "Owner", "Due"
    for phase, owner, due in [("Design", "Aoi", "Jul 5"),
                              ("Build", "Ken", "Aug 2"),
                              ("Launch", "Mio", "Sep 1")]:
        row = table.add_row().cells
        row[0].text, row[1].text, row[2].text = phase, owner, due
    doc.save(str(path))


def build_html(path: pathlib.Path) -> None:
    """A small HTML page (heading, paragraph, list, table)."""
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Release Notes</title></head><body>"
        "<h1>Release Notes — v2.1</h1>"
        "<p>An HTML page used to show that PDFto converts web pages too.</p>"
        "<h2>Changes</h2><ul>"
        "<li>Added multi-format input (Word, HTML, images).</li>"
        "<li>Fixed referenced image links.</li>"
        "<li>Shipped the <code>pdfto</code> CLI.</li></ul>"
        "<h2>Compatibility</h2>"
        "<table><thead><tr><th>Component</th><th>Min version</th></tr></thead>"
        "<tbody><tr><td>Python</td><td>3.10</td></tr>"
        "<tr><td>docling</td><td>2.0</td></tr></tbody></table>"
        "</body></html>",
        encoding="utf-8")


def build_pptx(path: pathlib.Path) -> None:
    """A small PowerPoint deck (title slide + a content slide with bullets)."""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = "Q3 Business Review"
    title_slide.placeholders[1].text = "A sample slide deck converted by PDFto"

    bullet_slide = prs.slides.add_slide(prs.slide_layouts[1])
    bullet_slide.shapes.title.text = "Highlights"
    body = bullet_slide.placeholders[1].text_frame
    body.text = "Revenue grew 12% quarter over quarter"
    for line in ("Widget led all regions", "Doohickey needs attention",
                 "Expanding Gizmo in Asia Pacific"):
        body.add_paragraph().text = line

    table_slide = prs.slides.add_slide(prs.slide_layouts[5])
    table_slide.shapes.title.text = "Revenue by Region"
    rows, cols = 4, 3
    table = table_slide.shapes.add_table(
        rows, cols, Inches(0.7), Inches(1.8), Inches(8), Inches(2.5)).table
    for c, head in enumerate(("Region", "Revenue", "Share")):
        table.cell(0, c).text = head
    for r, (region, rev, share) in enumerate(
            [("North America", "$1.2M", "41%"), ("Europe", "$0.9M", "31%"),
             ("Asia Pacific", "$0.7M", "24%")], start=1):
        table.cell(r, 0).text = region
        table.cell(r, 1).text = rev
        table.cell(r, 2).text = share
    prs.save(str(path))


def build_xlsx(path: pathlib.Path) -> None:
    """A small Excel workbook (a header row and a few data rows)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Revenue"
    ws.append(["Product", "Q1", "Q2", "Q3", "YoY"])
    for row in [["Widget", 100, 120, 140, "+18%"],
                ["Gadget", 90, 85, 95, "+6%"],
                ["Gizmo", 60, 75, 80, "+33%"],
                ["Doohickey", 45, 50, 48, "-4%"]]:
        ws.append(row)
    wb.save(str(path))


def convert_to_markdown(src: pathlib.Path, out: pathlib.Path) -> None:
    from app.converter import convert
    from app.models import ConversionOptions, OutputFormat

    result = convert(src, ConversionOptions(output_format=OutputFormat.markdown,
                                            do_table_structure=True))
    out.write_text(result.content, encoding="utf-8")
    print(f"wrote {out.name}  ({len(result.content)} chars)")


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

    # Non-PDF inputs (multi-format support, M8).
    docx = EXAMPLES / "sample.docx"
    build_docx(docx)
    print(f"wrote {docx}")
    convert_to_markdown(docx, EXAMPLES / "sample.docx.md")

    html = EXAMPLES / "sample.html"
    build_html(html)
    print(f"wrote {html}")
    convert_to_markdown(html, EXAMPLES / "sample.html.md")

    pptx = EXAMPLES / "sample.pptx"
    build_pptx(pptx)
    print(f"wrote {pptx}")
    convert_to_markdown(pptx, EXAMPLES / "sample.pptx.md")

    xlsx = EXAMPLES / "sample.xlsx"
    build_xlsx(xlsx)
    print(f"wrote {xlsx}")
    convert_to_markdown(xlsx, EXAMPLES / "sample.xlsx.md")


if __name__ == "__main__":
    main()
