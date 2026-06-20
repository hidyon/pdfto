# Spec: 変換完了 Webhook 通知

- **ID:** 0007
- **状態:** done
- **マイルストーン:** M2 公開・連携の強化
- **関連 issue:** M2-2（Webhook / コールバック（変換完了通知））
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

変換は非同期ジョブ（spec 0001）で実行され、クライアントは `/jobs/{id}` を
ポーリングして完了を知る。他システムと連携する際、ポーリングは無駄が多く実装も
面倒。**ジョブ完了時にコールバック URL へ通知**できれば、イベント駆動で組み込める。

変換開始時に `callback_url` を指定すると、ジョブが `succeeded` / `failed` になった
時点でその URL へ結果を POST する。受信側が真正性を確認できるよう、任意で
**HMAC 署名**を付与する。

## 2. スコープ

### やること
- 非同期変換（`POST /documents/{id}/convert`）で `callback_url` を受け取る。
- ジョブ完了（成功/失敗）時に `callback_url` へ JSON を POST する。
- `PDFTO_WEBHOOK_SECRET` 設定時、本文の HMAC-SHA256 署名を `X-PDFTO-Signature`
  ヘッダで付与する。
- SSRF 緩和: スキームは `http`/`https` のみ許可。任意で
  `PDFTO_WEBHOOK_ALLOWED_HOSTS`（許可ホスト）でさらに制限。
- 配送タイムアウトを設け、失敗してもジョブ自体は成功扱いのまま（通知失敗をログ）。

### やらないこと（非スコープ）
- 配送の再試行/バックオフ・配送ログの永続化（将来）。1 回試行のみ。
- 再起動で中断したジョブ（recover で `failed` 化）に対する通知（`callback_url` は
  永続化せずプロセス内で配送するため。将来、永続化と合わせて対応）。
- Web UI からの Webhook 設定。
- mTLS や OAuth による受信側認証。

## 3. 要件

### 機能要件
- `POST /api/v1/documents/{id}/convert?callback_url=<URL>` を受け付ける。
  `callback_url` 省略時は通知しない（従来挙動）。
- `callback_url` が `http`/`https` 以外、または許可ホスト外なら `422` で即時に拒否。
- ジョブ完了時、`callback_url` へ次の JSON を POST する:
  ```json
  {"event": "job.succeeded" | "job.failed", "job": { ...Job のフィールド... }}
  ```
- `PDFTO_WEBHOOK_SECRET` 設定時、本文の HMAC-SHA256 を
  `X-PDFTO-Signature: sha256=<hex>` で送る。
- 通知の成否はサーバログに残す。通知失敗はジョブ状態に影響しない。

### 非機能要件
- 標準ライブラリのみ（`urllib` / `hmac`）。新規依存なし。
- 配送は `PDFTO_WEBHOOK_TIMEOUT` 秒でタイムアウト。

## 4. 設計

### 設定（`app/config.py`）
- `webhook_secret: str | None`（`PDFTO_WEBHOOK_SECRET`）。
- `webhook_timeout: int`（`PDFTO_WEBHOOK_TIMEOUT`、既定 10）。
- `webhook_allowed_hosts: set[str]`（`PDFTO_WEBHOOK_ALLOWED_HOSTS`、空=制限なし）。

### `app/webhooks.py`（新規）
- `check_url(url, allowed_hosts) -> str | None`: 不正なら理由文字列、OK なら `None`。
  スキーム検証＋（許可ホストがあれば）ホスト一致（完全一致 or サフィックス）を判定。
- `sign(body: bytes, secret: str) -> str`: HMAC-SHA256 hexdigest。
- `deliver(url, payload: dict, *, secret, timeout) -> bool`: JSON を POST。署名が
  あれば付与。例外は捕捉してログし `False` を返す（送信は 1 回）。

### `app/jobs.py`
- `submit(..., callback_url: str | None = None)` を追加。`_run` に引き渡す。
- `_run` は最終状態確定後、`callback_url` があれば `deliver` を呼ぶ。`event` は
  最終 `status` から決定。`deliver` の結果はログのみ（ジョブ状態は不変）。
- `callback_url` はプロセス内で受け渡し（DB には保存しない）。

### API（`app/main.py`）
- `convert_document` に `callback_url: str | None = Query(None)` を追加。
  指定時は `check_url(...)` で検証し、不正なら `HTTPException(422)`。OK なら
  `jobs.submit(..., callback_url=callback_url)`。
- ワンショット `POST /api/v1/convert` は同期でファイルを返すため対象外。

### 影響範囲
- 追加: `app/webhooks.py`, `tests/test_webhooks.py`。
- 変更: `app/config.py`, `app/jobs.py`, `app/main.py`,
  `tests/test_api.py`（callback 経路）, `README.md`, `CLAUDE.md`/`docs/roadmap.md`。
- コア・既存の外形は不変（`callback_url` 省略時は挙動不変）。

## 5. 受け入れ条件（Definition of Done）

- [ ] `callback_url` 省略時は従来どおり（通知なし）。
- [ ] 成功ジョブで `callback_url` へ `event="job.succeeded"` と Job を含む POST が届く。
- [ ] 失敗ジョブで `event="job.failed"` の POST が届く。
- [ ] `PDFTO_WEBHOOK_SECRET` 設定時、`X-PDFTO-Signature` が本文の HMAC と一致する。
- [ ] 不正な `callback_url`（非 http(s) / 許可外ホスト）は `422`。
- [ ] 通知先がエラー/到達不能でもジョブは成功のまま、失敗はログに残る。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_webhooks.py`（新規）。受信側はテスト用のローカル HTTP サーバ
（`http.server` をスレッド起動）で実リクエストを捕捉、または `deliver` を monkeypatch。

- `check_url`: http/https 可、file/ftp 不可、許可ホスト一致/不一致。
- `sign`/署名: 既知入力で安定、受信本文から再計算した署名と一致。
- `deliver`: ローカルサーバへ POST が届き、ヘッダ・本文・署名が正しい。到達不能 URL で
  `False` を返し例外を投げない。
- jobs/API: `callback_url` 付きジョブ完了で `deliver` が呼ばれる（monkeypatch で捕捉）。
- API: 不正 `callback_url` で `422`。

## 7. リスク・代替案

- **SSRF。** サーバが任意 URL へ POST するため、内部エンドポイントを叩かれる恐れ。
  スキーム制限＋許可ホストで緩和し、運用では egress 制御を推奨（README 明記）。
- **配送の信頼性。** 1 回試行のため取りこぼし得る。再試行/永続化は将来 issue。
  当面はポーリング（`/jobs/{id}`）が確実な手段として併存する。
- **ワーカ占有。** 配送は変換ワーカスレッドで同期実行。タイムアウトを設けて長時間
  占有を防ぐ。

## 8. 未決事項

- 署名ヘッダ名は `X-PDFTO-Signature`（`sha256=` プレフィックス）で確定。
- 既定タイムアウト 10 秒で進める（環境変数で調整可）。
