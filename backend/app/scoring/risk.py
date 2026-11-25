"""Transparent noisy-OR weighted risk scoring model."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import (
    CheckResult,
    Finding,
    OcrWord,
    RiskLevel,
    ScoreContribution,
    Signal,
)

_HIGH_WEIGHT_CONSISTENCY_PREFIXES: tuple[str, ...] = (
    "rules:gst:gstin_checksum",
    "rules:gst:gstin_format",
    "rules:gst:state_code",
    "rules:gst:pan_constitution",
    "rules:invoice:tax_total_math",
    "rules:invoice:tax_rate_math",
    "rules:invoice:line_item_math",
    "rules:invoice:line_sum_vs_total",
    "rules:invoice:cgst_sgst_symmetry",
    "rules:bank:upi_tx_date_match",
    "rules:bank:date_ordering",
    "rules:bank:statement_period",
    "rules:receipt:repeated_identifier",
)

_WEAK_VISUAL_SIGNALS: frozenset[str] = frozenset(
    {
        "forensics:ela",
        "forensics:noise",
        "forensics:jpeg_ghost",
        "forensics:metadata",
    }
)

_SIGNAL_LABELS: dict[str, str] = {
    "forensics:text_patch": "Localized text-patch anomaly",
    "forensics:copy_move": "Duplicated/cloned region",
    "forensics:ela": "Error Level Analysis anomaly",
    "forensics:noise": "Local noise variance anomaly",
    "forensics:jpeg_ghost": "Double-JPEG recompression anomaly",
    "forensics:metadata": "Metadata or PDF structure indicator",
}


@dataclass(frozen=True)
class RiskAssessment:
    """Complete risk scoring output including confidence and breakdown."""

    risk_score: int
    risk_level: RiskLevel
    confidence: float
    score_breakdown: list[ScoreContribution]


def _signal_probability(sig: Signal) -> tuple[float, bool]:
    """Map a Signal to an effective noisy-OR probability and whether it is strong."""
    conf = max(0.0, min(1.0, sig.confidence))
    if sig.name.startswith(_HIGH_WEIGHT_CONSISTENCY_PREFIXES) or sig.category == "consistency":
        prob = min(0.88, max(0.45, sig.weight_hint) * conf * 1.05)
        return prob, True
    if sig.name == "forensics:text_patch":
        if conf >= 0.5:
            return min(0.84, 0.82 * conf), True
        return min(0.42, 0.55 * conf), False
    if sig.name == "forensics:copy_move":
        prob = min(0.68, 0.65 * conf)
        return prob, conf >= 0.75
    if sig.name in _WEAK_VISUAL_SIGNALS:
        return min(0.38, 0.42 * conf), False
    return min(0.60, sig.weight_hint * conf), sig.weight_hint * conf >= 0.65


def compute_overall_confidence(
    quality: dict[int, float] | None = None,
    ocr_words: dict[int, list[OcrWord]] | None = None,
    is_screenshot_like: bool = False,
) -> float:
    """Compute overall assessment confidence [0, 1] from quality, OCR, and screenshot status."""
    q_vals = list((quality or {}).values())
    mean_quality = sum(q_vals) / len(q_vals) if q_vals else 0.75

    all_words = [w for words in (ocr_words or {}).values() for w in words]
    mean_ocr = sum(w.conf for w in all_words) / len(all_words) if all_words else 0.75

    conf = 0.55 * mean_quality + 0.45 * mean_ocr
    if is_screenshot_like:
        conf *= 0.75
    return round(max(0.1, min(1.0, conf)), 3)


def assess_risk(
    findings: list[Finding],
    checks: list[CheckResult],
    signals: list[Signal] | None = None,
    quality: dict[int, float] | None = None,
    ocr_words: dict[int, list[OcrWord]] | None = None,
    is_screenshot_like: bool = False,
) -> RiskAssessment:
    """Combine signals, findings, and checks via noisy-OR into a 0-100 risk score."""
    active_signals = list(signals or [])
    terms: list[tuple[str, str, float, bool]] = []

    for sig in active_signals:
        prob, is_strong = _signal_probability(sig)
        if prob > 0.01:
            label = _SIGNAL_LABELS.get(sig.name, sig.name.replace(":", " - ").title())
            terms.append((sig.name, label, prob, is_strong))

    # Include WARN checks as a small additive/noisy-OR term.
    warn_checks = [c for c in checks if c.status == "warn"]
    for chk in warn_checks:
        terms.append((f"warn:{chk.name}", f"Warning: {chk.name}", 0.08, False))

    # Fallback if findings were passed directly without signals.
    if not active_signals and findings:
        sev_probs = {"low": 0.15, "medium": 0.40, "high": 0.72, "critical": 0.88}
        for fnd in findings:
            p = sev_probs.get(fnd.severity, 0.20)
            terms.append((f"finding:{fnd.id}", fnd.title, p, fnd.severity in {"high", "critical"}))

    # Noisy-OR combination: 1 - prod(1 - p_i)
    survival = 1.0
    for _, _, prob, _ in terms:
        survival *= max(0.0, min(1.0, 1.0 - prob))
    combined_prob = 1.0 - survival
    score = int(round(max(0.0, min(1.0, combined_prob)) * 100.0))

    # Single weak signal guard: never exceed MEDIUM (<= 55).
    strong_count = sum(1 for _, _, _, is_strong in terms if is_strong)
    if strong_count == 0 and len(terms) <= 2:
        score = min(score, 55)

    # Levels: LOW <30, MEDIUM 30-65, HIGH >65.
    if score > 65:
        level: RiskLevel = "HIGH"
    elif score >= 30:
        level = "MEDIUM"
    else:
        level = "LOW"

    # Build sorted score_breakdown proportional to each term's probability.
    total_prob = sum(p for _, _, p, _ in terms)
    breakdown: list[ScoreContribution] = []
    if total_prob > 0.0 and score > 0:
        for sig_name, label, prob, _ in terms:
            contrib = round((prob / total_prob) * score, 2)
            breakdown.append(
                ScoreContribution(signal=sig_name, label=label, contribution=contrib)
            )
        breakdown.sort(key=lambda item: item.contribution, reverse=True)

    confidence = compute_overall_confidence(quality, ocr_words, is_screenshot_like)
    return RiskAssessment(
        risk_score=score,
        risk_level=level,
        confidence=confidence,
        score_breakdown=breakdown,
    )
