# Spec: OCR 信頼度しきい値の公開（実写スキャンの recall 改善）

- **ID:** 0031
- **状態:** done
- **マイルストーン:** M10 変換品質の向上
- **関連 issue:** M10-5（OCR recall 改善）
- **作成日 / 更新日:** 2026-06-25 / 2026-06-25

## 1. 背景・目的

M10-2 の限界探索（spec 0030 §9 追補2）で、実写スキャン領収書（ICDAR SROIE）の
語句回収率が **0.33** に留まることが判明した。原因を切り分けたところ、**OCR の実力不足では
なく docling の既定設定**だった：

- docling/EasyOCR は既定で `confidence_threshold=0.5`。ノイズの多い写真スキャンでは
  **正しい読みも信頼度 0.5 未満**になり破棄される。
- 同じ画像を **EasyOCR で素に呼ぶと recall 0.83**、docling 経由（既定）では 0.33。
- docling の `confidence_threshold` を下げるだけで改善（実測）：

  | confidence_threshold | recall |
  |---|---|
  | 0.5（既定） | 0.42 |
  | 0.3 | 0.75 |
  | 0.1 | **0.92** |

そこで **OCR 信頼度しきい値を変換オプションとして公開**し、ノイズスキャンで recall を
取り戻せるようにする。LLM もモデル変更も不要で、ROI が最も高い。

## 2. スコープ

### やること
- `ConversionOptions` に `ocr_confidence_threshold: Optional[float]`（0.0–1.0）を追加。
  既定 `None`＝docling の既定（0.5）を維持し、**現挙動は不変**。
- converter で、値が指定された時に EasyOCR 経路の `confidence_threshold` へ反映する。
- 対話質問（スキャン/画像/フルページ OCR 時）と one-shot API クエリから指定できるようにする。
- 評価ランナーに `low_conf`（threshold=0.1）バリアントを追加し、外部ケースで効果を A/B できる。
- README にノブの意味と副作用（低くすると recall↑だが誤検出↑）を明記。

### やらないこと（非スコープ）
- 画像前処理（denoise/二値化/拡大）パイプライン（別 issue。本 issue と相補的）。
- OCR エンジンの切替（RapidOCR/Tesseract は本環境で不可）。
- LLM 後補正（M10-3）・VLM（M10-4）。
- 精度（precision）指標の追加（recall のみ。precision は将来 issue で検討）。

## 3. 要件

### 機能要件
- `ocr_confidence_threshold` 未指定（None）時、converter の挙動は従来どおり
  （docling 既定 OCR、しきい値 0.5）。回帰なし。
- 指定時、`do_ocr=True` なら EasyOCR を明示構築し `confidence_threshold` を渡す。
  言語・force_full_page_ocr が未指定でも、しきい値指定だけで EasyOCR 経路に入る。
- 範囲外（<0 または >1）は Pydantic バリデーションで弾く。
- one-shot API（`/api/v1/convert`）のクエリと対話質問の双方から設定できる。

### 非機能要件
- 既定 `pytest`（モック）で配線・既定不変を検証。実変換は opt-in。
- `_get_converter` のキャッシュキーにしきい値を含める（設定違いで別コンバータになる）。

## 4. 設計

### `app/models.py`
```python
ocr_confidence_threshold: Optional[float] = Field(
    default=None, ge=0.0, le=1.0,
    description="OCR 採用信頼度の下限（EasyOCR）。低いほど recall↑/誤検出↑。"
                "未指定はエンジン既定(0.5)。ノイズの多いスキャンで有効。")
```

### `app/converter.py`
- `_get_converter(...)` に `ocr_confidence_threshold: Optional[float] = None` を追加。
- EasyOCR を明示構築する条件を
  `do_ocr and (ocr_languages or force_full_page_ocr or ocr_confidence_threshold is not None)`
  に拡張。構築時 `EasyOcrOptions(..., )` の `confidence_threshold` を設定。
- `convert()` から `options.ocr_confidence_threshold` を渡す。

### `app/questions.py`
- スキャン/画像（または force_full_page_ocr 相当）の文脈で「OCR をどれだけ強気に拾うか」を
  問う質問を追加し、回答を `ocr_confidence_threshold` にマップ（例：標準=None / 強気=0.2 /
  最大=0.1）。`apply_answers` で反映。

### `app/main.py`
- one-shot 変換のクエリパラメータに `ocr_confidence_threshold` を追加。

### `eval/report.py`
- `VARIANTS` に `low_conf`（`ocr_confidence_threshold=0.1`）を追加。

### 影響範囲
- 変更：`app/models.py`, `app/converter.py`, `app/questions.py`, `app/main.py`,
  `eval/report.py`, `README.md`, `docs/roadmap.md`, テスト。
- 既定挙動・既存 API 後方互換は維持。

## 5. 受け入れ条件（Definition of Done）

- [x] `ocr_confidence_threshold` が `ConversionOptions` にあり、既定 None で現挙動維持。
- [x] converter に配線され、指定時のみ EasyOCR の `confidence_threshold` に反映
      （DocumentConverter をスタブし EasyOcrOptions を実物で検証）。
- [x] 範囲外がバリデーションで弾かれる（ge=0/le=1）。
- [x] one-shot API（クエリ）と対話質問（OCR 強さプリセット）から指定できる。
- [x] `eval/report.py` に `low_conf`（threshold=0.1）バリアントがあり、外部ケースで A/B できる。
- [x] 既定 `pytest` が通る。実変換で SROIE 領収書の recall 改善を確認（§9 参照）。
- [x] README に意味・副作用を記載。

## 9. 実装メモ（検証で判明した重要バグと修正）

検証中に **画像入力ではこの OCR ノブ（および従来からの `ocr_languages` /
`force_full_page_ocr`）が一切効かない**ことが判明した。`_get_converter` は
`format_options` に **`InputFormat.PDF` だけ**を登録しており、画像入力（jpg/png/…）は
docling の既定パイプライン（既定 OCR=RapidOCR、threshold 0.5）にフォールバックして
**こちらの pipeline_options を無視**していた。

**修正:** `InputFormat.IMAGE` にも同じ `pipeline_options` を `ImageFormatOption` で登録。
これで OCR 言語・full-page・confidence が画像入力にも適用される（PDF 入力は不変）。

修正後、SROIE 領収書（実写スキャン、正解 12 トークン）を **app の `convert()` 経由**で実測：

| 設定 | recall |
|---|---|
| 既定（do_ocr のみ＝RapidOCR） | 0.333 |
| `force_full_page_ocr` のみ（EasyOCR 切替） | 0.417 |
| **`ocr_confidence_threshold=0.1` のみ** | **0.917** |
| force + threshold=0.5 | 0.417 |
| force + threshold=0.1 | 0.917 |

**結論:** (1) 画像入力にオプションが届くようになったこと（バグ修正）と、(2) **confidence を
下げること**が支配的に効く（0.333→0.917）。full-page OCR は単独では限定的（0.417）。
画像入力では force すら不要で、しきい値だけで回収できる。`eval` の `low_conf`
（threshold=0.1）バリアントもこの値を再現する。

### 一般化の検証（実写スキャン 6 枚で横断 A/B）

1 枚では偶然の可能性があるため、SROIE 領収書を **6 枚（000–005）** に拡張し、各 receipt の
正解（key.json）から token を自動生成して横断で `baseline` vs `low_conf`(threshold=0.1) を実測：

| receipt | baseline | low_conf | Δ |
|---|---|---|---|
| sroie_000 | 0.333 | 0.917 | +0.583 |
| sroie_001 | 0.077 | 0.923 | +0.846 |
| sroie_002 | 0.526 | 1.000 | +0.474 |
| sroie_003 | 0.364 | 0.818 | +0.455 |
| sroie_004 | 0.167 | 0.333 | +0.167 |
| sroie_005 | 0.818 | 0.818 | +0.000 |
| **平均** | **0.38** | **0.80** | **+0.42** |

**所見:** confidence を下げる改善は**一般化する**——平均で 0.38→0.80、**6 枚中 5 枚で改善・
悪化ゼロ**（005 は既に baseline 0.818 で頭打ち、害なし）。残る弱点は sroie_004（0.33）の
ような特に劣化の激しい個体で、ここは次手（画像前処理 / LLM 補正 / VLM）の対象。
再現: `python scripts/fetch_external_samples.py` →
`PDFTO_RUN_DOCLING_TESTS=1 python -m eval.report --include-external --compare baseline low_conf`。

## 6. テスト計画

- 既定 `pytest`：
  - 未指定で `_get_converter` に従来どおりの引数（EasyOCR を明示構築しない）。
  - 指定で EasyOCR が構築され `confidence_threshold` が渡る（モックで kwargs 検証）。
  - 範囲外で `ValidationError`。
  - 質問→`apply_answers`→オプション、one-shot クエリのマッピング。
- opt-in（`PDFTO_RUN_DOCLING_TESTS=1`）＋外部サンプル：
  `python -m eval.report --include-external --cases sroie_receipt --compare baseline low_conf`
  で recall が大きく改善することを確認。

## 7. リスク・代替案

- **低しきい値で誤検出（precision 低下）**：既定は据え置き（None=0.5）、明示時のみ下げる。
  プリセットで「強気」を選ばせ、無闇に下げない。precision 指標は将来 issue。
- **EasyOCR 明示構築への切替差異**：既に languages/force で同じ経路に入る実績があり、
  しきい値指定時も同様。未指定時は一切変えない。
- **代替：前処理だけで対応**：前処理も有効（別 issue）だが、しきい値公開が最小変更で最大効果。

## 8. 未決事項

- 質問のプリセット値（強気=0.2 / 最大=0.1）は実測に合わせて調整可。
- precision とのトレードオフの可視化（recall/precision 両指標）は別 issue で検討。
