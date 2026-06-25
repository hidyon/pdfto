# Spec: 品質測定の土台（回帰サンプル＋指標＋A/B 比較）

- **ID:** 0030
- **状態:** done
- **マイルストーン:** M10 変換品質の向上
- **関連 issue:** M10-2（品質測定の土台）
- **作成日 / 更新日:** 2026-06-25 / 2026-06-25

## 1. 背景・目的

M10-1 で精度ノブ（cell matching / full-page OCR / 画像解像度）を追加したが、
「ノブを変えて**本当に良くなったか**」を数値で示す仕組みが無い。品質指標は現状
`tests/test_quality.py` の各テスト内にベタ書き（Markdown 表のパース・セル回収率の計算）
で、再利用も A/B 比較もできない。

本 issue では **品質測定の土台**を用意する。

- 再利用可能な**指標関数**（表のセル回収率・形状・テキスト語句の回収率）を分離する。
- 回帰用の**評価ケース登録簿**（サンプル + 期待値 + 適用する指標）を作る。
- ノブ設定（バリアント）を切り替えて同一サンプルを変換し、**指標を並べて比較（A/B）**
  できるランナーを用意する。
- 指標関数は**既定 `pytest`（モック・docling 不要）でテスト**し、測定コード自体の回帰を防ぐ。

これにより M10-1 の効果検証や、今後の M10-3/M10-4（LLM 補正・VLM）の改善も
同じ土台で A/B できる。

## 2. スコープ

### やること
- 新パッケージ `eval/`（dev/評価専用。アプリ実行時には import されない）:
  - `eval/metrics.py` — 依存ゼロの純粋な指標関数（出力文字列＋期待値 → スコア）。
  - `eval/cases.py` — 評価ケースの登録簿（サンプル・出力形式・期待値・スコアラ）。
  - `eval/report.py` — バリアント（ノブ設定）× ケースを実変換して指標表を出力し、
    2 バリアントの**差分（A/B）**を表示する CLI／関数。
- 既定テスト `tests/test_quality_metrics.py` — 指標関数とケース登録簿の整合をモックで検証。
- `tests/test_quality.py` を `eval.metrics` 利用へリファクタ（指標ロジックの重複排除）。
  opt-in（`PDFTO_RUN_DOCLING_TESTS=1`）の挙動は維持し、A/B ランナーの opt-in スモークを 1 本追加。
- 回帰サンプルを 1 つ拡張：本文テキストの忠実度を測る `samples/prose_sample.pdf`
  （既知の語句を含む散文ページ。`scripts/make_sample_pdfs.py` に生成器を追加）。
- 使い方を README に追記。

### やらないこと（非スコープ）
- アプリ実行時（`app/*`）のコード変更（指標は eval 専用で、API には載せない）。
- CI 構築（実変換は引き続き手動/専用環境。既定テストはモックのまま）。
- LLM/VLM の品質改善そのもの（M10-3 / M10-4）。本 issue は測定の土台のみ。
- 厳密な編集距離や BLEU などの重い指標（必要になったら別 issue）。

## 3. 要件

### 機能要件
- `eval/metrics.py`：
  - `parse_markdown_table(md) -> list[list[str]]`（空白正規化・区切り行除去）。
  - `table_cell_recovery(md, expected_rows) -> float`（0..1。期待セルの一致率）。
  - `table_shape(md) -> tuple[rows, cols]`（先頭表の行数・列数。列数は最頻値）。
  - `token_recall(text, tokens) -> float`（大文字小文字無視で語句の出現率 0..1）。
  - すべて純粋関数（docling/app に非依存。入力は文字列）。
- `eval/cases.py`：
  - `EvalCase(name, sample, output_format, options, score)` を列挙。
    `score(content) -> dict[str, float]` がそのケースの指標を返す。
  - 既存 3 サンプル（table_doc=セル回収率、scanned=OCR 語句回収率、prose=語句回収率）を登録。
- `eval/report.py`：
  - `VARIANTS`：名前付きのノブ上書き（例 `baseline` / `no_cell_match` /
    `force_ocr` / `high_res`）。
  - `run(cases, variants) -> 結果` と、指標表・A/B 差分を標準出力に整形する CLI
    （`python -m eval.report [--variants a,b] [--cases ...]`）。実変換するため**手動実行**前提。
- 既定 `pytest`：`tests/test_quality_metrics.py` が指標関数とケース登録簿を**docling 無し**で検証。
  既存の opt-in テストはフラグ無しで skip のまま。

### 非機能要件
- `eval/metrics.py` は標準ライブラリのみ（テストでモデル DL 不要）。
- A/B ランナーの実変換部は opt-in（CLI 実行 or `PDFTO_RUN_DOCLING_TESTS=1` のスモーク 1 本）。
- 既定テスト合計は増えるが、すべてモックで高速のまま。

## 4. 設計

### `eval/` パッケージ
```
eval/
  __init__.py
  metrics.py   純粋な指標関数（依存ゼロ）
  cases.py     EvalCase 登録簿（app.models のみ参照。convert は呼ばない）
  report.py    バリアント×ケースを実変換し指標表/A-B 差分を出力（app.converter を遅延 import）
```
- 依存方向は eval → app（評価ツールがアプリに依存）であり、アプリは eval に依存しない。
  コアの独立性は保たれる。
- `EvalCase.score` は `eval.metrics` のみ使用。`cases.py` は import 時に docling を引かない。

### 指標の定義（最小・解釈しやすいもの）
- **table_cell_recovery**：期待表の全セル数に対し、同位置・同値で一致したセルの割合。
- **table_shape**：`(rows, cols)`。期待形状との一致は呼び出し側で判定。
- **token_recall**：期待語句のうち本文（小文字化）に部分一致した割合。OCR・本文忠実度に使う。

### バリアント（A/B の例）
| 名前 | 上書き | 狙い |
|---|---|---|
| baseline | （既定） | 基準 |
| no_cell_match | `do_cell_matching=False` | セルマッチングの寄与を見る |
| high_res | `image_scale=4.0` | 解像度の寄与を見る |
| force_ocr | `force_full_page_ocr=True` | フルページ OCR の寄与を見る |

`report.py` は選んだバリアントで各ケースを変換し、`ケース×指標` の表と、
`--compare base other` 指定時に指標差分（other − base）を表示する。

### 回帰サンプル拡張：`prose_sample.pdf`
- A4 1 ページに既知の散文（固有語を含む数文）を配置。`token_recall` で本文忠実度を測る。
- 生成は `scripts/make_sample_pdfs.py::make_prose_sample` を追加（reportlab、生成物はコミット）。

### 影響範囲
- 追加：`eval/__init__.py`, `eval/metrics.py`, `eval/cases.py`, `eval/report.py`,
  `tests/test_quality_metrics.py`, `samples/prose_sample.pdf`。
- 変更：`tests/test_quality.py`（指標を `eval.metrics` から import、A/B スモーク追加）、
  `scripts/make_sample_pdfs.py`、`README.md`、`docs/roadmap.md`。
- アプリ本体・既定 API は不変。

## 5. 受け入れ条件（Definition of Done）

- [x] `eval/metrics.py` に純粋な指標関数があり、既定 `pytest` でテストされる。
- [x] `eval/cases.py` に既存 3（table_doc/scanned）+ prose の評価ケースが登録され、登録簿の整合をテストで検証。
- [x] `eval/report.py` でバリアント（ノブ）×ケースの指標表と A/B 差分を出力できる（CLI/関数・モックで配線検証）。
- [x] `tests/test_quality.py` が `eval.metrics` を再利用（重複排除）し、opt-in 挙動を維持。
- [x] `samples/prose_sample.pdf` を追加し、token_recall ケースとして登録（テキスト層 recall 1.0 を確認）。
- [x] 既定 `pytest` が通る（134 passed / 14 skipped。新規はすべてモック・高速）。使い方を README に記載。

## 6. テスト計画

- 既定 `python -m pytest`：`test_quality_metrics.py`（指標・登録簿）が通り、opt-in は skip のまま。
- `PDFTO_RUN_DOCLING_TESTS=1 python -m pytest tests/test_quality.py`：
  実変換の回帰＋ A/B スモーク（baseline で table_doc のセル回収率 1.0）。
- 手動：`python -m eval.report --variants baseline,force_ocr --compare baseline force_ocr`
  でノブの効果を数値で確認。

## 7. リスク・代替案

- **`eval` がパッケージ名として builtin `eval()` と紛らわしい**：パッケージ import
  （`from eval.metrics import ...`）は builtin を壊さない。明快さ優先で採用。
- **docling のモデル差で実スコアが揺れる**：既定テストはモックの純粋指標のみ。実変換の
  スコアは「形状/閾値」で見て厳密一致を避ける（spec 0012/0024 の知見）。
- **代替：指標を test 内に据え置く**：再利用・A/B ができないため土台として分離する。

## 8. 未決事項

- 追加指標（編集距離・表の行/列単位 F1 など）は必要になった時点で別 issue。
- バリアントの既定セットは最小限。ケース/バリアントは登録簿に足すだけで拡張できる。
