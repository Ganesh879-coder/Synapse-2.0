"""Risk score and risk level calculation from findings, checks, and signals."""

from __future__ import annotations

from app.models.schemas import CheckResult, Finding, RiskLevel, Signal

_SEVERITY_WEIGHTS: dict[str, int] = {
    "low": 10,
    "medium": 25,
    "high": 45,
    "critical": 70,
}


def compute_risk(
    findings: list[Finding],
    checks: list[CheckResult],
    signals: list[Signal] | None = None,
) -> tuple[int, RiskLevel]:
    """Compute a bounded 0-100 risk score and categorical risk level.

    A single weak signal is never allowed to trigger HIGH risk on its own.
    """
    _ = checks
    active_signals = signals or []
    finding_score = sum(_SEVERITY_WEIGHTS.get(item.severity, 10) for item in findings)
    signal_score = sum(
        int(round(sig.weight_hint * sig.confidence * 100)) for sig in active_signals
    )
    score = max(0, min(100, finding_score + signal_score))

    # Guard against single-weak-signal false positives reaching HIGH risk.
    if len(active_signals) <= 1 and len(findings) <= 1:
        max_sig_strength = max(
            (sig.weight_hint * sig.confidence for sig in active_signals),
            default=0.0,
        )
        if max_sig_strength < 0.65 and not any(
            f.severity in {"high", "critical"} for f in findings
        ):
            score = min(score, 59)

    if score >= 65:
        return score, "HIGH"
    if score >= 30:
        return score, "MEDIUM"
    return score, "LOW"
