"""Lightweight PDF inspection used to drive the interactive questions.

We deliberately avoid running docling here: the full conversion pipeline loads
ML models and can take seconds to minutes.  ``pypdf`` lets us cheaply learn
enough about a document (page count, whether text is extractable, images,
encryption) to ask the user the right questions before committing to a
conversion.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .formats import extension_of, kind_of
from .models import DocumentAnalysis

# Heuristic: if the average extracted text per page is below this many
# characters, the document is probably scanned and would benefit from OCR.
_MIN_CHARS_PER_PAGE = 32


def analyze(path: str | Path, filename: str) -> DocumentAnalysis:
    """Inspect *path* and return a :class:`DocumentAnalysis` for any format.

    PDFs get the full ``pypdf`` inspection; other formats get cheap,
    format-appropriate defaults (no heavy parsing) so the right questions can
    be asked.  *filename* supplies the extension used to pick the strategy.
    """

    path = Path(path)
    ext = extension_of(filename)
    kind = kind_of(ext)

    if kind == "pdf":
        analysis = analyze_pdf(path)
        analysis.source_extension = ext
        return analysis

    size = path.stat().st_size
    if kind == "image":
        # A single rasterised page; OCR is needed to recover any text.
        return DocumentAnalysis(
            page_count=1, has_extractable_text=False, likely_scanned=True,
            has_images=True, encrypted=False, file_size_bytes=size,
            source_extension=ext,
        )
    # Office / HTML / Markdown / CSV: text is extractable; docling handles
    # tables and images natively, so no OCR/table/page questions are needed.
    return DocumentAnalysis(
        page_count=0, has_extractable_text=True, likely_scanned=False,
        has_images=False, encrypted=False, file_size_bytes=size,
        source_extension=ext,
    )


def analyze_pdf(path: str | Path) -> DocumentAnalysis:
    """Inspect *path* and return a :class:`DocumentAnalysis`.

    The function never raises on malformed-but-readable PDFs; it degrades to
    conservative defaults so the caller can still offer a conversion.
    """

    path = Path(path)
    size = path.stat().st_size
    reader = PdfReader(str(path))

    encrypted = bool(getattr(reader, "is_encrypted", False))
    if encrypted:
        # Try the common case of an empty owner password.
        try:
            reader.decrypt("")
            encrypted = False
        except Exception:
            pass

    page_count = len(reader.pages)

    total_chars = 0
    has_images = False
    for page in reader.pages:
        try:
            total_chars += len(page.extract_text() or "")
        except Exception:
            pass
        if not has_images:
            try:
                if page.images:
                    has_images = True
            except Exception:
                pass

    has_extractable_text = total_chars > 0
    avg_chars = (total_chars / page_count) if page_count else 0
    likely_scanned = page_count > 0 and avg_chars < _MIN_CHARS_PER_PAGE

    return DocumentAnalysis(
        page_count=page_count,
        has_extractable_text=has_extractable_text,
        likely_scanned=likely_scanned,
        has_images=has_images,
        encrypted=encrypted,
        file_size_bytes=size,
    )
