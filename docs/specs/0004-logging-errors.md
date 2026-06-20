# Spec: 構造化ログとエラーハンドリング

- **ID:** 0004
- **状態:** done
- **マイルストーン:** M1 信頼性と運用性
- **関連 issue:** M1-4（構造化ログとエラーハンドリングの整備）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

現状、アプリのログは uvicorn のデフォルト任せで、変換ジョブやエラーの追跡情報が
ほとんど残らない。想定外の例外が起きた場合の API 応答も一定しておらず、運用時に
「いつ・どのリクエストで・何が起きたか」を追えない。

リクエストやジョブを横断して追跡できる **構造化ログ**（リクエスト ID 付き）と、
**一貫したエラー応答**（スタックトレースを外へ漏らさない 500 ハンドリング）を
整備し、運用性を底上げする。

## 2. スコープ

### やること
- アプリ全体のロギングを一元設定する（レベル・フォーマットを環境変数で制御）。
- ログに **リクエスト ID** を付与し、リクエスト〜ジョブ〜エラーを相関できるようにする。
- 各 HTTP リクエストのアクセスログ（method / path / status / 所要時間）を出す。
- 変換ジョブのライフサイクル（投入・開始・成功/失敗・所要時間）をログに残す。
- 想定外の例外を捕捉し、安定した JSON 形（`detail` + `request_id`）で 500 を返す。
- レスポンスに `X-Request-ID` ヘッダを付与する。

### やらないこと（非スコープ）
- 外部ログ集約基盤（Loki/ELK 等）への送信や OpenTelemetry トレーシング。
- メトリクス（Prometheus 等）の公開。
- 監査ログや PII マスキングなどの高度な要件。

## 3. 要件

### 機能要件
- `PDFTO_LOG_LEVEL`（既定 `INFO`）でログレベルを変更できる。
- `PDFTO_LOG_FORMAT`（`text` | `json`、既定 `text`）で出力形式を選べる。
- すべてのログ行に `request_id` が含まれる（リクエスト文脈外では `-`）。
- リクエストには ID が割り当てられる。受信ヘッダ `X-Request-ID` があれば踏襲し、
  無ければ生成する。応答に `X-Request-ID` を返す。
- 各リクエストにつき 1 行のアクセスログ（method, path, status, duration_ms）。
- ジョブの開始/終了がログに残り、終了ログには status と duration が含まれる。
- 想定外例外時は、トレースバックをログに記録し、クライアントには
  `{"detail": "internal server error", "request_id": "..."}` を 500 で返す。

### 非機能要件
- 標準ライブラリのみ（新規依存なし）。
- ロギング設定は冪等（多重初期化でハンドラが重複しない）。

## 4. 設計

### `app/logging_config.py`（新規）
- `request_id_var: ContextVar[str]`（既定 `"-"`）。
- `RequestIdFilter`: 各 `LogRecord` に `record.request_id` を注入。
- `JsonFormatter`: `time, level, logger, message, request_id`(+`exc_info`) を
  JSON 1 行で出力。
- テキストフォーマッタ: `time level logger [request_id] message`。
- `setup_logging(level: str, fmt: str)`: stdout ハンドラを 1 つ設定し、
  root / `uvicorn` / `uvicorn.access` / `pdfto` ロガーへ適用。再呼び出ししても
  ハンドラを重複追加しない。

### `app/main.py`
- 起動時（import 時 + lifespan）に `setup_logging(settings.log_level, settings.log_format)`。
- HTTP ミドルウェア:
  1. `X-Request-ID` を取得 or 生成し `request_id_var` にセット。
  2. `call_next` を実行し、所要時間を計測。
  3. アクセスログを 1 行出力し、応答へ `X-Request-ID` を付与。
- 例外ハンドラ `@app.exception_handler(Exception)`: トレースバックを
  `logger.exception` で記録し、500 + `{detail, request_id}` を返す。
- （任意）`HTTPException` ハンドラ: 応答ボディに `request_id` を含める。

### `app/jobs.py`
- `submit`/`_run` で `pdfto.jobs` ロガーへ出力（job_id, document_id, status,
  duration）。例外時は `logger.exception` 相当の情報を残しつつ、ジョブは
  従来どおり `failed` にする。

### `app/config.py`
- `log_level = PDFTO_LOG_LEVEL`（既定 `INFO`）。
- `log_format = PDFTO_LOG_FORMAT`（既定 `text`）。

### 影響範囲
- 追加: `app/logging_config.py`, `tests/test_logging.py`。
- 変更: `app/config.py`, `app/main.py`, `app/jobs.py`, `app/cleanup.py`
  （既存 logger 利用箇所の整合）, `README.md`, `CLAUDE.md`/`docs/roadmap.md`。
- コア（analysis/questions/converter）は原則無変更。

## 5. 受け入れ条件（Definition of Done）

- [ ] `PDFTO_LOG_FORMAT=json` で各ログ行が妥当な JSON になり、`request_id` を含む。
- [ ] レスポンスに `X-Request-ID` が付き、リクエストヘッダの値があれば踏襲される。
- [ ] 各リクエストでアクセスログ（status・duration）が 1 行出る。
- [ ] ジョブ終了時に status と duration を含むログが出る。
- [ ] ルート内で想定外例外が発生しても、500 + `{detail, request_id}` が返り、
      トレースバックがログに残る（クライアントには漏れない）。
- [ ] `setup_logging` を 2 回呼んでもハンドラが重複しない。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_logging.py`（新規）と `tests/test_api.py`（追記）。

- `JsonFormatter` が `request_id` 等を含む有効な JSON を出す。
- `setup_logging` 冪等性（root ハンドラ数が増えない）。
- API: 任意レスポンスに `X-Request-ID` が付く。送信ヘッダが踏襲される。
- API: ルートを monkeypatch で例外化し、500 + `{detail, request_id}` を確認。

## 7. リスク・代替案

- **uvicorn 既定ログとの二重出力。** `setup_logging` で uvicorn ロガーの
  ハンドラを置き換え/propagate 調整し重複を避ける。
- **代替: structlog 等の導入。** 依存を増やすため不採用。標準 logging で足りる。
- **ContextVar の伝播。** Starlette は同一タスクで実行されるため、ミドルウェアで
  set した `request_id` は同一リクエスト処理（ハンドラ/例外ハンドラ）に伝播する。

## 8. 未決事項

- ログ形式の既定は `text`（開発しやすさ優先）。本番で JSON を使う場合は
  `PDFTO_LOG_FORMAT=json` を設定する運用とする。
