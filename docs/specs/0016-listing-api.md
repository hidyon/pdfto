# Spec: ジョブ/ドキュメント一覧 API（追跡性）

- **ID:** 0016
- **状態:** done
- **マイルストーン:** M4 信頼性 UX（軽量）
- **関連 issue:** M4-2（ジョブ/ドキュメント一覧 API）
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

現状、ドキュメントやジョブは ID を知っていれば個別取得できるが、**一覧する手段が無い**。
何を変換したか・どのジョブが失敗したかを追えず、UI（M5）も作れない。

ドキュメントとジョブを**一覧取得する API**を追加し、「追える」体験の土台を作る。
永続化済み（SQLite）なので再起動後も一覧できる。

## 2. スコープ

### やること
- `GET /api/v1/documents`: ドキュメント一覧（新しい順・ページング）。
- `GET /api/v1/jobs`: ジョブ一覧（新しい順・`status` で絞り込み・ページング）。
- 一覧はサーバ側で件数を制限（`limit`/`offset`）。

### やらないこと（非スコープ）
- 全文検索・任意フィールドでの並び替え（新しい順固定）。
- カーソルベースのページング（`limit`/`offset` で十分）。
- 集計・統計エンドポイント。

## 3. 要件

### 機能要件
- `GET /api/v1/documents?limit=&offset=` が、作成日時の降順でドキュメントの
  サマリ（`id` / `filename` / `created_at` / `page_count`）を返す。
- `GET /api/v1/jobs?limit=&offset=&status=` が、更新日時（または作成日時）の降順で
  ジョブ（既存 `Job` 形）を返す。`status` 指定時はその状態のみ。
- `limit` は 1..200（既定 50）、`offset` は 0 以上（既定 0）。範囲外は弾く/丸める。
- 認証・レート制限（spec 0006）は `/api/v1/*` として従来どおり適用。
- TTL 掃除で削除済みのものは一覧に出ない（DB が正）。

### 非機能要件
- 新規依存なし。既存の `Database` クエリで実装。
- 既存エンドポイントの外形は不変。

## 4. 設計

### モデル（`app/models.py`）
- `DocumentSummary(id, filename, created_at, page_count)`。

### ストレージ（`app/storage.py`）
- `list_documents(limit, offset) -> list[DocumentRecord]`:
  `SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?`。
  既存 `get()` の行→レコード変換を `_row_to_record` に切り出して共用。

### ジョブ（`app/jobs.py`）
- `list_jobs(limit, offset, status=None) -> list[Job]`:
  `status` 有無で WHERE を分け、`ORDER BY created_at DESC LIMIT ? OFFSET ?`。

### API（`app/main.py`）
- `GET /api/v1/documents`（`limit: int=Query(50, ge=1, le=200)`,
  `offset: int=Query(0, ge=0)`）→ `list[DocumentSummary]`。
- `GET /api/v1/jobs`（同上 + `status: JobStatus | None = Query(None)`）→ `list[Job]`。
- ルート定義順に注意：`/documents/{doc_id}` より前に `/documents` を置く必要はない
  （パスが異なるため衝突しないが、可読性のため一覧を近くに配置）。

### 影響範囲
- 変更: `app/models.py`, `app/storage.py`, `app/jobs.py`, `app/main.py`,
  `tests/*`, `README.md`, `docs/roadmap.md`。
- 既存の取得/変換/ダウンロードは不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] `GET /documents` が新しい順でサマリ一覧を返し、`limit`/`offset` が効く。
- [ ] `GET /jobs` が新しい順で一覧を返し、`status` 絞り込みと `limit`/`offset` が効く。
- [ ] 範囲外の `limit`/`offset` は 422（FastAPI バリデーション）になる。
- [ ] 認証有効時は一覧 API もキーを要求する。
- [ ] `pytest` が通る。

## 6. テスト計画

- `storage.list_documents`: 複数作成 → 降順・ページング。
- `jobs.list_jobs`: 複数投入 → 降順・`status` 絞り込み・ページング。
- API: `GET /documents` / `GET /jobs` が一覧を返す。`limit` 上限超過で 422。
  認証有効時にキー無しで 401。

## 7. リスク・代替案

- **大量データでの offset ページング**：件数が増えると深い offset は非効率。本規模では
  許容。必要になればカーソル方式を別 issue 化。
- **代替: 一覧に総件数を含める**。UI のページャに有用だが、まずは配列のみを返し、
  必要になれば `X-Total-Count` ヘッダ等で追加する。

## 8. 未決事項

- 既定 `limit=50` / 上限 200 で進める。総件数の返却は当面行わない。
