# 変換サンプル（紹介用 before / after）

PDFto が**1 つの文書を複数の形式へ**どう変換するかを示すサンプルです。プロダクト紹介や
ドキュメントにそのまま引用できます。

## 1. リッチな文書（複数ページ・図・表）

入力は 2 ページの PDF（見出し・本文・箇条書き・**棒グラフ画像**・**2 つの表**を含む）。

| ファイル | 役割 |
|---|---|
| [`showcase.pdf`](showcase.pdf) | 入力（元の PDF・2 ページ） |
| [`showcase.md`](showcase.md) | → Markdown（見出し・箇条書き・表・画像参照を保持） |
| [`showcase.json`](showcase.json) | → 構造化 JSON（docling のドキュメントツリー。RAG/解析向け） |
| [`showcase.html`](showcase.html) | → HTML |
| [`showcase.txt`](showcase.txt) | → プレーンテキスト |
| [`assets/`](assets/) | Markdown/HTML が参照する抽出画像（棒グラフ） |

入力に含まれる要素：タイトル、説明段落、「Highlights」箇条書き、Q3 の棒グラフ図、
「Quarterly Revenue by Product」表（製品 × 四半期＋YoY）、（2 ページ目）「Regional
Breakdown」表、「Next Steps」リスト。

### Markdown 出力（抜粋）

```markdown
## Highlights

- Total revenue grew 12% quarter over quarter.
- Widget remained the top performer across all regions.

## Q3 Units by Product

![Image](assets/image_000000_....png)

## Quarterly Revenue by Product

| Product   |   Q1 |   Q2 |   Q3 | YoY   |
|-----------|------|------|------|-------|
| Widget    |  100 |  120 |  140 | +18%  |
| ...       |      |      |      |       |

## Regional Breakdown

| Region        | Revenue   |   Customers | Share   |
|---------------|-----------|-------------|---------|
| North America | $1.2M     |         320 | 41%     |
| ...           |           |             |         |
```

> 画像は *referenced* モードで `assets/` に書き出し、本文から相対パスで参照しています
> （`embedded` で base64 本文埋め込み、`placeholder` でプレースホルダのみ、も選べます）。

## 2. OCR デモ（スキャン画像 → テキスト復元）

入力は**テキストレイヤーのない画像のみ PDF**（請求書を画像化したもの）。OCR の有無で
出力がどう変わるかの before/after です。

| ファイル | 役割 |
|---|---|
| [`showcase_ocr.pdf`](showcase_ocr.pdf) | 入力（画像のみ・文字は埋め込まれていない） |
| [`showcase_ocr.ocr.txt`](showcase_ocr.ocr.txt) | **OCR あり** → 文字を復元 |
| [`showcase_ocr.no-ocr.txt`](showcase_ocr.no-ocr.txt) | **OCR なし** → 空（読み取れない） |

OCR ありの出力例：

```
ACME Supplies Invoice

Invoice number: 12345 Date: 2026-06-21 Bill to: Northwind Analytics

Item Qty Price Widgets 10 s100.00 Gadgets 5 s45.00 Shipping 1

Total due: $157.50

Thank you for your business:
```

> OCR は推定なので軽微な誤り（`$`→`s` など）が出ることがあります。OCR なしでは
> テキストが 1 文字も取れない（空）点が、OCR の効果を端的に示します。

## 再生成

```bash
python scripts/make_showcase.py   # reportlab + Pillow + docling が必要（初回はモデル DL）
```

> 変換品質はエンジン（docling）の ML モデルに依存します。表の検出は文書の体裁にも影響
> されるため、本サンプルは本文と並ぶ実務的な表組みを用いています。
