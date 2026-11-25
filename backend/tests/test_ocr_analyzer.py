"""Tests for the OcrAnalyzer stub and optional Tesseract guard."""

from pathlib import Path

from app.models.schemas import AnalysisContext, AnalyzerOutput, PageImage
from app.ocr import OcrAnalyzer
from app.ocr.analyzer import is_tesseract_available


def test_ocr_analyzer_returns_empty_output(tmp_path: Path) -> None:
    page_img = tmp_path / "page_1.png"
    page_img.write_bytes(b"stub")
    ctx = AnalysisContext(
        doc_id="doc_ocr",
        file_bytes=b"stub",
        mime="image/png",
        pages=[PageImage(page=1, image_path=page_img, width=100, height=100)],
        doc_type="gst_certificate",
    )

    result = OcrAnalyzer().run(ctx)
    assert isinstance(result, AnalyzerOutput)
    assert result.analyzer_name == "ocr"
    assert result.findings == []
    assert result.extracted_fields == {}
    assert result.signals == []
    assert isinstance(is_tesseract_available(), bool)
