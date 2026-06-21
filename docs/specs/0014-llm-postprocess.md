# Spec: LLM による任意整形（オプション）

- **ID:** 0014
- **状態:** done
- **マイルストーン:** M3 変換品質
- **関連 issue:** M3-4（LLM による任意整形（オプション、API キー前提））
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

docling は構造を保った変換を行うが、「要約して」「英語に翻訳して」「見出しを整えて」
といった**内容の整形**はできない。これらを任意指示で行えると用途が広がる。

変換後のテキストに対し、Claude API（`anthropic` SDK）で**任意のプロンプト整形**を
かけられるオプションを追加する。API キーを前提とする**オプトイン機能**で、未設定なら
従来どおり docling の出力をそのまま返す。

## 2. スコープ

### やること
- 変換後の Markdown / テキスト出力に、自由記述の指示で LLM 整形をかける。
- `anthropic` SDK（公式）を用いる。モデル既定は `claude-opus-4-8`、環境変数で変更可。
- API キー（`PDFTO_ANTHROPIC_API_KEY` または `ANTHROPIC_API_KEY`）がある時のみ有効。
- 対話フローに自由記述の質問（新タイプ `text`）を、機能有効時のみ追加。
- ワンショット `POST /convert` にも `llm_instruction` クエリを追加。

### やらないこと（非スコープ）
- HTML / JSON 出力への LLM 整形（対象は md/text のみ）。
- ストリーミング応答を API として中継すること（サーバ内で完結し、結果のみ保存）。
- バッチへの指定（まずは対話/ワンショットのみ）。
- ツール使用・拡張思考・複数ターン対話。

## 3. 要件

### 機能要件
- `llm_instruction` 未指定、または機能無効時は従来挙動（docling 出力そのまま）。
- 有効かつ `llm_instruction` 指定時、出力が md/text なら整形後テキストを保存・配信。
- LLM 失敗（キー無効・ネットワーク等）は `LLMError` に正規化し、ジョブは `failed`
  になりエラーメッセージが残る（プロセスは落ちない）。
- 既定モデルは `claude-opus-4-8`。`PDFTO_LLM_MODEL` で変更可（コスト優先なら
  `claude-sonnet-4-6` 等を設定）。

### 非機能要件
- `anthropic` は遅延 import（未導入でもアプリ起動・既定テストは可能）。
- 既定（キー未設定）の `pytest` は LLM を呼ばない。
- コア（converter）は docling 専用のまま。LLM 整形は Web/オーケストレーション層で行う。

## 4. 設計

### 設定（`app/config.py`）
- `anthropic_api_key`（`PDFTO_ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY`）。
- `llm_model`（`PDFTO_LLM_MODEL`、既定 `claude-opus-4-8`）。
- `llm_max_tokens`（`PDFTO_LLM_MAX_TOKENS`、既定 16000）。
- `llm_timeout`（`PDFTO_LLM_TIMEOUT`、既定 120 秒）。
- `llm_enabled`（プロパティ）= `bool(anthropic_api_key)`。

### モデル（`app/models.py`）
- `ConversionOptions.llm_instruction: Optional[str] = None`。
- `Question.type` に `text`（自由記述）を追加（型は str なのでモデル変更不要）。

### `app/llm.py`（新規）
- `LLMError(RuntimeError)`。
- `transform(content, instruction, *, model=None, max_tokens=None, api_key=None,
  timeout=None) -> str`:
  - キーが無ければ `LLMError`。`anthropic` を遅延 import（未導入は `LLMError`）。
  - `anthropic.Anthropic(api_key=...)` を生成し、`client.messages.stream(...)` +
    `get_final_message()`（長文入力対策・skill 準拠）。`temperature` 等は渡さない。
  - system で「PDF 変換テキストに指示を適用し、結果のみ返す」と指定。例外は
    `LLMError` に正規化。テキストブロックを連結して返す。

### API/オーケストレーション（`app/main.py`）
- ヘルパ `_apply_llm(content, options) -> str`: 機能有効 ＆ `llm_instruction` ＆
  出力が md/text のとき `llm.transform` を適用。それ以外は素通し。
- 変換 work と ワンショットで、`add_output`/`FileResponse` の前に `_apply_llm` を通す。
- ワンショットに `llm_instruction: str | None = Query(None)` を追加。

### 質問（`app/questions.py`）
- `settings.llm_enabled` のとき末尾に `llm_instruction`（type=`text`）を追加。
- `apply_answers`: 非空の `llm_instruction` を反映。

### Web UI（`app/static`）
- `text` タイプを `<textarea>` で描画。`collectAnswers` は値をそのまま送る。

### 影響範囲
- 追加: `app/llm.py`, `tests/test_llm.py`。
- 変更: `requirements.txt`（`anthropic`）, `app/config.py`, `app/models.py`,
  `app/questions.py`, `app/main.py`, `app/static/app.js`,
  `tests/test_questions.py` / `test_api.py`, `README.md`, `docs/roadmap.md`,
  `CLAUDE.md`。
- 既定（キー未設定）の挙動は不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] キー未設定では LLM 質問が出ず、`llm_instruction` を送っても素通し（従来挙動）。
- [ ] 有効時、`apply_answers` が `llm_instruction` を反映し、`build_questions` に
      `text` 質問が含まれる。
- [ ] 変換 work が、md/text かつ指示ありのとき `llm.transform` を通す（テストで確認）。
- [ ] `transform` がキー無しで `LLMError` を投げる。
- [ ] LLM 失敗時にジョブが `failed` + エラーメッセージになる。
- [ ] ワンショットが `llm_instruction` を受け付ける。
- [ ] 既定 `pytest` が通る（anthropic 未導入・LLM 未呼び出し）。

## 6. テスト計画

- `test_llm.py`: `transform` がキー無しで `LLMError`。`anthropic` を monkeypatch した
  ダミークライアントで、`stream().get_final_message()` のテキストを連結して返すこと。
- `test_questions.py`: `settings.llm_enabled=True` 時に `llm_instruction`(type=text)
  が出る／False 時は出ない。`apply_answers` が指示を反映。
- `test_api.py`: `main.llm.transform` を monkeypatch（＋`settings` 有効化）し、
  変換結果が整形後テキストになること、LLM 例外でジョブ `failed` になること。

## 7. リスク・代替案

- **コスト/レイテンシ。** 既定 `claude-opus-4-8` は高品質だが高コスト。運用者は
  `PDFTO_LLM_MODEL` で `claude-sonnet-4-6` 等に変更可能（README 明記）。
- **大きな文書。** 入力が大きいと出力も大きくなり `max_tokens` 超過の恐れ。
  ストリーミング＋`PDFTO_LLM_MAX_TOKENS` で調整。将来チャンク分割を検討。
- **外部送信。** 変換テキストが Anthropic API に送られる。オプトインであることと
  この点を README に明記する。
- **代替: 自前要約等。** 品質が出ないため、LLM 整形は Claude API を用いる。

## 8. 未決事項

- 既定モデルは `claude-opus-4-8`（skill 準拠）。コスト優先運用は環境変数で切替。
