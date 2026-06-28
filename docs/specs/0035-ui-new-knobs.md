# Spec: UI の追随（新ノブ・VLM をバッチへ・対話の確認）

- **ID:** 0035
- **状態:** done
- **マイルストーン:** M12 UI の追随
- **関連 issue:** M12-1
- **作成日 / 更新日:** 2026-06-27 / 2026-06-27

## 1. 背景・目的

M10/M11 で品質ノブが増えた（`ocr_confidence_threshold`・`force_full_page_ocr`・
`ocr_preprocess`・`use_vlm`・`llm_preset`）。対話フローは質問を**動的描画**しているため、
これらは既に画面へ自動で出る（build_questions が出力し、`renderQuestions` が choice/boolean を
描画）。一方、**バッチ**は UI もエンドポイントも `output_format`/`do_ocr` 等に限定され、
新ノブ・VLM を指定できない（spec 0020 で「共通オプションのみ」とした名残）。

本 issue では、増えた品質ノブ・VLM を **Web UI から使える**状態にする。主対象はバッチの
パリティ。対話フローは追随済みであることを確認（テスト）する。

## 2. スコープ

### やること
- `POST /api/v1/batches` に品質ノブを追加：`force_full_page_ocr`・`ocr_confidence_threshold`・
  `use_vlm`（バッチ共通オプションとして全ファイルに適用）。
- バッチ UI に対応コントロールを追加：VLM トグル／全ページ OCR トグル／OCR 強度セレクト
  （標準／強気=0.2／最大=0.1 を `ocr_confidence_threshold` にマップ）。
- 既定 `pytest` で、バッチが新ノブをジョブのオプションへ反映することを検証。
- 対話フローが新ノブ・VLM を質問として出すことをテストで固定（回帰防止）。

### やらないこと（非スコープ）
- 対話フローの UI 改修（既に動的描画で追随済み。質問のグルーピング等の UX 整理は別途）。
- バッチへの `llm_preset`・`ocr_preprocess` 追加（前者は対話/one-shot に、後者は既定 OFF・
  一般化せずのため見送り。必要になれば別 issue）。
- ブラウザ E2E 自動テスト（UI はスモーク確認のまま。spec 0019/0020 の方針踏襲）。

## 3. 要件

### 機能要件
- バッチ未指定時は現挙動どおり（新ノブは既定値＝OFF/None）。後方互換。
- バッチで `use_vlm=true` のとき、全ファイルが VLM パイプラインで変換される。
- `ocr_confidence_threshold` は 0.0–1.0（範囲外は 422）。`force_full_page_ocr` は bool。
- バッチ UI の選択がクエリパラメータに正しく載る（標準は信頼度を送らない＝エンジン既定）。
- 対話フロー：scanned PDF / 画像で `force_full_page_ocr`・`ocr_strength`・`use_vlm`
  （画像はさらに `ocr_preprocess`）が質問に含まれる。

### 非機能要件
- バックエンドは `apply_answers` を介して既存の検証・後方互換を流用。
- UI 追加は依存ゼロ（既存の素の JS/HTML パターンに合わせる）。

## 4. 設計

### `app/main.py`（`create_batch`）
クエリに追加：
```python
force_full_page_ocr: bool = Query(default=False),
ocr_confidence_threshold: Optional[float] = Query(default=None, ge=0.0, le=1.0),
use_vlm: bool = Query(default=False),
```
`apply_answers({... , "force_full_page_ocr":…, "ocr_confidence_threshold":…, "use_vlm":…})`。

### `app/static/index.html`（バッチ）
`batch-options` に追加：
- `<select id="batch-ocr-strength">`（標準/強気/最大）
- `<input type="checkbox" id="batch-fullpage-ocr">`（全ページ強制 OCR）
- `<input type="checkbox" id="batch-vlm">`（高精度 VLM）

### `app/static/app.js`（`submitBatch`）
`URLSearchParams` に上記を反映。OCR 強度は `{standard:"", aggressive:"0.2", max:"0.1"}` で
`ocr_confidence_threshold` を送る（standard は送らない）。`use_vlm`・`force_full_page_ocr` は
チェック状態を送る。

### 影響範囲
- 変更：`app/main.py`, `app/static/index.html`, `app/static/app.js`,
  `docs/roadmap.md`, `README.md`, テスト。
- 既存 API・対話フローは後方互換（追加のみ）。

## 5. 受け入れ条件（Definition of Done）

- [x] `create_batch` が `force_full_page_ocr`・`ocr_confidence_threshold`・`use_vlm` を受け取り、
      ジョブのオプションへ反映（テストで検証）。範囲外の信頼度は 422。
- [x] バッチ UI に VLM／全ページ OCR／OCR 強度のコントロールがあり、クエリに載る
      （served HTML/JS と OpenAPI でスモーク確認）。
- [x] 対話フローが新ノブ・VLM を質問として出す（test_questions で固定）。
- [x] 既定 `pytest` 169 passed。README のバッチ説明を更新。

## 6. テスト計画

- 既定 `pytest`：
  - `convert` を記録するスタブにして、バッチに `use_vlm=true&force_full_page_ocr=true&
    ocr_confidence_threshold=0.1` を投げ、ジョブ実行時のオプションへ反映されることを確認。
  - 範囲外 `ocr_confidence_threshold=2` が 422。
  - `build_questions` が scanned PDF / 画像で新ノブ・VLM を含む（test_questions に追加）。
- 手動：UI でバッチに VLM トグル等が出ること、クエリに載ることをスモーク確認。

## 7. リスク・代替案

- **バッチで VLM を選ぶと重い**：既定 OFF・利用者の明示選択時のみ。UI に「重い」旨を表示。
- **UI 自動テストが無い**：JS は最小で、サーバ側のパリティをテストで担保（UI はスモーク）。
- **代替：バッチは現状維持**：新ノブが UI から使えない不整合が残るため、最低限のパリティを取る。

## 8. 未決事項

- 対話フローの質問が増えたため、将来「詳細設定」の折りたたみで UX 整理を検討（別 issue）。
- バッチへの `llm_preset` 追加は需要次第。
