# PDFto Python クライアント

依存ゼロ（標準ライブラリのみ）の PDFto API クライアントです。`pip` で導入するか、
`pdfto_client.py` を 1 ファイルだけプロジェクトにコピーして使えます。

## インストール

```bash
# ソースから（このリポジトリ内）
pip install ./client/python

# 公開後（PyPI）
pip install pdfto-client

# もしくはコピー利用（依存ゼロなので 1 ファイルで動く）
cp client/python/pdfto_client.py your_project/
```

```python
import pdfto_client
print(pdfto_client.__version__)
from pdfto_client import PDFtoClient, PDFtoError
```

## CLI（`pdfto` コマンド）

インストールすると `pdfto` コマンドが使えます。動作中の PDFto API サーバ（ローカルで
`uvicorn app.main:app` か `docker run`、既定 `http://localhost:8000`）に対して変換します。

```bash
pdfto health                                   # サーバ疎通確認
pdfto convert report.pdf -f markdown -o out.md # ファイルへ出力
pdfto convert report.pdf -f json               # stdout へ出力
pdfto convert scan.png --ocr -o scan.md        # 画像を OCR して変換
pdfto --server http://host:8000 --api-key KEY convert a.docx
```

サーバ URL は `--server`（既定 `$PDFTO_SERVER`）、API キーは `--api-key`（既定
`$PDFTO_API_KEY`）で指定します。`-f/--format` は markdown/html/json/text、`--no-table` で
表構造復元を無効化。正常時は終了コード 0、エラー時は 1 を返します。

```python
from pdfto_client import PDFtoClient

client = PDFtoClient("http://localhost:8000", api_key=None)  # 認証有効なら api_key を指定

# 1 メソッドで完結（アップロード→変換→完了待ち→ダウンロード）
markdown = client.convert_file("report.pdf", output_format="markdown")
open("report.md", "wb").write(markdown)

# ステップごとに
doc = client.upload("report.pdf")
print([q["id"] for q in doc["questions"]])          # 提案された質問
job = client.convert(doc["id"], {"output_format": "json", "do_ocr": True})
job = client.wait_for_job(job["id"])
data = client.download(doc["id"], "json")

# ワンショット（同期・即ファイル）
pdf_md = client.convert_oneshot("report.pdf", output_format="markdown")

# バッチ
batch = client.batch(["a.pdf", "b.pdf"], output_format="markdown")
print(client.get_batch(batch["id"]))

# Webhook 通知（完了時に callback_url へ POST）
client.convert(doc["id"], {"output_format": "markdown"},
               callback_url="https://example.com/hook")
```

エラー時は `PDFtoError`（`.status` / `.detail`）が送出されます。

## パッケージの公開（メンテナ向け）

```bash
pip install build twine
python -m build           # dist/ に wheel と sdist を生成
twine upload dist/*       # PyPI へ公開（要アカウント・API トークン）
```

`pyproject.toml` の `version` と `pdfto_client.__version__` を揃えてから公開します。

## 他言語のクライアント

PDFto は OpenAPI を `/openapi.json` で公開しています。任意の言語のクライアントは
[openapi-generator](https://openapi-generator.tech/) で生成できます（プロジェクト
README の「クライアント / SDK」を参照）。
