# Spec: opt-in 実機テストスイートの整備（実変換 / OCR / LLM）

- **ID:** 0023
- **状態:** done
- **マイルストーン:** M7 検証スイートの拡充
- **関連 issue:** M7-1（opt-in 実機テストスイートの整備）
- **作成日 / 更新日:** 2026-06-22 / 2026-06-22

## 1. 背景・目的

既定 `pytest` は docling/anthropic をモックして軽く保つ方針（CLAUDE.md）。実変換・実 OCR は
`PDFTO_RUN_DOCLING_TESTS=1` の opt-in テスト（`tests/test_quality.py`）に分離済みだが、

- 実変換のカバレッジが**表サンプル＋ OCR のみ**で、出力形式（html/json/text）や
  ページ範囲などの実経路が未検証。
- **実 LLM 整形**（Anthropic API 実呼び出し）の opt-in テストが無い（モックのみ）。

これらを整理し、「重い検証は opt-in」という方針のまま**実経路の回帰**を捉えられるようにする。

## 2. スコープ

### やること
- 実変換の opt-in テストを**全出力形式（markdown/html/json/text）**とページ範囲指定に拡張。
- **実 LLM** の opt-in テストを新設し、専用フラグ `PDFTO_RUN_LLM_TESTS=1` ＋
  `ANTHROPIC_API_KEY` 必須でのみ実行（どちらか欠けたら skip）。
- 2 つの opt-in フラグ（docling / LLM）の使い方を CLAUDE.md・README に明記。

### やらないこと（非スコープ）
- 既定テスト（モック）の挙動変更。新しいモックテストの追加は最小限。
- 表抽出の品質指標・回帰サンプル拡張（=M7-2 で別途）。
- CI 構築（実行環境の用意は手動/専用環境に委ねる方針のまま）。

## 3. 要件

### 機能要件
- `PDFTO_RUN_DOCLING_TESTS=1` 時、`samples/table_sample.pdf` を
  markdown/html/json/text の 4 形式へ実変換し、各形式の最低限の形を検証する
  （json は `json.loads` 可能、html は要素を含む、いずれも非空）。
- ページ範囲（`page_start`/`page_end`）指定の実変換が成功する。
- `PDFTO_RUN_LLM_TESTS=1` かつ `ANTHROPIC_API_KEY` 設定時のみ、`llm.transform` が
  実 Claude を呼び、非空のテキストを返すことを検証する（フラグ/キーが無ければ skip）。
- 既定 `pytest`（フラグ無し）では上記はすべて **skip** され、結果は不変。

### 非機能要件
- LLM 実テストは**短い入力**で 1 回だけ呼ぶ（コスト最小）。
- アプリ本体（`app/*`）のコードは変更しない（テストとドキュメントのみ）。

## 4. 設計

### `tests/test_quality.py`（拡張）
- 既存の表変換（table_mode）・OCR テストは維持。
- 追加: `@pytest.mark.parametrize("fmt", [...4形式...])` の実変換テスト。
  - json: `json.loads(result.content)` が通る。
  - html: `"<"` を含む。
  - text/markdown: 非空。
- 追加: ページ範囲テスト（`page_start=1, page_end=1`）で例外なく非空。

### `tests/test_quality_llm.py`（新規）
- `RUN_LLM = os.environ.get("PDFTO_RUN_LLM_TESTS") == "1"`、
  `HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PDFTO_ANTHROPIC_API_KEY"))`。
- `pytestmark = skipif(not (RUN_LLM and HAS_KEY), reason=...)`。
- `llm.transform("Hello, world.", "Reply with only the word OK.")` 等の短い指示で、
  返り値が非空の `str` であることを検証（厳密一致はしない＝モデル差を許容）。

### CLAUDE.md / README
- 「重い検証は opt-in」の節に LLM 用フラグ `PDFTO_RUN_LLM_TESTS=1`（＋ `ANTHROPIC_API_KEY`）
  を追記し、docling 用と並べて手順を明記。

### 影響範囲
- 追加: `tests/test_quality_llm.py`。
- 変更: `tests/test_quality.py`, `CLAUDE.md`, `README.md`, `docs/roadmap.md`。
- アプリ本体・既定テストは不変。

## 5. 受け入れ条件（Definition of Done）

- [x] 既定 `pytest` で新規 opt-in テストが skip され、結果が従来どおり（95 passed / 11 skipped）。
- [x] `PDFTO_RUN_DOCLING_TESTS=1` で 4 形式＋ページ範囲の実変換テストが通る（10 passed）。
- [x] `PDFTO_RUN_LLM_TESTS=1`＋キー設定時に実 LLM テストが通る（本環境はキー無しで skip を確認。
      実呼び出しは手動/専用環境）。
- [x] 2 つの opt-in フラグが CLAUDE.md・README に明記されている。

## 6. テスト計画

- 既定 `python -m pytest`：新規テストが skip され、合計が従来どおりであること。
- `PDFTO_RUN_DOCLING_TESTS=1 python -m pytest tests/test_quality.py`：実変換（モデル DL あり）。
- 実 LLM：本リポジトリ環境では実 API キー/ネットワークが無いため**手動/専用環境**で実行。
  本環境では skip 状態（フラグ/キー無し）になることをもって配線を確認する。

## 7. リスク・代替案

- **実 LLM の課金/ネットワーク**：専用フラグ＋キー必須で誤起動を防ぐ。入力は最小。
- **docling のモデル差で出力が揺れる**：形式の「形」だけを検証し、内容の厳密一致は避ける
  （spec 0012 の知見を踏襲）。
- **代替: 実 LLM をモックのみで済ます**：実経路の回帰を捉えられないため、opt-in 実テストを
  別フラグで用意する。

## 8. 未決事項

- LLM 実テストのモデルは既定（`PDFTO_LLM_MODEL`）に従う。サンプル拡張は M7-2 で扱う。

## 9. 実装メモ（検証で判明したこと）

- 全形式テストの初回実行で **text 形式が空**になり失敗。`table_sample.pdf` は Picture
  として分類される（spec 0012）ため、画像のみページの `export_to_text()` は正当に空になる。
  → text は「例外なく `str` を返す」ことのみ検証し、非空は構造化形式（md/html/json）に限定。
  これは docling の挙動どおりであり、テスト側の前提を修正して整合させた。
- 既定 `pytest`: 95 passed / 11 skipped（opt-in 6 件が追加 skip）。
  `PDFTO_RUN_DOCLING_TESTS=1`: 10 件 passed（実変換・OCR・全形式・ページ範囲）。
