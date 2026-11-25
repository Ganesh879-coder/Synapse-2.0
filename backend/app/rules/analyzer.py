"""Stub consistency and format rules analyzer returning empty results."""

from __future__ import annotations

from app.models.schemas import AnalysisContext, AnalyzerOutput


class RulesAnalyzer:
    """Document consistency and format validation analyzer (stub)."""

    name: str = "rules"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Run format and internal consistency checks (stub)."""
        _ = ctx
        return AnalyzerOutput(analyzer_name=self.name)
