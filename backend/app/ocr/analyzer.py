"""Stub OCR analyzer returning empty results, with optional Tesseract guard."""

from __future__ import annotations

from typing import Any

from app.models.schemas import AnalysisContext, AnalyzerOutput

try:  # Optional dependency; never fail if Tesseract / pytesseract is absent.
    import pytesseract as _pytesseract
except ImportError:
    _pytesseract = None


def is_tesseract_available() -> bool:
    """Return True if the optional pytesseract package is importable."""
    return _pytesseract is not None


class OcrAnalyzer:
    """Per-page OCR and structured field extraction analyzer (stub)."""

    name: str = "ocr"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Extract document text and fields into context (stub)."""
        _ = ctx
        return AnalyzerOutput(analyzer_name=self.name)


def get_optional_tesseract() -> Any:
    """Return pytesseract module if installed, otherwise None."""
    return _pytesseract
