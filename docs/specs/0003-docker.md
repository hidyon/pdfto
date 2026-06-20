# Spec: Docker 化（モデル焼き込み）

- **ID:** 0003
- **状態:** done
- **マイルストーン:** M1 信頼性と運用性
- **関連 issue:** M1-3（Docker 化。モデルを焼き込み、初回 DL を不要に）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

現状はローカルに Python 環境を作って起動する必要があり、再現性が低い。また
docling は初回変換時に ML モデルをネットワークからダウンロードするため、最初の
リクエストが数十秒〜分単位で待たされ、オフライン環境では失敗する。

コンテナイメージにアプリと **docling のモデルを焼き込み**、`docker run` するだけで
**初回 DL なし**に変換できる状態を作る。これは M1 の DoD「コンテナで再現性よく
起動できる」を満たす。

## 2. スコープ

### やること
- アプリを動かす `Dockerfile` を用意する。
- ビルド時に docling の標準モデル一式（layout / tableformer / code_formula /
  picture_classifier / rapidocr）をイメージへ焼き込む。
- 焼き込んだモデルを実行時に参照する仕組み（`artifacts_path`）を設定で渡せるようにする。
- `docker-compose.yml` と `.dockerignore` を用意する。
- README に Docker での起動手順を追記する。

### やらないこと（非スコープ）
- EasyOCR など標準セット外の OCR エンジンモデルの焼き込み（イメージ肥大のため。
  OCR を使う場合、当該エンジンのモデルは初回利用時に取得され得る点を明記する）。
- マルチアーキ（arm64/amd64）ビルドや本番オーケストレーション（k8s 等）。
- イメージの公開（レジストリ push）や CI でのビルド自動化（将来の issue）。

## 3. 要件

### 機能要件
- `docker build` で動作するイメージが生成できる。
- そのイメージを `docker run -p 8000:8000` すると Web UI / API が起動する。
- ネットワークを切った状態でも、標準パイプライン（OCR 無し）の変換が
  **モデル DL なし**で完了する。
- 変換結果やアップロードは名前付きボリューム（`/data`）に保存され、コンテナ
  再生成後も TTL に従って管理される。

### 非機能要件
- 実行時にモデルの追加 DL を行わない（標準パイプライン）。
- イメージは公式 `python:3.11-slim` をベースとし、不要な肥大を避ける。

## 4. 設計

### モデル参照（`app/config.py` / `app/converter.py`）
- 設定に `docling_artifacts: str | None`（環境変数 `PDFTO_DOCLING_ARTIFACTS`）を追加。
- `converter._get_converter(...)` に `artifacts_path` を渡し、設定があれば
  `PdfPipelineOptions.artifacts_path` にセットする。未設定なら従来どおり
  docling の既定（HF キャッシュ）を使う。
- `convert()` は `settings.docling_artifacts` を参照して `_get_converter` に渡す。
  lru_cache のキーに `artifacts_path` を含める。

### Dockerfile
- ベース: `python:3.11-slim`。
- OS 依存: `libgl1` / `libglib2.0-0`（OpenCV 系が要求し得るため）。
- `pip install -r requirements.txt`（公式イメージの pip はクリーンなので
  antlr4 等のビルドは通る想定）。
- モデル焼き込み: `docling-tools models download -o /opt/docling/models`。
- 環境変数: `PDFTO_DOCLING_ARTIFACTS=/opt/docling/models`、`PDFTO_DATA_DIR=/data`。
- `VOLUME /data`、`EXPOSE 8000`。
- `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`。

### 付随ファイル
- `.dockerignore`: `.venv/`, `data/`, `.git/`, `__pycache__/`, `*.pyc` など。
- `docker-compose.yml`: サービス `pdfto`、`build: .`、`8000:8000`、
  `volumes: [pdfto-data:/data]`。

### 影響範囲
- 追加: `Dockerfile`, `.dockerignore`, `docker-compose.yml`,
  `tests/test_converter_config.py`（artifacts_path の受け渡し検証）。
- 変更: `app/config.py`, `app/converter.py`, `README.md`,
  `CLAUDE.md`/`docs/roadmap.md`。
- コア API・既存の振る舞いは不変（artifacts_path 未設定時は従来どおり）。

## 5. 受け入れ条件（Definition of Done）

- [ ] `docker build -t pdfto .` が成功する。
- [ ] `docker run -p 8000:8000 pdfto` で `GET /api/health` が `ok` を返す。
- [ ] ネットワーク無効化（`--network none` 等）で、OCR 無しの PDF 変換が
      モデル DL なしに完了する。
- [ ] `PDFTO_DOCLING_ARTIFACTS` を渡すと `artifacts_path` が converter に反映される
      （ユニットテストで検証）。
- [ ] `docker-compose up` で同等に起動できる。
- [ ] 既存 `pytest` が引き続き通る。

## 6. テスト計画

- `tests/test_converter_config.py`（新規）: `_get_converter` をモック前提でなく、
  docling の import を避けるため、`PdfPipelineOptions` に `artifacts_path` が
  設定されることを確認する軽量テスト（docling 未導入環境では skip）。
  もしくは `convert` が `settings.docling_artifacts` を読んで `_get_converter` に
  渡すことを monkeypatch で検証する。
- Docker の受け入れ条件はビルド/起動の手動確認（ログに記録）。CI 化は別 issue。

## 7. リスク・代替案

- **イメージサイズ。** torch(CPU) + モデルで数 GB になり得る。M1 では許容し、
  軽量化（multi-stage、CPU 専用 torch index 等）は将来の改善とする。
- **OCR モデルの扱い。** 標準セット外のため OCR 初回利用時に DL され得る。
  スコープ外として明記。必要なら別 issue で `with_easyocr` 等を焼き込む。
- **代替: モデルを実行時ボリュームに置く。** 再現性が下がるため不採用。焼き込みを優先。

## 8. 未決事項

- イメージ軽量化（CPU 版 torch の明示指定など）は本 issue ではやらず、必要になったら
  別 issue 化する。
