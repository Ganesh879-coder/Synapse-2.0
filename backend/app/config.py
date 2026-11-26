"""Runtime configuration for the Kavach backend."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    env: str = field(default_factory=lambda: os.getenv("KAVACH_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("KAVACH_LOG_LEVEL", "INFO"))
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("DATA_DIR") or Path(tempfile.gettempdir()) / "kavach_data"
        )
    )
    db_url: str = field(default_factory=lambda: os.getenv("DB_URL", ""))
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("KAVACH_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
    )
    file_ttl_minutes: int = field(
        default_factory=lambda: int(os.getenv("FILE_TTL_MINUTES", "60"))
    )
    retention_seconds: int = field(
        default_factory=lambda: int(
            os.getenv("KAVACH_RETENTION_SECONDS")
            or str(int(os.getenv("FILE_TTL_MINUTES", "60")) * 60)
        )
    )
    delete_after_view: bool = field(
        default_factory=lambda: os.getenv("DELETE_AFTER_VIEW", "false").lower()
        in {"1", "true", "yes"}
    )
    pdf_dpi: int = field(default_factory=lambda: int(os.getenv("KAVACH_PDF_DPI", "200")))
    max_pixels: int = field(
        default_factory=lambda: int(os.getenv("MAX_PIXELS", "25000000"))
    )
    max_pdf_pages: int = field(
        default_factory=lambda: int(os.getenv("MAX_PDF_PAGES", "10"))
    )
    analyzer_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("KAVACH_ANALYZER_TIMEOUT_SECONDS", "45.0"))
    )
    ocr_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("KAVACH_OCR_TIMEOUT_SECONDS", "60.0"))
    )
    request_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT_SECONDS", "120.0"))
    )
    max_concurrent_jobs: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
    )
    max_queue_length: int = field(
        default_factory=lambda: int(os.getenv("MAX_QUEUE_LENGTH", "16"))
    )
    api_keys: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(os.getenv("KAVACH_API_KEYS", ""))
    )
    rate_limit: str = field(
        default_factory=lambda: os.getenv("KAVACH_RATE_LIMIT", "30/minute")
    )
    trusted_proxies: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1"))
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(
            os.getenv("CORS_ORIGINS")
            or os.getenv("KAVACH_CORS_ORIGINS")
            or "http://localhost:5173"
        )
    )
    sentry_dsn: str = field(default_factory=lambda: os.getenv("SENTRY_DSN", "").strip())
    temp_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("KAVACH_TEMP_DIR")
            or (
                Path(os.getenv("DATA_DIR") or Path(tempfile.gettempdir()) / "kavach_data")
                / "uploads"
            )
        )
    )

    @property
    def resolved_db_url(self) -> str:
        """Return DB_URL or default SQLite database inside DATA_DIR."""
        if self.db_url.strip():
            return self.db_url.strip()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        db_path = (self.data_dir / "kavach.db").resolve()
        return f"sqlite:///{db_path.as_posix()}"


def get_settings() -> Settings:
    """Return current application settings."""
    return Settings()
