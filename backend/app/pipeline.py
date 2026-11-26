"""Pluggable document analysis pipeline orchestrator.

Fixed execution order:
    ocr -> classify -> rules -> forensics -> scoring -> explain

Each analyzer step reads and updates the shared ``AnalysisContext`` and returns
an ``AnalyzerOutput``. Every analyzer runs inside ``try/except`` with a
per-analyzer timeout so a failure or hang records ``CheckResult(status="skipped")``
without crashing the request.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Protocol

from app.explain import build_explanation_summary
from app.forensics import ForensicsAnalyzer
from app.models.schemas import (
    AnalysisContext,
    AnalysisResult,
    AnalyzerOutput,
    CheckResult,
    Finding,
    PageArtifact,
    PipelineStage,
    Region,
    Signal,
)
from app.ocr import OcrAnalyzer
from app.rules import ClassifyAnalyzer, RulesAnalyzer
from app.scoring import assess_risk
from app.utils.logging import get_logger

logger = get_logger("pipeline")

PIPELINE_ORDER: tuple[str, ...] = (
    "ocr",
    "classify",
    "rules",
    "forensics",
    "scoring",
    "explain",
)

_STAGE_BY_ANALYZER: dict[str, PipelineStage] = {
    "ocr": "reading",
    "classify": "reading",
    "rules": "numbers",
    "forensics": "edits",
}


class DocumentAnalyzer(Protocol):
    """Protocol implemented by every pluggable analyzer stage."""

    name: str

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Read/update shared context and return standardized analyzer output."""
        ...


class AnalysisPipeline:
    """Orchestrates fixed-order analyzers with fault and timeout isolation."""

    def __init__(
        self,
        analyzers: Sequence[DocumentAnalyzer] | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.analyzers: list[DocumentAnalyzer] = (
            list(analyzers)
            if analyzers is not None
            else [
                OcrAnalyzer(),
                ClassifyAnalyzer(),
                RulesAnalyzer(),
                ForensicsAnalyzer(),
            ]
        )
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        ctx: AnalysisContext,
        stage_callback: Callable[[PipelineStage], None] | None = None,
    ) -> AnalysisResult:
        """Execute ocr -> classify -> rules -> forensics -> scoring -> explain."""
        started = time.perf_counter()
        findings: list[Finding] = []
        regions: list[Region] = []
        checks: list[CheckResult] = []
        signals: list[Signal] = []

        for analyzer in self.analyzers:
            if stage_callback is not None:
                stage = _STAGE_BY_ANALYZER.get(analyzer.name)
                if stage is not None:
                    stage_callback(stage)

            output = self._run_single_analyzer(analyzer, ctx)
            if output is None:
                checks.append(
                    CheckResult(
                        name=f"analyzer:{analyzer.name}",
                        status="skipped",
                        detail="Analyzer failed or timed out and was skipped.",
                    )
                )
                continue
            findings.extend(output.findings)
            regions.extend(output.regions)
            checks.extend(output.checks)
            signals.extend(output.signals)
            ctx.extracted_fields.update(output.extracted_fields)

        if stage_callback is not None:
            stage_callback("scoring")

        assessment = assess_risk(
            findings=findings,
            checks=checks,
            signals=signals,
            quality=ctx.quality,
            ocr_words=ctx.ocr_words,
            is_screenshot_like=ctx.is_screenshot_like,
            pages=ctx.pages,
        )
        summary = build_explanation_summary(
            risk_level=assessment.risk_level,
            risk_score=assessment.risk_score,
            findings=findings,
            checks=checks,
        )
        page_artifacts = self._build_page_artifacts(ctx)
        top_heatmap = (
            page_artifacts[0].heatmap_url
            if page_artifacts and page_artifacts[0].heatmap_url
            else ctx.heatmap_url
        )
        processing_ms = int((time.perf_counter() - started) * 1000)

        return AnalysisResult(
            doc_id=ctx.doc_id,
            doc_type=ctx.doc_type,
            risk_score=assessment.risk_score,
            risk_level=assessment.risk_level,
            verdict=summary.verdict,
            findings=findings,
            regions=regions,
            extracted_fields={
                key: field.model_dump() for key, field in ctx.extracted_fields.items()
            },
            checks=checks,
            heatmap_url=top_heatmap,
            processing_ms=processing_ms,
            pages=page_artifacts,
            confidence=assessment.confidence,
            score_breakdown=assessment.score_breakdown,
            summary=summary,
        )

    def _build_page_artifacts(self, ctx: AnalysisContext) -> list[PageArtifact]:
        """Construct API URLs for each rendered page and its heatmap overlay."""
        artifacts: list[PageArtifact] = []
        for page in ctx.pages:
            heatmap_path = page.image_path.parent / f"heatmap_page_{page.page}.png"
            heatmap_url = (
                f"/api/analysis/{ctx.doc_id}/heatmap/{page.page}"
                if heatmap_path.is_file()
                else None
            )
            artifacts.append(
                PageArtifact(
                    page=page.page,
                    width=page.width,
                    height=page.height,
                    image_url=f"/api/analysis/{ctx.doc_id}/page/{page.page}",
                    heatmap_url=heatmap_url,
                )
            )
        return artifacts

    def _run_single_analyzer(
        self,
        analyzer: DocumentAnalyzer,
        ctx: AnalysisContext,
    ) -> AnalyzerOutput | None:
        """Run one analyzer with timeout and exception isolation."""
        analyzer_name = getattr(analyzer, "name", type(analyzer).__name__)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(analyzer.run, ctx)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FuturesTimeoutError:
            future.cancel()
            logger.warning(
                "Analyzer timed out and was isolated",
                extra={
                    "doc_id": ctx.doc_id,
                    "analyzer": analyzer_name,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            return None
        except Exception as exc:
            logger.warning(
                "Analyzer failed and was isolated",
                extra={
                    "doc_id": ctx.doc_id,
                    "analyzer": analyzer_name,
                    "error": type(exc).__name__,
                },
            )
            return None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
