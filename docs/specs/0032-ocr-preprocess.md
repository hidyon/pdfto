# Spec: OCR 前の画像前処理（denoise / 二値化 / 拡大）

- **ID:** 0032
- **状態:** done
- **マイルストーン:** M10 変換品質の向上
- **関連 issue:** M10-6（OCR 前の画像前処理）
- **作成日 / 更新日:** 2026-06-25 / 2026-06-25

## 1. 背景・目的

M10-5（confidence しきい値）で実写スキャンの recall が平均 0.38→0.80 に改善したが、
特に劣化の激しい個体（例 sroie_004=0.33）は依然弱い。検証の予備実験では、画像を
**OpenCV で前処理**（グレースケール→2倍拡大→ノイズ除去→適応的二値化）してから OCR すると、
EasyOCR 直呼びで 0.83→0.92 の上積みが得られた（spec 0031 §9 周辺の調査）。

そこで **OCR 前の画像前処理**を任意機能として追加し、confidence ノブと**相補的に**
recall をさらに押し上げられるようにする。効果は M10-2 の土台（実写 6 枚）で A/B 検証する。

## 2. スコープ

### やること
- 画像入力（jpg/png/tiff/…）に対し、OCR 前に前処理を施すオプション
  `ocr_preprocess: bool`（既定 False）を追加。
- 前処理は純粋関数として `app/preprocess.py` に分離（OpenCV を遅延 import、docling 非依存）。
  既定パイプライン：グレースケール→2倍拡大(cubic)→fastNlMeans ノイズ除去→
  Gaussian 適応的二値化。
- converter は、画像入力かつ `do_ocr` かつ `ocr_preprocess` のとき、前処理済みの一時画像を
  生成して docling に渡す（元ファイルは変更しない）。
- one-shot API クエリと対話質問（スキャン/画像文脈）から指定できる。
- 評価ランナーに `preprocess` / `pp_low_conf`（前処理＋threshold0.1）バリアントを追加。
- 実写 6 枚で `low_conf` 単独と `pp_low_conf` を A/B し、結果を spec に記録。README に使い方。

### やらないこと（非スコープ）
- PDF 入力の前処理（docling が内部でラスタライズするため対象外。画像入力のみ）。
- 前処理パラメータの細粒度な公開（block size 等）。まず固定の良プリセット 1 本。
- 傾き補正（deskew）の高度化や OCR エンジン切替（別 issue）。
- LLM 補正（M10-3）・VLM（M10-4）。

## 3. 要件

### 機能要件
- `ocr_preprocess=False`（既定）時、挙動は完全に従来どおり（回帰なし）。
- `True` かつ入力が画像かつ `do_ocr=True` のとき、前処理済み画像で OCR する。
- 入力が画像でない（PDF/Office/…）場合、`ocr_preprocess` は**無視**（no-op）。
- `do_ocr=False` のときは前処理しない（OCR しないので無意味）。
- OpenCV 未導入の環境で `ocr_preprocess=True` を要求したら、`ConversionError` で
  分かりやすく失敗（既定では import しないので通常運用に影響なし）。
- one-shot API と対話質問から設定できる。

### 非機能要件
- `app/preprocess.py` は cv2/numpy を遅延 import。既定テストはモック/小さな合成画像で
  検証し、docling もモデル DL も不要。
- 前処理済み一時ファイルは変換後に確実に削除する。

## 4. 設計

### `app/preprocess.py`（新規）
```python
def preprocess_image_for_ocr(src: Path, dst_dir: Path) -> Path:
    """Denoise + binarize + upscale a scanned image to aid OCR.

    Returns the path to a new image in *dst_dir*; never mutates *src*.
    """
    import cv2  # lazy; only needed when preprocessing is requested
    img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ConversionError(f"could not read image for preprocessing: {src}")
    up = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    den = cv2.fastNlMeansDenoising(up, h=10)
    th = cv2.adaptiveThreshold(den, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 11)
    out = dst_dir / (src.stem + "_pp.png")
    cv2.imwrite(str(out), th)
    return out
```
（`ConversionError` は循環 import を避けるため `app.preprocess` 内で再定義せず、
converter 側で例外を正規化するか、軽量に共有する。実装時に最小構成を選ぶ。）

### `app/converter.py`
- `convert()` で、`kind_of(extension_of(name)) == "image"` かつ `do_ocr` かつ
  `ocr_preprocess` の場合、`tempfile.TemporaryDirectory` に前処理画像を作り、
  その path を docling に渡す。`finally` で temp を破棄。

### `app/models.py`
```python
ocr_preprocess: bool = Field(
    default=False,
    description="Preprocess image inputs (denoise/binarize/upscale) before OCR. "
                "Improves noisy/photographed scans; ignored for non-image inputs.")
```

### `app/questions.py` / `app/main.py` / `eval/report.py`
- 質問 `ocr_preprocess`（boolean, 既定 False, スキャン/画像文脈）。`apply_answers` で反映。
- one-shot クエリ `ocr_preprocess: bool`。
- `VARIANTS` に `preprocess`（ocr_preprocess=True）と
  `pp_low_conf`（ocr_preprocess=True, ocr_confidence_threshold=0.1）。

### 影響範囲
- 追加：`app/preprocess.py`、テスト。
- 変更：`app/models.py`, `app/converter.py`, `app/questions.py`, `app/main.py`,
  `eval/report.py`, `README.md`, `docs/roadmap.md`。
- 既定挙動・既存 API 後方互換は維持。

## 5. 受け入れ条件（Definition of Done）

- [x] `ocr_preprocess` が `ConversionOptions` にあり、既定 False で現挙動維持。
- [x] `app/preprocess.py` の前処理関数が小さな合成画像でテストされる（実 cv2・モデル DL 不要）。
- [x] converter が「画像＋do_ocr＋ocr_preprocess」のときだけ前処理画像を docling に渡す
      （モックで検証）。非画像・OCR 無効では前処理しない。
- [x] one-shot API と対話質問から指定できる。
- [x] `eval/report.py` に `preprocess` / `pp_low_conf` バリアントがある。
- [x] 既定 `pytest` 156 passed。実写 6 枚で `low_conf` vs `pp_low_conf` を A/B し記録（§9）。
- [x] README に使い方・適用範囲（画像入力のみ）と negative result を記載。

## 6. テスト計画

- 既定 `pytest`：
  - `preprocess_image_for_ocr`：合成画像→出力が存在し、サイズが拡大・二値（0/255）である。
  - converter：画像入力＋ocr_preprocess で docling に渡る path が前処理ファイル（mock）。
    非画像、または ocr_preprocess False、または do_ocr False では元 path のまま。
  - 質問→`apply_answers`、one-shot クエリのマッピング。
- opt-in＋外部 6 枚：
  `PDFTO_RUN_DOCLING_TESTS=1 python -m eval.report --include-external --compare low_conf pp_low_conf`
  で recall の上積み（特に弱い個体）を確認。

## 7. リスク・代替案

- **二値化が一部画像で逆効果**：効果は画像依存。A/B で平均と個体差を確認し、
  既定 False の任意機能に留める。悪化する個体があっても既定は安全。
- **OpenCV 依存**：遅延 import＋既定 False。未導入環境では明示要求時のみ失敗。
- **代替：docling 側の前処理に委ねる**：細かな制御ができず、実測の上積みも取りこぼすため、
  入口で軽量に前処理する方式を採る。

## 8. 未決事項

- プリセットのパラメータ（h, blockSize, C, 拡大率）は実測で微調整可。
- 将来、deskew や複数プリセットを足す場合は別 issue で（本 issue は固定 1 本）。

## 9. 実測と結論（重要：前処理は一般化しなかった）

実写 6 枚で `low_conf`（threshold=0.1）に前処理を**上乗せ**して A/B した結果、
**前処理は平均で recall を下げた**。二値化あり（本実装）・なし（gentle: 拡大＋denoise のみ）の
両プリセットを検証：

| receipt | low_conf | +二値化前処理 | +gentle前処理 |
|---|---|---|---|
| sroie_000 | 0.917 | 1.000 | 0.833 |
| sroie_001 | 0.923 | 0.692 | 0.769 |
| sroie_002 | 1.000 | 0.895 | 0.842 |
| sroie_003 | 0.818 | 0.909 | 0.545 |
| sroie_004 | 0.333 | 0.222 | 0.167 |
| sroie_005 | 0.818 | 0.818 | 0.909 |
| **平均** | **0.80** | 0.76 | 0.68 |

**所見:**
- どちらのプリセットも**平均では low_conf 単独に劣る**（0.80 → 0.76 / 0.68）。
- 弱点 sroie_004 を**救えない**（むしろ悪化）。個体では有効な例（000 の二値化→1.0、
  005 の gentle→0.909）もあるが、**汎用的な改善にはならない**。
- 予備実験で 000 が 0.83→0.92 に伸びたのは、confidence を下げる前の EasyOCR 直呼びでの話。
  confidence を既に下げた状態では、前処理が文字情報を削って逆効果になりやすい。

**結論:** 前処理は**既定 OFF の任意ツール**として残す（特定画像では有効・eval で個別に
A/B 可能）が、**推奨ノブは引き続き M10-5 の confidence しきい値**。前処理は既定では使わない。
この negative result 自体が M10-2 の測定土台の価値（効くと思った施策を数値で棄却できる）を示す。
