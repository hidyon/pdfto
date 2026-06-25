# Spec: 変換の精度ノブを拡充

- **ID:** 0029
- **状態:** done
- **マイルストーン:** M10 変換品質の向上
- **関連 issue:** M10-1（精度ノブの拡充）
- **作成日 / 更新日:** 2026-06-24 / 2026-06-24

## 1. 背景・目的

現在公開している変換オプションは OCR ON/OFF・言語・表復元・表モード・画像モード・ページ範囲
のみ。docling にはさらに品質に効くノブがあり（実環境で確認済み）、これらを公開して品質を
上げられるようにする。後方互換（既定値で現挙動維持）を保つ。

確認した docling のフィールド：
- `TableStructureOptions.do_cell_matching`（表セルの対応付け）
- `EasyOcrOptions.force_full_page_ocr`（全ページ強制 OCR）
- `PdfPipelineOptions.images_scale`（描画解像度 = 抽出画像の解像度）

## 2. スコープ

### やること
- `ConversionOptions` に 3 ノブを追加（既定は現挙動）：
  - `do_cell_matching: bool = True`
  - `force_full_page_ocr: bool = False`
  - `image_scale: float = 2.0`
- converter に配線（PDF パイプライン）。`force_full_page_ocr` は EasyOCR 経路で有効化。
- 対話質問に `force_full_page_ocr` を追加（OCR 文脈・PDF/画像のみ）。`do_cell_matching` /
  `image_scale` は API オプション（高度設定）として公開（質問 UI には出さない）。
- one-shot API（`/api/v1/convert`）にもクエリで 3 ノブを追加。

### やらないこと（非スコープ）
- 高精度 VLM パイプライン（=M10-4）、LLM 補正（=M10-3）、品質測定（=M10-2）。
- 数式/コード/図リッチ化など他の docling 機能。

## 3. 要件

### 機能要件
- `do_cell_matching` が表構造復元時に `table_structure_options.do_cell_matching` に渡る。
- `force_full_page_ocr` が True のとき、OCR を EasyOCR で全ページ強制実行する
  （言語未指定なら既定 `["en"]`）。False（既定）かつ言語未指定なら**従来どおり**
  docling 既定 OCR（挙動不変）。
- `image_scale` が `PdfPipelineOptions.images_scale` に渡る（既定 2.0＝現状維持）。
- 既存の PDF/OCR/表テストが不変。

### 非機能要件
- 既定値で現挙動を完全維持（回帰なし）。`image_scale` は 1.0–4.0 に制限。
- コアは Web 非依存のまま。

## 4. 設計

### `app/models.py`（`ConversionOptions`）
- 追加: `do_cell_matching: bool = True`、`force_full_page_ocr: bool = False`、
  `image_scale: float = Field(2.0, ge=1.0, le=4.0)`。

### `app/converter.py`
- `_get_converter(...)` に `do_cell_matching`, `force_full_page_ocr`, `image_scale` を追加。
  - 表: `do_table_structure` 時に `table_structure_options.do_cell_matching = do_cell_matching`。
  - OCR: `need_easyocr = do_ocr and (ocr_languages or force_full_page_ocr)`。
    True のとき `EasyOcrOptions(lang=list(ocr_languages) or ["en"],
    force_full_page_ocr=force_full_page_ocr)`（オフラインモデル設定は従来どおり）。
    それ以外は従来（docling 既定 OCR）。
  - `pipeline_options.images_scale = image_scale`（常に設定。生成画像時は従来どおり
    `generate_picture_images=True`）。
- `convert()` から新オプションを渡す。

### `app/questions.py`
- PDF/画像のとき、OCR 質問群に `force_full_page_ocr`（boolean・既定 False・
  「テキスト層を無視して全ページ OCR。ハイブリッド PDF の取りこぼし対策」）を追加。

### `app/questions.py::apply_answers`
- パススルーキーに `force_full_page_ocr`・`do_cell_matching` を追加。
  `image_scale` は数値として受理（あれば `float`）。

### `app/main.py`（one-shot）
- `/api/v1/convert` のクエリに `force_full_page_ocr: bool=False`、
  `do_cell_matching: bool=True`、`image_scale: float=2.0` を追加し answers に載せる。

### 影響範囲
- 変更: `app/models.py`, `app/converter.py`, `app/questions.py`, `app/main.py`,
  `README.md`（オプション表）, `docs/roadmap.md`。テスト追加。

## 5. 受け入れ条件（Definition of Done）

- [x] 3 ノブが `ConversionOptions` にあり、既定で現挙動を維持。
- [x] converter に正しく配線される（モックで kwargs を検証）。
- [x] `force_full_page_ocr=True` で EasyOCR 経路（言語既定 en）になる／False＋言語なしは従来経路。
- [x] one-shot API と対話質問から指定できる。
- [x] 既定 `pytest` が通る（実変換でも検証: 表抽出 OK・full-page OCR で text 復元）。

## 6. テスト計画

- 既定 `python -m pytest`（converter は `_get_converter` をモックして kwargs 検証）：
  - `do_cell_matching` / `image_scale` / `force_full_page_ocr` が `_get_converter` に渡る。
  - `force_full_page_ocr=True` 時、`apply_answers`→`ConversionOptions` に反映。
  - 既定値（cell_matching=True, force=False, scale=2.0）。
- 既存の OCR・表・API テストが不変。
- 実効果の検証（品質が上がるか）は M10-2 の指標で扱う。

## 7. リスク・代替案

- **force_full_page_ocr の engine 既定変更**：言語なしで force を有効化すると EasyOCR(en) に
  なる。False 既定では従来経路を保持するため回帰なし。挙動は README に明記。
- **image_scale を上げると重くなる**：上限 4.0、既定 2.0。
- **代替: 全ノブを質問 UI に出す**：UX が煩雑になるため、高度ノブは API 専用にする。

## 8. 未決事項

- どのノブを既定 ON にするか（品質 vs 速度）は M10-2 の測定後に再検討。
