# Spec: 保存物の TTL と自動削除

- **ID:** 0002
- **状態:** done
- **マイルストーン:** M1 信頼性と運用性
- **関連 issue:** M1-2（保存物の TTL と自動削除 / `data/` の掃除）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

アップロードした PDF と変換成果物は `data/<doc_id>/` 配下に永続化され、ジョブは
インメモリ索引に蓄積される。現状はこれらを削除する仕組みが無く、放置すると
ディスクとメモリが**単調増加**する。長時間稼働するサービスとして不適切。

保存物（ドキュメント・成果物・ジョブ）に **TTL（有効期限）** を設け、期限切れを
**定期的に自動削除**する。あわせて、プロセス再起動でインメモリ索引が失われた後に
`data/` に残る**孤児ディレクトリ**も掃除する。

## 2. スコープ

### やること
- ドキュメント（`data/<doc_id>/` のディレクトリ）に TTL を設け、期限切れを削除する。
- ジョブ索引の期限切れエントリを削除する。
- バックグラウンドで定期実行する掃除（sweeper）を追加する。
- インメモリ索引に存在しない `data/` 配下の孤児ディレクトリ（前回起動の残骸）を、
  最終更新時刻ベースで掃除する。
- TTL・掃除間隔を環境変数で設定可能にする。

### やらないこと（非スコープ）
- 保存物の永続化やオブジェクトストレージ移行（将来）。
- ユーザー単位のクォータ/件数上限（本 issue は時間ベースの TTL のみ）。
- 削除予定の事前通知や猶予つき soft-delete（ハード削除のみ）。
- 明示的な手動削除 API（既存の `DELETE /documents/{id}` で十分）。

## 3. 要件

### 機能要件
- 作成から `PDFTO_TTL_MINUTES` を超えたドキュメントは、ディレクトリごと削除され、
  以後 `GET /documents/{id}` 等は `404` を返す。
- 同様に、最終更新から TTL を超えたジョブは索引から消え、`GET /jobs/{id}` は `404`。
- `data/` 配下に索引外のディレクトリがあり、その最終更新が TTL を超えていれば削除する。
- 掃除は `PDFTO_SWEEP_INTERVAL_SECONDS` ごとに自動実行される。
- `PDFTO_TTL_MINUTES <= 0` の場合は自動削除を無効化する（無期限）。

### 非機能要件
- 掃除はスレッドセーフで、進行中のリクエストやジョブ実行と競合しても安全。
- 新規の外部依存を増やさない（標準ライブラリのみ）。
- 掃除処理自体が例外で停止しても、次回以降の掃除が継続する。

## 4. 設計

### 設定（`app/config.py`）
- `ttl_minutes = int(PDFTO_TTL_MINUTES, default=60)`
- `sweep_interval_seconds = int(PDFTO_SWEEP_INTERVAL_SECONDS, default=300)`
- 派生プロパティ `ttl_seconds`、`cleanup_enabled = ttl_minutes > 0`。

### Storage（`app/storage.py`）
- `cleanup_expired(ttl_seconds: float) -> list[str]`:
  1. 索引内の各ドキュメントについて `now - created_at > ttl` なら `delete()`。
  2. `data/` 直下のディレクトリのうち索引に無いものを走査し、ディレクトリの
     `mtime` が `now - ttl` より古ければ `shutil.rmtree` で削除（孤児掃除）。
  - 削除した doc_id（孤児はディレクトリ名）のリストを返す。スレッドセーフに行う。

### JobManager（`app/jobs.py`）
- `cleanup_expired(ttl_seconds: float) -> list[str]`:
  - `now - job.updated_at > ttl` のジョブを索引から除去し、その id を返す。
  - 実行中（`running`/`pending`）のジョブは、updated_at が新しいため通常対象外。
    念のため終了状態（`succeeded`/`failed`）のみを削除対象とする。

### 定期実行（`app/cleanup.py` 新規）
- `PeriodicCleaner`: デーモンスレッドで `sweep_interval_seconds` ごとに
  `storage.cleanup_expired` と `jobs.cleanup_expired` を呼ぶ。
  - `start()` / `stop()`（`threading.Event` で停止）。
  - 1 回分の掃除を行う `sweep_once()` を公開し、テストから直接叩けるようにする。
  - 掃除中の例外は握りつぶしてログに残し、ループを止めない。
- `app/main.py` の FastAPI `lifespan` で、`cleanup_enabled` なら起動時に `start()`、
  終了時に `stop()`。

### 影響範囲
- 追加: `app/cleanup.py`, `tests/test_cleanup.py`。
- 変更: `app/config.py`, `app/storage.py`, `app/jobs.py`, `app/main.py`,
  `README.md`（環境変数）, `CLAUDE.md`/`docs/roadmap.md`。
- コア（`analysis`/`questions`/`converter`）は無変更。

## 5. 受け入れ条件（Definition of Done）

- [ ] `created_at` が TTL を超えたドキュメントは `cleanup_expired` で削除され、
      ディレクトリも消える（`GET /documents/{id}` が 404）。
- [ ] `updated_at` が TTL を超えた終了済みジョブは索引から消える（`GET /jobs/{id}` が 404）。
- [ ] 索引に無い `data/` 配下の古いディレクトリ（孤児）が削除される。
- [ ] `PDFTO_TTL_MINUTES <= 0` で自動削除が無効になる。
- [ ] `sweep_once()` が Storage と JobManager の掃除を 1 回で行う。
- [ ] 掃除処理中に一方が例外を投げても、もう一方や次回の掃除に影響しない。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_cleanup.py`（新規）。時間は `created_at`/`updated_at` を過去に
書き換える、または `ttl_seconds` に十分小さい値（例: 0）を与えて検証する。

- Storage: 期限切れドキュメントが削除され、新しいものは残る。
- Storage: 索引外の古いディレクトリ（孤児）が削除される。
- JobManager: 期限切れの終了ジョブが消え、実行中相当（updated_at が新しい）は残る。
- `PeriodicCleaner.sweep_once()` が両方を掃除する。
- TTL 無効化（`cleanup_enabled` False）で `lifespan` が cleaner を起動しないこと
  （API テストで起動してもエラーにならないことの確認で代替可）。

## 7. リスク・代替案

- **TTL の基準（作成時刻 vs 最終アクセス時刻）。** ドキュメントは `created_at`
  基準とする（予測可能・実装が単純）。最終アクセス基準は将来の改善余地として残す。
- **孤児掃除の mtime 依存。** ディレクトリの mtime はファイル追加で更新され得るが、
  「TTL より古ければ削除」という保守的判定なので実害は小さい。
- **代替: APScheduler 等の導入。** 単純なデーモンスレッドで足りるため不採用
  （依存を増やさない方針）。

## 8. 未決事項

- デフォルト TTL は 60 分・掃除間隔 5 分で問題ないか（変更は環境変数で可能なため、
  まずはこの既定で進める）。
