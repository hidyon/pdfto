# Spec: Docker イメージの軽量化（マルチステージ + CPU 版 torch）

- **ID:** 0022
- **状態:** done
- **マイルストーン:** M6 配布・軽量化
- **関連 issue:** M6-2（Docker マルチステージ / CPU 版 torch でイメージ軽量化）
- **作成日 / 更新日:** 2026-06-22 / 2026-06-22

## 1. 背景・目的

現状の Docker イメージは単一ステージで、`pip install` が docling/easyocr の依存として
**GPU 版 torch（CUDA ライブラリ同梱）**を引き込むため非常に大きい（数 GB の CUDA
wheel が無駄に入る）。本アプリは CPU 推論前提なので、**CPU 版 torch**に切り替え、
さらに**マルチステージビルド**で pip キャッシュ・ビルド時生成物を最終イメージから
除くことで、サイズとビルド/配布コストを下げる。

## 2. スコープ

### やること
- `pip` を CPU 版 torch（`https://download.pytorch.org/whl/cpu`）でインストールし、
  CUDA 版が入らないようにする。
- Dockerfile を**マルチステージ**化（builder で依存導入＋モデル取得、runtime には
  必要物のみコピー）。
- 既存の「docling/EasyOCR モデルを焼き込みオフライン変換可」を維持。
- 軽量化後のイメージサイズを記録し、オフライン変換が引き続き動くことを確認。

### やらないこと（非スコープ）
- アプリ機能・依存パッケージの追加/削除（torch の配布チャネル変更を除く）。
- GPU 対応イメージの提供（CPU 前提を明確化）。
- レジストリ公開・タグ運用。

## 3. 要件

### 機能要件
- ビルドが成功し、コンテナが起動して `/api/health` が応答する。
- 焼き込んだモデルにより、`--network none` でも変換が成功する（オフライン）。
- `docling` / `easyocr` の torch 依存が CPU 版で解決される。

### 非機能要件
- 最終イメージサイズが現状（単一ステージ・CUDA torch）より小さい。
- ビルドのレイヤキャッシュが効く（requirements → モデル → app の順は維持）。
- 既定テスト（`python -m pytest`）に影響しない（Docker 専用の変更）。

## 4. 設計

### Dockerfile（マルチステージ）
- **builder ステージ**（`python:3.11-slim`）:
  - CPU 版 torch を先に導入：
    `pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision`
  - 続けて `pip install -r requirements.txt`（torch は充足済みなので CUDA 版は入らない）。
  - `docling-tools models download -o /opt/docling/models`。
  - `python scripts/fetch_easyocr_models.py /opt/easyocr-models`。
  - 依存は専用 venv `/opt/venv` に入れ、まるごと runtime へ持ち込む。
- **runtime ステージ**（`python:3.11-slim`）:
  - OpenCV 系の実行時共有ライブラリ（`libgl1`, `libglib2.0-0`）のみ apt 導入。
  - builder から `/opt/venv`・`/opt/docling/models`・`/opt/easyocr-models` をコピー。
  - `app` をコピー、`/data` ボリューム、`EXPOSE 8000`、uvicorn 起動。
  - `ENV PATH=/opt/venv/bin:$PATH` と `PDFTO_*` を設定。

### 影響範囲
- 変更: `Dockerfile`, `docs/roadmap.md`,（必要なら）`README.md`。
- `docker-compose.yml`・`.dockerignore`・アプリコード・テストは原則不変。

## 5. 受け入れ条件（Definition of Done）

- [x] Dockerfile がマルチステージで、CPU 版 torch を導入している。
- [x] イメージがビルドできる（builder→runtime の 2 ステージ）。
- [x] `--network none` でオフライン変換が成功する（焼き込みモデル使用。docling 既定
      変換／EasyOCR の両方を検証）。
- [x] CPU 版 torch が使われ、CUDA/nvidia ライブラリがイメージに含まれないことを確認
      （= 従来比の軽量化を実証。詳細は下記「検証結果」）。
- [x] 既定 `pytest` が引き続き通る（Docker 変更はアプリに影響しない）。

### 検証結果（2026-06-22）

- ビルド成功（マルチステージ）。`torch` は `2.12.1+cpu`、`torch.version.cuda` は
  `None`、site-packages に `nvidia-*` / CUDA ライブラリは**存在しない**。
  （PyPI 既定の torch は CUDA 同梱で nvidia-* 依存が約 3–4GB 加わるため、その分を回避。）
- オフライン変換: `docker run --network none` で
  `samples/table_sample.pdf`（docling 既定）と `samples/scanned_sample.pdf`
  （`do_ocr=True, ocr_languages=['en']` → 焼き込み EasyOCR）の変換が成功。
- 最終イメージの内訳（実測 `du`）: venv（CPU torch 含む）約 1.9GB ／ docling モデル
  約 1.3GB ／ EasyOCR モデル約 162MB。サイズの大半は ML モデル（焼き込み）と
  Python/torch/OpenCV スタックで、これは仕様上不可避。
- 注: 本サンドボックスは空きディスクが少なく（約 5.5GB）、旧構成（単一ステージ・
  CUDA torch）の実ビルドができなかったため、数値の旧/新比較は未取得。CUDA スタックの
  不在（上記）をもって軽量化の根拠とする。
- `python -m pytest`: 95 passed, 5 skipped（アプリ非変更）。

## 6. テスト計画

- ビルド検証（手動・重い／本リポジトリ環境では TLS プロキシ CA 注入が必要）:
  - `docker build -t pdfto:slim .` が成功。
  - `docker run` → `GET /api/health` が `{"status":"ok"}`。
  - `docker run --network none ... convert`（サンプル PDF）で変換成功。
  - `docker images pdfto` のサイズを旧構成と比較し記録。
- 既定 `python -m pytest`（アプリ非変更の確認）。

> 本リポジトリのサンドボックスでは Docker デーモン手動起動・egress プロキシの CA 注入が
> 必要で実ビルドは重い（過去セッションで実施実績あり）。CA 注入は使い捨ての
> `Dockerfile.verify` + `_ci/`（gitignore 済）で行い、コミット対象の `Dockerfile` は
> クリーンに保つ。

## 7. リスク・代替案

- **torch CPU 版の解決失敗**：docling/easyocr のバージョン制約と CPU wheel の整合に注意。
  先に torch を入れて後段で `-r requirements.txt` を入れる順で吸収する。
- **代替: CUDA のまま単一ステージ**：サイズが大きく配布が重い。CPU 前提の本アプリでは不要。
- **代替: distroless runtime**：libgl 等の共有ライブラリ導入が難しく、OCR が動かなく
  なる恐れがあるため slim を採用。

## 8. 未決事項

- ベースイメージは `python:3.11-slim` を継続。GPU 版は提供しない（CPU 前提）。
