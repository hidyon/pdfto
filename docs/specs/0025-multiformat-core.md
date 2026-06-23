# Spec: 変換コア・保存の多形式入力対応

- **ID:** 0025
- **状態:** done
- **マイルストーン:** M8 入力フォーマット拡張
- **関連 issue:** M8-1（変換コア・保存の多形式対応）

- **作成日 / 更新日:** 2026-06-22 / 2026-06-22

## 1. 背景・目的

コア（converter）と保存（storage）は PDF 専用になっている：保存は常に `source.pdf`
として書き、`convert()` の引数も `pdf_path`、page_range を無条件に渡す。docling 自体は
DOCX/PPTX/XLSX/HTML/Markdown/画像など多形式に対応している（本環境で HTML・PNG・DOCX の
変換を spike で確認済み）。まず**コアと保存をフォーマット非依存に一般化**し、PDF 以外も
変換できる土台を作る（受け口/解析/質問の Web 層対応は M8-2）。

## 2. スコープ

### やること
- 対応拡張子の allowlist と判定ユーティリティを追加（依存ゼロ・docling 非 import）。
- 保存を**実拡張子**で行う（`source.pdf` 固定をやめ `source<ext>`）。
- `convert()` を任意ソースに対応（引数名一般化、docling は拡張子で形式自動判定）。
- ページ範囲（`page_range`）は **PDF のみ**に適用（非ページ形式に渡さない）。
- モックでコア/保存の挙動をユニットテスト（実変換は opt-in 側で別途）。

### やらないこと（非スコープ）
- アップロード受け口の検証拡張・analysis 分岐・質問の出し分け・UI/クライアント（=M8-2）。
- 形式別の高度オプション（PPTX のノート抽出等）。
- 新しい出力形式の追加。

## 3. 要件

### 機能要件
- `app/formats.py`：`SUPPORTED_EXTENSIONS`（pdf, docx, pptx, xlsx, html/htm, md,
  csv, png, jpg/jpeg, tif/tiff, bmp, webp）と、`extension_of(filename)` /
  `is_supported(ext)` / `is_pdf(ext)` を提供。
- `storage.create_document(filename, data, analysis)` は `filename` の拡張子で
  `source<ext>` に保存する（拡張子が無ければ `.pdf`）。`DocumentRecord` は保存先を
  `source_path` で公開する（DB 列名 `pdf_path` は据え置き＝マイグレーション不要、
  値に実拡張子のパスを格納）。
- `converter.convert(source_path, options, image_dir=None)`：docling が拡張子で形式を
  判定して変換。`page_range` は `source_path` が PDF のときのみ付与する。
- 失敗は従来どおり `ConversionError` に正規化。

### 非機能要件
- コアは Web/FastAPI に非依存のまま。`formats.py` は標準ライブラリのみ。
- 既存の PDF 経路の挙動は不変（回帰なし）。

## 4. 設計

### `app/formats.py`（新規）
```python
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
    ".md", ".csv", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
def extension_of(filename: str) -> str: ...   # 小文字の拡張子（先頭ドット付き）/ 無ければ ""
def is_supported(ext: str) -> bool: ...
def is_pdf(ext: str) -> bool: ...             # ext == ".pdf"
```

### `app/storage.py`
- `create_document`：`ext = extension_of(filename) or ".pdf"`、保存先 `d / f"source{ext}"`。
- `DocumentRecord.pdf_path` → `source_path` に改名（読み出しは DB 列 `pdf_path` のまま）。

### `app/converter.py`
- `convert(pdf_path → source_path, ...)`：引数名を一般化。
- `page_range` の付与を `is_pdf(extension_of(str(source_path)))` のときのみに限定。
- `_get_converter` は当面 PDF の `format_options` のみ設定（他形式は docling 既定）。
  画像 OCR は docling 既定で動く（spike 確認）。

### 影響範囲
- 追加: `app/formats.py`, テスト。
- 変更: `app/storage.py`, `app/converter.py`, `app/main.py`（`record.pdf_path` →
  `record.source_path` の参照更新）, `docs/roadmap.md`。
- DB スキーマ・既定 API 挙動・既存 PDF 変換は不変。

## 5. 受け入れ条件（Definition of Done）

- [x] `formats.py` の allowlist/判定が単体テストで検証される（test_formats.py）。
- [x] `storage.create_document` が拡張子に応じた `source<ext>` を書き、`source_path`
      で参照できる（PDF は従来どおり `source.pdf`）（test_storage.py）。
- [x] `convert()` が非 PDF で `page_range` を渡さない（PDF では従来どおり渡す）— モック検証
      （test_converter_config.py）。
- [x] `app/main.py` が `source_path` 参照に更新され、既定 `pytest` が通る。
- [x] 既存の PDF 経路の挙動が不変（103 passed / 12 skipped）。

## 6. テスト計画

- 既定 `python -m pytest`（モック）：
  - `formats`：拡張子判定・allowlist。
  - `storage`：`*.docx` を渡すと `source.docx` が書かれ `source_path` が一致。PDF は `source.pdf`。
  - `converter`（docling をモック）：非 PDF で `page_range` 不付与、PDF で付与を検証。
- 実変換（HTML/画像/DOCX）は opt-in（M8-2 で受け口を通した上で `test_quality.py` に追加検討）。

## 7. リスク・代替案

- **DB 列名 `pdf_path` の据え置き**：マイグレーションを避けつつ実拡張子のパスを格納。将来の
  混乱を避けるため Python 側は `source_path` に統一しコメントで明記。
- **形式別 backend の依存欠如**：未導入 backend は docling が例外 → `ConversionError` に正規化。
  実際に有効な形式は環境依存である旨をドキュメントに記す（M8-2）。
- **代替: 列名もマイグレーション**：今は不要なリスクなので見送り。

## 8. 未決事項

- OCR/表オプションの形式別最適化は将来課題。M8-1 は PDF の挙動を保ちつつ土台を作る。
