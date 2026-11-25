"""Runtime configuration for the Kavach backend."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    env: str = field(default_factory=lambda: os.getenv("KAVACH_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("KAVACH_LOG_LEVEL", "INFO"))
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("KAVACH_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
    )
    retention_seconds: int = field(
        default_factory=lambda: int(os.getenv("KAVACH_RETENTION_SECONDS", "3600"))
    )
    pdf_dpi: int = field(default_factory=lambda: int(os.getenv("KAVACH_PDF_DPI", "200")))
    analyzer_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("KAVACH_ANALYZER_TIMEOUT_SECONDS", "15.0"))
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.getenv("KAVACH_CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
    )
    temp_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("KAVACH_TEMP_DIR") or Path(tempfile.gettempdir()) / "kavach_uploads"
        )
    )


def get_settings() -> Settings:
    """Return current application settings."""
    return Settings()
