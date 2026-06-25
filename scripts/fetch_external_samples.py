"""Fetch real-world evaluation samples from the internet (dev tool, spec 0030 §9).

These probe PDFto's *limits* on genuine documents rather than synthetic ones.
The files are **not committed** (see .gitignore: ``samples/external/``) because
their redistribution terms differ from this repo; this script re-downloads them
on demand into ``samples/external/``.  The matching eval cases
(``eval/external_cases.py``) simply skip any file that has not been fetched.

Sources / licensing:
- IRS Form 1040 (``f1040.pdf``): a U.S. federal government work — public domain.
  A complex, born-digital tax form (dense fields, ruled line items).
- SROIE receipts (``sroie0NN.jpg`` + ``sroie0NN.key.json``): several scanned
  receipts from the ICDAR-2019 SROIE dataset (via the public
  zzzDavid/ICDAR-2019-SROIE mirror), used here only for local evaluation, not
  redistributed.  Real photographed receipts — hard OCR cases — each with
  ground-truth key fields (company/date/address/total).  Multiple receipts let
  us check whether an improvement *generalizes* rather than fitting one image.

Usage:
    python scripts/fetch_external_samples.py
"""

from __future__ import annotations

import pathlib
import urllib.request

EXTERNAL = pathlib.Path(__file__).resolve().parents[1] / "samples" / "external"

_SROIE = "https://raw.githubusercontent.com/zzzDavid/ICDAR-2019-SROIE/master/data"
# Receipts to pull; each contributes an image + ground-truth key file.
SROIE_IDS = ["000", "001", "002", "003", "004", "005"]

# (url, local filename) pairs.
SOURCES = [
    ("https://www.irs.gov/pub/irs-pdf/f1040.pdf", "f1040.pdf"),
]
for _id in SROIE_IDS:
    SOURCES.append((f"{_SROIE}/img/{_id}.jpg", f"sroie{_id}.jpg"))
    SOURCES.append((f"{_SROIE}/key/{_id}.json", f"sroie{_id}.key.json"))


def fetch(url: str, dest: pathlib.Path, timeout: int = 60) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "pdfto-eval/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())


def main() -> None:
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    for url, name in SOURCES:
        dest = EXTERNAL / name
        try:
            fetch(url, dest)
            print(f"wrote {dest} ({dest.stat().st_size} bytes)")
        except Exception as exc:  # noqa: BLE001 - best-effort dev fetch
            print(f"FAILED {url}: {exc}")


if __name__ == "__main__":
    main()
