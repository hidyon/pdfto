"""A tiny, dependency-free Python client for the PDFto API.

Standard library only — copy this single file into your project and use it.

Example
-------
    from pdfto_client import PDFtoClient

    client = PDFtoClient("http://localhost:8000", api_key="key-abc")
    markdown = client.convert_file("report.pdf", output_format="markdown")
    print(markdown.decode())
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional


class PDFtoError(Exception):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class PDFtoClient:
    """Synchronous client for the PDFto REST API."""

    def __init__(self, base_url: str = "http://localhost:8000",
                 api_key: Optional[str] = None, timeout: float = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # -- low-level ---------------------------------------------------------- #
    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if extra:
            headers.update(extra)
        return headers

    def _send(self, req: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            detail = body.decode("utf-8", "replace")
            try:
                detail = json.loads(body).get("detail", detail)
            except Exception:  # noqa: BLE001
                pass
            raise PDFtoError(exc.code, detail) from None

    def _request(self, method: str, path: str, *, json_body: Any = None,
                 query: Optional[dict] = None) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}
            )
        data = None
        headers = self._headers()
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        raw = self._send(req)
        return json.loads(raw) if raw else None

    def _post_multipart(self, path: str, files: Iterable[tuple[str, str, bytes]],
                        query: Optional[dict] = None, parse: bool = True) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}
            )
        boundary = uuid.uuid4().hex
        body = bytearray()
        for field, filename, content in files:
            ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            body += f"--{boundary}\r\n".encode()
            body += (f'Content-Disposition: form-data; name="{field}"; '
                     f'filename="{filename}"\r\n').encode()
            body += f"Content-Type: {ctype}\r\n\r\n".encode()
            body += content
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        headers = self._headers(
            {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        req = urllib.request.Request(url, data=bytes(body), headers=headers,
                                     method="POST")
        raw = self._send(req)
        if not parse:
            return raw
        return json.loads(raw) if raw else None

    # -- API ---------------------------------------------------------------- #
    def health(self) -> dict:
        return self._request("GET", "/api/health")

    def upload(self, path: str | Path) -> dict:
        path = Path(path)
        return self._post_multipart(
            "/api/v1/documents", [("file", path.name, path.read_bytes())]
        )

    def get_questions(self, document_id: str) -> list:
        return self._request("GET", f"/api/v1/documents/{document_id}/questions")

    def convert(self, document_id: str, answers: Optional[dict] = None,
                callback_url: Optional[str] = None) -> dict:
        return self._request(
            "POST", f"/api/v1/documents/{document_id}/convert",
            json_body=answers or {},
            query={"callback_url": callback_url} if callback_url else None,
        )

    def get_job(self, job_id: str) -> dict:
        return self._request("GET", f"/api/v1/jobs/{job_id}")

    def wait_for_job(self, job_id: str, interval: float = 1.5,
                     timeout: float = 300) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get_job(job_id)
            if job["status"] in ("succeeded", "failed"):
                return job
            time.sleep(interval)
        raise PDFtoError(0, "timed out waiting for job")

    def download(self, document_id: str, fmt: str = "markdown") -> bytes:
        url = (f"{self.base_url}/api/v1/documents/{document_id}/download"
               f"?format={fmt}")
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        return self._send(req)

    def convert_file(self, path: str | Path, wait: bool = True,
                     callback_url: Optional[str] = None, **answers) -> bytes:
        """Upload, convert and (by default) wait and return the output bytes."""
        doc = self.upload(path)
        job = self.convert(doc["id"], answers, callback_url=callback_url)
        if not wait:
            return job  # type: ignore[return-value]
        final = self.wait_for_job(job["id"])
        if final["status"] != "succeeded":
            raise PDFtoError(0, final.get("error") or "conversion failed")
        fmt = answers.get("output_format", "markdown")
        return self.download(doc["id"], fmt)

    def convert_oneshot(self, path: str | Path, output_format: str = "markdown",
                        do_ocr: bool = False, do_table_structure: bool = True) -> bytes:
        path = Path(path)
        return self._post_multipart(
            "/api/v1/convert", [("file", path.name, path.read_bytes())],
            query={"output_format": output_format, "do_ocr": str(do_ocr).lower(),
                   "do_table_structure": str(do_table_structure).lower()},
            parse=False,
        )

    def batch(self, paths: Iterable[str | Path], output_format: str = "markdown",
              do_ocr: bool = False, callback_url: Optional[str] = None) -> dict:
        files = []
        for p in paths:
            p = Path(p)
            files.append(("files", p.name, p.read_bytes()))
        return self._post_multipart(
            "/api/v1/batches", files,
            query={"output_format": output_format, "do_ocr": str(do_ocr).lower(),
                   "callback_url": callback_url},
        )

    def get_batch(self, batch_id: str) -> dict:
        return self._request("GET", f"/api/v1/batches/{batch_id}")
