"""FastAPI application entrypoint for Kavach."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.auth import ApiKeyRegistry
from app.api.jobs import AnalysisJobStore
from app.api.metrics import MetricsRegistry
from app.api.routes import limiter, rate_limit_var, router
from app.api.worker import BoundedAnalysisPool
from app.config import Settings, get_settings
from app.ocr.engine import _get_rapid_ocr
from app.pipeline import AnalysisPipeline
from app.utils.logging import configure_logging, get_logger, request_id_var
from app.utils.storage import TempDocumentStore, run_cleanup_loop


def _init_optional_sentry(dsn: str, env: str) -> None:
    """Initialize Sentry with PII disabled and a before_send scrubber if SENTRY_DSN is set."""
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        return

    def _scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
        _ = hint
        req = event.get("request")
        if isinstance(req, dict):
            req.pop("data", None)
            req.pop("cookies", None)
            headers = req.get("headers")
            if isinstance(headers, dict):
                for key in list(headers):
                    if key.lower() in {"x-kavach-key", "cookie", "authorization"}:
                        headers[key] = "[REDACTED]"
        extra = event.get("extra")
        if isinstance(extra, dict):
            for key in list(extra):
                if "text" in key.lower() or "extracted" in key.lower():
                    extra[key] = "[REDACTED]"
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        send_default_pii=False,
        before_send=_scrub_event,  # type: ignore[arg-type]
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup initialization, interrupted job recovery, and graceful shutdown."""
    settings: Settings = app.state.settings
    logger = get_logger("main")
    recovered = app.state.jobs.recover_interrupted_jobs()
    if recovered:
        logger.warning("Marked interrupted jobs as failed", extra={"recovered_count": recovered})

    _get_rapid_ocr()
    app.state.ocr_ready = True
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
        app.state.pool.shutdown(wait=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application with auth, rate limiting, and headers."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)
    _init_optional_sentry(cfg.sentry_dsn, cfg.env)

    application = FastAPI(
        title="Kavach Document Forensics API",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.settings = cfg
    application.state.limiter = limiter
    application.state.ocr_ready = False
    application.state.key_registry = ApiKeyRegistry(cfg.api_keys)
    application.state.store = TempDocumentStore(
        base_dir=cfg.temp_dir,
        retention_seconds=cfg.retention_seconds,
    )
    application.state.jobs = AnalysisJobStore(
        db_url=cfg.resolved_db_url,
        retention_seconds=cfg.retention_seconds,
        uploads_dir=cfg.temp_dir,
    )
    application.state.pool = BoundedAnalysisPool(
        max_workers=cfg.max_concurrent_jobs,
        max_queue_length=cfg.max_queue_length,
    )
    application.state.metrics = MetricsRegistry()
    application.state.pipeline = AnalysisPipeline(
        timeout_seconds=cfg.analyzer_timeout_seconds
    )

    @application.middleware("http")
    async def request_context_and_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(req_id)
        rl_token = rate_limit_var.set(cfg.rate_limit)
        try:
            response = await call_next(request)
        finally:
            rate_limit_var.reset(rl_token)
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'"
        )
        return response

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
