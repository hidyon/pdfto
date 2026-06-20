"""Storage for uploaded PDFs and their conversion outputs.

This is an intentionally small, dependency-free store backed by the local
filesystem plus an in-process index.  It is sufficient for a single-instance
deployment; swapping it for a database or object store later only requires
re-implementing this module's small surface.
"""

from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional

from .models import ConversionOptions, DocumentAnalysis, OutputFormat


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
    outputs: dict[str, OutputRecord] = field(default_factory=dict)


class Storage:
    """Thread-safe registry of documents and their outputs."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, DocumentRecord] = {}
        self._lock = Lock()

    def doc_dir(self, doc_id: str) -> Path:
        return self._root / doc_id

    def create_document(self, filename: str, data: bytes,
                        analysis: DocumentAnalysis) -> DocumentRecord:
        doc_id = uuid.uuid4().hex
        d = self.doc_dir(doc_id)
        d.mkdir(parents=True, exist_ok=True)
        pdf_path = d / "source.pdf"
        pdf_path.write_bytes(data)
        record = DocumentRecord(
            id=doc_id,
            filename=filename,
            pdf_path=pdf_path,
            analysis=analysis,
        )
        with self._lock:
            self._docs[doc_id] = record
        return record

    def get(self, doc_id: str) -> Optional[DocumentRecord]:
        with self._lock:
            return self._docs.get(doc_id)

    def add_output(self, doc_id: str, content: str, output_format: OutputFormat,
                   extension: str) -> OutputRecord:
        record = self.get(doc_id)
        if record is None:
            raise KeyError(doc_id)
        base = Path(record.filename).stem or "output"
        filename = f"{base}.{extension}"
        out_path = self.doc_dir(doc_id) / f"output.{extension}"
        out_path.write_text(content, encoding="utf-8")
        output = OutputRecord(
            path=out_path, output_format=output_format, filename=filename
        )
        with self._lock:
            record.outputs[output_format.value] = output
        return output

    def get_output(self, doc_id: str, output_format: str) -> Optional[OutputRecord]:
        record = self.get(doc_id)
        if record is None:
            return None
        return record.outputs.get(output_format)

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            record = self._docs.pop(doc_id, None)
        if record is None:
            return False
        shutil.rmtree(self.doc_dir(doc_id), ignore_errors=True)
        return True

    def cleanup_expired(self, ttl_seconds: float) -> list[str]:
        """Delete documents older than *ttl_seconds* and orphaned directories.

        Returns the ids (or directory names) that were removed.  Orphans are
        on-disk ``data/<id>/`` directories with no index entry — typically
        left over from a previous process run, since the index is in memory.
        """

        now = time.time()
        removed: list[str] = []

        with self._lock:
            expired = [
                doc_id for doc_id, rec in self._docs.items()
                if now - rec.created_at > ttl_seconds
            ]
        for doc_id in expired:
            if self.delete(doc_id):
                removed.append(doc_id)

        # Sweep orphaned directories left on disk without an index entry.
        with self._lock:
            known = set(self._docs)
        for child in self._root.iterdir():
            if not child.is_dir() or child.name in known:
                continue
            try:
                if now - child.stat().st_mtime > ttl_seconds:
                    shutil.rmtree(child, ignore_errors=True)
                    removed.append(child.name)
            except OSError:
                continue
        return removed
