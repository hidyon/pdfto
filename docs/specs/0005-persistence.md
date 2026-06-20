# Spec: 状態の SQLite 永続化

- **ID:** 0005
- **状態:** done
- **マイルストーン:** M1.5 状態の永続化
- **関連 issue:** M1.5-1（SQLite 永続化）, M1.5-2（中断ジョブ復旧）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

現状、ドキュメント索引（`Storage`）とジョブ（`JobManager`）はインメモリの dict に
保持されており、プロセス再起動で**すべて失われる**。`data/<id>/` のファイルは残るが
索引が消えるため参照できず、孤児として掃除されるだけになる。

索引とジョブを **SQLite に永続化**し、再起動後も状態を保てるようにする。あわせて、
再起動で実行スレッドが失われた**中断ジョブを整合的に復旧**する。索引アクセスは
リポジトリ抽象越しにして、将来 Postgres 等へ差し替えやすくする。

## 2. スコープ

### やること
- SQLite を用いた永続化層（`app/db.py`）を追加する。
- `Storage`（documents / outputs）と `JobManager`（jobs）を SQLite バックエンドに
  置き換える。公開 API（メソッドシグネチャ・戻り値の型）は原則維持する。
- 起動時に、`pending` / `running` のまま残ったジョブを `failed`（理由: 再起動で中断）
  に復旧する。
- 変換成果物・アップロード PDF は従来どおり `data/<id>/` のファイルとして保存し、
  パスとメタデータのみ DB に持つ。

### やらないこと（非スコープ）
- マルチインスタンスでの**ジョブ分散実行**（実行は引き続き各プロセスのスレッド
  プール。複数インスタンス共有のジョブキューは将来の issue）。
- Postgres / オブジェクトストレージ実装（抽象は意識するが実装はしない）。
- 既存データのマイグレーションツール（新規スキーマ前提。旧インメモリ運用からの
  移行は不要）。

## 3. 要件

### 機能要件
- アップロード・変換・ダウンロードの各 API は、プロセス再起動を挟んでも同じ
  `document_id` / `job_id` で動作する（成果物が存在すればダウンロードできる）。
- `GET /jobs/{id}` は再起動後も完了済みジョブの状態・`download_url` を返す。
- 再起動時、未完了（`pending`/`running`）だったジョブは `failed` になり、`error` に
  「interrupted by restart」相当のメッセージが入る。
- TTL クリーンアップ（spec 0002）は DB 上の期限切れ行と、対応するファイル・孤児
  ディレクトリを削除する。

### 非機能要件
- DB アクセスはスレッドセーフ（ジョブはワーカスレッドから更新される）。
- 新規の外部依存を増やさない（標準ライブラリ `sqlite3` のみ）。
- SQLite は WAL モードで開き、読み書きの並行性を確保する。

## 4. 設計

### `app/db.py`（新規）
- `Database(path)`:
  - `sqlite3.connect(path, check_same_thread=False)` + `row_factory=sqlite3.Row`。
  - `PRAGMA journal_mode=WAL`、`PRAGMA foreign_keys=ON`。
  - 起動時にスキーマを作成（`CREATE TABLE IF NOT EXISTS`）。
  - すべての実行を内部 `Lock` で直列化する薄いヘルパ：`execute(sql, params)`,
    `query(sql, params) -> list[Row]`, `query_one(...) -> Row | None`。
- スキーマ:
  - `documents(id PK, filename, pdf_path, analysis_json, created_at)`
  - `outputs(document_id, output_format, path, filename, created_at,
    PRIMARY KEY(document_id, output_format),
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE)`
  - `jobs(id PK, document_id, status, output_format, created_at, updated_at,
    download_url, filename, preview, truncated, error)`

### `Storage`（`app/storage.py` 改修）
- `Storage(root)`: シグネチャ維持。内部で `Database(root/pdfto.db)` を生成し
  `self.db` として公開（`JobManager` が同一 DB を共有するため）。
- 既存メソッド（`create_document` / `get` / `add_output` / `get_output` /
  `delete` / `cleanup_expired` / `doc_dir`）を SQLite 実装に置換。戻り値の
  `DocumentRecord` / `OutputRecord` は DB 行から再構築する。
- `cleanup_expired`: `created_at < now-ttl` の documents を削除（CASCADE で outputs
  も削除）し、ディレクトリを `rmtree`。索引外の孤児ディレクトリ掃除は従来どおり。

### `JobManager`（`app/jobs.py` 改修）
- `JobManager(max_workers, db)`: `db` は `Storage.db`。jobs を DB に永続化。
- `submit` で行を INSERT、`_update` で UPDATE、`get` で SELECT して `Job` を再構築。
- `recover_interrupted()`: `status IN ('pending','running')` を `failed` +
  `error='interrupted by restart'` に UPDATE。`__init__` で呼ぶ。
- `cleanup_expired`: 終了状態かつ期限切れの行を DELETE。

### 配線（`app/main.py`）
- `storage = Storage(settings.data_dir)`
- `jobs = JobManager(settings.max_workers, storage.db)`

### 影響範囲
- 追加: `app/db.py`, `tests/test_db.py`, `tests/test_persistence.py`。
- 改修: `app/storage.py`, `app/jobs.py`, `app/main.py`,
  `tests/test_jobs.py` / `tests/test_cleanup.py` / `tests/test_api.py`
  （`JobManager` 生成に `db` を渡すよう更新）。
- コア（analysis/questions/converter）と API の外形は不変。

## 5. 受け入れ条件（Definition of Done）

- [ ] `Storage` / `JobManager` が SQLite に永続化し、新しい `Database(path)` を
      開き直すと（=再起動相当）同じドキュメント/ジョブを取得できる。
- [ ] 再起動相当で `pending`/`running` だったジョブが `failed` になる。
- [ ] 既存 API テスト（アップロード→変換→ダウンロード、ジョブ・ポーリング）が
      引き続き通る。
- [ ] TTL クリーンアップが DB 行・ファイル・孤児ディレクトリを削除する。
- [ ] `pytest` が通る。
- [ ] ローカルでサーバ再起動を跨いでドキュメント/完了ジョブを参照できることを確認。

## 6. テスト計画

- `tests/test_db.py`: スキーマ作成・基本 CRUD・スレッドからの並行書き込みが
  例外なく直列化されること。
- `tests/test_persistence.py`:
  - `Storage` に作成 → 別 `Storage(same_root)` から `get` できる。
  - `JobManager` に完了ジョブ → 別 `JobManager(same db)` から `get` できる。
  - `pending`/`running` 行を仕込み → `recover_interrupted()` 後に `failed`。
- 既存テストは `JobManager(max_workers=1, db=Storage(tmp).db)` 形へ更新。

## 7. リスク・代替案

- **マルチインスタンスのジョブ実行。** 本 issue では実行は各プロセス内。複数
  インスタンスで同じ DB を共有しても、ジョブを投入したインスタンスが実行する
  モデルのまま（共有キューは将来）。これを前提として明記する。
- **SQLite の並行性。** WAL + 単一コネクション + Lock で直列化。高負荷では
  ボトルネックになり得るが、本スケールでは十分。Postgres 化が必要になったら
  `Database` 抽象を差し替える。
- **代替: ジョブだけ DB、ドキュメントはインメモリ。** 一貫性が崩れるため不採用。
  両方を同一 DB に置く。

## 8. 未決事項

- DB ファイルのパスは `data/pdfto.db`（`PDFTO_DATA_DIR` 配下）に固定。個別の
  `PDFTO_DB_PATH` は今回は導入しない（必要になったら追加）。
