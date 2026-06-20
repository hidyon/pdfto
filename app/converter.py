"""Conversion core: turn a PDF into the requested output format using docling.

docling is imported lazily inside :func:`convert` so that importing this module
(and therefore the whole web app and its tests) does not require the heavy
docling/ML stack to be installed.  Callers that only need analysis or the API
schema never pay that cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .config import settings
from .models import ConversionOptions, ImageMode, OutputFormat, TableMode


class ConversionError(RuntimeError):
    """Raised when a conversion cannot be completed."""


@dataclass
class ConvertedDocument:
    """Result of a conversion, ready to be persisted or returned."""

    content: str
    output_format: OutputFormat
    suggested_extension: str


_EXTENSIONS = {
    OutputFormat.markdown: "md",
    OutputFormat.html: "html",
    OutputFormat.json: "json",
    OutputFormat.text: "txt",
}


@lru_cache(maxsize=8)
def _get_converter(do_ocr: bool, do_table_structure: bool, table_mode: str,
                   generate_images: bool, artifacts_path: Optional[str] = None,
                   ocr_languages: tuple = ()):
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
        pipeline_options.ocr_options = EasyOcrOptions(lang=list(ocr_languages))
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


def _export(document, options: ConversionOptions, image_dir: Optional[Path]) -> str:
    """Export a docling document to the requested string output."""

    from docling_core.types.doc import ImageRefMode

    if options.output_format is OutputFormat.json:
        return json.dumps(document.export_to_dict(), ensure_ascii=False, indent=2)
    if options.output_format is OutputFormat.text:
        return document.export_to_text()

    image_mode = {
        ImageMode.placeholder: ImageRefMode.PLACEHOLDER,
        ImageMode.embedded: ImageRefMode.EMBEDDED,
        ImageMode.referenced: ImageRefMode.REFERENCED,
    }[options.image_mode]

    if options.output_format is OutputFormat.html:
        return document.export_to_html(image_mode=image_mode)
    return document.export_to_markdown(image_mode=image_mode)


def convert(pdf_path: str | Path, options: ConversionOptions,
            image_dir: Optional[str | Path] = None) -> ConvertedDocument:
    """Convert *pdf_path* according to *options*.

    Raises :class:`ConversionError` (never a raw docling exception) on failure so
    the web layer can map it to a clean HTTP response.
    """

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise ConversionError(f"file not found: {pdf_path}")

    generate_images = options.image_mode in (ImageMode.embedded, ImageMode.referenced)
    try:
        converter = _get_converter(
            do_ocr=options.do_ocr,
            do_table_structure=options.do_table_structure,
            table_mode=options.table_mode.value,
            generate_images=generate_images,
            artifacts_path=settings.docling_artifacts,
            ocr_languages=tuple(options.ocr_languages),
        )
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ConversionError(
            "docling is not installed; run `pip install docling`"
        ) from exc

    convert_kwargs = {}
    if options.page_start is not None or options.page_end is not None:
        start = options.page_start or 1
        end = options.page_end or 10**9
        convert_kwargs["page_range"] = (start, end)

    try:
        result = converter.convert(str(pdf_path), **convert_kwargs)
    except Exception as exc:  # noqa: BLE001 - normalise to ConversionError
        raise ConversionError(f"conversion failed: {exc}") from exc

    image_path = Path(image_dir) if image_dir else None
    content = _export(result.document, options, image_path)

    return ConvertedDocument(
        content=content,
        output_format=options.output_format,
        suggested_extension=_EXTENSIONS[options.output_format],
    )
