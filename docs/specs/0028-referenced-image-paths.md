# Spec: referenced 画像リンクの相対パス化（バグ修正）

- **ID:** 0028
- **状態:** done
- **マイルストーン:** （保守）— M8/紹介サンプル作成中に発見
- **関連 issue:** —（spec 0011「referenced 画像」のバグ修正）
- **作成日 / 更新日:** 2026-06-24 / 2026-06-24

## 1. 背景・目的

`image_mode=referenced` の変換で、出力（Markdown/HTML）中の画像リンクが**一時ディレクトリの
絶対パス**（例: `![img](/tmp/xxxx/assets/image_000.png)`）になっている。`_export_referenced`
が docling の `save_as_markdown/html` を一時ディレクトリ配下の `assets/` に書き、その絶対パス
がそのまま本文に埋まるため。結果として、保存・配信・zip 同梱された成果物の画像リンクが
**壊れる**（zip は `assets/<name>` で同梱しているのに本文は `/tmp/...` を指す）。

リンクを成果物の構成に合わせ、**相対パス `assets/<name>`** にする。

## 2. スコープ

### やること
- `_export_referenced` の戻り content で、一時 `assets` ディレクトリの絶対パスを相対 `assets`
  に書き換える（Markdown/HTML 両方）。
- 純粋ヘルパに切り出し、docling 非依存でユニットテストする。

### やらないこと（非スコープ）
- placeholder/embedded モードの挙動変更（影響なし）。
- 画像のファイル名規則や保存先の変更。

## 3. 要件

- referenced 変換の Markdown/HTML 本文の画像リンクが `assets/<name>` で始まる（絶対パスを
  含まない）。
- 返す assets（filename→bytes）は従来どおり。zip 同梱（`assets/<name>`）と本文リンクが一致。
- placeholder/embedded・他形式は不変。既定 `pytest` が通る。

## 4. 設計

### `app/converter.py`
- ヘルパ追加:
  ```python
  def _relativize_asset_links(content: str, assets_dir: Path) -> str:
      """Rewrite docling's absolute artifacts-dir paths to relative 'assets/...'."""
      return content.replace(str(assets_dir), "assets")
  ```
- `_export_referenced`：`content = out.read_text(...)` の直後に
  `content = _relativize_asset_links(content, assets_dir)`。

### テスト
- `tests/test_converter_config.py`：`_relativize_asset_links` を直接検証（docling 不要）。
  - Markdown: `![img]({abs}/assets/img_000.png)` → `![img](assets/img_000.png)`。
  - HTML: `<img src="{abs}/assets/p.png">` → `<img src="assets/p.png">`。
- 既存の `test_referenced_images_assets_and_zip`（API・convert モック）は不変で維持。

### 影響範囲
- 変更: `app/converter.py`, `tests/test_converter_config.py`,
  `scripts/make_showcase.py`（サンプル側の応急処置だった相対化を撤去し、コア修正に委ねる）,
  `docs/examples/*`（再生成）, `docs/roadmap.md`（保守記録・任意）。

## 5. 受け入れ条件（Definition of Done）

- [x] `_relativize_asset_links` のユニットテストが通る。
- [x] referenced 変換の本文画像リンクが相対 `assets/<name>`（サンプル再生成で確認・/tmp 漏れ 0）。
- [x] 既定 `pytest` が通る（113 passed / 13 skipped。既存 referenced テスト含む）。
- [x] サンプル（`docs/examples/showcase.md`）の画像リンクが相対のまま再生成できる
      （スクリプトの応急処置を撤去。出力は従来とバイト一致）。

## 6. テスト計画

- 既定 `python -m pytest`：新ユニットテスト＋既存 API referenced テスト。
- 実確認：`python scripts/make_showcase.py`（応急処置撤去後）で `showcase.md` の画像リンクが
  `assets/...` になることを確認。

## 7. リスク・代替案

- **docling のパス表記差**：観測では `str(assets_dir)/<name>` の絶対形。`replace(str(assets_dir),
  "assets")` で吸収。既に相対の版なら no-op で安全。
- **代替: docling 側オプションで相対出力**：安定した公開オプションが不明確なため、確実な
  後処理（文字列置換）を採用。

## 8. 未決事項

- なし（局所的なバグ修正）。
