"""API endpoints for health checks, async analysis jobs, artifacts, and PDF reports."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.jobs import AnalysisJobStore
from app.api.report import build_pdf_report
from app.config import Settings, get_settings
from app.models.schemas import (
    AnalysisContext,
    AnalysisStatusResponse,
    AnalyzeQueuedResponse,
    PipelineStage,
)
from app.pipeline import AnalysisPipeline
from app.utils.logging import get_logger
from app.utils.pdf import render_document_pages
from app.utils.storage import TempDocumentStore
from app.utils.validation import FileTooLargeError, UnsupportedMediaError, validate_upload_bytes

logger = get_logger("api")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def get_pipeline(request: Request) -> AnalysisPipeline:
    """Resolve the shared AnalysisPipeline from application state."""
    return cast(AnalysisPipeline, request.app.state.pipeline)


def get_store(request: Request) -> TempDocumentStore:
    """Resolve the shared TempDocumentStore from application state."""
    return cast(TempDocumentStore, request.app.state.store)


def get_jobs(request: Request) -> AnalysisJobStore:
    """Resolve the shared AnalysisJobStore from application state."""
    return cast(AnalysisJobStore, request.app.state.jobs)


def _execute_analysis_job(
    doc_id: str,
    source_path: Path,
    mime_type: str,
    raw_bytes: bytes,
    doc_type: str,
    dpi: int,
    pipeline: AnalysisPipeline,
    jobs: AnalysisJobStore,
) -> None:
    """Background worker that renders pages, runs the pipeline, and updates job state."""
    pages_dir = source_path.parent / "pages"
    try:
        jobs.set_stage(doc_id, "reading")
        pages = render_document_pages(
            source_path=source_path,
            mime_type=mime_type,
            output_dir=pages_dir,
            dpi=dpi,
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

        result = pipeline.run(ctx, stage_callback=_on_stage)
        jobs.set_done(doc_id, result)
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
    except Exception as exc:
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
    """Liveness probe endpoint."""
    return {"status": "ok", "service": "kavach"}


@router.post("/api/analyze", response_model=AnalyzeQueuedResponse)
@limiter.limit("30/minute")
async def analyze_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    doc_type: Annotated[str, Form()] = "unknown",
    settings: Settings = Depends(get_settings),
    pipeline: AnalysisPipeline = Depends(get_pipeline),
    store: TempDocumentStore = Depends(get_store),
    jobs: AnalysisJobStore = Depends(get_jobs),
) -> AnalyzeQueuedResponse:
    """Validate uploaded JPG/PNG/PDF by magic bytes and queue background analysis."""
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

    background_tasks.add_task(
        _execute_analysis_job,
        doc_id=doc_id,
        source_path=source_path,
        mime_type=mime_type,
        raw_bytes=raw_bytes,
        doc_type=doc_type,
        dpi=settings.pdf_dpi,
        pipeline=pipeline,
        jobs=jobs,
    )
    return AnalyzeQueuedResponse(doc_id=doc_id, status="queued")


@router.get("/api/analysis/{doc_id}", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    doc_id: str,
    jobs: AnalysisJobStore = Depends(get_jobs),
) -> AnalysisStatusResponse:
    """Poll job status, current stage, and completed AnalysisResult."""
    if not doc_id.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc_id.")
    job = jobs.get(doc_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return job


def _resolve_page_file(store: TempDocumentStore, doc_id: str, filename: str) -> Path:
    if "/" in filename or "\\" in filename or ".." in filename or not doc_id.isalnum():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path.")
    target = (store.base_dir / doc_id / "pages" / filename).resolve()
    base_resolved = store.base_dir.resolve()
    if not str(target).startswith(str(base_resolved)) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return target


@router.get("/api/analysis/{doc_id}/page/{page_num}")
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


@router.get("/api/analysis/{doc_id}/heatmap/{page_num}")
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


@router.get("/api/analysis/{doc_id}/report.pdf")
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


@router.get("/api/artifacts/{doc_id}/{filename}")
async def get_artifact(
    doc_id: str,
    filename: str,
    store: TempDocumentStore = Depends(get_store),
) -> FileResponse:
    """Serve a generated heatmap or page artifact from the temporary store."""
    target = _resolve_page_file(store, doc_id, filename)
    return FileResponse(target, media_type="image/png")
