"""Tests for structured logging configuration."""

from __future__ import annotations

import json
import logging

from app.logging_config import JsonFormatter, setup_logging


def test_json_formatter_emits_valid_json_with_fields():
    record = logging.LogRecord(
        "pdfto.test", logging.INFO, "file.py", 10, "hello %s", ("world",), None
    )
    record.request_id = "req-123"
    record.job_id = "job-9"

    out = JsonFormatter().format(record)
    data = json.loads(out)

    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "pdfto.test"
    assert data["request_id"] == "req-123"
    assert data["job_id"] == "job-9"


def test_json_formatter_defaults_request_id():
    record = logging.LogRecord(
        "pdfto.test", logging.INFO, "file.py", 10, "msg", (), None
    )
    data = json.loads(JsonFormatter().format(record))
    assert data["request_id"] == "-"


def test_setup_logging_is_idempotent():
    setup_logging("INFO", "text")
    setup_logging("DEBUG", "json")
    root = logging.getLogger()
    ours = [h for h in root.handlers if getattr(h, "_pdfto_handler", False)]
    assert len(ours) == 1
