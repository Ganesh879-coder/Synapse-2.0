"""OCR analyzer wiring preprocessing and RapidOCR/Tesseract."""

from __future__ import annotations

from app.models.schemas import AnalysisContext, AnalyzerOutput
from app.ocr.engine import _get_rapid_ocr, extract_ocr_words, is_tesseract_available


class OcrAnalyzer:
    """Per-page OCR analyzer populating ctx.ocr_words."""

    name: str = "ocr"

    def __init__(self) -> None:
        # Warm up RapidOCR ONNX session at pipeline construction so first page doesn't time out.
        _get_rapid_ocr()

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Run OCR per page and populate ctx.ocr_words."""
        for page in ctx.pages:
            words = extract_ocr_words(page)
            if words:
                ctx.ocr_words[page.page] = words
        return AnalyzerOutput(analyzer_name=self.name)


__all__ = ["OcrAnalyzer", "is_tesseract_available"]
