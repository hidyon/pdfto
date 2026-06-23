# Spec: 受け口・解析・質問の多形式対応（Web 層）

- **ID:** 0026
- **状態:** done
- **マイルストーン:** M8 入力フォーマット拡張
- **関連 issue:** M8-2（受け口/解析/質問の形式対応・UI/クライアント/docs）
- **作成日 / 更新日:** 2026-06-22 / 2026-06-22

## 1. 背景・目的

M8-1 でコア（converter/storage）は多形式対応になったが、Web 層がまだ PDF 専用：
アップロード検証は PDF のみ許可し、解析は常に `analyze_pdf`、質問は PDF 前提で出る。
受け口・解析・質問をフォーマットに応じて一般化し、PDF 以外（Office/HTML/画像など）も
**アップロード→質問→変換→ダウンロード**まで通せるようにする。

## 2. スコープ

### やること
- アップロード検証を allowlist（M8-1 の `formats.SUPPORTED_EXTENSIONS`）に拡張。
  `%PDF` マジック確認は PDF のみに適用。
- 解析をフォーマット別に分岐（PDF=従来の `analyze_pdf`、画像=OCR 前提の最小解析、
  その他=テキスト抽出可の最小解析）。`DocumentAnalysis` に `source_extension` を追加。
- 質問の出し分け：表構造の質問は PDF/画像のみ（その他は docling が自動処理）。OCR・画像・
  ページ範囲は既存の解析フラグ条件で自然に出し分く。
- UI（ドロップゾーン文言・`accept`）、README を多形式に更新。

### やらないこと（非スコープ）
- 形式別の高度オプション（PPTX ノート等）。新出力形式。
- クライアントの API 変更（パスを渡すだけで多形式は既に動く。docstring/README のみ調整）。

## 3. 要件

### 機能要件
- 対応拡張子のアップロードが 200 で受理され、未対応（例 `.txt`/`.exe`）は 415。
- 非 PDF アップロードで `analyze` が docling/pypdf を呼ばずに `DocumentAnalysis` を返す
  （既定テストはモデル不要のまま）。
- `GET .../questions` が形式に応じた質問集合を返す：
  - Office/HTML/テキスト/データ: 出力形式（＋ LLM 有効時のみ整形）。OCR・表・画像・ページ質問なし。
  - 画像: 出力形式＋OCR＋OCR言語＋表（＋画像＋LLM）。
  - PDF: 従来どおり（解析に応じて全質問）。
- 既存 PDF 経路は不変。

### 非機能要件
- コアは Web 非依存のまま。`formats.kind_of` は標準ライブラリのみ。
- `DocumentAnalysis.source_extension` はデフォルト `""` で後方互換（既存行も読める）。

## 4. 設計

### `app/formats.py`
- `kind_of(ext) -> str`：`pdf` / `image`（png,jpg,jpeg,tif,tiff,bmp,webp）/
  `office`（docx,pptx,xlsx）/ `web`（html,htm）/ `text`（md）/ `data`（csv）/ `""`。

### `app/models.py`
- `DocumentAnalysis` に `source_extension: str = ""` を追加。

### `app/analysis.py`
- `analyze(path, filename) -> DocumentAnalysis` を追加（`analyze_pdf` は維持）：
  - `pdf` → `analyze_pdf(path)` に `source_extension=".pdf"`。
  - `image` → `page_count=1, has_extractable_text=False, likely_scanned=True,
    has_images=True`（OCR を推奨）。
  - その他 → `page_count=0, has_extractable_text=True, likely_scanned=False,
    has_images=False`。
  - いずれも `file_size_bytes`・`source_extension` を設定。

### `app/main.py`
- `_read_upload(file)`：`ext=extension_of(filename)`。`is_supported(ext)` でなければ 415。
  空・サイズ確認は従来。`%PDF` 確認は `is_pdf(ext)` のときのみ。
- `_analyze_bytes(data, filename)`：正しい拡張子で一時保存し `analyze(tmp, filename)`。
  呼び出し 3 箇所（upload/oneshot/batch）に `filename` を渡す。

### `app/questions.py`
- 表の質問（`do_table_structure`/`table_mode`）を
  `kind_of(analysis.source_extension) in ("pdf","image")` のときのみ追加。

### UI / docs
- `index.html`：ドロップゾーン文言を「ファイル（PDF/Word/PowerPoint/Excel/HTML/画像）」に、
  ファイル入力の `accept` を allowlist に更新。
- `README.md`：対応入力形式の節を追加し、PDF 前提の表現を一般化（実際に有効な形式は
  docling のバックエンド導入状況に依存する旨を明記）。

### 影響範囲
- 変更: `app/formats.py`, `app/models.py`, `app/analysis.py`, `app/main.py`,
  `app/questions.py`, `app/static/index.html`,（任意）`app/static/app.js`,
  `README.md`, `client/python/README.md`(任意), `docs/roadmap.md`。
- テスト追加。DB スキーマは不変。

## 5. 受け入れ条件（Definition of Done）

- [x] 対応形式（例 `.docx`/`.png`/`.html`）が 200 で受理され、`.txt` 等は 415。
- [x] 非 PDF の `questions` が形式に応じた集合を返す（Office で OCR/表が出ない・画像で OCR が出る）。
- [x] 既定 `pytest` が通る（107 passed / 13 skipped、モデル不要のまま）。
- [x] opt-in（`PDFTO_RUN_DOCLING_TESTS=1`）で HTML の実変換が通る（1 passed）。
- [x] UI/README が多形式対応に更新されている。

## 6. テスト計画

- 既定 `python -m pytest`：
  - `formats.kind_of` 単体。
  - API: `.docx` アップロード 200 → questions に OCR/表が無い。`.png` アップロード 200 →
    questions に OCR がある。`.txt` は 415。（convert はモック、非 PDF 解析は docling 不要）
- opt-in: `test_quality.py` に一時 HTML を書いて実変換し、表/見出しが出ることを確認。

## 7. リスク・代替案

- **content_type の不確実性**：判定は拡張子主体にする（従来も filename フォールバックあり）。
- **バックエンド未導入の形式**：変換時に docling 例外 → `ConversionError` → クリーンな 5xx。
  README に「有効な形式は環境依存」を明記。
- **代替: 全形式で従来の質問を出す**：無意味な質問でUXが悪化するため出し分ける。

## 8. 未決事項

- `.txt` は当面非対応（docling 経由の利点が薄い）。必要になれば追加。
