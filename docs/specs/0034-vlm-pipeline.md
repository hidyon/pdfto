# Spec: 高精度 VLM パイプライン（use_vlm・ローカル/API）

- **ID:** 0034
- **状態:** done
- **マイルストーン:** M11 高精度 VLM パイプライン
- **関連 issue:** M11-1（VLM パイプライン統合）
- **作成日 / 更新日:** 2026-06-25 / 2026-06-25

## 1. 背景・目的

M10 で OCR recall（confidence しきい値）を改善し実写スキャンを 0.38→0.80 まで引き上げたが、
sroie_004 のような激しい劣化や、複雑フォームの**表構造**（IRS 1040 は table_blocks=0）は
従来の OCR＋レイアウト解析パイプラインの限界として残った。

docling は **VLM パイプライン**（`VlmPipeline`）を備え、ページ画像から VLM が直接
DococlingDocument（構造つき）を生成できる。OCR・レイアウト・表検出を 1 つのモデルが担うため、
劣化スキャンや複雑レイアウトに強い可能性がある。本 issue では、これを **opt-in** で選べる
ようにする。

## 2. スコープ

### やること
- `ConversionOptions.use_vlm: bool`（既定 False）を追加。True で VLM パイプラインを使う。
- converter に VLM 用のコンバータ構築を追加（`VlmPipeline` ＋ `VlmPipelineOptions`）。
  - **ローカル VLM**：transformers のモデル仕様（既定 GraniteDocling-258M）。`PDFTO_VLM_MODEL`
    で許可リストから選択。
  - **API VLM**：`PDFTO_VLM_API_URL` 設定時は OpenAI 互換エンドポイントへ（`ApiVlmOptions`、
    `enable_remote_services=True`、鍵は `PDFTO_VLM_API_KEY`、モデルは `PDFTO_VLM_API_MODEL`）。
- VLM 時は OCR/表/前処理ノブは無視（VLM が end-to-end で担う）。ページ範囲は PDF で有効のまま。
- 設定を `app/config.py`（`PDFTO_VLM_*`）に集約。
- one-shot API クエリ・対話質問から `use_vlm` を指定できる。
- 既定 `pytest`（モック）で配線を検証。実 VLM は専用フラグ `PDFTO_RUN_VLM_TESTS=1` の
  opt-in テスト（重いモデル DL を通常の docling テストから分離）。README に記載。

### やらないこと（非スコープ）
- VLM の精度を eval 土台で自動 A/B（モデル DL が重く本環境で常用不可。手動/専用環境に委譲）。
- MLX/vLLM バックエンド（本環境に無い）。まず transformers と API の 2 経路。
- 画像説明・チャート抽出など VLM の付随機能（将来 issue）。
- VLM 専用の出力後処理（既存の `_export` をそのまま使う）。

## 3. 要件

### 機能要件
- `use_vlm=False`（既定）時、挙動は完全に従来どおり（回帰なし）。
- `use_vlm=True` 時：
  - `PDFTO_VLM_API_URL` 未設定 → ローカル VLM（`PDFTO_VLM_MODEL`、既定 `granite_docling`）。
  - 設定済み → API VLM（`enable_remote_services=True`、`Authorization: Bearer <key>`）。
- VLM コンバータは PDF と画像入力の両方に適用（`InputFormat.PDF` / `IMAGE`）。
- 未知の `PDFTO_VLM_MODEL` は `ConversionError` で分かりやすく失敗。
- docling/transformers 未導入時は `ConversionError`（既定では import しない）。
- one-shot API・対話質問から設定でき、`apply_answers` がマップする。

### 非機能要件
- VLM 関連 import は `_get_vlm_converter` 内に閉じる（遅延）。既定テストはモデル DL 不要。
- VLM コンバータは `_get_converter` 同様にキャッシュ（モデルロードが高価）。

## 4. 設計

### `app/config.py`
```python
self.vlm_model = os.environ.get("PDFTO_VLM_MODEL", "granite_docling")
self.vlm_api_url = os.environ.get("PDFTO_VLM_API_URL") or None
self.vlm_api_key = os.environ.get("PDFTO_VLM_API_KEY") or None
self.vlm_api_model = os.environ.get("PDFTO_VLM_API_MODEL") or None
self.vlm_timeout = int(os.environ.get("PDFTO_VLM_TIMEOUT", "300"))
# property vlm_api_enabled -> bool(self.vlm_api_url)
```

### `app/models.py`
```python
use_vlm: bool = Field(default=False,
    description="Use the VLM (vision-language) pipeline: a model reads the page "
                "images end-to-end. Heavier; helps degraded scans / complex layouts. "
                "Ignores OCR/table knobs.")
```

### `app/converter.py`
- 許可リスト：`{"granite_docling": GRANITEDOCLING_TRANSFORMERS,
  "smoldocling": SMOLDOCLING_TRANSFORMERS}`。
- `@lru_cache _get_vlm_converter(model, api_url, api_key, api_model, timeout,
  artifacts_path, image_scale)`：
  - API: `ApiVlmOptions(url=api_url, params={"model": api_model}, headers={...},
    timeout=timeout, prompt=<convert-to-docling-markdown>)`、
    `VlmPipelineOptions(enable_remote_services=True, vlm_options=api_opts)`。
  - ローカル: `VlmPipelineOptions(vlm_options=<spec>)`。
  - `DocumentConverter(format_options={PDF: PdfFormatOption(pipeline_cls=VlmPipeline,
    pipeline_options=opts), IMAGE: ImageFormatOption(pipeline_cls=VlmPipeline,
    pipeline_options=opts)})`。
- `convert()`：`options.use_vlm` なら `_get_vlm_converter(...)` を使い、OCR/表/前処理の
  分岐をスキップ（ページ範囲は維持）。それ以外は従来どおり。

### `app/questions.py` / `app/main.py`
- 質問 `use_vlm`（boolean, 既定 False, pdf/image 文脈）。`apply_answers` の boolean キーに追加。
- one-shot に `use_vlm: bool = Query(default=False)`。

### 影響範囲
- 変更：`app/config.py`, `app/models.py`, `app/converter.py`, `app/questions.py`,
  `app/main.py`, `README.md`, `docs/roadmap.md`, テスト。
- 追加：`tests/test_quality_vlm.py`（opt-in 実 VLM）。
- 既定挙動・既存 API は後方互換。

## 5. 受け入れ条件（Definition of Done）

- [x] `use_vlm` が `ConversionOptions` にあり、既定 False で現挙動維持。
- [x] `use_vlm=True` で converter が `VlmPipeline` ベースで構築される（PDF/画像、モックで検証）。
- [x] `PDFTO_VLM_API_URL` 設定時は API VLM（`enable_remote_services`＋認証ヘッダ）になる（モック）。
- [x] 未知モデル名は `ConversionError`。
- [x] one-shot API と対話質問から指定でき、`apply_answers` がマップ。
- [x] 既定 `pytest` 166 passed（モデル DL 不要）。
- [x] 実 VLM は `PDFTO_RUN_VLM_TESTS=1` の opt-in テストで（手動・重い）。README に記載。

## 9. 実測（ローカル VLM・GraniteDocling-258M・CPU）

本環境で実際にローカル VLM を走らせ、`app.converter.convert(use_vlm=True)` の実経路で確認した
（モデル DL 後、CPU で約 60–65 秒/ページ）。

| 入力 | 指標 | 従来パイプライン | **VLM** |
|---|---|---|---|
| scanned_sample.pdf | 構造/本文 | OCR で本文のみ | **見出し `## …` ＋本文を構造化**（fox/invoice 取得） |
| sroie004（最難の実写領収書） | token_recall | OCR 0.33 / low_conf 0.33 | **0.833** |

**所見:** OCR＋confidence でも 0.33 止まりだった最難の実写領収書を、VLM は **0.833** まで
読み取れた（住所・明細まで復元）。会社名は `MR D.I.Y. (M)`→`(4) SON` 等の誤りも残るが、
従来パイプラインの天井を**大きく超える**。スキャン文書では見出し構造まで復元できた。
コストは CPU で約 1 分/ページと重く、**opt-in（既定 OFF）が妥当**。GPU/API VLM ならさらに
速度・精度が見込める。eval 土台への自動 A/B 統合はモデルが重いため専用環境向けに別途。

## 6. テスト計画

- 既定 `pytest`（モック）：
  - `_get_vlm_converter`：`DocumentConverter` をスタブし、PDF/IMAGE の `pipeline_cls` が
    `VlmPipeline`、ローカル既定でモデル仕様が載ること。
  - API 経路：`PDFTO_VLM_API_URL` 等を monkeypatch し、`enable_remote_services=True` と
    `ApiVlmOptions`（url・認証ヘッダ）になること。
  - 未知モデルで `ConversionError`。
  - `convert()`：`use_vlm=True` で `_get_vlm_converter` が呼ばれ、`_get_converter`（標準）は
    呼ばれないこと（mock）。
  - `apply_answers`/`build_questions` の `use_vlm` マップ・出現。
- opt-in（`PDFTO_RUN_VLM_TESTS=1`、手動）：`samples/scanned_sample.pdf` をローカル VLM で
  変換し、非空テキストを返す（厳密一致なし）。本環境ではモデル DL／CPU 実行が重いため
  既定では skip。

## 7. リスク・代替案

- **モデルが重く本環境で常用不可**：既定 OFF＋専用 opt-in フラグ。配線はモックで担保し、
  実効果は手動/専用環境で確認（spec 0023/0033 と同じ方針）。
- **VLM 出力が従来と傾向が違う（揺れ）**：opt-in。eval 自動 A/B は将来、専用環境で。
- **API VLM の外部送信**：`enable_remote_services=True` と URL 設定が前提のオプトイン。
  ページ画像が外部へ出るため README で明示。
- **代替：VLM を入れない**：従来パイプラインの限界（劣化スキャン・複雑表）に天井が残るため、
  opt-in の選択肢として用意する。

## 8. 未決事項

- 既定ローカルモデル（granite_docling-258M）でどこまで戻せるかは、鍵/GPU のある環境での
  実測に委ねる（本 issue は配線と選択肢提供まで）。
- VLM の eval 土台統合（専用環境での A/B）は需要が出た時点で別 issue。
