"""Consistency checks for payment receipts."""

from __future__ import annotations

import re
from datetime import date

from app.models.schemas import CheckResult, ExtractedField, Finding, Region, Signal
from app.rules.common import make_failure, parse_date

_RECEIPT_NO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{2,32}$")


def run_receipt_checks(
    fields: dict[str, ExtractedField],
    today: date | None = None,
) -> tuple[list[CheckResult], list[Finding], list[Region], list[Signal]]:
    """Verify payment receipt amount, date plausibility, receipt structure, and repeated IDs."""
    checks: list[CheckResult] = []
    findings: list[Finding] = []
    regions: list[Region] = []
    signals: list[Signal] = []
    current_date = today or date.today()

    def _add_issue(
        name: str,
        detail: str,
        title: str,
        severity: str,
        field: ExtractedField | None,
        weight: float = 0.7,
    ) -> None:
        chk, fnd, reg = make_failure(
            name,
            detail,
            title,
            "consistency",
            severity,  # type: ignore[arg-type]
            field=field,
        )
        checks.append(chk)
        findings.append(fnd)
        if reg is not None:
            regions.append(reg)
        signals.append(
            Signal(
                name=f"rules:{name}",
                category="consistency",
                weight_hint=weight,
                confidence=0.85,
                region_ids=[reg.id] if reg is not None else [],
            )
        )

    amt_field = fields.get("amount")
    if amt_field is not None:
        if float(amt_field.value) <= 0.0:
            _add_issue(
                "receipt:amount_positive",
                "The payment receipt amount must be greater than zero.",
                "Invalid payment amount",
                "high",
                amt_field,
            )
        else:
            checks.append(
                CheckResult(
                    name="receipt:amount_positive",
                    status="pass",
                    detail="Payment amount is valid and positive.",
                )
            )

    date_field = fields.get("date")
    if date_field is not None:
        parsed = parse_date(str(date_field.value))
        if parsed is not None and parsed > current_date:
            _add_issue(
                "receipt:future_date",
                f"The receipt date ({parsed.isoformat()}) is in the future.",
                "Future payment receipt date",
                "high",
                date_field,
            )
        elif parsed is not None:
            checks.append(
                CheckResult(
                    name="receipt:future_date",
                    status="pass",
                    detail="Receipt date is plausible.",
                )
            )

    rcpt_field = fields.get("receipt_no")
    if rcpt_field is not None:
        rcpt_str = str(rcpt_field.value).strip()
        if not _RECEIPT_NO_RE.fullmatch(rcpt_str):
            _add_issue(
                "receipt:number_structure",
                f"Receipt number '{rcpt_str}' does not match expected alphanumeric structure.",
                "Unusual receipt number structure",
                "medium",
                rcpt_field,
            )
        else:
            checks.append(
                CheckResult(
                    name="receipt:number_structure",
                    status="pass",
                    detail="Receipt number structure is valid.",
                )
            )

        cet_field = fields.get("cet_no")
        if cet_field is not None:
            cet_str = str(cet_field.value).strip()
            cet_digits = re.sub(r"\D", "", cet_str)
            rcpt_digits = re.sub(r"\D", "", rcpt_str)
            id_match = cet_str.upper() in rcpt_str.upper() or (
                bool(cet_digits) and len(cet_digits) >= 3 and cet_digits in rcpt_digits
            )
            if not id_match and (cet_digits or len(cet_str) >= 3):
                _add_issue(
                    "receipt:repeated_identifier",
                    (
                        f"CET/Reference number '{cet_str}' does not match the identifier "
                        f"embedded in receipt number '{rcpt_str}'."
                    ),
                    "Receipt and reference identifier mismatch",
                    "high",
                    cet_field,
                )
            else:
                checks.append(
                    CheckResult(
                        name="receipt:repeated_identifier",
                        status="pass",
                        detail="Repeated identifier (CET No.) matches receipt number.",
                    )
                )

    return checks, findings, regions, signals
