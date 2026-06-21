# Spec: 失敗ジョブの再実行 API

- **ID:** 0017
- **状態:** done
- **マイルストーン:** M4 信頼性 UX（軽量）
- **関連 issue:** M4-3（失敗ジョブの再実行 API）
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

変換ジョブが `failed`（LLM 失敗・OCR モデル取得失敗・一時的エラー等）になっても、
やり直す手段が無く、ユーザーはアップロードからやり直す必要がある。

元のドキュメントと**同じオプション**でジョブを**再実行**できる API を追加する。
そのためにジョブへ変換オプション（と `callback_url`）を永続化する。

## 2. スコープ

### やること
- ジョブ投入時に変換オプション一式（`ConversionOptions`）と `callback_url` を永続化。
- `POST /api/v1/jobs/{job_id}/retry`：同じドキュメント・同じオプションで新規ジョブを投入。
- 元ドキュメントが TTL 等で削除済みなら明確なエラーを返す。

### やらないこと（非スコープ）
- 同一ジョブ ID の "その場再実行"（毎回新しいジョブを作る方式）。
- 失敗ジョブの自動再試行（手動トリガのみ。Webhook 再試行=spec 0015 とは別）。
- オプションを変更しての再実行（変更したい場合は通常の convert を使う）。

## 3. 要件

### 機能要件
- ジョブ行に `options`（`ConversionOptions` の JSON）と `callback_url` を保存する。
- `POST /jobs/{job_id}/retry` は、当該ジョブの保存オプションで**新しいジョブ**を作り、
  `202` と新ジョブを返す（元ジョブは不変）。状態（succeeded/failed いずれ）でも再実行可。
- 元ドキュメントが存在しなければ `409`（再実行不可）。
- オプション未保存の古いジョブ（移行直後の既存行）は `422`（再実行情報なし）。
- 認証・レート制限（spec 0006）は `/api/v1/*` として適用。

### 非機能要件
- 既存スキーマへの後方互換な移行（`jobs.options` / `jobs.callback_url` 追加）。
- 新規依存なし。

## 4. 設計

### データ（`app/db.py`）
- `jobs` に `options TEXT` と `callback_url TEXT` を追加（fresh は CREATE、既存は
  `_migrate` で `PRAGMA table_info` を見て無ければ `ALTER TABLE ADD COLUMN`）。

### ジョブ（`app/jobs.py`）
- `submit(..., callback_url=None, batch_id=None, options_json=None)`:
  INSERT に `options`/`callback_url` を含める。
- `get_retry_info(job_id) -> dict | None`:
  `{document_id, options_json, callback_url}` を返す（未知は None）。

### API/配線（`app/main.py`）
- `convert_document` / `create_batch` の `submit` 呼び出しに
  `options_json=options.model_dump_json()` を渡す（`callback_url` は既存）。
- `POST /api/v1/jobs/{job_id}/retry`:
  1. `get_retry_info` で取得（無ければ 404）。`options_json` 無ければ 422。
  2. `storage.get(document_id)` が無ければ 409。
  3. `ConversionOptions.model_validate_json` で復元し `_conversion_work` で work を作り、
     `jobs.submit(..., callback_url=..., options_json=...)` で新ジョブを返す（202）。

### 影響範囲
- 変更: `app/db.py`, `app/jobs.py`, `app/main.py`, `tests/*`, `README.md`,
  `docs/roadmap.md`。
- 既存挙動は不変（新カラムは任意、retry は新規エンドポイント）。

## 5. 受け入れ条件（Definition of Done）

- [ ] ジョブ投入時に `options`/`callback_url` が永続化される。
- [ ] `POST /jobs/{id}/retry` が同じオプションで新ジョブを作り `202` を返す。
- [ ] 再実行ジョブの `output_format` 等が元と一致する。
- [ ] 未知ジョブは 404、元ドキュメント削除済みは 409。
- [ ] 既存 DB に対する移行で新カラムが追加される。
- [ ] `pytest` が通る。

## 6. テスト計画

- `db`: 旧 jobs 表（options 列なし）を開くと移行で `options`/`callback_url` 列が増える。
- `jobs`: `submit(..., options_json=...)` → `get_retry_info` が JSON を返す。
- API: convert → 完了 → `retry` → 新ジョブ ID が別で、`output_format` 一致、完了する。
  未知ジョブ 404。ドキュメント削除（`DELETE`）後の retry が 409。

## 7. リスク・代替案

- **オプション肥大/後方互換**：JSON 1 列で保持。フィールド追加は Pydantic 既定で吸収。
- **代替: 同一ジョブを in-place 再実行**。履歴が消え追跡性が落ちるため、毎回新ジョブを作る。
- **再実行の無限増殖**：手動トリガのみなので運用上の問題は小さい。

## 8. 未決事項

- 再実行で元ジョブとの関連（`retried_from`）は今回は保持しない（必要になれば列追加）。
