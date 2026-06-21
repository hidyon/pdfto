# CLAUDE.md

このファイルは、このリポジトリで作業する際の指針（プロジェクト概要・開発の進め方・
規約）をまとめたものです。**作業を始める前に必ず読んでください。**

---

## プロジェクト概要

**PDFto** — PDF を Markdown / HTML / JSON / テキストに変換するアプリ。
PDF の内容を解析し、内容に応じた質問に答えることで変換オプションを決め、
結果をダウンロードできる。変換エンジンは無料 OSS の
[docling](https://github.com/docling-project/docling)。

**設計の核は API ファースト**。Web UI は REST API の薄いクライアントにすぎず、
他システムからは API（`/docs` の OpenAPI）を叩くだけで同じことができる。
ユーザー向けの詳細な使い方は [README.md](README.md) を参照。

### アーキテクチャ

```
app/
  analysis.py    PDF の軽量解析（pypdf）— 質問の出し分けに使用
  questions.py   解析結果から質問を生成し、回答をオプションへ変換
  converter.py   docling を使った変換コア（遅延 import）
  jobs.py        変換をバックグラウンド実行するジョブ基盤（スレッドプール）
  cleanup.py     期限切れの保存物/ジョブを定期削除する掃除スレッド
  db.py          SQLite 永続化層（索引・ジョブを保存。スレッドセーフ）
  storage.py     アップロードと変換結果の保存（ファイル + SQLite 索引）
  logging_config.py  構造化ログ設定（リクエスト ID 付与・JSON/テキスト）
  security.py    API キー認証とレート制限（/api/v1/* に適用）
  webhooks.py    変換完了の Webhook 配送（署名・SSRF 緩和）
  models.py      API・コアで共有する Pydantic モデル
  main.py        FastAPI アプリ（REST API + Web UI 配信）
  static/        Web UI（HTML/CSS/JS）
client/python/   依存ゼロの Python クライアント（コピーして使える）
scripts/         OpenAPI 書き出し・サンプル PDF 生成等の補助スクリプト
samples/         変換の検証用サンプル PDF
tests/           pytest
docs/
  roadmap.md     ロードマップ（マイルストーン → issue）
  specs/         機能ごとのスペック（_template.md がテンプレート）
```

**コア（`analysis` / `questions` / `converter`）は Web 層から独立**している。
この境界は維持すること（コアが FastAPI などに依存し始めたら設計の劣化）。

---

## 開発の進め方

以下の 3 点を基本方針とする。具体的な手順は固定ではなく、
**定期的に見直して改善していく**（最後の節を参照）。

### 1. ロードマップとマイルストーン

- 計画は [docs/roadmap.md](docs/roadmap.md) で一元管理する。
- ロードマップは **複数のマイルストーン**で構成する。
- 1 つのマイルストーンは **複数の issue** を含む（マイルストーン = 達成したい状態、
  issue = そのための具体的な作業単位）。
- マイルストーンには「目的」と「完了条件（Definition of Done）」を必ず書く。
- 作業に着手する前に、その作業がどのマイルストーン・どの issue に紐づくかを
  はっきりさせる。該当する issue がなければ先にロードマップへ追加する。
- 状態は `roadmap.md` 上で更新する（`todo` / `in-progress` / `done`）。
  GitHub の Issues / Milestones を併用する場合は、roadmap.md を正本とし、
  GitHub 側はそのミラーとして扱う。

### 2. スペック駆動開発（Spec-Driven Development）

実装よりも先に**スペックを書く**ことを基本とする。

1. **スペックを書く** — `docs/specs/<番号>-<名前>.md` を
   [docs/specs/_template.md](docs/specs/_template.md) から作成する。
   背景・スコープ（やること/やらないこと）・要件・API/データ設計・
   受け入れ条件・テスト計画・未決事項を埋める。
2. **合意する** — スペックをレビューし、方針・受け入れ条件に合意してから着手する。
   不確実な点は実装前に「未決事項」に挙げ、必要なら確認する。
3. **実装する** — スペックに沿って実装する。途中でスペックと現実がずれたら、
   コードではなく**先にスペックを更新**して整合を取る。
4. **検証する** — スペックの「受け入れ条件」を満たすことをテストで確認する。
   新機能・バグ修正には原則テストを追加する。
5. **記録する** — 完了したらスペックの状態を `done` にし、roadmap.md の
   該当 issue を更新する。

小さな変更（typo 修正、軽微なリファクタ等）は正式なスペックを省略してよいが、
**振る舞いが変わる変更にはスペックを用意する**。

### 3. 進め方そのものを継続的に改善する

このプロセスは固定ではない。**定期的に振り返り、改善する。**

- 各マイルストーン完了時に短いふりかえりを行い、
  [docs/roadmap.md](docs/roadmap.md) の「ふりかえりログ」に
  「うまくいったこと / 課題 / 次に変えること」を記録する。
- そこで決めたプロセス改善は、この CLAUDE.md（または該当ドキュメント）に
  反映する。**CLAUDE.md は生きた文書**として更新し続ける。
- 「いつもこうする」「次回からこうする」というルールが生まれたら、
  口頭の合意で終わらせず必ずここに明文化する。

---

## 開発コマンド

```bash
# 初回セットアップ（仮想環境）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest        # テスト用

# 起動
uvicorn app.main:app --reload      # http://localhost:8000/ ・ /docs

# テスト
pytest                              # docling をモックするためモデル DL 不要

# Docker（モデルを焼き込み、初回 DL 不要）
docker build -t pdfto .
docker run -p 8000:8000 -v pdfto-data:/data pdfto
```

> 初回の実変換時に docling が ML モデルを自動ダウンロードする（ネットワーク必須）。
> テストは docling をモックしているので、モデルなしで実行できる。

### 規約・注意点

- **コミット前にテストを通す**（`pytest`）。振る舞いを変えたらテストを追加する。
- コードは周囲のスタイル（命名・コメント量・イディオム）に合わせる。
  コアの公開関数には docstring を付ける方針。
- 例外はコアの外へ生で漏らさない（例: 変換失敗は `ConversionError` に正規化し、
  Web 層で適切な HTTP ステータスへマッピングする）。
- 設定は環境変数（`PDFTO_*`）経由。`app/config.py` に集約する。
- 秘密情報・生成物（`data/`、`.venv/`）はコミットしない（`.gitignore` 済み）。
