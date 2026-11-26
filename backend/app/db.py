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


def normalize_db_url(db_url: str) -> str:
    """Normalize Postgres URLs (e.g., Supabase) to use the psycopg v3 driver."""
    url = db_url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def create_db_engine(db_url: str) -> Engine:
    """Create SQLAlchemy/SQLModel engine (with SQLite WAL or Postgres pooler support)."""
    normalized = normalize_db_url(db_url)
    is_sqlite = normalized.startswith("sqlite")
    if is_sqlite:
        connect_args: dict[str, object] = {"check_same_thread": False}
    elif normalized.startswith("postgresql+psycopg"):
        # Disable server-side prepared statements for Supabase PgBouncer transaction pooler.
        connect_args = {"prepare_threshold": None}
    else:
        connect_args = {}
    engine = create_engine(normalized, connect_args=connect_args, pool_pre_ping=True)
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
