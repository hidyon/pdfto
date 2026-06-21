# Spec: 表抽出の品質改善・検証用サンプル整備

- **ID:** 0012
- **状態:** done
- **マイルストーン:** M3 変換品質
- **関連 issue:** M3-2（表抽出の品質改善・検証用サンプル整備）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

表は変換品質の要だが、現状 `table_mode`（accurate/fast）は `ConversionOptions` に
あるだけで **API/質問から指定できず**、また表抽出が実際に効いているかを確かめる
**検証用サンプルが無い**。

`table_mode` を選べるようにして品質と速度を制御できるようにし、表を含む
**検証用サンプル**と、それを使った（任意実行の）変換テストを整備する。これにより
今後の変更で表抽出が壊れていないかを確認できる土台を作る。

## 2. スコープ

### やること
- 対話フローに `table_mode` の質問（accurate/fast）を追加（表構造 ON のとき）。
- ワンショット `POST /convert`・バッチ `POST /batches` に `table_mode` を追加。
- 表を含む検証用サンプル PDF（`samples/table_sample.pdf`）を同梱。
- サンプル生成スクリプト `scripts/make_sample_pdfs.py`（reportlab、開発用）。
- 任意実行（環境変数で有効化）の実変換テストで、サンプルから Markdown 表が
  得られることを検証。

### やらないこと（非スコープ）
- docling 内部の表抽出アルゴリズム自体の改変（エンジン任せ）。
- セル単位の厳密一致検証（OCR/レイアウトの揺れがあるため、主要セルの存在確認に留める）。
- CI への重い実変換テストの常時組み込み（既定はスキップ）。

## 3. 要件

### 機能要件
- `table_mode`（`accurate`（既定）/`fast`）を対話・ワンショット・バッチで指定できる。
- `do_table_structure=false` のとき `table_mode` は無視される（既存挙動）。
- `samples/table_sample.pdf` が存在し、`scripts/make_sample_pdfs.py` で再生成できる。
- 実変換テストは `PDFTO_RUN_DOCLING_TESTS=1` のときのみ実行し、未設定なら skip。
  実行時、サンプルの変換が **成功し（例外なし）、非空の出力**を返すこと（パイプラインの
  スモークテスト）を確認する。

> **注（実機検証で判明）:** docling の既定は `do_ocr=True`、本アプリの既定は
> `do_ocr=False`。born-digital PDF はテキスト層から抽出できるが、合成 PDF
> （reportlab 等）はテキスト層が docling のパーサで読めず OCR 前提になる場合がある。
> また合成 PDF は ML の表検出が安定しない。そのため検証テストは「主要セルの厳密一致」や
> 「Markdown 表の生成」を**ハードな合否条件にはしない**（モデル/PDF 依存のため）。
> 表構造の精度は実文書での手動確認に委ね、ここではパイプラインが壊れていないことを担保する。

### 非機能要件
- 既定（環境変数未設定）の `pytest` はモデル DL 不要のまま（実変換テストは skip）。
- reportlab はサンプル生成スクリプトの依存（実行時/テスト本体には不要）。

## 4. 設計

### 質問（`app/questions.py`）
- `do_table_structure` の質問の後に `table_mode`（type=choice, accurate/fast,
  既定 accurate）を追加。`apply_answers` は既に `table_mode` を取り込む。

### API（`app/main.py`）
- ワンショット/バッチに `table_mode: TableMode = Query(default=TableMode.accurate)` を
  追加し、`apply_answers` に渡す。

### サンプル（`samples/`, `scripts/make_sample_pdfs.py`）
- `make_sample_pdfs.py`: reportlab で表入り PDF を `samples/table_sample.pdf` に生成。
- サンプル PDF はリポジトリに同梱（小さなバイナリ）。

### テスト（`tests/test_quality.py`）
- `PDFTO_RUN_DOCLING_TESTS` 未設定なら `pytest.skip`。
- 設定時、`convert(samples/table_sample.pdf, accurate)` の Markdown に
  `|` と `Widget`/`Gadget` 等が含まれることを確認。

### 影響範囲
- 変更: `app/questions.py`, `app/main.py`,
  `tests/test_questions.py` / `test_api.py`, `README.md`, `docs/roadmap.md`。
- 追加: `samples/table_sample.pdf`, `scripts/make_sample_pdfs.py`,
  `tests/test_quality.py`。

## 5. 受け入れ条件（Definition of Done）

- [ ] 対話の質問に `table_mode`（accurate/fast, 既定 accurate）が含まれる。
- [ ] ワンショット/バッチで `table_mode` を受け付ける。
- [ ] `samples/table_sample.pdf` が同梱され、スクリプトで再生成できる。
- [ ] `PDFTO_RUN_DOCLING_TESTS=1` で実変換テストが成功し非空出力を返す。未設定では skip。
- [ ] 既定の `pytest` がモデル DL 無しで通る。

## 6. テスト計画

- `build_questions` に `table_mode`（type=choice, default accurate）が含まれる。
- API: ワンショット `?table_mode=fast`、バッチ `?table_mode=accurate` が受理される。
- `tests/test_quality.py`（opt-in）: サンプルの実変換が成功し非空出力を返す。
- 既定 `pytest`：実変換テストは skip され、他は通る。

## 7. リスク・代替案

- **サンプルの表検出が環境/モデル更新で揺れる。** 主要セルの存在のみ確認し、厳密一致は
  避ける。テストは opt-in なので CI を不安定化させない。
- **reportlab 依存。** 生成スクリプト限定（同梱 PDF があれば再生成不要）。
- **代替: 合成 PDF をテスト時に毎回生成。** モデル DL に加え生成依存も増えるため、
  サンプルを同梱して固定する。

## 8. 未決事項

- `table_mode` 既定は `accurate`（品質優先）。速度優先は明示指定で `fast`。
