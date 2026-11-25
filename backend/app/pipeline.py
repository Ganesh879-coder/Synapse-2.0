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
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Protocol, Sequence

from app.explain import build_verdict
from app.forensics import ForensicsAnalyzer
from app.models.schemas import (
    AnalysisContext,
    AnalysisResult,
    AnalyzerOutput,
    CheckResult,
    Finding,
    Region,
    Signal,
)
from app.ocr import OcrAnalyzer
from app.rules import ClassifyAnalyzer, RulesAnalyzer
from app.scoring import compute_risk
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

    def run(self, ctx: AnalysisContext) -> AnalysisResult:
        """Execute ocr -> classify -> rules -> forensics -> scoring -> explain."""
        started = time.perf_counter()
        findings: list[Finding] = []
        regions: list[Region] = []
        checks: list[CheckResult] = []
        signals: list[Signal] = []

        for analyzer in self.analyzers:
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

        risk_score, risk_level = compute_risk(findings, checks, signals)
        verdict = build_verdict(risk_level, findings)
        processing_ms = int((time.perf_counter() - started) * 1000)

        return AnalysisResult(
            doc_id=ctx.doc_id,
            doc_type=ctx.doc_type,
            risk_score=risk_score,
            risk_level=risk_level,
            verdict=verdict,
            findings=findings,
            regions=regions,
            extracted_fields={
                key: field.model_dump() for key, field in ctx.extracted_fields.items()
            },
            checks=checks,
            heatmap_url=ctx.heatmap_url,
            processing_ms=processing_ms,
        )

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
