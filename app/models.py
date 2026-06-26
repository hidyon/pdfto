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


class LLMPreset(str, Enum):
    """Named LLM post-processing presets for common quality corrections."""

    ocr_fix = "ocr_fix"   # fix OCR misreads from context (no add/remove)
    cleanup = "cleanup"   # repair wraps/hyphenation, strip scan artifacts
    tables = "tables"     # reconstruct clearly-tabular text as Markdown tables


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
    ocr_languages: list[str] = Field(
        default_factory=list,
        description="OCR languages (EasyOCR codes, e.g. ['ja','en']). "
        "Empty uses the engine default.",
    )
    do_table_structure: bool = Field(
        default=True,
        description="Recover the structure of tables instead of flattening them.",
    )
    table_mode: TableMode = TableMode.accurate
    do_cell_matching: bool = Field(
        default=True,
        description="Match table cells to the detected grid (better table fidelity).",
    )
    force_full_page_ocr: bool = Field(
        default=False,
        description="OCR every page even where a text layer exists (uses EasyOCR; "
        "helps hybrid/partial-text PDFs). Defaults to English when no languages set.",
    )
    ocr_confidence_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Minimum OCR confidence to keep a read (EasyOCR). Lower = higher "
        "recall but more false positives; None uses the engine default (0.5). "
        "Lowering it markedly improves noisy/photographed scans.",
    )
    ocr_preprocess: bool = Field(
        default=False,
        description="Preprocess image inputs (denoise/binarize/upscale) before OCR. "
        "Improves noisy/photographed scans; ignored for non-image inputs and when "
        "OCR is off.",
    )
    image_scale: float = Field(
        default=2.0, ge=1.0, le=4.0,
        description="Render scale for page/figure images (higher = sharper, slower).",
    )
    image_mode: ImageMode = ImageMode.placeholder
    llm_preset: Optional[LLMPreset] = Field(
        default=None,
        description="LLM correction preset (ocr_fix/cleanup/tables). Combinable with "
        "llm_instruction. Requires an Anthropic API key (opt-in).",
    )
    llm_instruction: Optional[str] = Field(
        default=None,
        description="Optional natural-language instruction to post-process the "
        "converted text with an LLM (e.g. 'summarize', 'translate to English').",
    )
    page_start: Optional[int] = Field(
        default=None, ge=1, description="First page to convert (1-based, inclusive)."
    )
    page_end: Optional[int] = Field(
        default=None, ge=1, description="Last page to convert (1-based, inclusive)."
    )


class DocumentAnalysis(BaseModel):
    """A lightweight inspection of an uploaded document.

    Produced without running the (expensive) full conversion so we can ask the
    user the right questions up front.
    """

    page_count: int
    has_extractable_text: bool
    likely_scanned: bool
    has_images: bool
    encrypted: bool
    file_size_bytes: int
    # Lowercase source extension (e.g. ".pdf", ".docx"); "" if unknown.
    source_extension: str = ""


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


class DocumentSummary(BaseModel):
    """Lightweight document entry for listings."""

    id: str
    filename: str
    created_at: float
    page_count: int


class BatchItem(BaseModel):
    """One file within a batch and the job converting it."""

    filename: str
    document_id: str
    job_id: str
    status: JobStatus


class BatchResponse(BaseModel):
    """A batch submission and the current state of its items."""

    id: str
    created_at: float
    count: int
    items: list[BatchItem]


class DocumentResponse(BaseModel):
    """Returned right after upload."""

    id: str
    filename: str
    analysis: DocumentAnalysis
    questions: list[Question]


class JobStatus(str, Enum):
    """Lifecycle states of a conversion job."""

    pending = "pending"  # queued, not started yet
    running = "running"  # being converted
    succeeded = "succeeded"
    failed = "failed"


class Job(BaseModel):
    """A conversion job.

    Conversions run in the background; clients submit a job and poll it.  A
    ``succeeded`` job carries the preview and a ``download_url``; a ``failed``
    job carries an ``error`` message.
    """

    id: str
    document_id: str
    status: JobStatus
    output_format: OutputFormat
    created_at: float
    updated_at: float
    download_url: Optional[str] = None
    filename: Optional[str] = None
    preview: Optional[str] = None
    truncated: bool = False
    error: Optional[str] = None
