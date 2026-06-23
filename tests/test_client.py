"""Tests for the bundled Python client against a real server thread.

The server runs in-process (uvicorn in a thread) with docling mocked, so the
client's real HTTP path (urllib, multipart, polling) is exercised end-to-end.
"""

from __future__ import annotations

import pathlib
import socket
import sys
import threading
import time

import pytest
import uvicorn

from app import main
from app.converter import ConvertedDocument
from app.jobs import JobManager
from app.security import RateLimiter
from app.storage import Storage

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "client" / "python"))
from pdfto_client import PDFtoClient, PDFtoError  # noqa: E402

_EXT = {"markdown": "md", "html": "html", "json": "json", "text": "txt"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def base_url(tmp_path, monkeypatch):
    store = Storage(tmp_path)
    monkeypatch.setattr(main, "storage", store)
    monkeypatch.setattr(main, "jobs", JobManager(max_workers=2, db=store.db))
    monkeypatch.setattr(main, "rate_limiter", RateLimiter())

    def fake_convert(pdf_path, options, image_dir=None):
        return ConvertedDocument(
            content=f"# md {options.output_format.value}",
            output_format=options.output_format,
            suggested_extension=_EXT[options.output_format.value],
        )

    monkeypatch.setattr(main, "convert", fake_convert)

    port = _free_port()
    config = uvicorn.Config(main.app, host="127.0.0.1", port=port,
                            log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "server did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def pdf(tmp_path, text_pdf):
    p = tmp_path / "doc.pdf"
    p.write_bytes(text_pdf)
    return p


def test_health(base_url):
    assert PDFtoClient(base_url).health()["status"] == "ok"


def test_convert_file_end_to_end(base_url, pdf):
    client = PDFtoClient(base_url)
    out = client.convert_file(str(pdf), output_format="markdown")
    assert out == b"# md markdown"


def test_oneshot(base_url, pdf):
    out = PDFtoClient(base_url).convert_oneshot(str(pdf), output_format="text")
    assert out == b"# md text"


def test_batch(base_url, tmp_path, text_pdf):
    a = tmp_path / "a.pdf"; a.write_bytes(text_pdf)
    b = tmp_path / "b.pdf"; b.write_bytes(text_pdf)
    client = PDFtoClient(base_url)
    batch = client.batch([str(a), str(b)], output_format="markdown")
    assert batch["count"] == 2
    for item in batch["items"]:
        job = client.wait_for_job(item["job_id"], interval=0.05, timeout=10)
        assert job["status"] == "succeeded"
    agg = client.get_batch(batch["id"])
    assert {i["status"] for i in agg["items"]} == {"succeeded"}


def test_auth_required(base_url, pdf, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "api_keys", {"key-1"})

    with pytest.raises(PDFtoError) as exc:
        PDFtoClient(base_url).upload(str(pdf))
    assert exc.value.status == 401

    ok = PDFtoClient(base_url, api_key="key-1").upload(str(pdf))
    assert ok["id"]


def test_export_openapi_schema():
    schema = main.app.openapi()
    assert "openapi" in schema
    assert "/api/v1/documents" in schema["paths"]


# -- CLI -------------------------------------------------------------------- #
from pdfto_client import main as cli_main  # noqa: E402


def test_cli_health(base_url, capsys):
    rc = cli_main(["--server", base_url, "health"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"status"' in out and "ok" in out


def test_cli_convert_stdout(base_url, pdf, capsysbinary):
    rc = cli_main(["--server", base_url, "convert", str(pdf), "-f", "text"])
    assert rc == 0
    assert b"# md text" in capsysbinary.readouterr().out


def test_cli_convert_to_file(base_url, pdf, tmp_path):
    out = tmp_path / "out.md"
    rc = cli_main(["--server", base_url, "convert", str(pdf),
                   "-f", "markdown", "-o", str(out)])
    assert rc == 0
    assert out.read_bytes() == b"# md markdown"


def test_cli_unreachable_server_returns_1(pdf, capsys):
    rc = cli_main(["--server", "http://127.0.0.1:1", "convert", str(pdf)])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_cli_version():
    import pytest as _pytest
    with _pytest.raises(SystemExit) as exc:
        cli_main(["--version"])
    assert exc.value.code == 0
