# Spec: EasyOCR 言語モデルの焼き込み（オフライン言語 OCR）

- **ID:** 0013
- **状態:** done
- **マイルストーン:** M3 変換品質
- **関連 issue:** M3-1 派生（言語指定 OCR をオフライン/Docker で動作させる）
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

言語指定 OCR（`ocr_languages`）は EasyOCR を用いるが、EasyOCR のモデルは Docker
イメージに焼き込まれておらず、初回 OCR 時にネットワークから取得していた。
オフライン環境や閉域では言語 OCR が失敗する。

EasyOCR の言語モデルを **Docker イメージに焼き込み**、ネットワーク無しでも
`ocr_languages` 指定の OCR が動くようにする。

## 2. スコープ

### やること
- `easyocr` を依存に追加する。
- 変換コアで、焼き込み済みモデルディレクトリが設定されていれば、EasyOCR を
  **オフライン**（`model_storage_directory` 指定・`download_enabled=False`）で使う。
- Dockerfile でビルド時に対象言語の EasyOCR モデルを取得して焼き込む。
- 設定 `PDFTO_EASYOCR_MODELS`（モデルディレクトリ）を追加。

### やらないこと（非スコープ）
- 既定エンジン（RapidOCR、言語未指定時）の変更（現状維持・既に焼き込み済み）。
- すべての EasyOCR 言語の網羅（質問で提示する言語: en/ja/ch_sim/ko/fr/de/es に限定）。
- GPU 対応。

## 3. 要件

### 機能要件
- `PDFTO_EASYOCR_MODELS` 未設定時は従来どおり（必要に応じ実行時 DL）。
- 設定時、`ocr_languages` 指定 OCR が**ネットワーク無し**で動作する。
- 対象言語（en/ja/ch_sim/ko/fr/de/es）のモデルがイメージに含まれる。
- 言語未指定 OCR（RapidOCR）は従来どおりオフライン動作。

### 非機能要件
- 既定 `pytest`（docling モック）はモデル不要のまま。
- 新規ランタイム依存は `easyocr` のみ（torch 等は既存）。

## 4. 設計

### 設定（`app/config.py`）
- `easyocr_models: str | None`（`PDFTO_EASYOCR_MODELS`）。

### コア（`app/converter.py`）
- `_get_converter(..., ocr_languages, easyocr_models=None)`:
  言語指定時の `EasyOcrOptions` に、`easyocr_models` があれば
  `model_storage_directory=easyocr_models, download_enabled=False` を設定。
  無ければ従来どおり（`download_enabled` 既定、実行時 DL 可）。
- `convert()` は `settings.easyocr_models` を渡す。lru_cache キーに含める。

### Dockerfile
- `requirements.txt` 経由で `easyocr` を導入。
- ビルド時に対象言語の EasyOCR モデルを `/opt/easyocr-models` へ取得
  （`easyocr.Reader(langs, model_storage_directory=..., download_enabled=True)` を
  言語グループごとに実行。CJK は english と個別に、latin 系はまとめて）。
- `ENV PDFTO_EASYOCR_MODELS=/opt/easyocr-models`。

### 影響範囲
- 変更: `requirements.txt`, `app/config.py`, `app/converter.py`, `Dockerfile`,
  `tests/test_converter_config.py`, `README.md`, `docs/roadmap.md`。
- 既定挙動（言語未指定・`PDFTO_EASYOCR_MODELS` 未設定）は不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] `easyocr` が依存に入る。
- [ ] `PDFTO_EASYOCR_MODELS` 設定時、`convert()` が `_get_converter` に
      `easyocr_models` を渡し、`EasyOcrOptions` が
      `model_storage_directory` 設定・`download_enabled=False` になる（テストで確認）。
- [ ] Dockerfile が対象言語の EasyOCR モデルを焼き込み、`PDFTO_EASYOCR_MODELS` を設定。
- [ ] ネットワーク無しで、焼き込みモデルを使った言語 OCR が文字を抽出できる（実機確認）。
- [ ] `PDFTO_EASYOCR_MODELS` 未設定の既存挙動は不変（既存テストが通る）。

## 6. テスト計画

- `test_converter_config.py`: `settings.easyocr_models` 設定時に `convert()` が
  `_get_converter` へ `easyocr_models=<dir>` を渡すことを monkeypatch で確認。
- 実機（手動/opt-in）: 対象言語のモデルを dir に取得 → ネットワーク遮断下で
  `scanned_sample.pdf` を `do_ocr=True, ocr_languages=["en"]` 変換 → 本文抽出。

## 7. リスク・代替案

- **イメージ肥大。** EasyOCR モデル（検出 + 各言語認識）で数百 MB 増。M3 では許容。
  必要言語のみ焼き込む。
- **EasyOCR の言語組み合わせ制約。** ビルド時は言語グループ単位で取得し、全対象言語の
  モデルファイルを揃える（実行時は要求言語のみで Reader を構成）。
- **代替: RapidOCR を多言語に使う。** 既に焼き込み済みだが、言語コード規約と多言語
  認識の扱いが EasyOCR と異なるため、言語指定は EasyOCR 方針を維持する。

## 8. 未決事項

- 焼き込む言語セットは質問で提示する 7 言語に一致させる。将来増やす場合は Dockerfile を
  更新する。
