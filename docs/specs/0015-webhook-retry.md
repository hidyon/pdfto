# Spec: Webhook 配送の再試行と永続化

- **ID:** 0015
- **状態:** done
- **マイルストーン:** M4 信頼性 UX（軽量）
- **関連 issue:** M4-1（Webhook 配送の再試行と永続化）
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

現在の Webhook（spec 0007）は **1 回のみ・プロセス内・状態を持たない**配送で、受信側が
一時的に落ちていると通知が失われる。再起動でも消える。連携の信頼性 UX として弱い。

配送を **SQLite に永続化**し、失敗時に**指数バックオフで再試行**する。配送状態を
参照できるようにし、「取りこぼさない・追える」体験にする。Redis 等の新規依存は使わない。

## 2. スコープ

### やること
- Webhook 配送を `webhook_deliveries` テーブルに永続化（状態・試行回数・次回時刻）。
- 失敗時に指数バックオフで自動再試行するバックグラウンド配送スレッド。
- ジョブ完了時、即時 1 回試行＋失敗なら以降は再試行に委ねる。
- 配送状態を参照する API（`GET /api/v1/jobs/{job_id}/deliveries`）。
- 再試行回数・間隔・掃除間隔を環境変数で設定可能にする。

### やらないこと（非スコープ）
- 複数インスタンスでの配送分散（単一プロセスが自分の配送を担う前提）。
- 受信側の冪等性保証（送信側の `event.id` 相当は将来課題）。
- 任意イベントの購読管理（配送はジョブ完了通知のみ、spec 0007 の範囲）。

## 3. 要件

### 機能要件
- `callback_url` 付きジョブが完了すると配送レコードが作られ、即時に 1 回試行する。
- 2xx 以外/到達不能なら `attempts` を増やし、`PDFTO_WEBHOOK_MAX_ATTEMPTS` 未満なら
  `next_attempt_at = now + base * 2^(attempts-1)` で再試行予約（`status=pending`）。
- 上限に達したら `status=failed`、成功したら `status=delivered`。
- バックグラウンドスレッドが `PDFTO_WEBHOOK_SWEEP_SECONDS` ごとに期限到来の pending を
  処理する。プロセス再起動後も pending は残り、再開される。
- `GET /jobs/{job_id}/deliveries` が配送履歴（url/status/attempts/last_error/時刻）を返す。
- 署名・SSRF 緩和（spec 0007）は従来どおり適用。

### 非機能要件
- 新規外部依存なし（SQLite + stdlib）。
- 既定挙動の互換：`callback_url` 未指定なら何も起きない。
- 配送はジョブ実行ワーカ/掃除スレッドから行い、リクエスト処理を止めない。

## 4. 設計

### データ（`app/db.py`）
- 新規テーブル `webhook_deliveries`:
  `id PK, job_id, url, event, payload TEXT, status TEXT, attempts INT,
   max_attempts INT, next_attempt_at REAL, last_error TEXT, created_at, updated_at`。
  既存 DB へは `CREATE TABLE IF NOT EXISTS` で追加（ALTER 不要）。

### 配送（`app/webhooks.py`）
- 既存の `check_url` / `sign` / `deliver`（純粋関数）は維持。
- `WebhookDispatcher`（新規・`Database` を共有）:
  - `enqueue(job: Job, url: str)`: payload を作り pending 行を INSERT、即時 `_attempt`。
  - `_attempt(row)`: `deliver(url, payload, secret, timeout)` を呼び、成功で `delivered`、
    失敗で `attempts++`／上限で `failed`／未満で `next_attempt_at` 予約。
  - `sweep_once()`: `status='pending' AND next_attempt_at<=now` を取得し各々 `_attempt`。
  - `start()/stop()`: `PDFTO_WEBHOOK_SWEEP_SECONDS` 間隔のデーモンスレッド（cleanup と同型）。
  - `list_for_job(job_id) -> list[dict]`。
  - 例外は握りつぶしてログ（配送がジョブ状態に影響しない）。

### ジョブ連携（`app/jobs.py`）
- `JobManager(max_workers, db, dispatcher=None)`。`_notify` は `dispatcher` があれば
  `dispatcher.enqueue(job, callback_url)`、無ければ従来どおり `deliver`（後方互換）。

### API/配線（`app/main.py`）
- `dispatcher = WebhookDispatcher(storage.db, ...)`、`jobs = JobManager(..., dispatcher)`。
- `lifespan` で `dispatcher.start()/stop()`。
- `GET /api/v1/jobs/{job_id}/deliveries` を追加（未知ジョブでも空配列か 404 は実装で統一）。

### 設定（`app/config.py`）
- `webhook_max_attempts`（`PDFTO_WEBHOOK_MAX_ATTEMPTS`、既定 5）。
- `webhook_retry_base_seconds`（`PDFTO_WEBHOOK_RETRY_BASE_SECONDS`、既定 10）。
- `webhook_sweep_seconds`（`PDFTO_WEBHOOK_SWEEP_SECONDS`、既定 30）。

### 影響範囲
- 変更: `app/db.py`, `app/webhooks.py`, `app/jobs.py`, `app/main.py`, `app/config.py`,
  `tests/*`, `README.md`, `docs/roadmap.md`。
- 追加テスト: `tests/test_webhook_retry.py`。
- 既存の `deliver`/`sign`/`check_url` と署名・SSRF は不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] `callback_url` 付きジョブ完了で配送行が作られ、成功時 `delivered` になる。
- [ ] 受信側失敗時、`attempts` が増え `next_attempt_at` が設定され、`sweep_once` で
      後から成功すると `delivered` になる。
- [ ] 上限到達で `failed` になる。
- [ ] 配送行は再オープン（再起動相当）後も残り、`sweep_once` で再開できる。
- [ ] `GET /jobs/{id}/deliveries` が履歴を返す。
- [ ] `callback_url` 未指定では配送が発生しない。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_webhook_retry.py`（`webhooks.deliver` を monkeypatch でフェイク化）。

- `enqueue` で deliver 成功 → `delivered`、`attempts=1`。
- deliver 失敗 → `pending`、`attempts=1`、`next_attempt_at>now`。その後 deliver 成功に
  切替え `sweep_once` → `delivered`。
- 上限まで失敗 → `failed`。
- 別 `WebhookDispatcher`（同 DB）から pending を `sweep_once` できる（永続化）。
- API: `GET /jobs/{id}/deliveries` が配送を返す（convert/job はモック）。
- `callback_url` 無しでは配送行が作られない。

## 7. リスク・代替案

- **多重配送**：単一プロセス前提のため重複は限定的。再試行で受信側に重複が届き得る点は
  受信側の冪等化に委ねる（将来 `event.id` 付与を検討）と明記。
- **ワーカ占有**：即時試行は変換ワーカ上で同期実行。タイムアウトで長時間占有を防ぐ
  （spec 0007 の方針を踏襲）。再試行は専用スレッド。
- **代替: 即時試行をやめ全て掃除スレッド任せ**。初回通知が最大 1 間隔遅れるため、
  即時 1 回＋以降再試行とする。

## 8. 未決事項

- 既定の最大試行 5・基準 10 秒（10/20/40/80/160s）で進める。配送履歴の TTL は
  ドキュメント削除（CASCADE 対象外の独立表）に合わせ、当面は無期限（将来 TTL 検討）。
