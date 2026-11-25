"""FastAPI application entrypoint for Kavach."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.jobs import AnalysisJobStore
from app.api.routes import limiter, router
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
    """Create and configure the FastAPI application with rate limiting and error handlers."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    application = FastAPI(
        title="Kavach Document Forensics API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = cfg
    application.state.limiter = limiter
    application.state.store = TempDocumentStore(
        base_dir=cfg.temp_dir,
        retention_seconds=cfg.retention_seconds,
    )
    application.state.jobs = AnalysisJobStore(retention_seconds=cfg.retention_seconds)
    application.state.pipeline = AnalysisPipeline(
        timeout_seconds=cfg.analyzer_timeout_seconds
    )

    @application.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        _ = (request, exc)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "rate_limit_exceeded", "detail": "Too many requests; retry later."},
        )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        _ = request
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": f"http_{exc.status_code}", "detail": str(exc.detail)},
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _ = request
        get_logger("main").error("Unhandled server error", extra={"error": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "internal_server_error", "detail": "An internal error occurred."},
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
