"""Centralised logging setup with request-scoped correlation ids.

Every log line carries a ``request_id`` so a request can be traced across the
access log, its background job, and any error.  The id lives in a
:class:`contextvars.ContextVar` that the HTTP middleware sets per request; code
running outside a request (startup, cleaner thread) logs ``"-"``.

Standard library only — no external logging dependency.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

# Current request id; "-" when there is no active request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes present on every LogRecord; anything else is treated as a custom
# field and included in the JSON output.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"request_id", "message", "asctime"}


class RequestIdFilter(logging.Filter):
    """Attach the current request id to each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"

# Marks our handler so setup is idempotent.
_HANDLER_FLAG = "_pdfto_handler"


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Configure root and uvicorn loggers; safe to call more than once."""

    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _HANDLER_FLAG, True)
    handler.addFilter(RequestIdFilter())
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    log_level = getattr(logging, level, logging.INFO)

    root = logging.getLogger()
    # Drop any handler we previously installed so repeated calls don't stack.
    root.handlers = [h for h in root.handlers if not getattr(h, _HANDLER_FLAG, False)]
    root.addHandler(handler)
    root.setLevel(log_level)

    # Route uvicorn's loggers through our handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(log_level)
