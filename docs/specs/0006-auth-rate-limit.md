# Spec: API キー認証とレート制限

- **ID:** 0006
- **状態:** done
- **マイルストーン:** M2 公開・連携の強化
- **関連 issue:** M2-1（API キー認証 + レート制限）
- **作成日 / 更新日:** 2026-06-20 / 2026-06-20

## 1. 背景・目的

これまでアプリは無認証で、誰でも変換 API を叩けた。外部公開に耐えるには、最低限
**認証**で利用者を限定し、**レート制限**で過剰利用・濫用を防ぐ必要がある。

API ファーストの方針に沿い、他システムから扱いやすい **API キー認証**と、キー単位の
**レート制限**を導入する。ローカル/開発のしやすさを損なわないよう、キー未設定時は
従来どおり無認証で動く（オプトイン）。

## 2. スコープ

### やること
- API キー認証（`PDFTO_API_KEYS` に設定したキーのいずれかを要求）。
- キーは `X-API-Key` ヘッダまたは `Authorization: Bearer <key>` で受け付ける。
- キー単位（未認証運用時は IP 単位）の固定ウィンドウ・レート制限。
- 保護対象は `/api/v1/*`。超過時は `429` と `Retry-After` を返す。
- 認証失敗は `401`。いずれも `{detail, request_id}` 形で返す。

### やらないこと（非スコープ）
- キー発行/失効を管理する管理 API や DB 管理（環境変数で静的に設定）。
- ユーザー/ロール、スコープ別権限、OAuth/JWT。
- 分散レート制限（複数インスタンス共有のカウンタ）。インメモリ・プロセス単位
  （M1.5 ふりかえりの「投入インスタンスが実行する」前提に合わせる）。
- Web UI への API キー入力欄の追加（将来。認証有効時 UI から叩くにはキーが要る点は
  README に明記）。

## 3. 要件

### 機能要件
- `PDFTO_API_KEYS` が未設定なら認証は無効（全 API 開放、従来挙動）。
- 設定時、`/api/v1/*` への要求は有効なキーを要し、無ければ `401`。
- `/api/health`・`/docs`・`/openapi.json`・`/`（UI）・`/static/*` は常に開放。
- レート制限（`PDFTO_RATE_LIMIT` 件 / `PDFTO_RATE_WINDOW_SECONDS` 秒）を超えると
  `429` と `Retry-After`（秒）を返す。`PDFTO_RATE_LIMIT <= 0` で無効。
- 制限の単位は、認証有効時は API キー、無効時はクライアント IP。

### 非機能要件
- 新規依存なし（標準ライブラリのみ）。
- ミドルウェアでまとめて適用し、各ルートを変更しない。
- レート計数はスレッドセーフ。

## 4. 設計

### 設定（`app/config.py`）
- `api_keys: set[str]`（`PDFTO_API_KEYS` のカンマ区切り、空要素は除外）。
- `auth_enabled: bool = bool(api_keys)`。
- `rate_limit: int`（`PDFTO_RATE_LIMIT`、既定 60）。
- `rate_window_seconds: int`（`PDFTO_RATE_WINDOW_SECONDS`、既定 60）。
- `rate_limit_enabled: bool = rate_limit > 0`。

### `app/security.py`（新規）
- `extract_api_key(request) -> str | None`: `X-API-Key` か `Bearer` を読む。
- `RateLimiter`: `identity -> (window_start, count)` を `Lock` 付き dict で保持。
  `check(identity, limit, window) -> (allowed: bool, retry_after: int)`。固定
  ウィンドウ（ウィンドウ満了でカウンタリセット）。`limit<=0` は常に許可。

### ミドルウェア（`app/main.py`）
- `auth_and_rate_limit`: `path` が `/api/v1` で始まる場合のみ：
  1. `settings.api_keys` があればキーを検証（不一致/欠如→`401`）。識別子は `key:<key>`。
     無ければ識別子は `ip:<client>`。
  2. `rate_limiter.check(...)` で超過なら `429` + `Retry-After`。
  3. それ以外は通常処理。
- 既存の `request_context`（リクエスト ID + アクセスログ）を**最外**に保ち、
  401/429 応答にも `request_id` と `X-Request-ID` が付くようにする（定義順で制御）。
- `rate_limiter = RateLimiter()` をモジュールレベルに置く。

### 影響範囲
- 追加: `app/security.py`, `tests/test_security.py`。
- 変更: `app/config.py`, `app/main.py`, `README.md`,
  `CLAUDE.md`/`docs/roadmap.md`。
- 既存 API の外形・コアは不変（キー未設定なら挙動不変）。

## 5. 受け入れ条件（Definition of Done）

- [ ] `PDFTO_API_KEYS` 未設定では全 API が従来どおり動く（既存テストが通る）。
- [ ] 設定時、キー無し/誤りの `/api/v1/*` は `401`、正しいキーで `200`。
- [ ] `X-API-Key` と `Authorization: Bearer` の双方を受け付ける。
- [ ] `/api/health`・`/docs`・UI は認証有効時も開放。
- [ ] レート上限超過で `429` と `Retry-After` が返る。`rate_limit<=0` で無効。
- [ ] 401/429 応答に `request_id` と `X-Request-ID` が含まれる。
- [ ] `pytest` が通る。

## 6. テスト計画

`tests/test_security.py`（新規）。`settings` を monkeypatch、`main.rate_limiter` を
都度リセット。

- `RateLimiter`: 上限内は許可、超過で不許可＋`retry_after>0`、ウィンドウ無効化。
- API: キー未設定なら `/api/v1/documents` 等が従来どおり（401 にならない）。
- API: キー設定時、無キー→401、誤キー→401、正キー（ヘッダ/Bearer 両方）→成功。
- API: 低い上限で連続要求 → `429` + `Retry-After`。
- API: `/api/health` は認証有効でも `200`。

## 7. リスク・代替案

- **APIキー比較のタイミング攻撃。** 集合の包含判定は定数時間ではないが、本用途では
  許容。必要なら `hmac.compare_digest` での照合に強化できる。
- **インメモリ・レート制限は再起動/多重インスタンスでリセットされる。** 単一
  インスタンス前提として明記。分散が必要になれば共有ストア（Redis 等）を別 issue 化。
- **代替: DB 管理のキー + 管理 API。** 運用は柔軟だがスコープが大きい。まずは
  環境変数方式で最小限に。

## 8. 未決事項

- 既定レート（60 req / 60s）で十分か。環境変数で調整可能なため、まずこの値で進める。
