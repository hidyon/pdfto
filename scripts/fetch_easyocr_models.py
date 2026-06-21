"""Pre-download EasyOCR models for the languages PDFto offers.

Used at Docker build time to bake models into the image so language OCR runs
offline.  Downloads into the directory given as argv[1] (default
/opt/easyocr-models).

EasyOCR can only load certain language combinations together, so we fetch them
in valid groups; this still writes every needed recognition model into the
shared directory.
"""

import sys

import easyocr

# Language groups that EasyOCR allows loading together. Each CJK language pairs
# with English; latin-script languages can be grouped.
GROUPS = [
    ["en"],
    ["ja", "en"],
    ["ch_sim", "en"],
    ["ko", "en"],
    ["fr", "de", "es", "en"],
]


def main() -> None:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/easyocr-models"
    for langs in GROUPS:
        print(f"downloading EasyOCR models for {langs} ...", flush=True)
        easyocr.Reader(langs, model_storage_directory=out_dir,
                       download_enabled=True, gpu=False)
    print(f"EasyOCR models ready in {out_dir}")


if __name__ == "__main__":
    main()
