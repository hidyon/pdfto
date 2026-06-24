# 変換サンプル（紹介用 before / after）

PDFto が**1 つの文書を複数の形式へ**どう変換するかを示すサンプルです。プロダクト紹介や
ドキュメントにそのまま引用できます。入力は 1 ページの PDF（見出し・本文・箇条書き・表を含む）。

| ファイル | 役割 |
|---|---|
| [`showcase.pdf`](showcase.pdf) | 入力（元の PDF） |
| [`showcase.md`](showcase.md) | → Markdown（見出し `#`・箇条書き `-`・表 `\|` を保持） |
| [`showcase.json`](showcase.json) | → 構造化 JSON（docling のドキュメントツリー。RAG/解析向け） |
| [`showcase.html`](showcase.html) | → HTML |
| [`showcase.txt`](showcase.txt) | → プレーンテキスト |

## 入力（PDF）の中身

- タイトル「Northwind Analytics — Q3 Product Report」
- 説明の段落
- 「Highlights」見出し＋箇条書き 3 項目
- 「Quarterly Revenue by Product」見出し＋表（製品 × 四半期、YoY 列付き）

## Markdown 出力（抜粋）

```markdown
## Northwind Analytics - Q3 Product Report

This report summarizes product performance for the third quarter. ...

## Highlights

- Total revenue grew 12% quarter over quarter.
- Widget remained the top performer across all regions.
- Doohickey dipped slightly and needs attention.

## Quarterly Revenue by Product

| Product   |   Q1 |   Q2 |   Q3 | YoY   |
|-----------|------|------|------|-------|
| Widget    |  100 |  120 |  140 | +18%  |
| ...       |      |      |      |       |
```

## 再生成

```bash
python scripts/make_showcase.py   # reportlab + docling が必要（初回はモデル DL）
```

> 注: 変換品質はエンジン（docling）の ML モデルに依存します。表の検出は文書の体裁に
> 影響されるため、本サンプルは「文書中に本文と並ぶ表」を用いています。
