# Spec: Python クライアントの PyPI パッケージ化

- **ID:** 0021
- **状態:** done
- **マイルストーン:** M6 配布・軽量化
- **関連 issue:** M6-1（Python クライアントの PyPI パッケージ化）
- **作成日 / 更新日:** 2026-06-21 / 2026-06-21

## 1. 背景・目的

同梱の Python クライアント（`client/python/pdfto_client.py`）は「コピーして使う」前提で、
`pip install` で導入できない。導入体験を上げるため、**配布可能なパッケージ**として
整備し、`pip` でインストール・ビルドできるようにする。

> 本リポジトリ環境からの PyPI への実公開は行わない（できない）。本 issue のゴールは
> 「公開可能な正式パッケージ化＝メタデータ/ビルド構成の整備と、ローカルでのビルド・
> インストール検証、公開手順の文書化」とする。

## 2. スコープ

### やること
- `client/python` を `pyproject.toml` を持つ配布物にする（依存ゼロ・stdlib のみ）。
- モジュールに `__version__` を持たせ、`PDFtoClient` / `PDFtoError` を公開 API とする。
- ソースからの `pip install ./client/python` が通り、`from pdfto_client import
  PDFtoClient` が使えることをローカル検証。
- `python -m build` で sdist/wheel が生成できることを検証。
- 公開手順（build → `twine upload`）をクライアント README に記載。

### やらないこと（非スコープ）
- 実際の PyPI 公開・名前予約。
- 非同期クライアントや機能追加（既存 API のまま）。
- サーバ（`app`）側のパッケージングへの影響。

## 3. 要件

### 機能要件
- `client/python/pyproject.toml` に配布名 `pdfto-client`、バージョン、説明、
  `requires-python`、`readme` を定義。依存は無し。
- 配布対象は単一モジュール `pdfto_client`（`example.py` は同梱しない/import 対象外）。
- `pip install ./client/python` 後に `import pdfto_client` が成功する。
- `python -m build` が `dist/*.whl` と `*.tar.gz` を生成する。

### 非機能要件
- 既存のコピー利用（単一ファイル）も引き続き可能（ファイル構成は壊さない）。
- サーバのテスト・依存は不変。

## 4. 設計

### `client/python/pyproject.toml`（新規）
- `[build-system]` setuptools。
- `[project]` name=`pdfto-client`, version=`0.1.0`, description, readme=`README.md`,
  requires-python>=3.9, license, urls。dependencies は空。
- `[tool.setuptools] py-modules = ["pdfto_client"]`（単一モジュール配布）。

### `client/python/pdfto_client.py`
- 先頭に `__version__ = "0.1.0"` を追加（`pyproject` と一致）。

### クライアント README
- 「インストール」節：`pip install ./client/python`（ソース）/ 公開後の
  `pip install pdfto-client`、ならびに `python -m build` + `twine upload` の公開手順。

### 影響範囲
- 追加: `client/python/pyproject.toml`。
- 変更: `client/python/pdfto_client.py`（`__version__`）, `client/python/README.md`,
  `README.md`（任意）, `docs/roadmap.md`。
- サーバ・テストは不変。

## 5. 受け入れ条件（Definition of Done）

- [x] `client/python/pyproject.toml` があり、`pdfto-client` として定義されている。
- [x] `pip install ./client/python` が成功し、`from pdfto_client import PDFtoClient`
      が使える（クリーン環境で検証）。
- [x] `python -m build` で wheel/sdist が生成できる（`pdfto_client-0.1.0-py3-none-any.whl`
      / `pdfto_client-0.1.0.tar.gz`）。
- [x] 公開手順が README に記載されている。
- [x] サーバの `pytest` が引き続き通る（95 passed, 5 skipped）。

## 6. テスト計画

- ローカル検証（手動/スモーク）:
  - 一時 venv で `pip install ./client/python` → `python -c "import pdfto_client;
    print(pdfto_client.__version__)"`。
  - `python -m build` の成果物（whl/tar.gz）が `dist/` にできることを確認。
- サーバの既定 `pytest` が通る（クライアント変更はサーバに影響しない）。

## 7. リスク・代替案

- **名前衝突**：`pdfto-client` が PyPI で空いている保証はない。公開時に調整する前提。
- **代替: サーバと同一配布に同梱**：利用者がサーバ依存（docling 等）まで入れることに
  なり重い。クライアントは独立・依存ゼロの配布物にする。

## 8. 未決事項

- バージョンは `0.1.0`（サーバと独立採番）。公開可否・名前は将来判断。
