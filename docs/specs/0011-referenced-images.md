# Spec: 画像の参照モード（別ファイル書き出し）の完成

- **ID:** 0011
- **状態:** done
- **マイルストーン:** M3 変換品質
- **関連 issue:** M3-3（画像の参照モードの API/UI 完成）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

`image_mode` には `placeholder` / `embedded` / `referenced` があるが、`referenced`
（画像を別ファイルに書き出して参照）は出力中に相対パスのリンクが入るだけで、
**画像ファイルが実際に保存・取得できない**ため未完成。

`referenced` を完成させ、画像を別ファイルとして書き出し、(1) アセットとして配信、
(2) 本文＋画像をまとめた ZIP でダウンロードできるようにする。

## 2. スコープ

### やること
- 変換コアで `referenced`（md/html）時に docling の `save_as_markdown`/
  `save_as_html(artifacts_dir=..., image_mode=REFERENCED)` を使い、画像ファイルを
  生成する。本文は画像を `assets/<name>` で相対参照する。
- 生成した画像を `data/<id>/assets/` に保存する。
- アセット配信: `GET /api/v1/documents/{id}/assets/{filename}`。
- ZIP 同梱ダウンロード: `GET .../download?...&bundle=zip` で本文＋`assets/` を ZIP 化。
- Web UI: 結果に「ZIP でダウンロード」を出す（参照モードかつ画像がある場合）。

### やらないこと（非スコープ）
- `embedded`（base64 埋め込み）・`placeholder` の挙動変更（現状維持）。
- 画像の再エンコード/最適化・サムネイル生成。
- json/text 出力での画像取り出し（対象は md/html）。

## 3. 要件

### 機能要件
- `image_mode=referenced` かつ画像を含む md/html 変換で、画像が
  `data/<id>/assets/` に保存され、本文が `assets/<name>` を参照する。
- `GET /documents/{id}/assets/{filename}` が該当画像を返す。存在しなければ `404`。
  パストラバーサル（`..`・区切り文字）は拒否する。
- `GET /documents/{id}/download?format=...&bundle=zip` が本文と `assets/` を含む
  ZIP を返す（`bundle` 省略時は従来どおり単一ファイル）。アセットが無い場合でも
  ZIP（本文のみ）を返せる。
- 既存の `placeholder`/`embedded`、json/text の挙動は不変。

### 非機能要件
- 変換コアは Web 層非依存のまま（アセットはバイト列で受け渡し、保存は storage）。
- ZIP はメモリ上で生成（小〜中規模想定）。

## 4. 設計

### コア（`app/converter.py`）
- `ConvertedDocument.assets: dict[str, bytes]`（既定空）を追加。
- `_export`: `referenced` かつ md/html のとき、一時ディレクトリへ
  `save_as_markdown/html(out, artifacts_dir=tmp/"assets", image_mode=REFERENCED)`、
  本文を読み戻し、`assets/` 配下のファイルを `assets` dict に収集して返す。
  他モード/形式は従来どおり（assets 空）。

### 保存（`app/storage.py`）
- `add_output(..., assets: dict[str, bytes] | None = None)`: アセットを
  `doc_dir/assets/<name>` に書き出す。`asset_path(doc_id, name)` / `asset_dir` 補助。

### API（`app/main.py`）
- 変換 work で `storage.add_output(..., assets=converted.assets)`。
- `GET /documents/{id}/assets/{filename}`: 名前を検証して `assets/<name>` を返す。
- `download` に `bundle: str | None = Query(None)` を追加。`bundle == "zip"` の場合、
  本文（`output.<ext>`）＋ `assets/` を ZIP 化して返す。

### Web UI（`app/static/app.js`）
- 変換結果が参照モードでアセットを持つ場合、「ZIP でダウンロード」リンクを表示。
  （簡便のため、`download_url` に `&bundle=zip` を付けたリンクを併記。）

### 影響範囲
- 変更: `app/converter.py`, `app/storage.py`, `app/main.py`,
  `app/static/app.js`, `tests/test_api.py`（assets/zip 経路）, `README.md`,
  `docs/roadmap.md`。
- 既存挙動は参照モード以外で不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] `referenced` 変換で画像が `data/<id>/assets/` に保存され、本文が相対参照する。
- [ ] `GET /documents/{id}/assets/{name}` が画像を返し、未知/不正名は `404`/`400`。
- [ ] `download?...&bundle=zip` が本文＋`assets/` を含む ZIP を返す。
- [ ] `placeholder`/`embedded`・json/text の既存挙動は不変（既存テストが通る）。
- [ ] パストラバーサルを拒否する。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_api.py`（追記）。`convert` を assets 付き `ConvertedDocument` を返す
フェイクに monkeypatch して検証（実画像/モデル不要）。

- アセット付き変換 → `assets/<name>` が保存され `GET assets/<name>` が中身を返す。
- `download?bundle=zip` の戻りが ZIP で、`output.md` と `assets/<name>` を含む。
- `GET assets/../secret` 等のトラバーサルが拒否される（`400`/`404`）。
- 既存のダウンロード（bundle 無し）は従来どおり。

## 7. リスク・代替案

- **docling の参照パス規約。** `save_as_*` は `artifacts_dir` への相対パスで参照する。
  本文の参照名と保存先（`assets/`）を一致させる。実画像を伴う検証は手動。
- **ZIP のメモリ生成。** 大量/巨大画像ではメモリを使う。対象規模では許容、必要なら
  ストリーミング化を別 issue。
- **代替: 常に ZIP で返す。** 後方互換を壊すため不採用。`bundle` で明示。

## 8. 未決事項

- ZIP 内のレイアウトは `output.<ext>` ＋ `assets/<name>`（本文の参照と一致）で確定。
