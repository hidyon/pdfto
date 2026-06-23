"""Input-format helpers, shared by the core and web layers.

Standard library only — this module is imported on the cheap path (upload,
analysis) so it must never pull in docling or other heavy dependencies.  The
allowlist mirrors the input formats docling can convert; whether a given format
actually works also depends on the docling backends installed in the
environment (conversion failures are normalised to ``ConversionError``).
"""

from __future__ import annotations

from pathlib import Path

# Extensions we accept for conversion (lowercase, leading dot).
SUPPORTED_EXTENSIONS = frozenset({
    ".pdf",
    ".docx", ".pptx", ".xlsx",
    ".html", ".htm",
    ".md", ".csv",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
})


def extension_of(filename: str) -> str:
    """Return the lowercase extension (with leading dot), or ``""`` if none."""
    return Path(filename or "").suffix.lower()


def is_supported(ext: str) -> bool:
    """Whether *ext* (e.g. ``".docx"``) is an accepted input extension."""
    return ext.lower() in SUPPORTED_EXTENSIONS


def is_pdf(ext: str) -> bool:
    """Whether *ext* denotes a PDF (the only format with page ranges)."""
    return ext.lower() == ".pdf"
