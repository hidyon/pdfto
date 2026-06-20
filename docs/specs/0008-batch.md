# Spec: バッチ変換（複数 PDF の一括投入）

- **ID:** 0008
- **状態:** done
- **マイルストーン:** M2 公開・連携の強化
- **関連 issue:** M2-3（バッチ変換（複数 PDF を一括投入））
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

現状は 1 リクエスト 1 ファイル。多数の PDF を変換したい連携システムは、毎回
アップロード→変換を個別に呼ぶ必要があり面倒。**複数 PDF を一括投入**し、
ファイルごとに非同期ジョブを生成して**バッチ単位で進捗を集約**できるようにする。

バッチは非対話（質問なし）で、オプションは全ファイル共通に指定する（対話的な
出し分けはバッチには馴染まないため）。

## 2. スコープ

### やること
- `POST /api/v1/batches`: 複数 PDF を受け取り、ファイルごとに document を作成し
  変換ジョブを投入。バッチ ID と各ファイルのジョブ一覧を返す。
- 変換オプションは共通指定（`output_format` / `do_ocr` / `do_table_structure`）。
- `callback_url`（任意）は各ジョブに適用（spec 0007）。
- `GET /api/v1/batches/{batch_id}`: バッチ内ジョブの状態を集約して返す。
- 1 バッチあたりのファイル数上限（`PDFTO_MAX_BATCH_FILES`、既定 20）。

### やらないこと（非スコープ）
- バッチ全体の完了を 1 通だけ通知する「バッチ完了 Webhook」（通知はジョブ単位）。
- ファイルごとに異なるオプション指定（共通のみ）。
- ZIP 一括ダウンロード（各成果物は従来の `/documents/{id}/download` で取得）。
- 対話的フロー（質問）との統合。

## 3. 要件

### 機能要件
- `POST /api/v1/batches` は multipart で複数 `files` を受け取り、各ファイルにつき
  document を作成・解析し、変換ジョブを `202` で投入する。
- レスポンスはバッチ ID と `items`（各 `filename` / `document_id` / `job_id` /
  `status`）。
- ファイル数が 0、または上限超過なら `422`。各ファイルは既存の検証（PDF か・
  サイズ上限）を満たすこと。1 つでも不正なら `4xx` で全体を拒否（部分成功にしない）。
- `GET /api/v1/batches/{batch_id}` は現在の各ジョブ状態を含む `items` を返す。
  未知の batch は `404`。
- 認証・レート制限（spec 0006）は `/api/v1/*` として従来どおり適用。

### 非機能要件
- 既存スキーマへの後方互換な移行（`jobs.batch_id` 追加、`batches` 表追加）。
- 新規依存なし。

## 4. 設計

### データ（`app/db.py`）
- `batches(id PK, created_at, count)` を追加。
- `jobs` に `batch_id TEXT`（NULL 可）を追加。既存 DB 向けに、起動時 `PRAGMA
  table_info(jobs)` を見て無ければ `ALTER TABLE jobs ADD COLUMN batch_id TEXT`。

### モデル（`app/models.py`）
- `BatchItem(filename, document_id, job_id, status: JobStatus)`。
- `BatchResponse(id, created_at, count, items: list[BatchItem])`。

### JobManager（`app/jobs.py`）
- `submit(..., batch_id: str | None = None)`: jobs 行に `batch_id` を記録。
- `create_batch(batch_id, count)` / `get_batch(batch_id)` / `list_by_batch(batch_id)
  -> list[Job]`。

### API（`app/main.py`）
- `POST /api/v1/batches`（`files: list[UploadFile]`, `output_format`/`do_ocr`/
  `do_table_structure` クエリ, `callback_url` 任意）:
  1. 件数チェック（1..max）。`callback_url` 検証。
  2. 各ファイルを `_read_upload` で検証→解析→`create_document`→`jobs.submit(...,
     batch_id=...)`。
  3. `batches` 行を作成して `BatchResponse` を返す（`202`）。
- `GET /api/v1/batches/{batch_id}`: `get_batch` で存在確認し、`list_by_batch` の
  各ジョブ＋document の filename から `items` を構築。

### 影響範囲
- 追加: `tests/test_batch.py`（または `test_api.py` 追記）。
- 変更: `app/db.py`, `app/models.py`, `app/jobs.py`, `app/main.py`,
  `app/config.py`（`PDFTO_MAX_BATCH_FILES`）, `README.md`, `CLAUDE.md`/
  `docs/roadmap.md`。
- コア・既存エンドポイントの外形は不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] 複数 PDF を `POST /batches` で投入でき、ファイル数ぶんのジョブが作られる。
- [ ] レスポンスの各 item に `document_id` / `job_id` / `status` が入る。
- [ ] 各ジョブが完了すると、対応 document の成果物がダウンロードできる。
- [ ] `GET /batches/{id}` が各ジョブの現在状態を集約して返す。未知は `404`。
- [ ] ファイル数 0／上限超過は `422`。不正ファイル混在は全体拒否。
- [ ] 既存 DB でも `batch_id` 列が移行で追加され、既存テストが通る。
- [ ] `pytest` が通る。

## 6. テスト計画

- `POST /batches` に 2 つの PDF → `202`、items が 2 件、各 `job_id` あり。
- ジョブをポーリング（docling はモック）→ 全 `succeeded`、成果物 DL 可。
- `GET /batches/{id}` が 2 件の状態を返す。未知 batch → `404`。
- ファイル 0／上限超過 → `422`。非 PDF 混在 → `4xx`。
- `db`: 既存（batch_id なし）jobs 表に対する移行で列が追加されること。

## 7. リスク・代替案

- **大量ファイルでの負荷。** 上限と既存のワーカ数（`PDFTO_MAX_WORKERS`）で抑制。
  ジョブはキューイングされ順次処理される。
- **部分失敗の扱い。** 投入時の検証は全体拒否（分かりやすさ優先）。変換時の失敗は
  ジョブ単位で `failed`（バッチ全体は止めない）。
- **代替: バッチ完了の集約通知。** 有用だが状態集約が増えるため非スコープ。必要に
  なれば別 issue。

## 8. 未決事項

- 既定の最大ファイル数は 20。環境変数 `PDFTO_MAX_BATCH_FILES` で変更可能とする。
