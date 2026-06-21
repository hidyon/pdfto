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

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .analysis import analyze_pdf
from .cleanup import PeriodicCleaner
from .config import settings
from .converter import ConversionError, convert
from .jobs import JobManager
from .logging_config import request_id_var, setup_logging
from .models import (
    BatchItem,
    BatchResponse,
    DocumentAnalysis,
    DocumentResponse,
    Job,
    OutputFormat,
    Question,
    TableMode,
)
from .questions import apply_answers, build_questions
from .security import RateLimiter, extract_api_key
from .storage import Storage
from .webhooks import check_url

setup_logging(settings.log_level, settings.log_format)
logger = logging.getLogger("pdfto")

storage = Storage(settings.data_dir)
jobs = JobManager(settings.max_workers, storage.db)
rate_limiter = RateLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the periodic cleaner while the app is running (if TTL is enabled)."""
    # Re-apply our logging config so it survives uvicorn's own setup.
    setup_logging(settings.log_level, settings.log_format)
    logger.info("pdfto starting", extra={"version": __version__})
    cleaner = None
    if settings.cleanup_enabled:
        cleaner = PeriodicCleaner(
            storage, jobs, settings.ttl_seconds, settings.sweep_interval_seconds
        )
        cleaner.start()
    try:
        yield
    finally:
        if cleaner is not None:
            cleaner.stop()
        logger.info("pdfto shutting down")


app = FastAPI(
    title="PDFto",
    version=__version__,
    description="Convert PDF documents into Markdown, HTML, JSON or text.",
    lifespan=lifespan,
)


def _error_response(status: int, detail: str, extra_headers: dict | None = None):
    rid = request_id_var.get()
    headers = {"X-Request-ID": rid}
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(status_code=status,
                        content={"detail": detail, "request_id": rid},
                        headers=headers)


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    """Protect /api/v1/* with optional API-key auth and rate limiting.

    Both are opt-in: with no API keys configured the API stays open, and
    rate limiting is keyed by client IP instead of API key.
    """
    if request.url.path.startswith("/api/v1"):
        if settings.api_keys:
            key = extract_api_key(request.headers)
            if key not in settings.api_keys:
                return _error_response(401, "invalid or missing API key")
            identity = f"key:{key}"
        else:
            client = request.client.host if request.client else "unknown"
            identity = f"ip:{client}"
        allowed, retry_after = rate_limiter.check(
            identity, settings.rate_limit, settings.rate_window_seconds
        )
        if not allowed:
            return _error_response(429, "rate limit exceeded",
                                   {"Retry-After": str(retry_after)})
    return await call_next(request)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Assign a request id, log access, and expose X-Request-ID.

    The id is not reset after the request: each request runs in its own task
    context (so there is no cross-request leak), and leaving it set lets the
    outer exception handler report the same id on failures.
    """
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    request_id_var.set(rid)
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        "%s %s -> %s", request.method, request.url.path, response.status_code,
        extra={"method": request.method, "path": request.url.path,
               "status": response.status_code, "duration_ms": duration_ms},
    )
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the traceback and return a clean 500 without leaking internals."""
    rid = request_id_var.get()
    logger.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "request_id": rid},
        headers={"X-Request-ID": rid},
    )


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


def _conversion_work(doc_id: str, pdf_path, options):
    """Build the job's work closure: convert, persist, return result fields."""
    def work() -> dict:
        converted = convert(pdf_path, options, storage.doc_dir(doc_id))
        output = storage.add_output(
            doc_id, converted.content, converted.output_format,
            converted.suggested_extension, assets=converted.assets,
        )
        preview = converted.content[: settings.preview_chars]
        return {
            "download_url": f"/api/v1/documents/{doc_id}/download"
                            f"?format={converted.output_format.value}",
            "filename": output.filename,
            "preview": preview,
            "truncated": len(converted.content) > len(preview),
        }
    return work


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


@app.post("/api/v1/documents/{doc_id}/convert", response_model=Job,
          status_code=202, tags=["documents"])
def convert_document(
    doc_id: str,
    answers: dict = Body(
        default={},
        description="Flat mapping of question id to answer, e.g. "
        '{"output_format": "markdown", "do_ocr": true}.',
    ),
    callback_url: Optional[str] = Query(
        default=None,
        description="Optional URL to POST the result to when the job finishes.",
    ),
) -> Job:
    """Start converting a document; returns a job to poll.

    Conversion runs in the background (it can take seconds to minutes).  Poll
    ``GET /api/v1/jobs/{job_id}`` until the status is ``succeeded`` (then use
    ``download_url``) or ``failed``.  If ``callback_url`` is given, a webhook is
    POSTed there on completion.
    """

    record = storage.get(doc_id)
    if record is None:
        raise HTTPException(404, "document not found")

    if callback_url:
        error = check_url(callback_url, settings.webhook_allowed_hosts)
        if error:
            raise HTTPException(422, error)

    options = apply_answers(answers or {})
    work = _conversion_work(doc_id, record.pdf_path, options)
    return jobs.submit(doc_id, options.output_format, work, callback_url=callback_url)


@app.get("/api/v1/jobs/{job_id}", response_model=Job, tags=["jobs"])
def get_job(job_id: str) -> Job:
    """Return the current state of a conversion job."""

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/v1/documents/{doc_id}/download", tags=["documents"])
def download(doc_id: str,
             format: OutputFormat = Query(default=OutputFormat.markdown),
             bundle: Optional[str] = Query(
                 default=None,
                 description="Set to 'zip' to download the output plus its "
                             "referenced images as a single archive.")):
    output = storage.get_output(doc_id, format.value)
    if output is None:
        raise HTTPException(404, "no converted output for that format; convert first")

    if bundle == "zip":
        return _zip_response(doc_id, output)

    return FileResponse(
        output.path,
        filename=output.filename,
        media_type="application/octet-stream",
    )


def _zip_response(doc_id: str, output) -> Response:
    """Bundle the output file and its assets/ directory into a zip."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(output.path, arcname=output.filename)
        adir = storage.asset_dir(doc_id)
        if adir.is_dir():
            for asset in sorted(adir.iterdir()):
                if asset.is_file():
                    zf.write(asset, arcname=f"assets/{asset.name}")
    buf.seek(0)
    zip_name = f"{Path(output.filename).stem}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@app.get("/api/v1/documents/{doc_id}/assets/{filename}", tags=["documents"])
def get_asset(doc_id: str, filename: str) -> FileResponse:
    """Serve a referenced image written during conversion."""
    # Reject path traversal: only a bare filename is allowed.
    if filename != Path(filename).name or filename in ("", ".", ".."):
        raise HTTPException(400, "invalid asset name")
    path = storage.asset_dir(doc_id) / filename
    if not path.is_file():
        raise HTTPException(404, "asset not found")
    return FileResponse(path)


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
    table_mode: TableMode = Query(default=TableMode.accurate),
    ocr_languages: list[str] = Query(default=[]),
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
        "table_mode": table_mode.value,
        "ocr_languages": ocr_languages,
    })
    try:
        converted = await run_in_threadpool(
            convert, record.pdf_path, options, storage.doc_dir(record.id)
        )
    except ConversionError as exc:
        raise HTTPException(422, str(exc)) from exc

    output = storage.add_output(
        record.id, converted.content, converted.output_format,
        converted.suggested_extension, assets=converted.assets,
    )
    return FileResponse(
        output.path, filename=output.filename, media_type="application/octet-stream"
    )


# --------------------------------------------------------------------------- #
# Batch
# --------------------------------------------------------------------------- #
@app.post("/api/v1/batches", response_model=BatchResponse, status_code=202,
          tags=["batch"])
async def create_batch(
    files: list[UploadFile] = File(...),
    output_format: OutputFormat = Query(default=OutputFormat.markdown),
    do_ocr: bool = Query(default=False),
    do_table_structure: bool = Query(default=True),
    table_mode: TableMode = Query(default=TableMode.accurate),
    ocr_languages: list[str] = Query(default=[]),
    callback_url: Optional[str] = Query(default=None),
) -> BatchResponse:
    """Submit several PDFs at once; each becomes its own conversion job.

    Options are shared by all files (batches are non-interactive).  Poll the
    returned ``job_id``s, or ``GET /api/v1/batches/{id}`` for aggregate status.
    """
    if not files:
        raise HTTPException(422, "no files provided")
    if len(files) > settings.max_batch_files:
        raise HTTPException(422, f"too many files (max {settings.max_batch_files})")
    if callback_url:
        error = check_url(callback_url, settings.webhook_allowed_hosts)
        if error:
            raise HTTPException(422, error)

    # Validate and analyse every file first so a single bad file rejects the
    # whole batch (no partial submission).
    prepared = []
    for f in files:
        data = await _read_upload(f)
        filename = f.filename or "document.pdf"
        try:
            analysis = _analyze_bytes(data)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"could not read PDF '{filename}': {exc}") from exc
        prepared.append((filename, data, analysis))

    options = apply_answers({
        "output_format": output_format.value,
        "do_ocr": do_ocr,
        "do_table_structure": do_table_structure,
        "table_mode": table_mode.value,
        "ocr_languages": ocr_languages,
    })
    batch_id = uuid.uuid4().hex
    items: list[BatchItem] = []
    for filename, data, analysis in prepared:
        record = storage.create_document(filename, data, analysis)
        work = _conversion_work(record.id, record.pdf_path, options)
        job = jobs.submit(record.id, options.output_format, work,
                          callback_url=callback_url, batch_id=batch_id)
        items.append(BatchItem(filename=filename, document_id=record.id,
                               job_id=job.id, status=job.status))
    jobs.create_batch(batch_id, len(items))
    return BatchResponse(id=batch_id, created_at=time.time(),
                         count=len(items), items=items)


@app.get("/api/v1/batches/{batch_id}", response_model=BatchResponse, tags=["batch"])
def get_batch(batch_id: str) -> BatchResponse:
    """Return a batch and the current status of each of its jobs."""
    row = jobs.get_batch(batch_id)
    if row is None:
        raise HTTPException(404, "batch not found")
    items: list[BatchItem] = []
    for job in jobs.list_by_batch(batch_id):
        doc = storage.get(job.document_id)
        items.append(BatchItem(
            filename=doc.filename if doc else "(deleted)",
            document_id=job.document_id, job_id=job.id, status=job.status,
        ))
    return BatchResponse(id=batch_id, created_at=row["created_at"],
                         count=row["count"], items=items)


# --------------------------------------------------------------------------- #
# Web UI
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
