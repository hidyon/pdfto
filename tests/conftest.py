"""Shared test fixtures and helpers."""

from __future__ import annotations

import pytest


def make_pdf(page_texts: list[str]) -> bytes:
    """Build a minimal but valid multi-page PDF containing *page_texts*.

    The xref table offsets are computed so pypdf parses it without needing its
    recovery path.  Each entry of *page_texts* becomes one page.
    """

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)  # 1-based object number

    font_num = None  # assigned later
    page_nums: list[int] = []
    content_nums: list[int] = []

    # Reserve catalog (1) and pages (2) numbers up front for references.
    catalog_num = 1
    pages_num = 2
    objects.append(b"")  # placeholder for catalog
    objects.append(b"")  # placeholder for pages

    font_num = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for text in page_texts:
        safe = text.replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
        content = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        content_num = add(content)
        content_nums.append(content_num)

    for content_num in content_nums:
        page = (
            f"<< /Type /Page /Parent {pages_num} 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {content_num} 0 R >>"
        ).encode("latin-1")
        page_nums.append(add(page))

    kids = " ".join(f"{n} 0 R" for n in page_nums)
    objects[pages_num - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_nums)} >>"
    ).encode("latin-1")
    objects[catalog_num - 1] = (
        f"<< /Type /Catalog /Pages {pages_num} 0 R >>"
    ).encode("latin-1")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"

    xref_pos = len(out)
    n = len(objects)
    out += f"xref\n0 {n + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for i in range(1, n + 1):
        out += f"{offsets[i]:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {n + 1} /Root {catalog_num} 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


@pytest.fixture
def text_pdf() -> bytes:
    # Realistic amount of text per page so it is not mistaken for a scan.
    para = (
        "This is a sample document used in the PDFto test suite. "
        "It contains enough extractable text that the analyzer treats it "
        "as a born-digital PDF rather than a scanned image."
    )
    return make_pdf([para, "Second page: " + para])


@pytest.fixture
def scanned_pdf() -> bytes:
    # Pages with no real text → looks scanned.
    return make_pdf(["", ""])
