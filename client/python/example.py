"""Example usage of the PDFto Python client.

Run a PDFto server first (see the project README), then:

    python example.py path/to/report.pdf
"""

import sys

from pdfto_client import PDFtoClient


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "report.pdf"
    client = PDFtoClient("http://localhost:8000")  # api_key="..." if enabled

    print("health:", client.health())

    # One call: upload, convert, wait, download.
    markdown = client.convert_file(path, output_format="markdown")
    print(markdown.decode("utf-8")[:500])

    # Or step by step, inspecting the suggested questions first.
    doc = client.upload(path)
    print("questions:", [q["id"] for q in doc["questions"]])
    job = client.convert(doc["id"], {"output_format": "json"})
    job = client.wait_for_job(job["id"])
    print("job status:", job["status"])


if __name__ == "__main__":
    main()
