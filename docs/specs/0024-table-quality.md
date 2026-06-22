# Spec: 表抽出の品質指標と回帰サンプルの拡張

- **ID:** 0024
- **状態:** done
- **マイルストーン:** M7 検証スイートの拡充
- **関連 issue:** M7-2（表抽出の品質指標と回帰サンプル拡張）
- **作成日 / 更新日:** 2026-06-22 / 2026-06-22

## 1. 背景・目的

既存の `table_sample.pdf` は full-grid＋本文なしのため docling に **Picture** と分類され、
表として抽出されない（spec 0012）。そのため「表抽出が壊れていないか」を捉える回帰指標が
無かった。docling が**確実に表として抽出できる**サンプルを追加し、抽出セルの復元率という
品質指標で回帰を検出できるようにする。

> spike（試行）で確認: 表の前後に本文段落を置き、罫線を控えめ（ヘッダ下線＋最下線）に
> すると docling は表として正しく検出し、Markdown 表（セル全復元）を出力する。

## 2. スコープ

### やること
- 新しい回帰サンプル `samples/table_doc_sample.pdf` を生成（本文付き・罫線控えめの
  「文書中の表」）。生成は `scripts/make_sample_pdfs.py` に追加し、PDF をコミット。
- opt-in 実機テスト（`PDFTO_RUN_DOCLING_TESTS=1`）に**表抽出の品質指標**を追加：
  Markdown 表を解析し、列数・行数と**セル復元率**を検証する。
- 既存 `table_sample.pdf`（Picture 分類の既知ケース）はそのまま残す。

### やらないこと（非スコープ）
- 既定テスト（モック）の変更。OCR・LLM 経路の変更。
- 複数ページ・結合セル・複雑表の網羅（単純表の回帰に絞る）。
- アプリ本体（`app/*`）の変更。

## 3. 要件

### 機能要件
- `table_doc_sample.pdf` を docling（`do_table_structure=True`）で Markdown 変換すると、
  Markdown 表が出力される（区切り行 `---` と `|` セルを含む）。
- 期待セル（5 行 × 4 列の既知の値）の**復元率が 1.0**（全セル一致）であること。
- 抽出表の**列数=4・データ行数=5**（ヘッダ除く）であること。
- 既定 `pytest`（フラグ無し）では当該テストが skip され、結果は不変。

### 非機能要件
- 品質指標は再現可能で、モデル差の軽微なゆらぎに過度に脆くない（セル値は文字列一致、
  数値の桁内空白などは正規化して比較）。

## 4. 設計

### `scripts/make_sample_pdfs.py`
- `make_table_doc_sample(path)` を追加。タイトル＋説明段落＋表（罫線: ヘッダ下線・最下線、
  ヘッダ太字）＋脚注段落。表データは既知の 5×4。`main()` で `table_doc_sample.pdf` も出力。

### `tests/test_quality.py`
- 既知の期待データ `EXPECTED_TABLE`（generator と一致）を定義。
- ヘルパ `parse_markdown_table(md)`：最初の Markdown 表を行×セルの 2 次元リストに復元
  （区切り行 `---` は除外、セル前後空白を strip）。
- `test_table_doc_quality()`（opt-in）：
  - 変換 → `parse_markdown_table` で表を取得。
  - 列数=4、データ行数=5 を assert。
  - セル復元率 = 一致セル数 / 期待セル数 を計算し `== 1.0` を assert。

### 影響範囲
- 追加: `samples/table_doc_sample.pdf`。
- 変更: `scripts/make_sample_pdfs.py`, `tests/test_quality.py`,
  `README.md`（サンプル説明・任意）, `docs/roadmap.md`。
- アプリ本体・既定テストは不変。

## 5. 受け入れ条件（Definition of Done）

- [x] `samples/table_doc_sample.pdf` が追加され、生成手順がスクリプトにある。
- [x] opt-in テストで列数=4・行数=5・セル復元率=1.0 を検証できる。
- [x] `PDFTO_RUN_DOCLING_TESTS=1` で当該テストが通る（1 passed、復元率 1.0）。
- [x] 既定 `pytest` では skip され、結果が従来どおり（95 passed / 12 skipped）。

## 6. テスト計画

- 既定 `python -m pytest`：新テストが skip され合計が従来どおり。
- `PDFTO_RUN_DOCLING_TESTS=1 python -m pytest tests/test_quality.py`：表品質テストを含め通る。
- サンプル再生成 `python scripts/make_sample_pdfs.py` が `table_doc_sample.pdf` を出力。

## 7. リスク・代替案

- **モデル更新で抽出が変わる**：復元率という指標で検出できる（回帰の可視化が目的）。
  ゆらぎに弱すぎないようセル比較は空白正規化する。
- **代替: 既存 table_sample を作り直す**：spec 0012 の既知ケース（Picture 分類）を失うため、
  別サンプルを追加する。

## 8. 未決事項

- 当面は単純表 1 種の回帰に絞る。複雑表・複数ページは将来の課題。
