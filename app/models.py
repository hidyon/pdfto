"""Pydantic models shared across the API and the conversion core."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    """Formats PDFto can export to."""

    markdown = "markdown"
    html = "html"
    json = "json"
    text = "text"


class ImageMode(str, Enum):
    """How images embedded in the PDF are represented in the output."""

    placeholder = "placeholder"  # keep a text placeholder, drop the image data
    embedded = "embedded"  # inline the image as a base64 data URI
    referenced = "referenced"  # write images to separate files and link them


class TableMode(str, Enum):
    """Trade-off between table-extraction accuracy and speed."""

    fast = "fast"
    accurate = "accurate"


class ConversionOptions(BaseModel):
    """Options controlling a single conversion.

    Every field has a sensible default so the simplest possible request — just a
    file — produces a reasonable Markdown document.  The interactive questions
    only exist to override these defaults when the document calls for it.
    """

    output_format: OutputFormat = OutputFormat.markdown
    do_ocr: bool = Field(
        default=False,
        description="Run OCR over the document. Needed for scanned/image PDFs.",
    )
    do_table_structure: bool = Field(
        default=True,
        description="Recover the structure of tables instead of flattening them.",
    )
    table_mode: TableMode = TableMode.accurate
    image_mode: ImageMode = ImageMode.placeholder
    page_start: Optional[int] = Field(
        default=None, ge=1, description="First page to convert (1-based, inclusive)."
    )
    page_end: Optional[int] = Field(
        default=None, ge=1, description="Last page to convert (1-based, inclusive)."
    )


class DocumentAnalysis(BaseModel):
    """A lightweight inspection of an uploaded PDF.

    Produced without running the (expensive) full conversion so we can ask the
    user the right questions up front.
    """

    page_count: int
    has_extractable_text: bool
    likely_scanned: bool
    has_images: bool
    encrypted: bool
    file_size_bytes: int


class QuestionChoice(BaseModel):
    value: str
    label: str


class Question(BaseModel):
    """A single conversion question presented to the caller.

    Designed to be consumed by any UI: ``id`` maps onto a
    :class:`ConversionOptions` field, ``type`` tells the client how to render it.
    """

    id: str
    type: str  # "choice" | "boolean" | "range"
    prompt: str
    help: Optional[str] = None
    default: object = None
    choices: Optional[list[QuestionChoice]] = None


class DocumentResponse(BaseModel):
    """Returned right after upload."""

    id: str
    filename: str
    analysis: DocumentAnalysis
    questions: list[Question]


class ConversionResult(BaseModel):
    """Returned after a conversion completes."""

    document_id: str
    output_format: OutputFormat
    filename: str
    download_url: str
    preview: str
    truncated: bool
