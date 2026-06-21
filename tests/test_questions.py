"""Tests for question generation and answer mapping."""

from __future__ import annotations

from app.models import DocumentAnalysis, ImageMode, OutputFormat
from app.questions import apply_answers, build_questions


def _analysis(**kw) -> DocumentAnalysis:
    base = dict(
        page_count=3,
        has_extractable_text=True,
        likely_scanned=False,
        has_images=False,
        encrypted=False,
        file_size_bytes=1234,
    )
    base.update(kw)
    return DocumentAnalysis(**base)


def test_scanned_doc_defaults_ocr_on():
    qs = {q.id: q for q in build_questions(_analysis(likely_scanned=True))}
    assert qs["do_ocr"].default is True


def test_non_scanned_doc_defaults_ocr_off():
    qs = {q.id: q for q in build_questions(_analysis())}
    assert qs["do_ocr"].default is False


def test_image_question_only_when_images_present():
    qs_no = {q.id for q in build_questions(_analysis(has_images=False))}
    qs_yes = {q.id for q in build_questions(_analysis(has_images=True))}
    assert "image_mode" not in qs_no
    assert "image_mode" in qs_yes


def test_page_range_only_for_multipage():
    single = {q.id for q in build_questions(_analysis(page_count=1))}
    multi = {q.id for q in build_questions(_analysis(page_count=5))}
    assert "page_range" not in single
    assert "page_range" in multi


def test_apply_answers_maps_fields():
    opts = apply_answers({
        "output_format": "html",
        "do_ocr": True,
        "image_mode": "embedded",
        "page_range": [2, 4],
    })
    assert opts.output_format is OutputFormat.html
    assert opts.do_ocr is True
    assert opts.image_mode is ImageMode.embedded
    assert opts.page_start == 2
    assert opts.page_end == 4


def test_apply_answers_defaults_on_empty():
    opts = apply_answers({})
    assert opts.output_format is OutputFormat.markdown
    assert opts.do_table_structure is True
    assert opts.ocr_languages == []


def test_ocr_language_question_for_scanned():
    qs = {q.id: q for q in build_questions(_analysis(likely_scanned=True))}
    assert "ocr_languages" in qs
    assert qs["ocr_languages"].type == "multichoice"
    assert qs["ocr_languages"].default == ["ja", "en"]


def test_no_ocr_language_question_for_clean_text():
    qs = {q.id for q in build_questions(_analysis())}
    assert "ocr_languages" not in qs


def test_apply_answers_maps_ocr_languages():
    opts = apply_answers({"do_ocr": True, "ocr_languages": ["ja", "en"]})
    assert opts.ocr_languages == ["ja", "en"]


def test_table_mode_question_present_with_default_accurate():
    qs = {q.id: q for q in build_questions(_analysis())}
    assert "table_mode" in qs
    assert qs["table_mode"].type == "choice"
    assert qs["table_mode"].default == "accurate"


def test_apply_answers_maps_table_mode():
    from app.models import TableMode
    opts = apply_answers({"table_mode": "fast"})
    assert opts.table_mode is TableMode.fast
