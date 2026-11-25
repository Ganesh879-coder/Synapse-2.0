"""End-to-end pipeline smoke test over every document in samples/."""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import AnalysisContext, AnalysisResult
from app.pipeline import AnalysisPipeline
from app.utils.pdf import render_document_pages
from app.utils.validation import detect_mime_from_magic_bytes

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
IGNORED_FILES = {".gitkeep", "README.md"}


def _iter_sample_files() -> list[Path]:
    if not SAMPLES_DIR.exists():
        return []
    return sorted(
        path
        for path in SAMPLES_DIR.iterdir()
        if path.is_file() and path.name not in IGNORED_FILES
    )


def test_pipeline_end_to_end_on_samples(tmp_path: Path) -> None:
    """Build an AnalysisContext from each file in samples/ and assert valid AnalysisResult."""
    sample_files = _iter_sample_files()
    pipeline = AnalysisPipeline()

    for idx, sample_path in enumerate(sample_files, start=1):
        raw_bytes = sample_path.read_bytes()
        mime = detect_mime_from_magic_bytes(raw_bytes)
        pages_dir = tmp_path / f"sample_{idx}"
        pages = render_document_pages(
            source_path=sample_path,
            mime_type=mime,
            output_dir=pages_dir,
            dpi=200,
        )
        ctx = AnalysisContext(
            doc_id=f"sample_{idx}",
            file_bytes=raw_bytes,
            mime=mime,
            pages=pages,
        )
        result = pipeline.run(ctx)
        assert isinstance(result, AnalysisResult)
        assert 0 <= result.risk_score <= 100
        assert result.risk_level in {"LOW", "MEDIUM", "HIGH"}
