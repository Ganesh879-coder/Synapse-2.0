"""SQLModel database engine and job table definitions."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlmodel import Field, SQLModel, create_engine


class AnalysisJobRow(SQLModel, table=True):
    """Persistent analysis job state and serialized AnalysisResult."""

    __tablename__ = "analysis_jobs"

    doc_id: str = Field(primary_key=True, max_length=64)
    status: str = Field(index=True, max_length=24)
    stage: str | None = Field(default=None, max_length=24)
    result_json: str | None = Field(default=None)
    error: str | None = Field(default=None)
    created_at: float = Field(index=True)
    updated_at: float = Field(index=True)


def create_db_engine(db_url: str) -> Engine:
    """Create SQLAlchemy/SQLModel engine (with SQLite WAL mode when applicable)."""
    is_sqlite = db_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    SQLModel.metadata.create_all(engine)
    if is_sqlite:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.commit()
    return engine


def check_db_reachable(engine: Engine) -> bool:
    """Return True if database responds to SELECT 1."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
