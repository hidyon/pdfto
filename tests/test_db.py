"""Tests for the SQLite Database wrapper."""

from __future__ import annotations

from threading import Thread

from app.db import Database


def test_schema_and_basic_crud(tmp_path):
    db = Database(tmp_path / "t.db")
    db.execute(
        "INSERT INTO documents (id, filename, pdf_path, analysis_json, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        ("d1", "a.pdf", "/x", "{}", 1.0),
    )
    row = db.query_one("SELECT * FROM documents WHERE id = ?", ("d1",))
    assert row["filename"] == "a.pdf"
    assert db.query_one("SELECT * FROM documents WHERE id = ?", ("nope",)) is None


def test_cascade_deletes_outputs(tmp_path):
    db = Database(tmp_path / "t.db")
    db.execute(
        "INSERT INTO documents (id, filename, pdf_path, analysis_json, created_at)"
        " VALUES ('d1', 'a.pdf', '/x', '{}', 1.0)"
    )
    db.execute(
        "INSERT INTO outputs (document_id, output_format, path, filename, created_at)"
        " VALUES ('d1', 'markdown', '/o', 'a.md', 1.0)"
    )
    db.execute("DELETE FROM documents WHERE id = 'd1'")
    assert db.query("SELECT * FROM outputs WHERE document_id = 'd1'") == []


def test_migration_adds_batch_id_to_existing_jobs(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    # Simulate a pre-batch jobs table (no batch_id column).
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, document_id TEXT, status TEXT,"
        " output_format TEXT, created_at REAL, updated_at REAL, download_url TEXT,"
        " filename TEXT, preview TEXT, truncated INTEGER, error TEXT)"
    )
    conn.commit()
    conn.close()

    db = Database(path)  # opening should migrate
    cols = {r["name"] for r in db.query("SELECT name FROM pragma_table_info('jobs')")}
    assert "batch_id" in cols


def test_concurrent_writes_are_serialised(tmp_path):
    db = Database(tmp_path / "t.db")

    def writer(start):
        for i in range(start, start + 50):
            db.execute(
                "INSERT INTO jobs (id, document_id, status, output_format,"
                " created_at, updated_at, truncated)"
                " VALUES (?, 'd', 'pending', 'markdown', 0, 0, 0)",
                (f"j{i}",),
            )

    threads = [Thread(target=writer, args=(s,)) for s in (0, 100, 200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = db.query("SELECT COUNT(*) AS n FROM jobs")
    assert rows[0]["n"] == 150
