"""Regression tests for real sample documents in samples/ (skipped if absent)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.schemas import AnalysisContext
from app.pipeline import AnalysisPipeline
from app.rules.checks_gst import compute_gstin_check_digit, normalize_gstin_with_confusion
from app.rules.common import parse_amount_with_confusion
from app.utils.pdf import render_document_pages
from app.utils.validation import detect_mime_from_magic_bytes

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"

EXPECTED_SAMPLES: list[tuple[tuple[str, ...], str]] = [
    (("bill_clean.jpg", "bill_clean.jpg.jpeg"), "INVOICE_BILL"),
    (("kea_receipt.jpg", "kea_receipt.jpg.jpeg"), "PAYMENT_RECEIPT"),
    (("phonepe_stmt.png", "phonepe_stmt.png.jpeg"), "BANK_UPI_STATEMENT"),
    (("gst_2023.jpg", "gst_2023.jpg.jpeg"), "GST_CERT"),
    (("gst_2018.jpg", "gst_2018.jpg.jpeg"), "GST_CERT"),
]


def _resolve_sample(candidates: tuple[str, ...]) -> Path | None:
    for name in candidates:
        path = SAMPLES_DIR / name
        if path.is_file():
            return path
    return None


def test_confusion_corrections_for_gstin_and_amount() -> None:
    valid_gstin = "27AAAPS1234P1Z" + compute_gstin_check_digit("27AAAPS1234P1Z")
    confused = "27AAAPS" + valid_gstin[7:].replace("1", "I", 1).replace("0", "O", 1)
    if confused != valid_gstin:
        fixed, was_corrected = normalize_gstin_with_confusion(confused)
        assert fixed == valid_gstin
        assert was_corrected is True

    amt, amt_corrected = parse_amount_with_confusion("256O.00")
    assert amt == 2560.0
    assert amt_corrected is True


@pytest.mark.parametrize(("candidates", "expected_doc_type"), EXPECTED_SAMPLES)
def test_real_sample_document_regression(
    tmp_path: Path, candidates: tuple[str, ...], expected_doc_type: str
) -> None:
    sample_path = _resolve_sample(candidates)
    if sample_path is None:
        pytest.skip(f"Sample file not present: {candidates[0]}")

    raw_bytes = sample_path.read_bytes()
    mime = detect_mime_from_magic_bytes(raw_bytes)
    pages = render_document_pages(
        source_path=sample_path,
        mime_type=mime,
        output_dir=tmp_path / sample_path.stem,
        dpi=200,
    )
    ctx = AnalysisContext(
        doc_id=sample_path.stem,
        file_bytes=raw_bytes,
        mime=mime,
        pages=pages,
    )
    result = AnalysisPipeline().run(ctx)
    assert result.doc_type == expected_doc_type

    if "bill_clean" in sample_path.name:
        assert all(c.status == "pass" for c in result.checks)
