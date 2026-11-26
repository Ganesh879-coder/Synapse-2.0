"""API endpoints for health/readiness, auth, metrics, async jobs, artifacts, and PDFs."""

from __future__ import annotations

import shutil
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from slowapi import Limiter

from app.api.auth import ApiKeyRegistry, get_rate_limit_key, require_api_key
from app.api.jobs import AnalysisJobStore
from app.api.metrics import MetricsRegistry
from app.api.report import build_pdf_report
from app.api.worker import BoundedAnalysisPool, QueueFullError
from app.config import Settings, get_settings
from app.db import check_db_reachable
from app.models.schemas import (
    AnalysisContext,
    AnalysisStatusResponse,
    AnalyzeQueuedResponse,
    PipelineStage,
)
from app.pipeline import AnalysisPipeline
from app.utils.logging import get_logger
from app.utils.pdf import DocumentLimitError, EncryptedPdfError, render_document_pages
from app.utils.storage import TempDocumentStore
from app.utils.validation import FileTooLargeError, UnsupportedMediaError, validate_upload_bytes

logger = get_logger("api")
router = APIRouter()
limiter = Limiter(key_func=get_rate_limit_key)
rate_limit_var: ContextVar[str | None] = ContextVar("kavach_rate_limit", default=None)


class LoginRequest(BaseModel):
    """Payload for POST /api/auth/login."""

    access_key: str


def get_pipeline(request: Request) -> AnalysisPipeline:
    """Resolve the shared AnalysisPipeline from application state."""
    return cast(AnalysisPipeline, request.app.state.pipeline)


def get_store(request: Request) -> TempDocumentStore:
    """Resolve the shared TempDocumentStore from application state."""
    return cast(TempDocumentStore, request.app.state.store)


def get_jobs(request: Request) -> AnalysisJobStore:
    """Resolve the shared AnalysisJobStore from application state."""
    return cast(AnalysisJobStore, request.app.state.jobs)


def get_pool(request: Request) -> BoundedAnalysisPool:
    """Resolve the shared BoundedAnalysisPool from application state."""
    return cast(BoundedAnalysisPool, request.app.state.pool)


def get_metrics(request: Request) -> MetricsRegistry:
    """Resolve the shared MetricsRegistry from application state."""
    return cast(MetricsRegistry, request.app.state.metrics)


def get_app_settings(request: Request) -> Settings:
    """Resolve the active Settings from application state."""
    return cast(Settings, getattr(request.app.state, "settings", get_settings()))


def _dynamic_rate_limit() -> str:
    return rate_limit_var.get() or get_settings().rate_limit


def _execute_analysis_job(
    doc_id: str,
    source_path: Path,
    mime_type: str,
    raw_bytes: bytes,
    doc_type: str,
    settings: Settings,
    pipeline: AnalysisPipeline,
    jobs: AnalysisJobStore,
    metrics: MetricsRegistry,
) -> None:
    """Worker-pool task that renders pages, runs the pipeline, and updates SQLite."""
    pages_dir = source_path.parent / "pages"
    metrics.inc_started()
    try:
        jobs.set_stage(doc_id, "reading")
        pages = render_document_pages(
            source_path=source_path,
            mime_type=mime_type,
            output_dir=pages_dir,
            dpi=settings.pdf_dpi,
            max_pdf_pages=settings.max_pdf_pages,
            max_pixels=settings.max_pixels,
        )
        ctx = AnalysisContext(
            doc_id=doc_id,
            file_bytes=raw_bytes,
            mime=mime_type,
            pages=pages,
            doc_type=doc_type,
        )

        def _on_stage(stage: PipelineStage) -> None:
            jobs.set_stage(doc_id, stage)

        result = pipeline.run(
            ctx,
            stage_callback=_on_stage,
            analyzer_observer=metrics.observe_analyzer,
        )
        jobs.set_done(doc_id, result)
        metrics.inc_finished()
        logger.info(
            "Document analysis completed",
            extra={
                "doc_id": doc_id,
                "mime_type": mime_type,
                "page_count": len(pages),
                "risk_level": result.risk_level,
                "processing_ms": result.processing_ms,
            },
        )
    except (EncryptedPdfError, DocumentLimitError) as exc:
        metrics.inc_failed()
        logger.warning(
            "Document rejected by limits/encryption guard",
            extra={"doc_id": doc_id, "mime_type": mime_type, "error": type(exc).__name__},
        )
        jobs.set_failed(doc_id, str(exc))
    except Exception as exc:
        metrics.inc_failed()
        logger.warning(
            "Document analysis job failed",
            extra={"doc_id": doc_id, "mime_type": mime_type, "error": type(exc).__name__},
        )
        jobs.set_failed(
            doc_id,
            f"Unable to process this document ({type(exc).__name__}). Please try another file.",
        )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Public liveness probe endpoint."""
    return {"status": "ok", "service": "kavach"}


@router.get("/ready", dependencies=[Depends(require_api_key)])
async def readiness_check(
    request: Request,
    settings: Settings = Depends(get_settings),
    jobs: AnalysisJobStore = Depends(get_jobs),
) -> JSONResponse:
    """Readiness probe: OCR warmed up, DB reachable, and disk space available."""
    ocr_ready = bool(getattr(request.app.state, "ocr_ready", False))
    db_ok = check_db_reachable(jobs.engine)
    disk_free_mb = shutil.disk_usage(settings.data_dir).free // (1024 * 1024)
    disk_ok = disk_free_mb >= 50
    ready = ocr_ready and db_ok and disk_ok
    code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=code,
        content={
            "status": "ready" if ready else "not_ready",
            "ocr_ready": ocr_ready,
            "db_reachable": db_ok,
            "disk_free_mb": disk_free_mb,
        },
    )


@router.get("/api/metrics", dependencies=[Depends(require_api_key)])
async def prometheus_metrics(
    pool: BoundedAnalysisPool = Depends(get_pool),
    metrics: MetricsRegistry = Depends(get_metrics),
) -> PlainTextResponse:
    """Prometheus-format metrics endpoint behind the access key."""
    return PlainTextResponse(
        metrics.render_prometheus(pool.queue_depth),
        media_type="text/plain; version=0.0.4",
    )


@router.post("/api/auth/login")
async def auth_login(payload: LoginRequest, request: Request) -> JSONResponse:
    """Verify an access key and set an HttpOnly session cookie."""
    registry: ApiKeyRegistry = request.app.state.key_registry
    if not registry.verify(payload.access_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access code.",
        )
    resp = JSONResponse({"status": "authenticated"})
    resp.set_cookie(
        key="kavach_key",
        value=payload.access_key.strip(),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return resp


@router.post("/api/auth/logout")
async def auth_logout() -> JSONResponse:
    """Clear the access key cookie."""
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie("kavach_key")
    return resp


@router.post(
    "/api/analyze",
    response_model=AnalyzeQueuedResponse,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(_dynamic_rate_limit)
async def analyze_document(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    doc_type: Annotated[str, Form()] = "unknown",
    settings: Settings = Depends(get_app_settings),
    pipeline: AnalysisPipeline = Depends(get_pipeline),
    store: TempDocumentStore = Depends(get_store),
    jobs: AnalysisJobStore = Depends(get_jobs),
    pool: BoundedAnalysisPool = Depends(get_pool),
    metrics: MetricsRegistry = Depends(get_metrics),
) -> AnalyzeQueuedResponse:
    """Validate uploaded JPG/PNG/PDF by magic bytes and enqueue in bounded worker pool."""
    _ = request
    try:
        raw_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file stream.",
        ) from exc

    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        mime_type = validate_upload_bytes(raw_bytes, settings.max_upload_bytes)
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except UnsupportedMediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc

    doc_id = uuid.uuid4().hex
    try:
        source_path = store.save_original(doc_id, mime_type, raw_bytes)
    except Exception as exc:
        logger.warning(
            "Failed to persist uploaded file",
            extra={"doc_id": doc_id, "error": type(exc).__name__},
        )
        jobs.create_queued(doc_id)
        jobs.set_failed(doc_id, "Failed to store uploaded file for processing.")
        return AnalyzeQueuedResponse(doc_id=doc_id, status="queued")

    jobs.create_queued(doc_id)
    try:
        pool.submit(
            _execute_analysis_job,
            doc_id=doc_id,
            source_path=source_path,
            mime_type=mime_type,
            raw_bytes=raw_bytes,
            doc_type=doc_type,
            settings=settings,
            pipeline=pipeline,
            jobs=jobs,
            metrics=metrics,
        )
    except QueueFullError as exc:
        jobs.delete_job(doc_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return AnalyzeQueuedResponse(doc_id=doc_id, status="queued")


@router.get(
    "/api/analysis/{doc_id}",
    response_model=AnalysisStatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_analysis_status(
    doc_id: str,
    settings: Settings = Depends(get_app_settings),
    jobs: AnalysisJobStore = Depends(get_jobs),
) -> AnalysisStatusResponse:
    """Poll job status, current stage, and completed AnalysisResult."""
    if not doc_id.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc_id.")
    job = jobs.get(doc_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    if settings.delete_after_view and job.status == "done":
        jobs.redact_extracted_fields(doc_id)
    return job


@router.delete("/api/analysis/{doc_id}", dependencies=[Depends(require_api_key)])
async def delete_analysis(
    doc_id: str,
    jobs: AnalysisJobStore = Depends(get_jobs),
) -> dict[str, str]:
    """Immediately delete stored files and database record for an analysis."""
    if not doc_id.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc_id.")
    if not jobs.delete_job(doc_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return {"status": "deleted", "doc_id": doc_id}


def _resolve_page_file(store: TempDocumentStore, doc_id: str, filename: str) -> Path:
    if "/" in filename or "\\" in filename or ".." in filename or not doc_id.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path.")
    target = (store.base_dir / doc_id / "pages" / filename).resolve()
    base_resolved = store.base_dir.resolve()
    if not str(target).startswith(str(base_resolved)) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return target


@router.get("/api/analysis/{doc_id}/page/{page_num}", dependencies=[Depends(require_api_key)])
async def get_page_image(
    doc_id: str,
    page_num: int,
    store: TempDocumentStore = Depends(get_store),
) -> FileResponse:
    """Return the original rendered PNG for the requested page."""
    if page_num < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid page number.")
    target = _resolve_page_file(store, doc_id, f"page_{page_num}.png")
    return FileResponse(target, media_type="image/png")


@router.get("/api/analysis/{doc_id}/heatmap/{page_num}", dependencies=[Depends(require_api_key)])
async def get_heatmap_image(
    doc_id: str,
    page_num: int,
    store: TempDocumentStore = Depends(get_store),
) -> FileResponse:
    """Return the heatmap overlay PNG for the requested page (falling back to page PNG)."""
    if page_num < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid page number.")
    try:
        target = _resolve_page_file(store, doc_id, f"heatmap_page_{page_num}.png")
    except HTTPException:
        target = _resolve_page_file(store, doc_id, f"page_{page_num}.png")
    return FileResponse(target, media_type="image/png")


@router.get("/api/analysis/{doc_id}/report.pdf", dependencies=[Depends(require_api_key)])
async def get_pdf_report(
    doc_id: str,
    jobs: AnalysisJobStore = Depends(get_jobs),
    store: TempDocumentStore = Depends(get_store),
) -> Response:
    """Generate and return a one-page PDF verification report."""
    if not doc_id.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc_id.")
    job = jobs.get(doc_id)
    if job is None or job.result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completed analysis not found.",
        )

    pages_dir = store.base_dir / doc_id / "pages"
    annotated_path: Path | None = pages_dir / "heatmap_page_1.png"
    if annotated_path is not None and not annotated_path.is_file():
        fallback = pages_dir / "page_1.png"
        annotated_path = fallback if fallback.is_file() else None

    pdf_bytes = build_pdf_report(job.result, annotated_path)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="kavach_{doc_id}.pdf"'},
    )


@router.get("/api/artifacts/{doc_id}/{filename}", dependencies=[Depends(require_api_key)])
async def get_artifact(
    doc_id: str,
    filename: str,
    store: TempDocumentStore = Depends(get_store),
) -> FileResponse:
    """Serve a generated heatmap or page artifact from the temporary store."""
    target = _resolve_page_file(store, doc_id, filename)
    return FileResponse(target, media_type="image/png")
