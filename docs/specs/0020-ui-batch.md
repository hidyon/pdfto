# Spec: Web UI にバッチ投入・進捗表示

- **ID:** 0020
- **状態:** done
- **マイルストーン:** M5 UI の追随
- **関連 issue:** M5-3（バッチ投入・進捗表示の UI）
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

バッチ変換 API（spec 0008：`POST /api/v1/batches`・`GET /api/v1/batches/{id}`）は
あるが、Web UI からは使えず、複数 PDF をまとめて変換するにはコマンドが必要だった。

UI に**複数 PDF をまとめて投入**し、各ファイルの**進捗を表示・ダウンロード**できる
セクションを追加する。

## 2. スコープ

### やること
- UI に「バッチ変換（複数 PDF）」セクションを追加：複数ファイル選択＋共通オプション
  （出力形式・OCR）＋投入ボタン。
- 投入後、`GET /api/v1/batches/{id}` をポーリングして各ファイルの状態を表示。
- 完了（succeeded）ファイルにダウンロードボタンを表示。
- 認証キー（spec 0019）を全呼び出しに付与。

### やらないこと（非スコープ）
- バッチ用の細かいオプション（言語・表精度・画像モード・LLM 指示）の UI。共通の
  出力形式と OCR の ON/OFF のみ（高度な指定は API/対話フローを使う）。
- バッチ一覧・履歴（直近バッチの進捗のみ表示。ジョブ履歴は M5-2 の履歴に出る）。
- バックエンドの変更（既存 API のみ）。

## 3. 要件

### 機能要件
- 複数 PDF を選択し「変換」を押すと `POST /api/v1/batches?output_format=&do_ocr=` に
  multipart（`files` 複数）で投入する。
- レスポンスの `items`（filename/document_id/job_id/status）を一覧表示する。
- `GET /api/v1/batches/{id}` を約 2 秒間隔でポーリングし、各行の状態バッジを更新。
  pending/running が無くなれば停止。
- `succeeded` の行にダウンロードボタン（`/documents/{document_id}/download?format=`）。
- 投入/完了時に履歴（M5-2）も更新する。
- 1 件も選ばれていなければ投入しない。エラー（4xx）はメッセージ表示。

### 非機能要件
- フロントエンドのみ（バニラ JS）。バックエンド・API は不変。
- 既存の単一フロー UI と独立して動く。

## 4. 設計

### `app/static/index.html`
- `<section id="batch" class="card">`：複数 `file` 入力、出力形式 `select`、OCR
  チェックボックス、`#batch-submit` ボタン、`#batch-status`、`#batch-list`。

### `app/static/app.js`
- `submitBatch()`: 選択ファイルを FormData(`files`) に詰め、クエリに `output_format`/
  `do_ocr` を付けて POST（`authHeaders()`）。返った `items` を描画し `pollBatch(id, fmt)`。
- `pollBatch(batchId, fmt)`: `GET /batches/{id}` を取得→各 item を再描画。pending/running が
  あれば `setTimeout` で継続、無ければ停止。完了行に `downloadFile` ボタン。
- 既存の `authHeaders` / `downloadFile` / `loadHistory` を再利用。

### `app/static/style.css`
- 既存の `.history-row` / `.badge` を流用（必要なら軽微追加）。

### 影響範囲
- 変更: `app/static/index.html`, `app/static/app.js`,（必要なら）`style.css`,
  `README.md`（UI 説明・任意）, `docs/roadmap.md`。
- Python・テストは不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] 複数 PDF を選んで投入でき、各ファイルの行が表示される。
- [ ] ポーリングで状態が更新され、全完了で停止する。
- [ ] 完了ファイルをダウンロードできる（認証有効時も）。
- [ ] 認証キー設定時、バッチ投入/進捗取得/ダウンロードにキーが付与される。
- [ ] 既存の単一フロー・履歴は不変。

## 6. テスト計画

UI は自動テスト対象外（バッチ API は spec 0008 でテスト済み）。スモークで確認：
- 静的配信され、`index.html` に `#batch` 要素が含まれる。
- 2 ファイル投入 → 各行が表示され、完了でダウンロードが出る（手動）。

## 7. リスク・代替案

- **多数ファイルでの負荷**：サーバ側で `PDFTO_MAX_BATCH_FILES` により上限制御済み。UI は
  超過時のエラーを表示する。
- **代替: 単一フローにまとめる**：操作が混乱するため、バッチは独立セクションにする。

## 8. 未決事項

- ポーリング間隔 2 秒・出力形式は単一フローと同じ選択肢で進める。
