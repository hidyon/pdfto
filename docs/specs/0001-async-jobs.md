# Spec: 変換の非同期ジョブ化

- **ID:** 0001
- **状態:** done
- **マイルストーン:** M1 信頼性と運用性
- **関連 issue:** M1-1（変換をバックグラウンド処理 + 進捗ポーリング）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

現在 `POST /api/v1/documents/{id}/convert` は変換が終わるまでリクエストを
ブロックする（内部で `run_in_threadpool`）。docling の変換はページ数や OCR の
有無によって数秒〜数分かかり、初回はモデルのロードも入る。重い PDF では
リバースプロキシやクライアントのタイムアウトに容易に到達し、UI も「変換中」の
まま固まったように見える。

変換を**バックグラウンドのジョブ**として実行し、クライアントは**ジョブ ID で
進捗をポーリング**できるようにする。これにより長時間の変換でもリクエストが
タイムアウトせず、状態が観測可能になる。

## 2. スコープ

### やること
- 変換をジョブ化し、対話フロー（`/documents/{id}/convert`）を非同期化する。
- ジョブの状態を取得するエンドポイントを追加する。
- 単一プロセス内のジョブ実行基盤（スレッドプール + ジョブ索引）を追加する。
- Web UI を「投入 → ポーリング → 完了時にダウンロード」に更新する。

### やらないこと（非スコープ）
- 複数プロセス/複数ホストでの分散ジョブ（Celery/Redis 等）。本 issue は単一
  プロセス前提。永続化や分散は将来のマイルストーンで検討する。
- ジョブ/成果物の TTL・自動削除（**M1-2** で扱う）。
- 進捗の「%」表示。状態は離散ステータスのみ（細かい進捗は docling の制約上困難）。
- ワンショット `POST /api/v1/convert` の非同期化（即時にファイルを返す用途のため
  同期のまま残す）。

## 3. 要件

### 機能要件
- `POST /api/v1/documents/{id}/convert` は変換を**開始**し、`202 Accepted` で
  ジョブを返す（完了を待たない）。リクエストボディは従来どおり回答のフラット JSON。
- `GET /api/v1/jobs/{job_id}` でジョブの現在状態を取得できる。
- ジョブ状態は `pending` / `running` / `succeeded` / `failed` の 4 つ。
- `succeeded` のジョブは `download_url` と `preview`・`truncated` を持つ。
- `failed` のジョブは `error`（人間可読なメッセージ）を持つ。
- 既存の `GET /documents/{id}/download` は変更しない（成果物が無ければ 404）。

### 非機能要件
- 同時実行数は上限を設ける（既定 2、`PDFTO_MAX_WORKERS` で変更可）。超過分は
  キューで待つ。
- 単一プロセス・インメモリで完結し、新規の外部依存を増やさない（コアの軽さを維持）。

## 4. 設計

### データ/モデル（`app/models.py`）
- `JobStatus(str, Enum)`: `pending|running|succeeded|failed`。
- `Job(BaseModel)`:
  - `id: str`
  - `document_id: str`
  - `status: JobStatus`
  - `output_format: OutputFormat`
  - `created_at: float`, `updated_at: float`
  - `download_url: str | None`
  - `preview: str | None`, `truncated: bool`
  - `error: str | None`
- 既存 `ConversionResult` は段階的に `Job`（`succeeded` 時の形）へ統合。当面は
  `Job` を正とし、`ConversionResult` は廃止する。

### ジョブ基盤（新規 `app/jobs.py`）
- `JobManager`: `ThreadPoolExecutor(max_workers=settings.max_workers)` と
  `dict[str, Job]` をスレッドセーフに保持。
  - `submit(document_id, fn) -> Job`: ジョブを `pending` で登録し executor へ投入。
    実行開始時に `running`、成功で `succeeded`、例外で `failed` に更新。
  - `get(job_id) -> Job | None`。
- 変換ワーカは `app.converter.convert` を呼ぶ。`ConversionError` は捕捉して
  `failed` + `error` に変換（コアの例外を Web 層へ生で漏らさない方針を踏襲）。
- コア（analysis/questions/converter）には依存させない。`jobs.py` は Web 寄りの
  オーケストレーション層とする。

### API（`app/main.py`）
- `POST /api/v1/documents/{id}/convert` → `202`、`Job`（`pending`）を返す。
  - 本文の回答は従来どおり `apply_answers` で `ConversionOptions` に変換。
  - ジョブ成功時、成果物は従来どおり `storage.add_output` で保存し、`download_url`
    を `Job` に格納する。
- `GET /api/v1/jobs/{job_id}` → `Job`。未知の ID は `404`。
- ワンショット `POST /api/v1/convert` は同期のまま（変更なし）。

### Web UI（`app/static/app.js`）
- 「変換する」で convert を呼び、返ったジョブ ID を `GET /jobs/{id}` で
  ポーリング（例: 1.5 秒間隔）。`succeeded` で結果表示、`failed` でエラー表示。
- ポーリング中は既存のスピナー表示を流用。

### 影響範囲
- 変更: `app/models.py`, `app/main.py`, `app/static/app.js`, `tests/test_api.py`,
  `README.md`（API 説明）。
- 追加: `app/jobs.py`, `tests/test_jobs.py`。
- コア（`analysis.py` / `questions.py` / `converter.py`）は無変更。

## 5. 受け入れ条件（Definition of Done）

- [ ] `POST /documents/{id}/convert` が `202` とステータス `pending`/`running` の
      `Job` を即座に返す（変換完了を待たない）。
- [ ] `GET /jobs/{job_id}` がジョブの状態を返し、完了後は `succeeded` と
      有効な `download_url`・`preview` を持つ。
- [ ] 変換失敗時、ジョブが `failed` になり `error` にメッセージが入る
      （プロセスはクラッシュしない）。
- [ ] 完了後 `GET /documents/{id}/download?format=...` で成果物が取得できる。
- [ ] 同時実行数が `PDFTO_MAX_WORKERS` を超えない。
- [ ] Web UI が投入→ポーリング→ダウンロードで動作する。
- [ ] `pytest` が通る（docling はモック）。

## 6. テスト計画

`tests/test_jobs.py`（新規）と `tests/test_api.py`（更新）。docling はモックする。

- `convert` が `202` と `Job` を返す（`test_api`）。
- ジョブをポーリングすると最終的に `succeeded` になり `download_url` を持つ
  （モック変換は即時完了。必要なら短い遅延を挟んで `pending→succeeded` 遷移を確認）。
- 変換ワーカが `ConversionError` を投げたケースで `failed` + `error` になる。
- 未知の `job_id` は `404`。
- 完了後にダウンロードできる。

## 7. リスク・代替案

- **代替案A: `convert?wait=true` で同期も選べる二刀流。** クライアントは楽だが
  レスポンス形が状況で変わり API が複雑化。→ 採らない。同期が欲しい用途は
  ワンショット `/api/v1/convert` を使う。
- **代替案B: 最初から Celery+Redis。** スケールするが外部依存と運用コストが重く、
  単一インスタンス MVP には過剰。→ M1 では採らない（将来再検討）。
- **リスク: インメモリのジョブ索引は再起動で消える。** M1-2（TTL/掃除）や将来の
  永続化と合わせて扱う。本 issue では「単一プロセス・揮発」を明示的な前提とする。
- **リスク: FastAPI の `BackgroundTasks` はレスポンス後に同一イベントループで
  動き、ポーリング用の状態を持てない。** よって専用の `ThreadPoolExecutor` +
  ジョブ索引を使う。

## 8. 未決事項

- ~~対話フロー convert を非同期のみにするか、wait フラグで両対応にするか。~~
  → **決定: 非同期のみ。** 同期で 1 発で欲しい用途はワンショット
  `POST /api/v1/convert` を使う（2026-06-20）。
- ジョブ索引のサイズ上限/掃除は M1-2 に委ねる（本 issue では無制限のまま）。
- ポーリング間隔のデフォルトは UI 側 1.5 秒とする。
