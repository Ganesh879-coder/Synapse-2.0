"""Plain-English explanation templates, optional LLM rewrite, and action builder."""

from __future__ import annotations

import json
import os

import httpx

from app.models.schemas import CheckResult, ExplanationSummary, Finding, RiskLevel

_DISCLAIMER = (
    "This automated assessment highlights statistical and structural indicators only. "
    "It does not constitute legal proof of forgery or authenticity; always perform "
    "independent verification before taking action."
)

_ACTION_BY_PREFIX: tuple[tuple[str, str], ...] = (
    (
        "gst:",
        (
            "Verify the GSTIN, legal name, and registration status directly on the "
            "official GST portal (gst.gov.in)."
        ),
    ),
    (
        "invoice:",
        (
            "Request the original itemized tax invoice or POS receipt from the vendor "
            "and recompute taxes independently."
        ),
    ),
    (
        "bank:",
        (
            "Confirm bank/UPI details by calling a number you already trust and verify "
            "the UTR in your bank portal."
        ),
    ),
    (
        "receipt:",
        (
            "Cross-check the receipt number and reference/CET ID on the issuing "
            "authority's official portal."
        ),
    ),
)

_DEFAULT_VISUAL_ACTION = (
    "Ask the issuer for the original unmodified PDF or raw photograph rather than a "
    "re-saved or screenshotted copy."
)


def build_verdict(
    risk_level: RiskLevel,
    findings: list[Finding],
    incomplete_analysis: bool = False,
) -> str:
    """Return a 2-3 sentence plain-English summary without claiming absolute certainty."""
    if incomplete_analysis:
        return (
            "Kavach could not complete all checks on this file. "
            "Treat the result as unverified and ask for a clearer copy."
        )
    if not findings and risk_level == "LOW":
        return (
            "No significant indicators of tampering were detected in this document. "
            "All completed structural checks appear consistent with a genuine record. "
            "Routine manual verification is still recommended for high-value transactions."
        )
    if risk_level == "LOW":
        return (
            f"Only minor irregularities ({len(findings)} indicator(s)) were observed, which "
            "can occur in normal scans or screenshots. Overall indicators suggest low risk, "
            "though standard verification is still advisable."
        )
    if risk_level == "MEDIUM":
        return (
            f"Moderate anomalies ({len(findings)} indicator(s)) were detected that may "
            "indicate editing, recompression, or inconsistent details. Please review the "
            "highlighted regions and verify key fields with the issuer."
        )
    return (
        f"Multiple strong indicators suggest possible tampering ({len(findings)} indicator(s) "
        "detected across document checks). Do not rely on this document without independent "
        "verification from the original source."
    )


def _build_top_reasons(findings: list[Finding], checks: list[CheckResult]) -> list[str]:
    """Select up to 4 plain-English reasons ordered by finding severity."""
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(findings, key=lambda f: severity_rank.get(f.severity, 4))
    reasons: list[str] = []
    for fnd in ordered:
        text = fnd.plain_explanation.strip()
        if text and text not in reasons:
            reasons.append(text)
        if len(reasons) >= 4:
            return reasons

    for chk in checks:
        if chk.status in {"fail", "warn"} and chk.detail not in reasons:
            reasons.append(chk.detail)
            if len(reasons) >= 4:
                break
    return reasons


def _build_next_actions(findings: list[Finding], checks: list[CheckResult]) -> list[str]:
    """Choose specific follow-up actions based on which checks/categories failed."""
    actions: list[str] = []
    failed_names = [c.name for c in checks if c.status in {"fail", "warn"}]

    for prefix, action in _ACTION_BY_PREFIX:
        if any(name.startswith(prefix) for name in failed_names):
            actions.append(action)

    if any(f.category in {"visual", "metadata"} for f in findings) or any(
        n.startswith("metadata:") for n in failed_names
    ):
        actions.append(_DEFAULT_VISUAL_ACTION)

    if not actions:
        actions.append(
            "Retain this report for your records and perform standard vendor KYC checks."
        )
    return actions


def _optional_llm_rewrite(
    summary: ExplanationSummary,
    risk_level: RiskLevel,
    risk_score: int,
    findings: list[Finding],
) -> ExplanationSummary:
    """Optionally polish verdict/top_reasons via Anthropic or Gemini at temperature=0."""
    if not findings:
        return summary

    structured_payload = {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "findings": [
            {
                "category": f.category,
                "severity": f.severity,
                "title": f.title,
                "explanation": f.plain_explanation,
            }
            for f in findings[:6]
        ],
    }
    prompt = (
        "Rewrite the verdict (2-3 plain sentences for a non-technical buyer) and up to 4 "
        "concise bullet reasons based ONLY on this JSON. Never claim certainty or say "
        "'proven fake'; use phrases like 'indicators suggest'. Return JSON with keys "
        "'verdict' (string) and 'top_reasons' (list of strings).\n"
        f"{json.dumps(structured_payload)}"
    )

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    try:
        if anthropic_key:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": os.getenv("KAVACH_ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                    "max_tokens": 350,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=5.0,
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            parsed = json.loads(text)
            return summary.model_copy(
                update={
                    "verdict": str(parsed.get("verdict") or summary.verdict),
                    "top_reasons": [
                        str(x) for x in parsed.get("top_reasons", summary.top_reasons)
                    ][:4],
                }
            )

        if gemini_key:
            model = os.getenv("KAVACH_GEMINI_MODEL", "gemini-2.0-flash")
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={gemini_key}"
            )
            resp = httpx.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=5.0,
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return summary.model_copy(
                update={
                    "verdict": str(parsed.get("verdict") or summary.verdict),
                    "top_reasons": [
                        str(x) for x in parsed.get("top_reasons", summary.top_reasons)
                    ][:4],
                }
            )
    except Exception:
        return summary

    return summary


def build_explanation_summary(
    risk_level: RiskLevel,
    risk_score: int,
    findings: list[Finding],
    checks: list[CheckResult],
) -> ExplanationSummary:
    """Build deterministic plain-English summary with optional LLM polish."""
    incomplete = any(
        c.status == "skipped" and c.name in {"analyzer:ocr", "analyzer:rules", "analyzer:classify"}
        for c in checks
    )
    base = ExplanationSummary(
        verdict=build_verdict(risk_level, findings, incomplete_analysis=incomplete),
        top_reasons=_build_top_reasons(findings, checks),
        next_actions=_build_next_actions(findings, checks),
        disclaimer=_DISCLAIMER,
    )
    return _optional_llm_rewrite(base, risk_level, risk_score, findings)
