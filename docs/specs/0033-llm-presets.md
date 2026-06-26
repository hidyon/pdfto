# Spec: LLM 品質補正プリセット（OCR 誤り修正・整形）

- **ID:** 0033
- **状態:** done
- **マイルストーン:** M10 変換品質の向上
- **関連 issue:** M10-3（LLM による品質補正プリセット）
- **作成日 / 更新日:** 2026-06-25 / 2026-06-25

## 1. 背景・目的

M10-5（confidence しきい値）で実写スキャンの recall は平均 0.38→0.80 に改善したが、
残るのは「**読めてはいるが一部誤読**」（例：`SDN BHD` の取りこぼし、文字の取り違え）。
これは OCR では取り切れず、**文脈で直す**タイプの誤りで、LLM 後補正が向く領域（M10-2 の
限界探索で「欠落は LLM では直せないが、化けは直せる」と整理済み）。

PDFto には既に自由指示の LLM 整形（`llm_instruction`、spec 0014）がある。本 issue では
**よく使う補正を「プリセット」として用意**し、利用者が指示文を考えずに OCR 誤り修正・
整形を選べるようにする。

## 2. スコープ

### やること
- LLM 補正プリセットを定義（`ocr_fix` / `cleanup` / `tables`）。各プリセットは
  吟味した指示文へ展開する。
- `ConversionOptions.llm_preset`（enum, 既定 None）を追加。`llm_instruction`（自由文）と
  **併用可**（プリセット＋追加指示）。
- 既存の LLM 適用箇所（`_apply_llm`）で、preset と instruction を 1 つの指示に解決して適用。
- one-shot API クエリと対話質問から選べるようにする。
- プリセットの解決ロジックと配線を既定 `pytest`（モック）で検証。

### やらないこと（非スコープ）
- LLM 実呼び出しの自動計測（API キーが要るため opt-in／手動。spec 0023 の方針を踏襲）。
- 新しい LLM プロバイダや、変換そのものの LLM 化（M10-4 VLM は別）。
- プリセット文言の多言語化・高度なテンプレート機構（まずは固定の良文 3 本）。

## 3. 要件

### 機能要件
- プリセット名は安定（`ocr_fix` / `cleanup` / `tables`）。未知の値は型で弾く（enum）。
- `llm_preset` 単独、`llm_instruction` 単独、両方、いずれも None を扱える。
  両方指定時はプリセット文＋追加指示を結合した 1 指示にする。
- `llm_enabled`（API キー設定時）かつ出力が markdown/text のときのみ適用（既存条件を踏襲）。
- 既定（どちらも未指定）では LLM を呼ばない＝現挙動維持・回帰なし。
- one-shot API・対話質問の双方から指定できる。

### 非機能要件
- `models.py` は軽量を保つ（enum のみ追加、`llm` を import しない）。
- プリセット文言は `app/llm.py` に集約。`anthropic` SDK は従来どおり遅延 import。

## 4. 設計

### `app/models.py`
```python
class LLMPreset(str, Enum):
    ocr_fix = "ocr_fix"   # 文脈で OCR 誤りを修正（情報の追加・削除はしない）
    cleanup = "cleanup"   # 改行/ハイフネーション/ノイズの整形
    tables  = "tables"    # 明確な表を Markdown 表に再構成

# ConversionOptions:
llm_preset: Optional[LLMPreset] = Field(default=None,
    description="LLM correction preset (ocr_fix/cleanup/tables). Combinable with "
                "llm_instruction. Requires an Anthropic API key (opt-in).")
```

### `app/llm.py`
```python
PRESET_INSTRUCTIONS: dict[str, str] = {
    "ocr_fix": "Fix obvious OCR recognition errors using surrounding context ... "
               "Do NOT add or remove information; preserve numbers/dates/currency "
               "and the document structure.",
    "cleanup": "Repair broken line wraps and hyphenation, remove scanning artifacts/"
               "stray characters, normalize whitespace. Keep all real content; do not "
               "summarize or rewrite.",
    "tables":  "Where the text clearly represents tabular data, reconstruct it as "
               "Markdown tables. Leave non-tabular text unchanged. Do not invent values.",
}

def resolve_instruction(preset, instruction) -> Optional[str]:
    """Combine a preset (enum/str/None) and a free instruction into one, or None."""
```

### `app/main.py`
- `_apply_llm`: `instruction = llm.resolve_instruction(options.llm_preset,
  options.llm_instruction)`; 以降は従来どおり（instruction があれば transform）。
- one-shot に `llm_preset: Optional[LLMPreset] = Query(default=None)` を追加し、
  `apply_answers` 入力に渡す。

### `app/questions.py`
- `llm_enabled` のとき `llm_preset`（choice: none/ocr_fix/cleanup/tables, 既定 none）を追加。
  `apply_answers` で none/空は無視、それ以外を `llm_preset` にマップ。

### 影響範囲
- 変更：`app/models.py`, `app/llm.py`, `app/main.py`, `app/questions.py`,
  `README.md`, `docs/roadmap.md`, テスト。
- 既定挙動・既存 API は後方互換。

## 5. 受け入れ条件（Definition of Done）

- [x] `LLMPreset` と `ConversionOptions.llm_preset`（既定 None）が追加され、未知値は型で弾く。
- [x] `llm.resolve_instruction` が preset/instruction の 4 通り（両/各/無）を正しく解決。
- [x] `_apply_llm` が解決結果で transform を呼ぶ（モックで検証）。どちらも無指定なら呼ばない。
- [x] one-shot API と対話質問から指定でき、`apply_answers` がマップする。
- [x] 既定 `pytest` 160 passed（LLM はモック。opt-in 実 LLM は key 無しで skip）。
- [x] README にプリセットの意味・併用・opt-in（キー必須）を記載。

## 6. テスト計画

- 既定 `pytest`（モック）：
  - `resolve_instruction`：preset のみ／instruction のみ／両方（結合）／両方 None→None。
  - `_apply_llm`：`llm_enabled=True` を monkeypatch、`llm.transform` をスタブし、
    preset 指定で解決済み指示が渡ること、未指定で呼ばれないこと。
  - `apply_answers`：`llm_preset` のマップ（none/空→None）。
  - `build_questions`：`llm_enabled` で `llm_preset` が出る／無効で出ない。
- opt-in（手動・要キー）：`PDFTO_RUN_LLM_TESTS=1` で `transform` にプリセット指示を与え、
  非空テキストが返ることを確認（実効果の定量は手動。eval 土台は convert のみのため別途）。

## 7. リスク・代替案

- **LLM が情報を捏造/改変**：プリセット文で「追加・削除しない」を明示。既定 OFF・opt-in。
- **実効果を自動計測できない**（キー無し）：spec 0023 同様 opt-in に委ね、本 issue は配線と
  プリセット品質に集中。将来キーのある環境で eval 連携（convert→llm）を追加可能。
- **代替：自由指示のみで足りる**：毎回良い指示を書く負担があるため、定番をプリセット化する。

## 8. 未決事項

- プリセットの追加（例：`translate_en`、`summarize`）は需要を見て別途。
- eval 土台への LLM 経路統合（convert＋llm を通すランナー）は、キーのある環境向けに別 issue。
