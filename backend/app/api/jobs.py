"""In-memory thread-safe analysis job state store with TTL eviction."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.models.schemas import AnalysisResult, AnalysisStatusResponse, PipelineStage


@dataclass
class _JobEntry:
    response: AnalysisStatusResponse
    updated_at: float


class AnalysisJobStore:
    """Tracks asynchronous document analysis jobs and purges expired entries."""

    def __init__(self, retention_seconds: int = 3600) -> None:
        self.retention_seconds = retention_seconds
        self._lock = threading.Lock()
        self._jobs: dict[str, _JobEntry] = {}

    def create_queued(self, doc_id: str) -> None:
        """Register a newly queued job."""
        with self._lock:
            self._evict_expired_locked()
            self._jobs[doc_id] = _JobEntry(
                response=AnalysisStatusResponse(status="queued"),
                updated_at=time.time(),
            )

    def set_stage(self, doc_id: str, stage: PipelineStage) -> None:
        """Update a running job's current pipeline stage."""
        with self._lock:
            entry = self._jobs.get(doc_id)
            if entry is not None:
                entry.response = AnalysisStatusResponse(status="processing", stage=stage)
                entry.updated_at = time.time()

    def set_done(self, doc_id: str, result: AnalysisResult) -> None:
        """Mark job complete with its AnalysisResult."""
        with self._lock:
            self._jobs[doc_id] = _JobEntry(
                response=AnalysisStatusResponse(status="done", result=result),
                updated_at=time.time(),
            )

    def set_failed(self, doc_id: str, error: str) -> None:
        """Mark job failed with an error summary."""
        with self._lock:
            self._jobs[doc_id] = _JobEntry(
                response=AnalysisStatusResponse(status="failed", error=error),
                updated_at=time.time(),
            )

    def get(self, doc_id: str) -> AnalysisStatusResponse | None:
        """Return current job status or None if unknown/expired."""
        with self._lock:
            self._evict_expired_locked()
            entry = self._jobs.get(doc_id)
            return entry.response if entry is not None else None

    def _evict_expired_locked(self) -> None:
        now = time.time()
        expired = [
            key
            for key, entry in self._jobs.items()
            if now - entry.updated_at >= self.retention_seconds
        ]
        for key in expired:
            del self._jobs[key]
