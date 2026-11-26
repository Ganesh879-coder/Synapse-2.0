"""SQLite/SQLModel-backed analysis job state store with TTL and restart recovery."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.db import AnalysisJobRow, create_db_engine
from app.models.schemas import AnalysisResult, AnalysisStatusResponse, JobStatus, PipelineStage


class AnalysisJobStore:
    """Persists asynchronous document analysis jobs and purges expired records."""

    def __init__(
        self,
        db_url: str | None = None,
        retention_seconds: int = 3600,
        uploads_dir: Path | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.retention_seconds = retention_seconds
        self.uploads_dir = uploads_dir
        self.engine = engine or create_db_engine(db_url or "sqlite:///:memory:")

    def recover_interrupted_jobs(self) -> int:
        """Mark any jobs left in queued/processing at startup as failed."""
        now = time.time()
        recovered = 0
        with Session(self.engine) as session:
            rows = session.exec(
                select(AnalysisJobRow).where(
                    AnalysisJobRow.status.in_(["queued", "processing"])  # type: ignore[attr-defined]
                )
            ).all()
            for row in rows:
                row.status = "failed"
                row.stage = None
                row.error = (
                    "Server restarted while analysis was in progress. "
                    "Please re-upload your document."
                )
                row.updated_at = now
                session.add(row)
                recovered += 1
            if recovered:
                session.commit()
        return recovered

    def create_queued(self, doc_id: str) -> None:
        """Register a newly queued job."""
        now = time.time()
        with Session(self.engine) as session:
            self._evict_expired_locked(session, now)
            row = AnalysisJobRow(
                doc_id=doc_id,
                status="queued",
                created_at=now,
                updated_at=now,
            )
            session.merge(row)
            session.commit()

    def set_stage(self, doc_id: str, stage: PipelineStage) -> None:
        """Update a running job's current pipeline stage."""
        with Session(self.engine) as session:
            row = session.get(AnalysisJobRow, doc_id)
            if row is not None:
                row.status = "processing"
                row.stage = stage
                row.updated_at = time.time()
                session.add(row)
                session.commit()

    def set_done(self, doc_id: str, result: AnalysisResult) -> None:
        """Mark job complete with its serialized AnalysisResult."""
        with Session(self.engine) as session:
            row = session.get(AnalysisJobRow, doc_id)
            now = time.time()
            if row is None:
                row = AnalysisJobRow(
                    doc_id=doc_id,
                    status="done",
                    result_json=result.model_dump_json(),
                    created_at=now,
                    updated_at=now,
                )
            else:
                row.status = "done"
                row.stage = None
                row.result_json = result.model_dump_json()
                row.error = None
                row.updated_at = now
            session.add(row)
            session.commit()

    def set_failed(self, doc_id: str, error: str) -> None:
        """Mark job failed with an error summary."""
        with Session(self.engine) as session:
            row = session.get(AnalysisJobRow, doc_id)
            now = time.time()
            if row is None:
                row = AnalysisJobRow(
                    doc_id=doc_id,
                    status="failed",
                    error=error,
                    created_at=now,
                    updated_at=now,
                )
            else:
                row.status = "failed"
                row.stage = None
                row.error = error
                row.updated_at = now
            session.add(row)
            session.commit()

    def get(self, doc_id: str) -> AnalysisStatusResponse | None:
        """Return current job status or None if unknown/expired."""
        now = time.time()
        with Session(self.engine) as session:
            self._evict_expired_locked(session, now)
            row = session.get(AnalysisJobRow, doc_id)
            if row is None:
                return None
            result = (
                AnalysisResult.model_validate_json(row.result_json)
                if row.result_json
                else None
            )
            return AnalysisStatusResponse(
                status=row.status,  # type: ignore[arg-type]
                stage=row.stage,  # type: ignore[arg-type]
                result=result,
                error=row.error,
            )

    def redact_extracted_fields(self, doc_id: str) -> None:
        """Clear extracted_fields from stored result when DELETE_AFTER_VIEW is enabled."""
        with Session(self.engine) as session:
            row = session.get(AnalysisJobRow, doc_id)
            if row is None or not row.result_json:
                return
            result = AnalysisResult.model_validate_json(row.result_json)
            result.extracted_fields = {}
            row.result_json = result.model_dump_json()
            session.add(row)
            session.commit()

    def delete_job(self, doc_id: str) -> bool:
        """Delete job row and associated temp files immediately."""
        deleted = False
        with Session(self.engine) as session:
            row = session.get(AnalysisJobRow, doc_id)
            if row is not None:
                session.delete(row)
                session.commit()
                deleted = True
        if self.uploads_dir is not None:
            doc_dir = self.uploads_dir / doc_id
            if doc_dir.exists():
                shutil.rmtree(doc_dir, ignore_errors=True)
                deleted = True
        return deleted

    def cleanup_expired(self, now: float | None = None) -> int:
        """Delete expired job rows and return removed count."""
        current = now if now is not None else time.time()
        with Session(self.engine) as session:
            return self._evict_expired_locked(session, current)

    def _evict_expired_locked(self, session: Session, now: float) -> int:
        cutoff = now - self.retention_seconds
        expired = session.exec(
            select(AnalysisJobRow).where(AnalysisJobRow.updated_at <= cutoff)
        ).all()
        removed = 0
        for row in expired:
            doc_id = row.doc_id
            session.delete(row)
            if self.uploads_dir is not None:
                doc_dir = self.uploads_dir / doc_id
                if doc_dir.exists():
                    shutil.rmtree(doc_dir, ignore_errors=True)
            removed += 1
        if removed:
            session.commit()
        return removed


__all__ = ["AnalysisJobStore", "JobStatus"]
