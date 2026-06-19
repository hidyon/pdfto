"""FastAPI application: REST API plus a thin web UI.

The API is the primary interface — it is fully documented at ``/docs`` (OpenAPI)
so other systems can integrate without reading this file.  The web UI under
``/`` is a thin client over the same endpoints.

Typical flow
------------
1. ``POST /api/v1/documents`` with a PDF → returns an id, an analysis, and the
   questions to ask.
2. ``POST /api/v1/documents/{id}/convert`` with the answers → returns a preview
   and a download URL.
3. ``GET  /api/v1/documents/{id}/download`` → the converted file.

For non-interactive callers, ``POST /api/v1/convert`` does the whole thing in a
single request.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .analysis import analyze_pdf
from .config import settings
from .converter import ConversionError, convert
from .models import (
    ConversionResult,
    DocumentAnalysis,
    DocumentResponse,
    OutputFormat,
    Question,
)
from .questions import apply_answers, build_questions
from .storage import Storage

app = FastAPI(
    title="PDFto",
    version=__version__,
    description="Convert PDF documents into Markdown, HTML, JSON or text.",
)

storage = Storage(settings.data_dir)

_STATIC_DIR = Path(__file__).parent / "static"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _read_upload(file: UploadFile) -> bytes:
    if file.content_type not in (None, "application/pdf", "application/octet-stream"):
        # Be lenient: some clients send odd content types, but reject obvious
        # non-PDFs early.
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(415, "only PDF files are supported")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"file exceeds {settings.max_upload_mb} MB limit")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "file does not look like a PDF")
    return data


def _analyze_bytes(data: bytes) -> DocumentAnalysis:
    with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return analyze_pdf(tmp.name)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/api/v1/documents", response_model=DocumentResponse, tags=["documents"])
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    """Upload a PDF, analyse it, and return the questions to ask."""

    data = await _read_upload(file)
    try:
        analysis = _analyze_bytes(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"could not read PDF: {exc}") from exc

    record = storage.create_document(file.filename or "document.pdf", data, analysis)
    return DocumentResponse(
        id=record.id,
        filename=record.filename,
        analysis=analysis,
        questions=build_questions(analysis),
    )


@app.get("/api/v1/documents/{doc_id}", response_model=DocumentResponse,
         tags=["documents"])
def get_document(doc_id: str) -> DocumentResponse:
    record = storage.get(doc_id)
    if record is None:
        raise HTTPException(404, "document not found")
    return DocumentResponse(
        id=record.id,
        filename=record.filename,
        analysis=record.analysis,
        questions=build_questions(record.analysis),
    )


@app.get("/api/v1/documents/{doc_id}/questions", response_model=list[Question],
         tags=["documents"])
def get_questions(doc_id: str) -> list[Question]:
    record = storage.get(doc_id)
    if record is None:
        raise HTTPException(404, "document not found")
    return build_questions(record.analysis)


@app.post("/api/v1/documents/{doc_id}/convert", response_model=ConversionResult,
          tags=["documents"])
async def convert_document(
    doc_id: str,
    answers: dict = Body(
        default={},
        description="Flat mapping of question id to answer, e.g. "
        '{"output_format": "markdown", "do_ocr": true}.',
    ),
) -> ConversionResult:
    """Convert a previously uploaded document using the supplied answers."""

    record = storage.get(doc_id)
    if record is None:
        raise HTTPException(404, "document not found")

    options = apply_answers(answers or {})
    try:
        converted = await run_in_threadpool(
            convert, record.pdf_path, options, storage.doc_dir(doc_id)
        )
    except ConversionError as exc:
        raise HTTPException(422, str(exc)) from exc

    output = storage.add_output(
        doc_id, converted.content, converted.output_format,
        converted.suggested_extension,
    )

    preview = converted.content[: settings.preview_chars]
    return ConversionResult(
        document_id=doc_id,
        output_format=converted.output_format,
        filename=output.filename,
        download_url=f"/api/v1/documents/{doc_id}/download"
                     f"?format={converted.output_format.value}",
        preview=preview,
        truncated=len(converted.content) > len(preview),
    )


@app.get("/api/v1/documents/{doc_id}/download", tags=["documents"])
def download(doc_id: str,
             format: OutputFormat = Query(default=OutputFormat.markdown)) -> FileResponse:
    output = storage.get_output(doc_id, format.value)
    if output is None:
        raise HTTPException(404, "no converted output for that format; convert first")
    return FileResponse(
        output.path,
        filename=output.filename,
        media_type="application/octet-stream",
    )


@app.delete("/api/v1/documents/{doc_id}", status_code=204, tags=["documents"])
def delete_document(doc_id: str) -> None:
    if not storage.delete(doc_id):
        raise HTTPException(404, "document not found")


@app.post("/api/v1/convert", tags=["one-shot"])
async def convert_oneshot(
    file: UploadFile = File(...),
    output_format: OutputFormat = Query(default=OutputFormat.markdown),
    do_ocr: bool = Query(default=False),
    do_table_structure: bool = Query(default=True),
) -> FileResponse:
    """Upload and convert in a single request (no questions).

    Convenient for other systems that already know the options they want.
    Returns the converted file directly.
    """

    data = await _read_upload(file)
    try:
        analysis = _analyze_bytes(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"could not read PDF: {exc}") from exc
    record = storage.create_document(file.filename or "document.pdf", data, analysis)

    options = apply_answers({
        "output_format": output_format.value,
        "do_ocr": do_ocr,
        "do_table_structure": do_table_structure,
    })
    try:
        converted = await run_in_threadpool(
            convert, record.pdf_path, options, storage.doc_dir(record.id)
        )
    except ConversionError as exc:
        raise HTTPException(422, str(exc)) from exc

    output = storage.add_output(
        record.id, converted.content, converted.output_format,
        converted.suggested_extension,
    )
    return FileResponse(
        output.path, filename=output.filename, media_type="application/octet-stream"
    )


# --------------------------------------------------------------------------- #
# Web UI
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
