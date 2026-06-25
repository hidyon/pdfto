"""Build the interactive questions for a document, and apply the answers.

The set of questions adapts to what :mod:`app.analysis` found in the PDF: a
scanned document is asked about OCR, a multi-page document about page ranges,
and so on.  Each question's ``id`` matches a field on
:class:`~app.models.ConversionOptions`, so applying answers is a direct mapping.
"""

from __future__ import annotations

from .formats import kind_of
from .models import (
    ConversionOptions,
    DocumentAnalysis,
    ImageMode,
    OutputFormat,
    Question,
    QuestionChoice,
    TableMode,
)


def build_questions(analysis: DocumentAnalysis) -> list[Question]:
    """Return the questions appropriate for *analysis*."""

    questions: list[Question] = [
        Question(
            id="output_format",
            type="choice",
            prompt="どの形式に変換しますか？",
            help="他システムで扱うなら Markdown か JSON が便利です。",
            default=OutputFormat.markdown.value,
            choices=[
                QuestionChoice(value=OutputFormat.markdown.value, label="Markdown (.md)"),
                QuestionChoice(value=OutputFormat.html.value, label="HTML (.html)"),
                QuestionChoice(value=OutputFormat.json.value, label="JSON (構造化)"),
                QuestionChoice(value=OutputFormat.text.value, label="プレーンテキスト (.txt)"),
            ],
        )
    ]

    # OCR and table-structure questions only apply to formats that go through
    # the docling PDF/image pipeline.  Office/HTML/etc. extract text and tables
    # natively, so OCR/table options have no effect there.  An unknown
    # extension ("" for legacy/PDF-only analyses) is treated as PDF.
    pipeline_input = kind_of(analysis.source_extension or ".pdf") in ("pdf", "image")

    if pipeline_input:
        # OCR — only worth asking when text extraction looked poor.
        if analysis.likely_scanned or not analysis.has_extractable_text:
            ocr_default = True
            ocr_help = "テキストが抽出できませんでした。スキャン文書の可能性が高いため、OCR を推奨します。"
        else:
            ocr_default = False
            ocr_help = "通常は不要です。画像内の文字も読み取りたい場合のみ有効化してください。"
        questions.append(
            Question(
                id="do_ocr",
                type="boolean",
                prompt="OCR（画像からの文字認識）を行いますか？",
                help=ocr_help,
                default=ocr_default,
            )
        )
        # OCR language selection — only relevant when OCR is on the table.
        if analysis.likely_scanned or not analysis.has_extractable_text:
            questions.append(
                Question(
                    id="ocr_languages",
                    type="multichoice",
                    prompt="OCR の言語は？（複数選択可）",
                    help="OCR を行う場合の対象言語。文書の言語に合わせて選んでください。",
                    default=["ja", "en"],
                    choices=[
                        QuestionChoice(value="en", label="English"),
                        QuestionChoice(value="ja", label="日本語"),
                        QuestionChoice(value="ch_sim", label="简体中文"),
                        QuestionChoice(value="ko", label="한국어"),
                        QuestionChoice(value="fr", label="Français"),
                        QuestionChoice(value="de", label="Deutsch"),
                        QuestionChoice(value="es", label="Español"),
                    ],
                )
            )
        # Full-page OCR — useful for hybrid PDFs with a partial text layer.
        questions.append(
            Question(
                id="force_full_page_ocr",
                type="boolean",
                prompt="全ページを強制 OCR しますか？",
                help="テキスト層を無視して全ページを OCR します。一部だけ文字が埋まった"
                "ハイブリッド PDF の取りこぼし対策に有効です（処理は重くなります）。",
                default=False,
            )
        )
        # OCR aggressiveness — lowering the confidence threshold recovers text
        # from noisy/photographed scans (at the cost of more false positives).
        questions.append(
            Question(
                id="ocr_strength",
                type="choice",
                prompt="OCR の拾い方の強さは？",
                help="ノイズの多い写真スキャンで文字を取りこぼす場合は「強気」を選ぶと"
                "回収率が上がります（誤検出も増えます）。通常は標準で十分です。",
                default="standard",
                choices=[
                    QuestionChoice(value="standard", label="標準（推奨）"),
                    QuestionChoice(value="aggressive", label="強気（低品質スキャン向け）"),
                    QuestionChoice(value="max", label="最大（かなりノイジーなスキャン）"),
                ],
            )
        )

    # Table structure recovery (same PDF/image pipeline condition).
    if pipeline_input:
        questions.append(
            Question(
                id="do_table_structure",
                type="boolean",
                prompt="表の構造を復元しますか？",
                help="表を含む文書では有効を推奨します（処理は少し重くなります）。",
                default=True,
            )
        )
        questions.append(
            Question(
                id="table_mode",
                type="choice",
                prompt="表抽出の精度は？",
                help="accurate は精度重視、fast は速度重視。表構造を復元する場合に有効です。",
                default=TableMode.accurate.value,
                choices=[
                    QuestionChoice(value=TableMode.accurate.value, label="高精度 (accurate)"),
                    QuestionChoice(value=TableMode.fast.value, label="高速 (fast)"),
                ],
            )
        )

    # Image handling — only relevant when images are present.
    if analysis.has_images:
        questions.append(
            Question(
                id="image_mode",
                type="choice",
                prompt="画像の扱いをどうしますか？",
                help="埋め込みは単一ファイルで完結、参照は画像を別ファイルに書き出します。",
                default=ImageMode.placeholder.value,
                choices=[
                    QuestionChoice(value=ImageMode.placeholder.value, label="プレースホルダのみ（軽量）"),
                    QuestionChoice(value=ImageMode.embedded.value, label="本文に埋め込む (base64)"),
                    QuestionChoice(value=ImageMode.referenced.value, label="別ファイルに書き出して参照"),
                ],
            )
        )

    # Page range — only worth asking for multi-page documents.
    if analysis.page_count > 1:
        questions.append(
            Question(
                id="page_range",
                type="range",
                prompt=f"変換するページ範囲は？（全 {analysis.page_count} ページ）",
                help="空欄なら全ページを変換します。",
                default=[1, analysis.page_count],
            )
        )

    # LLM post-processing — only when the feature is configured.
    from .config import settings
    if settings.llm_enabled:
        questions.append(
            Question(
                id="llm_instruction",
                type="text",
                prompt="変換後にAIで整形しますか？（任意の指示）",
                help="例: 「日本語に翻訳」「要約」「見出しを整える」。空欄ならそのまま出力します。",
                default="",
            )
        )

    return questions


def apply_answers(answers: dict) -> ConversionOptions:
    """Translate a flat ``{question_id: value}`` mapping into options.

    Unknown keys are ignored and missing keys fall back to the model defaults,
    so a partial set of answers is always valid.
    """

    data: dict = {}
    for key in ("output_format", "do_ocr", "do_table_structure", "image_mode",
                "table_mode", "force_full_page_ocr", "do_cell_matching"):
        if key in answers and answers[key] is not None:
            data[key] = answers[key]

    if answers.get("image_scale") is not None:
        data["image_scale"] = float(answers["image_scale"])

    # OCR strength preset → confidence threshold. "standard" leaves the engine
    # default (None); stronger presets lower the threshold to raise recall.
    _ocr_strength = {"aggressive": 0.2, "max": 0.1}
    strength = answers.get("ocr_strength")
    if strength in _ocr_strength:
        data["ocr_confidence_threshold"] = _ocr_strength[strength]
    elif answers.get("ocr_confidence_threshold") is not None:
        data["ocr_confidence_threshold"] = float(answers["ocr_confidence_threshold"])

    langs = answers.get("ocr_languages")
    if isinstance(langs, (list, tuple)):
        data["ocr_languages"] = [str(x) for x in langs]

    instruction = answers.get("llm_instruction")
    if isinstance(instruction, str) and instruction.strip():
        data["llm_instruction"] = instruction.strip()

    page_range = answers.get("page_range")
    if isinstance(page_range, (list, tuple)) and len(page_range) == 2:
        start, end = page_range
        if start is not None:
            data["page_start"] = int(start)
        if end is not None:
            data["page_end"] = int(end)
    else:
        if answers.get("page_start") is not None:
            data["page_start"] = int(answers["page_start"])
        if answers.get("page_end") is not None:
            data["page_end"] = int(answers["page_end"])

    return ConversionOptions(**data)
