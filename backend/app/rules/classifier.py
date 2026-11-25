"""Stub document classifier analyzer."""

from __future__ import annotations

from app.models.schemas import AnalysisContext, AnalyzerOutput


class ClassifyAnalyzer:
    """Document type classifier stage (stub)."""

    name: str = "classify"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Classify document type from OCR words and layout (stub)."""
        _ = ctx
        return AnalyzerOutput(analyzer_name=self.name)
