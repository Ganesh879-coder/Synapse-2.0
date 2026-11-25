"""Shared Pydantic schemas used across all Kavach analyzers, context, and APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FindingCategory = Literal["visual", "metadata", "consistency", "format"]
SeverityLevel = Literal["low", "medium", "high", "critical"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
CheckStatus = Literal["pass", "fail", "warn", "skipped"]


def _validate_normalized_bbox(
    value: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Ensure all bounding box coordinates (x0, y0, x1, y1) are in [0.0, 1.0]."""
    for coord in value:
        if not 0.0 <= coord <= 1.0:
            raise ValueError("bbox coordinates must be normalized between 0.0 and 1.0")
    return value


class Region(BaseModel):
    """Normalized bounding box on a document page indicating an anomaly region."""

    id: str
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    score: float = Field(ge=0.0, le=1.0)
    reason: str

    @field_validator("bbox")
    @classmethod
    def validate_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """Validate normalized bounding box coordinates."""
        return _validate_normalized_bbox(value)


class Finding(BaseModel):
    """Single tampering indicator or anomaly detected by an analyzer."""

    id: str
    category: FindingCategory
    severity: SeverityLevel
    title: str
    plain_explanation: str
    technical_detail: str
    evidence_region_ids: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    """Result of a discrete consistency or format verification check."""

    name: str
    status: CheckStatus
    detail: str


class OcrWord(BaseModel):
    """Single OCR token with confidence and normalized bounding box."""

    text: str
    conf: float = Field(ge=0.0, le=1.0)
    bbox: tuple[float, float, float, float]

    @field_validator("bbox")
    @classmethod
    def validate_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """Validate normalized OCR word bounding box."""
        return _validate_normalized_bbox(value)


class ExtractedField(BaseModel):
    """Structured field extracted from a document page."""

    value: Any
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float] | None = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(
        cls, value: tuple[float, float, float, float] | None
    ) -> tuple[float, float, float, float] | None:
        """Validate optional normalized bounding box."""
        if value is None:
            return None
        return _validate_normalized_bbox(value)


class Signal(BaseModel):
    """Weighted indicator signal emitted by analyzers for the scoring stage."""

    name: str
    category: FindingCategory
    weight_hint: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    region_ids: list[str] = Field(default_factory=list)


class PageImage(BaseModel):
    """Rendered page image passed into per-page analyzers."""

    page: int = Field(ge=1)
    image_path: Path
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class AnalysisContext(BaseModel):
    """Shared pipeline context read and updated across all pipeline stages."""

    doc_id: str
    file_bytes: bytes
    mime: str
    pages: list[PageImage] = Field(default_factory=list)
    ocr_words: dict[int, list[OcrWord]] = Field(default_factory=dict)
    doc_type: str = "unknown"
    extracted_fields: dict[str, ExtractedField] = Field(default_factory=dict)
    quality: dict[int, float] = Field(default_factory=dict)
    is_screenshot_like: bool = False
    heatmap_url: str | None = None

    @field_validator("quality")
    @classmethod
    def validate_quality_scores(cls, value: dict[int, float]) -> dict[int, float]:
        """Ensure per-page quality scores stay within [0.0, 1.0]."""
        for page, score in value.items():
            if page < 1:
                raise ValueError("quality page numbers must be >= 1")
            if not 0.0 <= score <= 1.0:
                raise ValueError("quality scores must be between 0.0 and 1.0")
        return value


class AnalyzerOutput(BaseModel):
    """Standardized output returned by every pluggable analyzer."""

    analyzer_name: str = ""
    regions: list[Region] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    extracted_fields: dict[str, ExtractedField] = Field(default_factory=dict)
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    signals: list[Signal] = Field(default_factory=list)


class ScoreContribution(BaseModel):
    """Single signal or check contribution to the final risk score."""

    signal: str
    label: str
    contribution: float = Field(ge=0.0, le=100.0)


class ExplanationSummary(BaseModel):
    """Plain-English summary, reasons, next actions, and disclaimer."""

    verdict: str
    top_reasons: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    disclaimer: str


class PageArtifact(BaseModel):
    """Metadata and URLs for a rendered document page and its heatmap."""

    page: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    image_url: str
    heatmap_url: str | None = None


class AnalysisResult(BaseModel):
    """Top-level response contract returned by the analysis pipeline and API."""

    doc_id: str
    doc_type: str
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    verdict: str
    findings: list[Finding] = Field(default_factory=list)
    regions: list[Region] = Field(default_factory=list)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    checks: list[CheckResult] = Field(default_factory=list)
    heatmap_url: str | None = None
    processing_ms: int = Field(ge=0)
    pages: list[PageArtifact] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    score_breakdown: list[ScoreContribution] = Field(default_factory=list)
    summary: ExplanationSummary | None = None


JobStatus = Literal["queued", "processing", "done", "failed"]
PipelineStage = Literal["reading", "edits", "numbers", "scoring"]


class AnalyzeQueuedResponse(BaseModel):
    """Immediate response returned by POST /api/analyze."""

    doc_id: str
    status: Literal["queued"] = "queued"


class AnalysisStatusResponse(BaseModel):
    """Polling response returned by GET /api/analysis/{doc_id}."""

    status: JobStatus
    stage: PipelineStage | None = None
    result: AnalysisResult | None = None
    error: str | None = None
