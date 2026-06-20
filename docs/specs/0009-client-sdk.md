# Spec: クライアント SDK と OpenAPI 生成手順

- **ID:** 0009
- **状態:** done
- **マイルストーン:** M2 公開・連携の強化
- **関連 issue:** M2-4（クライアント SDK もしくは OpenAPI からの生成手順）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

API ファーストで作ってきたが、他システムが組み込む際のとっかかり（クライアント）が
まだ無い。最小の手間で使い始められるよう、(1) すぐ使える**軽量 Python クライアント**と、
(2) 任意の言語向けに **OpenAPI からクライアントを生成する手順**を用意する。

## 2. スコープ

### やること
- 依存ゼロ（標準ライブラリのみ）の Python クライアント `client/python/pdfto_client.py`。
  アップロード→変換→ポーリング→ダウンロードの一連、ワンショット、バッチ、API キーに対応。
- 使い方の例（`client/python/example.py`）とクライアント用 README。
- OpenAPI スキーマを書き出すスクリプト `scripts/export_openapi.py`。
- README に「OpenAPI からのクライアント生成手順」（`openapi-generator` 等）を追記。

### やらないこと（非スコープ）
- 複数言語の公式 SDK をリポジトリに同梱（生成手順の提供にとどめる）。
- PyPI への配布パッケージング（将来）。
- 非同期（asyncio）クライアント（同期版のみ）。

## 3. 要件

### 機能要件（Python クライアント）
- `PDFtoClient(base_url, api_key=None, timeout=...)`。`api_key` 指定時は
  `X-API-Key` を付与。
- メソッド:
  - `health()`
  - `upload(path) -> dict`（解析結果・質問を含む document レスポンス）
  - `convert(document_id, answers=None, callback_url=None) -> job`
  - `get_job(job_id) -> job` / `wait_for_job(job_id, ...) -> job`
  - `download(document_id, fmt="markdown") -> bytes`
  - `convert_file(path, wait=True, **answers) -> bytes`（一連をまとめた便利関数）
  - `convert_oneshot(path, output_format="markdown", ...) -> bytes`
  - `batch(paths, output_format="markdown", ...) -> batch` / `get_batch(id)`
- HTTP エラー（4xx/5xx）は `PDFtoError`（`status` と `detail` を持つ）に正規化。
- 標準ライブラリ（`urllib`）のみ。multipart 送信は自前エンコード。

### 機能要件（OpenAPI 生成）
- `python scripts/export_openapi.py [out.json]` で OpenAPI を JSON 出力できる。
- README に、稼働中サーバの `/openapi.json` か書き出した JSON から
  `openapi-generator-cli` でクライアントを生成する手順を記載。

### 非機能要件
- クライアントはサーバ依存（FastAPI 等）を持たない単一ファイルで、コピーして使える。

## 4. 設計

### `client/python/pdfto_client.py`
- `PDFtoError(Exception)`: `status: int`, `detail: str`。
- `PDFtoClient`: 内部 `_request(method, path, data=None, headers=None) -> bytes/dict`、
  `_post_multipart(path, files, fields)`（境界文字列で multipart/form-data を構築）。
- JSON 応答は `dict`、ダウンロードは `bytes` を返す。

### `scripts/export_openapi.py`
- `from app.main import app; json.dump(app.openapi(), ...)`。引数で出力先指定、
  既定は標準出力。

### ドキュメント
- README「クライアント / SDK」節：Python クライアントの例 ＋ OpenAPI 生成手順。

### 影響範囲
- 追加: `client/python/pdfto_client.py`, `client/python/example.py`,
  `client/python/README.md`, `scripts/export_openapi.py`,
  `tests/test_client.py`。
- 変更: `README.md`, `CLAUDE.md`/`docs/roadmap.md`。
- サーバ側コードは無変更（クライアントは外側の追加物）。

## 5. 受け入れ条件（Definition of Done）

- [ ] `PDFtoClient` で health/upload/convert/wait/download が動く（テストで確認）。
- [ ] `convert_file` がアップロード〜ダウンロードを 1 メソッドで完結させる。
- [ ] `batch` 投入と `get_batch` 取得が動く。
- [ ] API キー設定時、未指定だと `PDFtoError(status=401)`、指定で成功。
- [ ] `scripts/export_openapi.py` が妥当な OpenAPI JSON（`openapi`/`paths` キー）を出す。
- [ ] README に生成手順が載る。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_client.py`: 実サーバをスレッドで起動（`uvicorn.Server`）し、docling は
`app.main.convert` を高速なフェイクに monkeypatch、`storage`/`jobs` を一時 DB に
差し替える。

- `convert_file` で markdown を取得できる。
- `batch` で 2 ファイル投入 → 各ジョブ完了 → `get_batch` が集約を返す。
- `convert_oneshot` がバイト列を返す。
- API キー有効時、キー無しクライアントは `PDFtoError(status=401)`、キー付きは成功。
- `export_openapi`：`app.openapi()` に `openapi` と `paths` が含まれる（関数を直接検証）。

## 7. リスク・代替案

- **テストでの実サーバ起動の不安定さ。** 起動完了を待ち、エフェメラルポートを使う。
  失敗時はタイムアウトで検知。
- **代替: OpenAPI 生成のみ提供しクライアントは同梱しない。** すぐ使える価値が高い
  ため、軽量 Python クライアントは同梱する。多言語は生成手順で補う。

## 8. 未決事項

- クライアントの配布（PyPI 化）は将来 issue。今回は単一ファイル同梱に留める。
