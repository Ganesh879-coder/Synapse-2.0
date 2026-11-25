"""Tests for OCR engine, keyword classifier, extractors, and consistency rules."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.models.schemas import AnalysisContext, OcrWord, PageImage
from app.ocr.engine import extract_ocr_words, preprocess_for_ocr
from app.rules.analyzer import RulesAnalyzer
from app.rules.checks_bank import run_bank_checks
from app.rules.checks_gst import (
    compute_gstin_check_digit,
    run_gst_checks,
    verify_gstin_checksum,
)
from app.rules.checks_invoice import run_invoice_checks
from app.rules.checks_receipt import run_receipt_checks
from app.rules.classifier import classify_document
from app.rules.extract_bank import extract_bank_fields
from app.rules.extract_gst import extract_gst_fields
from app.rules.extract_invoice import extract_invoice_fields
from app.rules.extract_receipt import extract_receipt_fields


def _words_from_lines(lines: list[str], page: int = 1) -> dict[int, list[OcrWord]]:
    """Build synthetic normalized OcrWord lines for deterministic rule testing."""
    result: list[OcrWord] = []
    step = 1.0 / max(1, len(lines) + 1)
    for idx, line in enumerate(lines):
        y0 = round(idx * step + 0.01, 4)
        y1 = round(y0 + step * 0.7, 4)
        tokens = line.split()
        x_step = 0.85 / max(1, len(tokens))
        for t_idx, tok in enumerate(tokens):
            x0 = round(0.05 + t_idx * x_step, 4)
            x1 = round(x0 + x_step * 0.8, 4)
            result.append(OcrWord(text=tok, conf=0.98, bbox=(x0, y0, x1, y1)))
    return {page: result}


def test_ocr_preprocessing_and_rapidocr_on_synthetic_image(tmp_path: Path) -> None:
    img = Image.new("RGB", (600, 200), color=(230, 230, 230))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((40, 60), "BILL NO INV-101 NET TOTAL 525.00", fill=(20, 20, 20), font=font)

    img_path = tmp_path / "bill.png"
    img.save(img_path, format="PNG")
    page = PageImage(page=1, image_path=img_path, width=600, height=200)

    import cv2

    bgr = cv2.imread(str(img_path))
    assert bgr is not None
    preprocessed = preprocess_for_ocr(bgr)
    assert preprocessed.shape[0] >= 200

    words = extract_ocr_words(page)
    assert len(words) > 0
    assert all(0.0 <= c <= 1.0 for w in words for c in w.bbox)


def test_classifier_keywords() -> None:
    assert classify_document([], "Form GST REG-06 Registration Certificate") == "GST_CERT"
    assert classify_document([], "BILL NO 442 CGST SGST NET TOTAL") == "INVOICE_BILL"
    assert (
        classify_document([], "Transaction Statement UTR DEBIT CREDIT")
        == "BANK_UPI_STATEMENT"
    )
    assert classify_document([], "Payment Receipt Receipt No PR-2026") == "PAYMENT_RECEIPT"
    assert classify_document([], "Random unrelated memo") == "UNKNOWN"


def test_gstin_checksum_valid_and_mutated() -> None:
    # Known valid GSTINs: 27AAPFU0939F1ZV, 29AABCU9603R1ZM
    valid_1 = "27AAPFU0939F1Z" + compute_gstin_check_digit("27AAPFU0939F1Z")
    valid_2 = "29AABCU9603R1Z" + compute_gstin_check_digit("29AABCU9603R1Z")
    assert verify_gstin_checksum(valid_1)
    assert verify_gstin_checksum(valid_2)

    # Mutate last character
    bad = valid_1[:-1] + ("A" if valid_1[-1] != "A" else "B")
    assert not verify_gstin_checksum(bad)


def test_gst_certificate_valid_and_mutated() -> None:
    valid_gstin = "27AAAPS1234P1Z" + compute_gstin_check_digit("27AAAPS1234P1Z")
    valid_lines = [
        "FORM GST REG-06 Registration Certificate",
        f"GSTIN {valid_gstin}",
        "Legal Name Rajesh Sharma",
        "Trade Name Sharma Enterprises",
        "Constitution of Business Proprietorship",
        "Address of Principal Place 12 MG Road, Pune, Maharashtra",
        "Date of Liability 01/04/2023",
        "Date of Issue 15/05/2023",
    ]
    fields = extract_gst_fields(_words_from_lines(valid_lines))
    checks, findings, _regions, _signals = run_gst_checks(fields, today=date(2026, 1, 1))
    assert findings == []
    assert all(c.status == "pass" for c in checks)

    # Mutated: wrong state in address + bad checksum + Not Verified signature
    bad_gstin = valid_gstin[:-1] + ("0" if valid_gstin[-1] != "0" else "1")
    mutated_lines = [
        "FORM GST REG-06 Registration Certificate",
        f"GSTIN {bad_gstin}",
        "Legal Name Rajesh Verma",
        "Trade Name Verma Enterprises",
        "Constitution of Business Private Limited",
        "Address of Principal Place 12 MG Road, Bengaluru, Karnataka",
        "Date of Liability 01/04/2023",
        "Date of Issue 15/05/2023",
        "Digitally signed Signature Not Verified",
    ]
    m_fields = extract_gst_fields(_words_from_lines(mutated_lines))
    m_checks, m_findings, m_regions, _ = run_gst_checks(m_fields, today=date(2026, 1, 1))
    assert any(c.status == "fail" for c in m_checks)
    assert len(m_findings) >= 3
    assert len(m_regions) >= 2


def test_restaurant_bill_passes_all_checks_and_mutated_fails() -> None:
    valid_bill = [
        "TAX INVOICE",
        "BILL NO REST-2026-089",
        "Date 14/02/2026",
        "Masala Dosa 2 100.00 200.00",
        "Filter Coffee 2 50.00 100.00",
        "Taxable Amount 300.00",
        "CGST @ 2.5% 7.50",
        "SGST @ 2.5% 7.50",
        "NET TOTAL 315.00",
    ]
    words = _words_from_lines(valid_bill)
    fields = extract_invoice_fields(words)
    checks, findings, _regions, _ = run_invoice_checks(fields, today=date(2026, 3, 1))
    assert findings == []
    assert len(checks) >= 4
    assert all(c.status == "pass" for c in checks)

    # Mutate NET TOTAL without updating CGST/SGST -> must fail with bbox region.
    mutated_bill = list(valid_bill)
    mutated_bill[-1] = "NET TOTAL 415.00"
    m_fields = extract_invoice_fields(_words_from_lines(mutated_bill))
    m_checks, m_findings, m_regions, _ = run_invoice_checks(m_fields, today=date(2026, 3, 1))
    assert any(c.status == "fail" for c in m_checks)
    assert any("CGST and SGST" in f.plain_explanation for f in m_findings)
    assert len(m_regions) >= 1


def test_bank_statement_valid_and_mutated() -> None:
    valid_stmt = [
        "Transaction Statement",
        "Statement Period: 01/01/2026 to 31/01/2026",
        "20/01/2026 T20260120112233 601234567890 DEBIT 500.00",
        "10/01/2026 T20260110998877 601234567891 CREDIT 1200.00",
        "Page 1 of 1",
    ]
    fields = extract_bank_fields(_words_from_lines(valid_stmt))
    checks, findings, _regions, _ = run_bank_checks(fields, today=date(2026, 2, 1))
    assert findings == []
    assert all(c.status == "pass" for c in checks)

    # Mutate: UPI tx ID date doesn't match row date, and row outside period
    mutated_stmt = [
        "Transaction Statement",
        "Statement Period: 01/01/2026 to 31/01/2026",
        "20/01/2026 T20260115112233 601234567890 DEBIT 500.00",
        "05/02/2026 T20260205998877 601234567891 CREDIT 1200.00",
        "Page 1 of 1",
    ]
    m_fields = extract_bank_fields(_words_from_lines(mutated_stmt))
    m_checks, m_findings, m_regions, _ = run_bank_checks(m_fields, today=date(2026, 3, 1))
    assert any(c.status == "fail" for c in m_checks)
    assert len(m_findings) >= 2
    assert len(m_regions) >= 2


def test_payment_receipt_valid_and_mutated() -> None:
    valid_rcpt = [
        "Payment Receipt",
        "Receipt No RCPT-2026-445566",
        "CET No 445566",
        "Date 12/01/2026",
        "Amount 2500.00",
    ]
    ctx = AnalysisContext(
        doc_id="rcpt_ok",
        file_bytes=b"",
        mime="image/png",
        doc_type="PAYMENT_RECEIPT",
        ocr_words=_words_from_lines(valid_rcpt),
    )
    out = RulesAnalyzer().run(ctx)
    assert out.findings == []
    assert all(c.status == "pass" for c in out.checks)

    mutated_rcpt = [
        "Payment Receipt",
        "Receipt No RCPT-2026-445566",
        "CET No 998877",
        "Date 12/01/2026",
        "Amount 2500.00",
    ]
    m_fields = extract_receipt_fields(_words_from_lines(mutated_rcpt))
    m_checks, m_findings, m_regions, _ = run_receipt_checks(m_fields, today=date(2026, 2, 1))
    assert any(c.name == "receipt:repeated_identifier" and c.status == "fail" for c in m_checks)
    assert len(m_findings) == 1
    assert len(m_regions) == 1
