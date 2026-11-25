"""API endpoints for health checks and document analysis."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.models.schemas import AnalysisContext, AnalysisResult
from app.pipeline import AnalysisPipeline
from app.utils.logging import get_logger
from app.utils.pdf import render_document_pages
from app.utils.storage import TempDocumentStore
from app.utils.validation import FileTooLargeError, UnsupportedMediaError, validate_upload_bytes

logger = get_logger("api")
router = APIRouter()


def get_pipeline(request: Request) -> AnalysisPipeline:
    """Resolve the shared AnalysisPipeline from application state."""
    return cast(AnalysisPipeline, request.app.state.pipeline)


def get_store(request: Request) -> TempDocumentStore:
    """Resolve the shared TempDocumentStore from application state."""
    return cast(TempDocumentStore, request.app.state.store)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok", "service": "kavach"}


@router.post("/api/analyze", response_model=AnalysisResult)
async def analyze_document(
    file: Annotated[UploadFile, File(...)],
    doc_type: Annotated[str, Form()] = "unknown",
    settings: Settings = Depends(get_settings),
    pipeline: AnalysisPipeline = Depends(get_pipeline),
    store: TempDocumentStore = Depends(get_store),
) -> AnalysisResult:
    """Validate uploaded JPG/PNG/PDF by magic bytes and run the analysis pipeline."""
    raw_bytes = await file.read()
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
    source_path = store.save_original(doc_id, mime_type, raw_bytes)
    pages_dir = source_path.parent / "pages"

    try:
        pages = render_document_pages(
            source_path=source_path,
            mime_type=mime_type,
            output_dir=pages_dir,
            dpi=settings.pdf_dpi,
        )
    except Exception as exc:
        logger.warning(
            "Failed to render document pages",
            extra={"doc_id": doc_id, "mime_type": mime_type, "error": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to decode the uploaded document.",
        ) from exc

    ctx = AnalysisContext(
        doc_id=doc_id,
        file_bytes=raw_bytes,
        mime=mime_type,
        pages=pages,
        doc_type=doc_type,
    )
    result = pipeline.run(ctx)
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
    return result


@router.get("/api/artifacts/{doc_id}/{filename}")
async def get_artifact(
    doc_id: str,
    filename: str,
    store: TempDocumentStore = Depends(get_store),
) -> FileResponse:
    """Serve a generated heatmap or page artifact from the temporary store."""
    if "/" in filename or "\\" in filename or ".." in filename or not doc_id.isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid artifact path."
        )
    target = (store.base_dir / doc_id / "pages" / filename).resolve()
    base_resolved = store.base_dir.resolve()
    if not str(target).startswith(str(base_resolved)) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return FileResponse(target, media_type="image/png")
