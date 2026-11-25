"""Backward-compatible wrapper around scoring.risk.assess_risk."""

from __future__ import annotations

from app.models.schemas import CheckResult, Finding, RiskLevel, Signal
from app.scoring.risk import assess_risk


def compute_risk(
    findings: list[Finding],
    checks: list[CheckResult],
    signals: list[Signal] | None = None,
) -> tuple[int, RiskLevel]:
    """Compute a bounded 0-100 risk score and categorical risk level."""
    assessment = assess_risk(findings=findings, checks=checks, signals=signals)
    return assessment.risk_score, assessment.risk_level
