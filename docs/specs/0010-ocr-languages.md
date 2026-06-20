# Spec: OCR 言語の選択・多言語対応

- **ID:** 0010
- **状態:** done
- **マイルストーン:** M3 変換品質
- **関連 issue:** M3-1（OCR 言語の選択と多言語対応）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

現状 OCR は `do_ocr` の有無のみで、言語を指定できない。スキャン文書の言語に
合わせて OCR 言語を選べないと、日本語など非英語の認識精度が出ない。

OCR 言語を**複数選択**できるようにし、内容に応じた質問で提示する。言語コードの
規約を安定させるため、言語指定時は OCR エンジンに **EasyOCR** を用いる
（2 文字系コード: `en` / `ja` / `fr` …）。

## 2. スコープ

### やること
- `ConversionOptions.ocr_languages: list[str]` を追加。
- 変換コアで、`do_ocr` かつ `ocr_languages` 指定時に EasyOCR を言語付きで使用。
- OCR が関係する文書（スキャン疑い等）で「OCR 言語」を複数選択する質問を追加
  （新しい質問タイプ `multichoice`）。
- ワンショット `POST /convert`・バッチ `POST /batches` でも言語指定を受け付ける。
- Web UI に複数選択（チェックボックス群）の描画を追加。

### やらないこと（非スコープ）
- OCR エンジンの切り替え UI（Tesseract/RapidOCR 等の選択）。言語指定時は EasyOCR 固定。
- OCR モデルの Docker への焼き込み（spec 0003 のとおり OCR モデルは実行時取得）。
- 言語自動判定。

## 3. 要件

### 機能要件
- `ocr_languages` 省略時は従来挙動（docling 既定の OCR）。
- `do_ocr=true` かつ `ocr_languages` 指定時、その言語で OCR される
  （内部で EasyOCR を使用）。
- 質問 `ocr_languages`（`multichoice`）は OCR 質問が出る文書でのみ提示し、既定は
  `["ja", "en"]`。
- ワンショット/バッチでは `ocr_languages` をクエリ（繰り返し可）で受け付ける。

### 非機能要件
- `ocr_languages` 省略時の挙動・既存 API の外形は不変。
- 変換コアは Web 層から独立のまま。

## 4. 設計

### モデル（`app/models.py`）
- `ConversionOptions.ocr_languages: list[str] = []`。
- `Question` に新タイプ `multichoice`（`choices` と `default: list` を使用）。

### コア（`app/converter.py`）
- `_get_converter(..., ocr_languages: tuple[str, ...] = ())` を追加（lru_cache キー）。
  `do_ocr` かつ `ocr_languages` があれば
  `pipeline_options.ocr_options = EasyOcrOptions(lang=list(ocr_languages))`。
- `convert()` は `tuple(options.ocr_languages)` を渡す。

### 質問（`app/questions.py`）
- OCR 質問を出す分岐で `ocr_languages`（`multichoice`、候補: en/ja/ch_sim/ko/fr/de/es、
  既定 `["ja","en"]`）を追加。
- `apply_answers`: `ocr_languages` が list なら `ConversionOptions.ocr_languages` へ。

### API（`app/main.py`）
- 対話 `convert`: 回答 JSON 内の `ocr_languages`（list）をそのまま反映（apply_answers）。
- ワンショット/バッチ: `ocr_languages: list[str] = Query(default=[])` を追加し
  apply_answers に渡す。

### Web UI（`app/static/app.js`, `style.css`）
- `multichoice` をチェックボックス群で描画。`collectAnswers` は選択値を配列で収集。

### 影響範囲
- 変更: `app/models.py`, `app/converter.py`, `app/questions.py`, `app/main.py`,
  `app/static/app.js`, `app/static/style.css`,
  `tests/test_questions.py` / `test_converter_config.py` / `test_api.py`,
  `README.md`, `docs/roadmap.md`。
- コア外形・既存挙動は `ocr_languages` 省略時不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] `ocr_languages` 省略時は既存テストが通る（挙動不変）。
- [ ] `convert()` が `ocr_languages` を `_get_converter` に渡す（テストで確認）。
- [ ] スキャン疑い文書の質問に `ocr_languages`（multichoice, 既定 ja/en）が含まれる。
- [ ] `apply_answers` が `ocr_languages` を反映する。
- [ ] ワンショット/バッチで `ocr_languages` クエリを受け付ける。
- [ ] Web UI が multichoice を描画し、選択を送信できる。
- [ ] `pytest` が通る。

## 6. テスト計画

- `apply_answers({"ocr_languages": ["ja","en"]})` → `options.ocr_languages == ["ja","en"]`。
- スキャン疑いの `build_questions` に `ocr_languages`（type=multichoice, default ja/en）。
- `convert()` の monkeypatch で `_get_converter` に `ocr_languages=("ja","en")` が
  渡ることを確認。
- API: `convert` に `{"do_ocr": true, "ocr_languages": ["ja"]}` を送って `202`。
  ワンショット `?ocr_languages=ja&ocr_languages=en` が受理される。
- 実 OCR 変換（モデル DL/スキャン PDF 必須）は CI 非対象。手動確認に委ねる。

## 7. リスク・代替案

- **EasyOCR の言語組み合わせ制約。** 一部言語は同時指定不可。無効な組み合わせは
  変換時エラー → ジョブ `failed`（既存のエラー処理に乗る）。候補は組み合わせ可能な
  範囲を中心に提示する。
- **OCR モデルの実行時 DL。** オフライン/Docker では OCR 時に取得が必要（既知の制限、
  README 明記）。
- **代替: auto エンジンに lang を渡す。** コード規約が不定で不安定なため、言語指定時は
  EasyOCR を明示する。

## 8. 未決事項

- 既定言語は `["ja","en"]`（本リポジトリの主用途）。環境差は質問で選択して上書き可能。
