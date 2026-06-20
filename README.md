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

### 質問とオプションの対応

各質問の `id` は変換オプションのフィールド名と一致しており、回答はそのまま送れます。

| id | 内容 | 例 |
|----|------|----|
| `output_format` | 出力形式 | `markdown` / `html` / `json` / `text` |
| `do_ocr` | OCR を行うか（スキャン文書向け） | `true` / `false` |
| `do_table_structure` | 表構造を復元するか | `true` / `false` |
| `image_mode` | 画像の扱い | `placeholder` / `embedded` / `referenced` |
| `page_range` | 変換するページ範囲 | `[1, 5]` |

## 設定（環境変数）

| 変数 | 既定値 | 説明 |
|------|--------|------|
| `PDFTO_DATA_DIR` | `data` | アップロード/出力の保存先 |
| `PDFTO_MAX_UPLOAD_MB` | `50` | アップロード上限 (MB) |
| `PDFTO_PREVIEW_CHARS` | `4000` | API が返すプレビューの文字数 |
| `PDFTO_MAX_WORKERS` | `2` | 同時に実行する変換ジョブ数 |
| `PDFTO_TTL_MINUTES` | `60` | 保存物（PDF/成果物/完了ジョブ）の保持時間（分）。`0` 以下で無効 |
| `PDFTO_SWEEP_INTERVAL_SECONDS` | `300` | 期限切れを自動削除する掃除の実行間隔（秒） |

## アーキテクチャ

```
app/
  analysis.py    PDF の軽量解析（pypdf）— 質問の出し分けに使用
  questions.py   解析結果から質問を生成し、回答をオプションへ変換
  converter.py   docling を使った変換コア（遅延 import）
  storage.py     アップロードと変換結果の保存（ファイル + インメモリ索引）
  models.py      API・コアで共有する Pydantic モデル
  main.py        FastAPI アプリ（REST API + Web UI 配信）
  static/        Web UI（HTML/CSS/JS）
tests/           pytest（docling をモックした API テスト等）
```

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
