"""Plain-English verdict builder using non-certainty language."""

from __future__ import annotations

from app.models.schemas import Finding, RiskLevel


def build_verdict(risk_level: RiskLevel, findings: list[Finding]) -> str:
    """Return a plain-English summary without claiming absolute certainty."""
    if not findings or risk_level == "LOW":
        return (
            "No significant indicators of tampering were detected in this document. "
            "Standard manual verification is still recommended."
        )
    if risk_level == "MEDIUM":
        return (
            f"Some anomalies ({len(findings)} indicator(s)) were detected that may "
            "suggest tampering or formatting irregularities. Please review highlighted regions."
        )
    return (
        f"Multiple strong indicators of tampering ({len(findings)} indicator(s)) were "
        "detected. Do not rely on this document without independent verification."
    )
