"""Conversion core: turn a PDF into the requested output format using docling.

docling is imported lazily inside :func:`convert` so that importing this module
(and therefore the whole web app and its tests) does not require the heavy
docling/ML stack to be installed.  Callers that only need analysis or the API
schema never pay that cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .config import settings
from .formats import extension_of, is_pdf
from .models import ConversionOptions, ImageMode, OutputFormat, TableMode


class ConversionError(RuntimeError):
    """Raised when a conversion cannot be completed."""


@dataclass
class ConvertedDocument:
    """Result of a conversion, ready to be persisted or returned."""

    content: str
    output_format: OutputFormat
    suggested_extension: str
    assets: dict = field(default_factory=dict)  # filename -> bytes (referenced images)


_EXTENSIONS = {
    OutputFormat.markdown: "md",
    OutputFormat.html: "html",
    OutputFormat.json: "json",
    OutputFormat.text: "txt",
}


@lru_cache(maxsize=8)
def _get_converter(do_ocr: bool, do_table_structure: bool, table_mode: str,
                   generate_images: bool, artifacts_path: Optional[str] = None,
                   ocr_languages: tuple = (), easyocr_models: Optional[str] = None):
    """Build (and cache) a docling ``DocumentConverter`` for a set of options.

    docling converters are expensive to construct because they load models, so
    we cache them keyed by the options that actually affect the pipeline.

    *artifacts_path* points at a directory of pre-downloaded models (used in the
    Docker image so no models are fetched at runtime); ``None`` falls back to
    docling's default cache.
    """

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    if artifacts_path:
        pipeline_options.artifacts_path = artifacts_path
    pipeline_options.do_ocr = do_ocr
    if do_ocr and ocr_languages:
        # Use EasyOCR so language codes have a stable convention (en/ja/...).
        from docling.datamodel.pipeline_options import EasyOcrOptions
        ocr_opts = EasyOcrOptions(lang=list(ocr_languages))
        if easyocr_models:
            # Use models baked into the image; never reach the network.
            ocr_opts.model_storage_directory = easyocr_models
            ocr_opts.download_enabled = False
        pipeline_options.ocr_options = ocr_opts
    pipeline_options.do_table_structure = do_table_structure
    if do_table_structure:
        pipeline_options.table_structure_options.mode = (
            TableFormerMode.ACCURATE
            if table_mode == TableMode.accurate.value
            else TableFormerMode.FAST
        )
    if generate_images:
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = 2.0

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def _export(document, options: ConversionOptions) -> tuple[str, dict]:
    """Export a docling document to (content, assets).

    *assets* maps ``filename -> bytes`` and is only populated for the
    ``referenced`` image mode (md/html), where images are written as separate
    files and the content links them as ``assets/<name>``.
    """

    from docling_core.types.doc import ImageRefMode

    if options.output_format is OutputFormat.json:
        return json.dumps(document.export_to_dict(), ensure_ascii=False, indent=2), {}
    if options.output_format is OutputFormat.text:
        return document.export_to_text(), {}

    is_html = options.output_format is OutputFormat.html

    if options.image_mode is ImageMode.referenced:
        return _export_referenced(document, is_html)

    image_mode = {
        ImageMode.placeholder: ImageRefMode.PLACEHOLDER,
        ImageMode.embedded: ImageRefMode.EMBEDDED,
    }[options.image_mode]
    if is_html:
        return document.export_to_html(image_mode=image_mode), {}
    return document.export_to_markdown(image_mode=image_mode), {}


def _relativize_asset_links(content: str, assets_dir: Path) -> str:
    """Rewrite docling's absolute artifacts-dir paths to relative ``assets/...``.

    ``save_as_markdown/html`` link images by the absolute path of the temp
    ``assets`` dir; the persisted/zipped output expects a relative
    ``assets/<name>`` link instead.  A no-op if links are already relative.
    """
    return content.replace(str(assets_dir), "assets")


def _export_referenced(document, is_html: bool) -> tuple[str, dict]:
    """Save with images written to a sibling ``assets/`` dir; return both."""

    import tempfile
    from docling_core.types.doc import ImageRefMode

    ext = "html" if is_html else "md"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out = td / f"output.{ext}"
        assets_dir = td / "assets"
        if is_html:
            document.save_as_html(out, artifacts_dir=assets_dir,
                                  image_mode=ImageRefMode.REFERENCED)
        else:
            document.save_as_markdown(out, artifacts_dir=assets_dir,
                                      image_mode=ImageRefMode.REFERENCED)
        content = _relativize_asset_links(out.read_text(encoding="utf-8"), assets_dir)
        assets: dict = {}
        if assets_dir.is_dir():
            for f in sorted(assets_dir.iterdir()):
                if f.is_file():
                    assets[f.name] = f.read_bytes()
        return content, assets


def convert(source_path: str | Path, options: ConversionOptions,
            image_dir: Optional[str | Path] = None) -> ConvertedDocument:
    """Convert *source_path* according to *options*.

    The input may be any format docling supports (PDF/Office/HTML/image/...);
    the format is detected from the file extension.  Raises
    :class:`ConversionError` (never a raw docling exception) on failure so the
    web layer can map it to a clean HTTP response.
    """

    source_path = Path(source_path)
    if not source_path.exists():
        raise ConversionError(f"file not found: {source_path}")

    generate_images = options.image_mode in (ImageMode.embedded, ImageMode.referenced)
    try:
        converter = _get_converter(
            do_ocr=options.do_ocr,
            do_table_structure=options.do_table_structure,
            table_mode=options.table_mode.value,
            generate_images=generate_images,
            artifacts_path=settings.docling_artifacts,
            ocr_languages=tuple(options.ocr_languages),
            easyocr_models=settings.easyocr_models,
        )
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ConversionError(
            "docling is not installed; run `pip install docling`"
        ) from exc

    convert_kwargs = {}
    # Page ranges only apply to paginated input (PDF); other formats ignore them.
    if is_pdf(extension_of(source_path.name)) and (
            options.page_start is not None or options.page_end is not None):
        start = options.page_start or 1
        end = options.page_end or 10**9
        convert_kwargs["page_range"] = (start, end)

    try:
        result = converter.convert(str(source_path), **convert_kwargs)
    except Exception as exc:  # noqa: BLE001 - normalise to ConversionError
        raise ConversionError(f"conversion failed: {exc}") from exc

    content, assets = _export(result.document, options)

    return ConvertedDocument(
        content=content,
        output_format=options.output_format,
        suggested_extension=_EXTENSIONS[options.output_format],
        assets=assets,
    )
