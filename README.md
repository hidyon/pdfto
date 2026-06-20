# PDFto

PDF を **Markdown / HTML / JSON / プレーンテキスト** に変換するアプリです。
PDF の内容を解析し、**内容に応じた質問**（OCR は必要か、ページ範囲は、画像の扱いは…）に
答えるだけで変換でき、結果は**ダウンロード**できます。

変換エンジンには無料の OSS [docling](https://github.com/docling-project/docling) を使用しています。

> **設計方針:** API ファースト。Web UI は REST API の薄いクライアントにすぎないので、
> 他システムからは API（`/docs` に OpenAPI ドキュメント）を叩くだけで同じことができます。

## 特長

- **インタラクティブ変換** — アップロードした PDF を解析し、最適な質問だけを提示
- **複数の出力形式** — Markdown / HTML / 構造化 JSON / テキスト
- **OCR・表構造・画像** — スキャン文書の OCR、表の構造復元、画像の埋め込み/参照に対応
- **API ファースト** — すべての機能を REST API として公開（自動 OpenAPI ドキュメント付き）
- **Web UI** — ブラウザだけで完結する操作画面を同梱

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 初回の変換時に docling が必要な ML モデルを自動ダウンロードします（ネットワーク必須）。

## 起動

```bash
uvicorn app.main:app --reload
```

- Web UI: <http://localhost:8000/>
- API ドキュメント (Swagger): <http://localhost:8000/docs>
- ヘルスチェック: <http://localhost:8000/api/health>

## Docker で起動

イメージには docling の標準モデルが**焼き込まれており**、初回変換でも
モデルのダウンロードは不要です（OCR を使う場合の OCR モデルは対象外）。

```bash
# ビルド（torch とモデルを含むため初回は時間がかかります）
docker build -t pdfto .

# 起動（成果物は名前付きボリュームに保存）
docker run -p 8000:8000 -v pdfto-data:/data pdfto
```

docker compose でも起動できます:

```bash
docker compose up --build
```

> 焼き込んだモデルは `/opt/docling/models` に置かれ、環境変数
> `PDFTO_DOCLING_ARTIFACTS` で参照されます。データは `/data`（ボリューム）に保存され、
> `PDFTO_TTL_MINUTES` に従って自動削除されます。

## API の使い方

### インタラクティブ・フロー（UI と同じ）

変換はバックグラウンドのジョブとして実行されます。投入してジョブ ID を受け取り、
完了するまでポーリングします（重い PDF でもリクエストがタイムアウトしません）。

```
POST /api/v1/documents              # PDF をアップロード → id・解析結果・質問が返る
POST /api/v1/documents/{id}/convert # 回答(JSON)を送って変換を開始 → 202 + ジョブ
GET  /api/v1/jobs/{job_id}          # ジョブの状態をポーリング（succeeded で download_url）
GET  /api/v1/documents/{id}/download?format=markdown   # 変換ファイルを取得
```

例:

```bash
# 1. アップロード（解析して質問を取得）
curl -F file=@report.pdf http://localhost:8000/api/v1/documents
# → {"id":"...", "analysis":{...}, "questions":[...]}

# 2. 回答を送って変換を開始（question id → 回答 のフラットな JSON）
curl -X POST http://localhost:8000/api/v1/documents/<ID>/convert \
     -H 'Content-Type: application/json' \
     -d '{"output_format":"markdown","do_ocr":false,"page_range":[1,5]}'
# → 202 {"id":"<JOB_ID>","status":"pending", ...}

# 3. 完了までポーリング（status が succeeded / failed になるまで）
curl http://localhost:8000/api/v1/jobs/<JOB_ID>
# → {"status":"succeeded","download_url":"...","preview":"..."}

# 4. ダウンロード
curl -OJ "http://localhost:8000/api/v1/documents/<ID>/download?format=markdown"
```

> ジョブの状態は `pending` → `running` → `succeeded`（または `failed`）と遷移します。
> 失敗時は `error` にメッセージが入ります。同時実行数は `PDFTO_MAX_WORKERS` で制御します。

### ワンショット（他システム向け）

オプションが決まっている場合は 1 リクエストで完結します。変換ファイルがそのまま返ります。

```bash
curl -OJ "http://localhost:8000/api/v1/convert?output_format=markdown&do_ocr=false" \
     -F file=@report.pdf
```

### バッチ変換（複数 PDF 一括）

複数の PDF を 1 リクエストで投入します。ファイルごとに非同期ジョブが作られ、
バッチ単位で進捗を集約できます（オプションは全ファイル共通）。

```bash
# 投入（202 + バッチと各ファイルの job_id が返る）
curl -X POST "http://localhost:8000/api/v1/batches?output_format=markdown" \
     -F files=@a.pdf -F files=@b.pdf -F files=@c.pdf

# バッチの集約ステータス
curl "http://localhost:8000/api/v1/batches/<BATCH_ID>"
# → {"id":"...","count":3,"items":[{"filename":"a.pdf","document_id":"...","job_id":"...","status":"succeeded"}, ...]}
```

各成果物は通常どおり `GET /api/v1/documents/{document_id}/download?format=...` で
取得します。1 バッチのファイル数は `PDFTO_MAX_BATCH_FILES`（既定 20）まで。

### OCR と言語

スキャン文書は `do_ocr` を有効にし、`ocr_languages` で言語を指定します
（[EasyOCR の言語コード](https://www.jaided.ai/easyocr/)、例: `ja` / `en` / `ch_sim` /
`ko` / `fr` / `de` / `es`）。対話フローでは内容に応じて言語を複数選択できます。

```bash
# ワンショットで日本語+英語 OCR
curl -OJ "http://localhost:8000/api/v1/convert?do_ocr=true&ocr_languages=ja&ocr_languages=en" \
     -F file=@scanned.pdf
```

> OCR モデル（EasyOCR）は Docker イメージに焼き込まれておらず、初回 OCR 時に
> ダウンロードされます（オフライン環境では別途用意が必要）。

### 画像の扱い（参照モード）

`image_mode` で画像の扱いを選べます。

- `placeholder`（既定）: 画像はプレースホルダのみ（軽量）
- `embedded`: 本文に base64 で埋め込む（単一ファイルで完結）
- `referenced`: 画像を別ファイルに書き出して `assets/<name>` を参照

`referenced` では、画像は個別に保存され次の方法で取得できます。

```bash
# 本文＋画像をまとめて ZIP でダウンロード
curl -OJ "http://localhost:8000/api/v1/documents/<ID>/download?format=markdown&bundle=zip"

# 個別の画像を取得
curl -O "http://localhost:8000/api/v1/documents/<ID>/assets/<filename>"
```

### 質問とオプションの対応

各質問の `id` は変換オプションのフィールド名と一致しており、回答はそのまま送れます。

| id | 内容 | 例 |
|----|------|----|
| `output_format` | 出力形式 | `markdown` / `html` / `json` / `text` |
| `do_ocr` | OCR を行うか（スキャン文書向け） | `true` / `false` |
| `ocr_languages` | OCR の対象言語（複数可・EasyOCR コード） | `["ja","en"]` |
| `do_table_structure` | 表構造を復元するか | `true` / `false` |
| `image_mode` | 画像の扱い | `placeholder` / `embedded` / `referenced` |
| `page_range` | 変換するページ範囲 | `[1, 5]` |

## クライアント / SDK

### Python クライアント（同梱・依存ゼロ）

[`client/python/pdfto_client.py`](client/python/pdfto_client.py) をコピーするだけで
使えます。

```python
from pdfto_client import PDFtoClient

client = PDFtoClient("http://localhost:8000", api_key=None)  # 認証有効なら api_key
markdown = client.convert_file("report.pdf", output_format="markdown")
open("report.md", "wb").write(markdown)
```

詳しくは [client/python/README.md](client/python/README.md) を参照。

### 他言語（OpenAPI から生成）

PDFto は OpenAPI を `/openapi.json` で公開しています。スキーマを書き出して
[openapi-generator](https://openapi-generator.tech/) で任意の言語のクライアントを
生成できます。

```bash
# 稼働中サーバから取得
curl http://localhost:8000/openapi.json -o openapi.json
# またはサーバ無しで書き出し
python scripts/export_openapi.py openapi.json

# 例: TypeScript クライアントを生成
npx @openapitools/openapi-generator-cli generate \
    -i openapi.json -g typescript-fetch -o ./pdfto-ts-client
```

## 設定（環境変数）

| 変数 | 既定値 | 説明 |
|------|--------|------|
| `PDFTO_DATA_DIR` | `data` | アップロード/出力の保存先 |
| `PDFTO_MAX_UPLOAD_MB` | `50` | アップロード上限 (MB) |
| `PDFTO_MAX_BATCH_FILES` | `20` | 1 バッチで受け付ける最大ファイル数 |
| `PDFTO_PREVIEW_CHARS` | `4000` | API が返すプレビューの文字数 |
| `PDFTO_MAX_WORKERS` | `2` | 同時に実行する変換ジョブ数 |
| `PDFTO_TTL_MINUTES` | `60` | 保存物（PDF/成果物/完了ジョブ）の保持時間（分）。`0` 以下で無効 |
| `PDFTO_SWEEP_INTERVAL_SECONDS` | `300` | 期限切れを自動削除する掃除の実行間隔（秒） |
| `PDFTO_LOG_LEVEL` | `INFO` | ログレベル（`DEBUG`/`INFO`/`WARNING` など） |
| `PDFTO_LOG_FORMAT` | `text` | ログ出力形式（`text` / `json`） |
| `PDFTO_API_KEYS` | （空） | API キー（カンマ区切り）。設定すると `/api/v1/*` に認証必須。空なら無認証 |
| `PDFTO_RATE_LIMIT` | `60` | レート上限（件 / ウィンドウ）。`0` 以下で無効 |
| `PDFTO_RATE_WINDOW_SECONDS` | `60` | レート制限のウィンドウ（秒） |
| `PDFTO_WEBHOOK_SECRET` | （空） | 設定すると Webhook 本文に HMAC-SHA256 署名を付与 |
| `PDFTO_WEBHOOK_TIMEOUT` | `10` | Webhook 配送のタイムアウト（秒） |
| `PDFTO_WEBHOOK_ALLOWED_HOSTS` | （空） | Webhook 送信先の許可ホスト（カンマ区切り）。空なら制限なし |

## 認証とレート制限

`PDFTO_API_KEYS` を設定すると、`/api/v1/*` に **API キー認証**が必須になります
（未設定なら無認証で従来どおり）。キーは `X-API-Key` か `Authorization: Bearer` で
送ります。`/api/health`・`/docs`・Web UI は常に開放です。

```bash
export PDFTO_API_KEYS="key-abc,key-def"

curl -H "X-API-Key: key-abc" -F file=@report.pdf \
     http://localhost:8000/api/v1/documents
# または
curl -H "Authorization: Bearer key-abc" ... 
```

レート制限は `PDFTO_RATE_LIMIT` 件 / `PDFTO_RATE_WINDOW_SECONDS` 秒（既定 60/60）で、
認証有効時はキー単位、無効時はクライアント IP 単位です。超過すると `429` と
`Retry-After` を返します（`PDFTO_RATE_LIMIT=0` で無効）。

> カウンタはプロセス内（インメモリ）です。複数インスタンスで共有する分散レート
> 制限は対象外です。認証を有効にした場合、同梱 Web UI から API を叩くにはキーが
> 必要になります（UI へのキー入力欄は将来対応）。

## Webhook（変換完了通知）

変換開始時に `callback_url` を指定すると、ジョブ完了（`succeeded` / `failed`）時に
その URL へ結果が POST されます。ポーリング（`/jobs/{id}`）の代わりにイベント駆動で
連携できます。

```bash
curl -X POST "http://localhost:8000/api/v1/documents/<ID>/convert?callback_url=https://example.com/hook" \
     -H 'Content-Type: application/json' -d '{"output_format":"markdown"}'
```

通知ボディ:

```json
{"event": "job.succeeded", "job": {"id": "...", "status": "succeeded", "download_url": "...", ...}}
```

`PDFTO_WEBHOOK_SECRET` を設定すると、本文の HMAC-SHA256 署名が
`X-PDFTO-Signature: sha256=<hex>` ヘッダで付与され、受信側で真正性を検証できます。

> 配送は 1 回のみ（再試行なし）・タイムアウトあり。確実性が必要な場合はポーリングを
> 併用してください。サーバが任意 URL へ POST するため、SSRF 対策として送信先は
> `http`/`https` に限定され、`PDFTO_WEBHOOK_ALLOWED_HOSTS` で許可ホストを絞れます。
> 再起動で中断したジョブには通知されません。

## ログと監視

すべてのログ行に **リクエスト ID** が付き、アクセスログ・変換ジョブ・エラーを
横断して相関できます。各レスポンスには `X-Request-ID` ヘッダが付与され、
リクエスト側で `X-Request-ID` を指定すればその値が踏襲されます。
本番では `PDFTO_LOG_FORMAT=json` を推奨します。

```json
{"time":"...","level":"INFO","logger":"pdfto","request_id":"...","message":"POST /api/v1/documents/.../convert -> 202","status":202,"duration_ms":3}
```

想定外のエラーは内部情報を漏らさず `{"detail":"internal server error","request_id":"..."}`
として 500 で返り、トレースバックはサーバログにのみ記録されます。

## アーキテクチャ

```
app/
  analysis.py    PDF の軽量解析（pypdf）— 質問の出し分けに使用
  questions.py   解析結果から質問を生成し、回答をオプションへ変換
  converter.py   docling を使った変換コア（遅延 import）
  jobs.py        変換をバックグラウンド実行するジョブ基盤（SQLite 永続化）
  cleanup.py     期限切れの保存物/ジョブを定期削除する掃除スレッド
  db.py          SQLite 永続化層（索引・ジョブ）
  storage.py     アップロードと変換結果の保存（ファイル + SQLite 索引）
  logging_config.py  構造化ログ設定（リクエスト ID 付与）
  models.py      API・コアで共有する Pydantic モデル
  main.py        FastAPI アプリ（REST API + Web UI 配信）
  static/        Web UI（HTML/CSS/JS）
tests/           pytest（docling をモックした API テスト等）
```

ドキュメント索引とジョブは `data/pdfto.db`（SQLite）に永続化され、プロセス再起動を
跨いで保持されます。再起動で中断したジョブは起動時に `failed` として復旧されます。
変換ファイル・アップロード PDF は `data/<id>/` に保存されます。

コア（`analysis` / `questions` / `converter`）は Web 層から独立しているため、
Python から直接 import して使うこともできます:

```python
from app.converter import convert
from app.models import ConversionOptions, OutputFormat

result = convert("report.pdf", ConversionOptions(output_format=OutputFormat.markdown))
print(result.content)
```

## テスト

```bash
pip install pytest
pytest
```

API テストは docling をモックするため、ML モデルのダウンロードなしで実行できます。

## ライセンス / クレジット

変換処理は [docling](https://github.com/docling-project/docling)（MIT License）に依存しています。
