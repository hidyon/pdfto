"""SQLite persistence layer shared by storage and jobs.

A thin, thread-safe wrapper around a single ``sqlite3`` connection.  All access
goes through a lock so worker threads (running conversions) and request threads
can read/write safely.  WAL mode keeps readers from blocking the writer.

Keeping this generic (just execute/query helpers + schema) means the domain
logic lives in :mod:`app.storage` and :mod:`app.jobs`, and the backend could be
swapped for another database later without touching them much.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    pdf_path      TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outputs (
    document_id   TEXT NOT NULL,
    output_format TEXT NOT NULL,
    path          TEXT NOT NULL,
    filename      TEXT NOT NULL,
    created_at    REAL NOT NULL,
    PRIMARY KEY (document_id, output_format),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL,
    status        TEXT NOT NULL,
    output_format TEXT NOT NULL,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    download_url  TEXT,
    filename      TEXT,
    preview       TEXT,
    truncated     INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    batch_id      TEXT,
    options       TEXT,
    callback_url  TEXT
);

CREATE TABLE IF NOT EXISTS batches (
    id         TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    count      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL,
    url             TEXT NOT NULL,
    event           TEXT NOT NULL,
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL,
    next_attempt_at REAL,
    last_error      TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
"""


class Database:
    """A lock-guarded SQLite connection with the PDFto schema."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Apply backward-compatible schema upgrades for existing databases."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(jobs)")}
        if "batch_id" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN batch_id TEXT")
        if "options" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN options TEXT")
        if "callback_url" not in cols:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN callback_url TEXT")

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
