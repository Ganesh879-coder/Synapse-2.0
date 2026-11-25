"""Tests for the RulesAnalyzer and ClassifyAnalyzer stubs."""

from pathlib import Path

from app.models.schemas import AnalysisContext, AnalyzerOutput, PageImage
from app.rules import ClassifyAnalyzer, RulesAnalyzer


def test_rules_analyzer_returns_empty_output(tmp_path: Path) -> None:
    page_img = tmp_path / "page_1.png"
    page_img.write_bytes(b"stub")
    ctx = AnalysisContext(
        doc_id="doc_rules",
        file_bytes=b"stub",
        mime="image/png",
        pages=[PageImage(page=1, image_path=page_img, width=100, height=100)],
        doc_type="bank_statement",
    )

    result = RulesAnalyzer().run(ctx)
    assert isinstance(result, AnalyzerOutput)
    assert result.analyzer_name == "rules"
    assert result.findings == []
    assert result.checks == []
    assert result.signals == []


def test_classify_analyzer_sets_doc_type(tmp_path: Path) -> None:
    page_img = tmp_path / "page_1.png"
    page_img.write_bytes(b"stub")
    ctx = AnalysisContext(
        doc_id="doc_classify",
        file_bytes=b"stub",
        mime="image/png",
        pages=[PageImage(page=1, image_path=page_img, width=100, height=100)],
    )

    result = ClassifyAnalyzer().run(ctx)
    assert isinstance(result, AnalyzerOutput)
    assert result.analyzer_name == "classify"
    assert result.signals == []
    assert ctx.doc_type == "UNKNOWN"
