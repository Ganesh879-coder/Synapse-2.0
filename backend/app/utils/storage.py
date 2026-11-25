"""Temporary document storage with automatic 1-hour privacy cleanup."""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger("storage")


class TempDocumentStore:
    """Manages per-document temporary directories and retention cleanup."""

    def __init__(self, base_dir: Path, retention_seconds: int = 3600) -> None:
        self.base_dir = base_dir
        self.retention_seconds = retention_seconds
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_doc_dir(self, doc_id: str) -> Path:
        """Create and return an isolated temporary directory for a document."""
        doc_dir = self.base_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir

    def save_original(self, doc_id: str, mime_type: str, data: bytes) -> Path:
        """Persist uploaded bytes into the document's temp directory."""
        ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/pdf": ".pdf",
        }[mime_type]
        doc_dir = self.create_doc_dir(doc_id)
        target = doc_dir / f"original{ext}"
        target.write_bytes(data)
        return target

    def cleanup_expired(self, now: float | None = None) -> int:
        """Delete document directories older than retention_seconds."""
        current_time = now if now is not None else time.time()
        removed = 0
        if not self.base_dir.exists():
            return 0
        for entry in self.base_dir.iterdir():
            if not entry.is_dir():
                continue
            age = current_time - entry.stat().st_mtime
            if age >= self.retention_seconds:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        if removed:
            logger.info("Cleaned up expired temp documents", extra={"removed_count": removed})
        return removed


async def run_cleanup_loop(store: TempDocumentStore, interval_seconds: int = 300) -> None:
    """Periodically purge expired temporary document directories."""
    while True:
        try:
            store.cleanup_expired()
        except Exception as exc:  # pragma: no cover - defensive loop guard
            logger.warning("Temp cleanup iteration failed", extra={"error": type(exc).__name__})
        await asyncio.sleep(interval_seconds)
