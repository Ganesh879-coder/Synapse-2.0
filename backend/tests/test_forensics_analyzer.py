"""Tests for the ForensicsAnalyzer orchestrator."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.forensics import ForensicsAnalyzer
from app.models.schemas import AnalysisContext, AnalyzerOutput, PageImage


def test_forensics_analyzer_runs_on_clean_image(tmp_path: Path) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (128, 128), color=(245, 245, 245)).save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    page_img = tmp_path / "page_1.png"
    page_img.write_bytes(raw_bytes)
    ctx = AnalysisContext(
        doc_id="doc_forensics",
        file_bytes=raw_bytes,
        mime="image/png",
        pages=[PageImage(page=1, image_path=page_img, width=128, height=128)],
        doc_type="invoice",
    )

    result = ForensicsAnalyzer().run(ctx)
    assert isinstance(result, AnalyzerOutput)
    assert result.analyzer_name == "forensics"
    assert result.findings == []
    assert result.regions == []
    assert any(c.name == "metadata:image_software" and c.status == "pass" for c in result.checks)
    assert (tmp_path / "heatmap_page_1.png").is_file()
