"""Storage for uploaded PDFs and their conversion outputs.

The index (document and output metadata) is persisted in SQLite so it survives
process restarts; the PDF and converted files themselves live on disk under
``<root>/<doc_id>/``.  The :class:`Database` is exposed as ``.db`` so the job
manager can share the same connection.
"""

from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .db import Database
from .models import DocumentAnalysis, OutputFormat


@dataclass
class OutputRecord:
    path: Path
    output_format: OutputFormat
    filename: str
    created_at: float = field(default_factory=time.time)


@dataclass
class DocumentRecord:
    id: str
    filename: str
    pdf_path: Path
    analysis: DocumentAnalysis
    created_at: float = field(default_factory=time.time)


class Storage:
    """SQLite-backed registry of documents and their outputs."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self.db = Database(self._root / "pdfto.db")

    def doc_dir(self, doc_id: str) -> Path:
        return self._root / doc_id

    # -- documents ---------------------------------------------------------- #
    def create_document(self, filename: str, data: bytes,
                        analysis: DocumentAnalysis) -> DocumentRecord:
        doc_id = uuid.uuid4().hex
        d = self.doc_dir(doc_id)
        d.mkdir(parents=True, exist_ok=True)
        pdf_path = d / "source.pdf"
        pdf_path.write_bytes(data)
        created_at = time.time()
        self.db.execute(
            "INSERT INTO documents (id, filename, pdf_path, analysis_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (doc_id, filename, str(pdf_path), analysis.model_dump_json(), created_at),
        )
        return DocumentRecord(
            id=doc_id, filename=filename, pdf_path=pdf_path,
            analysis=analysis, created_at=created_at,
        )

    def get(self, doc_id: str) -> Optional[DocumentRecord]:
        row = self.db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if row is None:
            return None
        return DocumentRecord(
            id=row["id"],
            filename=row["filename"],
            pdf_path=Path(row["pdf_path"]),
            analysis=DocumentAnalysis.model_validate_json(row["analysis_json"]),
            created_at=row["created_at"],
        )

    def delete(self, doc_id: str) -> bool:
        row = self.db.query_one("SELECT id FROM documents WHERE id = ?", (doc_id,))
        if row is None:
            return False
        self.db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        shutil.rmtree(self.doc_dir(doc_id), ignore_errors=True)
        return True

    # -- outputs ------------------------------------------------------------ #
    def asset_dir(self, doc_id: str) -> Path:
        return self.doc_dir(doc_id) / "assets"

    def add_output(self, doc_id: str, content: str, output_format: OutputFormat,
                   extension: str, assets: Optional[dict] = None) -> OutputRecord:
        record = self.get(doc_id)
        if record is None:
            raise KeyError(doc_id)
        base = Path(record.filename).stem or "output"
        filename = f"{base}.{extension}"
        out_path = self.doc_dir(doc_id) / f"output.{extension}"
        out_path.write_text(content, encoding="utf-8")
        if assets:
            adir = self.asset_dir(doc_id)
            adir.mkdir(parents=True, exist_ok=True)
            for name, data in assets.items():
                # Guard against odd names; keep only the basename.
                safe = Path(name).name
                (adir / safe).write_bytes(data)
        created_at = time.time()
        self.db.execute(
            "INSERT OR REPLACE INTO outputs "
            "(document_id, output_format, path, filename, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (doc_id, output_format.value, str(out_path), filename, created_at),
        )
        return OutputRecord(
            path=out_path, output_format=output_format,
            filename=filename, created_at=created_at,
        )

    def get_output(self, doc_id: str, output_format: str) -> Optional[OutputRecord]:
        row = self.db.query_one(
            "SELECT * FROM outputs WHERE document_id = ? AND output_format = ?",
            (doc_id, output_format),
        )
        if row is None:
            return None
        return OutputRecord(
            path=Path(row["path"]),
            output_format=OutputFormat(row["output_format"]),
            filename=row["filename"],
            created_at=row["created_at"],
        )

    # -- cleanup ------------------------------------------------------------ #
    def cleanup_expired(self, ttl_seconds: float) -> list[str]:
        """Delete documents older than *ttl_seconds* and orphaned directories."""

        now = time.time()
        removed: list[str] = []

        rows = self.db.query(
            "SELECT id FROM documents WHERE ? - created_at > ?", (now, ttl_seconds)
        )
        for row in rows:
            if self.delete(row["id"]):
                removed.append(row["id"])

        # Sweep orphaned directories on disk with no matching document row.
        for child in self._root.iterdir():
            if not child.is_dir():
                continue
            if self.db.query_one(
                "SELECT 1 FROM documents WHERE id = ?", (child.name,)
            ) is not None:
                continue
            try:
                if now - child.stat().st_mtime > ttl_seconds:
                    shutil.rmtree(child, ignore_errors=True)
                    removed.append(child.name)
            except OSError:
                continue
        return removed
