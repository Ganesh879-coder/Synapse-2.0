"""FastAPI application entrypoint for Kavach."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import Settings, get_settings
from app.pipeline import AnalysisPipeline
from app.utils.logging import configure_logging, get_logger
from app.utils.storage import TempDocumentStore, run_cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup initialization and background temp-file cleanup."""
    settings: Settings = app.state.settings
    logger = get_logger("main")
    cleanup_task = asyncio.create_task(run_cleanup_loop(app.state.store))
    logger.info(
        "Kavach backend started",
        extra={"env": settings.env, "retention_seconds": settings.retention_seconds},
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    application = FastAPI(
        title="Kavach Document Forensics API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = cfg
    application.state.store = TempDocumentStore(
        base_dir=cfg.temp_dir,
        retention_seconds=cfg.retention_seconds,
    )
    application.state.pipeline = AnalysisPipeline(
        timeout_seconds=cfg.analyzer_timeout_seconds
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
