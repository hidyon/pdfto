"""Write the PDFto OpenAPI schema to a file (or stdout).

Usage:
    python scripts/export_openapi.py            # prints to stdout
    python scripts/export_openapi.py openapi.json
"""

import json
import pathlib
import sys

# Allow running as `python scripts/export_openapi.py` from the repo root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()
    text = json.dumps(schema, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {sys.argv[1]}")
    else:
        print(text)


if __name__ == "__main__":
    main()
