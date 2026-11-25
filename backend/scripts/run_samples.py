"""Run the full Kavach pipeline on every document in samples/ and print diagnostics."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import AnalysisContext  # noqa: E402
from app.pipeline import AnalysisPipeline  # noqa: E402
from app.utils.pdf import render_document_pages  # noqa: E402
from app.utils.validation import detect_mime_from_magic_bytes  # noqa: E402

SAMPLES_DIR = BACKEND_DIR.parent / "samples"
IGNORED = {".gitkeep", "README.md"}


def main() -> None:
    """Execute pipeline over all sample documents and print detailed diagnostics."""
    sample_files = sorted(
        p for p in SAMPLES_DIR.iterdir() if p.is_file() and p.name not in IGNORED
    )
    if not sample_files:
        print("No sample files found in samples/")
        return

    pipeline = AnalysisPipeline()
    with tempfile.TemporaryDirectory(prefix="kavach_samples_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        for idx, path in enumerate(sample_files, start=1):
            raw_bytes = path.read_bytes()
            mime = detect_mime_from_magic_bytes(raw_bytes)
            pages = render_document_pages(
                source_path=path,
                mime_type=mime,
                output_dir=tmp_root / f"doc_{idx}",
                dpi=200,
            )
            ctx = AnalysisContext(
                doc_id=f"sample_{idx}",
                file_bytes=raw_bytes,
                mime=mime,
                pages=pages,
            )
            result = pipeline.run(ctx)

            all_words = [w for words in ctx.ocr_words.values() for w in words]
            mean_conf = (
                sum(w.conf for w in all_words) / len(all_words) if all_words else 0.0
            )

            print("=" * 72)
            print(f"FILE: {path.name} ({mime}, {len(pages)} page(s))")
            print(
                f"DOC_TYPE: {result.doc_type} | RISK: {result.risk_score}/100 ({result.risk_level})"
                f" | CONFIDENCE: {result.confidence:.3f} | TIME: {result.processing_ms} ms"
            )
            print(f"OCR: {len(all_words)} words, mean_conf={mean_conf:.3f}")
            print(
                f"QUALITY: {ctx.quality} | is_screenshot_like={ctx.is_screenshot_like}"
            )
            print("EXTRACTED_FIELDS:")
            for key, val in result.extracted_fields.items():
                print(f"  - {key}: {val.get('value')}")
            print("CHECKS:")
            for chk in result.checks:
                print(f"  - [{chk.status.upper()}] {chk.name}: {chk.detail}")
            print("FORENSICS_REGIONS:")
            if not result.regions:
                print("  (none)")
            for reg in result.regions:
                print(
                    f"  - page={reg.page} score={reg.score:.3f} bbox={reg.bbox} reason={reg.reason}"
                )


if __name__ == "__main__":
    main()
