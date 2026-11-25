"""Unit tests for noisy-OR risk scoring, confidence scaling, and breakdown."""

from __future__ import annotations

from app.models.schemas import CheckResult, Finding, OcrWord, Signal
from app.scoring.risk import assess_risk


def test_clean_input_is_low_risk() -> None:
    assessment = assess_risk(
        findings=[],
        checks=[CheckResult(name="invoice:tax_total_math", status="pass", detail="OK")],
        signals=[],
        quality={1: 0.9},
        ocr_words={1: [OcrWord(text="Total", conf=0.95, bbox=(0.1, 0.1, 0.2, 0.2))]},
        is_screenshot_like=False,
    )
    assert assessment.risk_score == 0
    assert assessment.risk_level == "LOW"
    assert assessment.confidence > 0.8
    assert assessment.score_breakdown == []


def test_single_weak_signal_stays_low_or_medium() -> None:
    weak = Signal(
        name="forensics:ela",
        category="visual",
        weight_hint=0.45,
        confidence=0.85,
    )
    assessment = assess_risk(findings=[], checks=[], signals=[weak])
    assert assessment.risk_score <= 65
    assert assessment.risk_level in {"LOW", "MEDIUM"}
    assert len(assessment.score_breakdown) == 1


def test_failed_checksum_plus_strong_text_patch_is_high() -> None:
    checksum_sig = Signal(
        name="rules:gst:gstin_checksum",
        category="consistency",
        weight_hint=0.85,
        confidence=0.9,
    )
    patch_sig = Signal(
        name="forensics:text_patch",
        category="visual",
        weight_hint=0.9,
        confidence=0.85,
    )
    finding = Finding(
        id="f1",
        category="consistency",
        severity="high",
        title="GSTIN checksum mismatch",
        plain_explanation="The GSTIN check digit does not match.",
        technical_detail="mod-36 failed",
    )
    assessment = assess_risk(
        findings=[finding],
        checks=[CheckResult(name="gst:gstin_checksum", status="fail", detail="Bad checksum")],
        signals=[checksum_sig, patch_sig],
        quality={1: 0.85},
        is_screenshot_like=False,
    )
    assert assessment.risk_score > 65
    assert assessment.risk_level == "HIGH"
    contribs = [item.contribution for item in assessment.score_breakdown]
    assert contribs == sorted(contribs, reverse=True)


def test_screenshot_scales_confidence_down() -> None:
    normal = assess_risk(
        findings=[],
        checks=[],
        signals=[],
        quality={1: 0.9},
        ocr_words={1: [OcrWord(text="OK", conf=0.95, bbox=(0.1, 0.1, 0.2, 0.2))]},
        is_screenshot_like=False,
    )
    screenshot = assess_risk(
        findings=[],
        checks=[],
        signals=[],
        quality={1: 0.9},
        ocr_words={1: [OcrWord(text="OK", conf=0.95, bbox=(0.1, 0.1, 0.2, 0.2))]},
        is_screenshot_like=True,
    )
    assert screenshot.confidence < normal.confidence
