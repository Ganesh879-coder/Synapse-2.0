"""Consistency checks for bank and UPI transaction statements."""

from __future__ import annotations

from datetime import date

from app.models.schemas import CheckResult, ExtractedField, Finding, Region, Signal
from app.rules.common import make_failure, parse_date


def _extract_tx_embedded_date(tx_id: str) -> date | None:
    """Parse YYYYMMDD or YYMMDD embedded right after leading 'T' in UPI transaction IDs."""
    if not tx_id.startswith("T") or len(tx_id) < 9:
        return None
    digits = tx_id[1:]
    if len(digits) >= 8 and digits[:8].isdigit():
        candidate = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
        parsed = parse_date(candidate)
        if parsed is not None:
            return parsed
    if len(digits) >= 6 and digits[:6].isdigit():
        candidate = f"20{digits[:2]}-{digits[2:4]}-{digits[4:6]}"
        return parse_date(candidate)
    return None


def run_bank_checks(
    fields: dict[str, ExtractedField],
    today: date | None = None,
) -> tuple[list[CheckResult], list[Finding], list[Region], list[Signal]]:
    """Verify bank/UPI row date ordering, UPI tx ID dates, UTR format, period, and pagination."""
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
        weight: float = 0.75,
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

    period_field = fields.get("statement_period")
    period_start = (
        parse_date(str(period_field.value.get("start", "")))
        if period_field and isinstance(period_field.value, dict)
        else None
    )
    period_end = (
        parse_date(str(period_field.value.get("end", "")))
        if period_field and isinstance(period_field.value, dict)
        else None
    )

    tx_field = fields.get("transactions")
    if tx_field and isinstance(tx_field.value, list):
        row_dates: list[tuple[date, ExtractedField]] = []
        tx_id_mismatch = False
        utr_invalid = False
        period_violation = False
        future_found = False

        for row in tx_field.value:
            row_f = ExtractedField(
                value=row,
                page=int(row.get("page", 1)),
                bbox=row.get("bbox"),
            )
            r_date = parse_date(str(row.get("date_str", "")))
            if r_date is not None:
                row_dates.append((r_date, row_f))
                if r_date > current_date and not future_found:
                    future_found = True
                    _add_issue(
                        "bank:future_date",
                        f"Transaction row date ({r_date.isoformat()}) is in the future.",
                        "Future transaction date",
                        "high",
                        row_f,
                    )
                if period_start and period_end and not (period_start <= r_date <= period_end):
                    if not period_violation:
                        period_violation = True
                        _add_issue(
                            "bank:statement_period",
                            (
                                f"Transaction date {r_date.isoformat()} falls outside "
                                f"period {period_start.isoformat()} to {period_end.isoformat()}."
                            ),
                            "Transaction outside statement period",
                            "high",
                            row_f,
                        )

            tx_id = row.get("tx_id")
            if isinstance(tx_id, str) and r_date is not None:
                embedded = _extract_tx_embedded_date(tx_id)
                if embedded is not None and embedded != r_date and not tx_id_mismatch:
                    tx_id_mismatch = True
                    _add_issue(
                        "bank:upi_tx_date_match",
                        (
                            f"UPI transaction ID '{tx_id}' encodes date {embedded.isoformat()}, "
                            f"which does not match row date {r_date.isoformat()}."
                        ),
                        "UPI transaction ID date mismatch",
                        "high",
                        row_f,
                    )

            utr = row.get("utr")
            if utr is not None and (
                not isinstance(utr, str) or len(utr) != 12 or not utr.isdigit()
            ):
                if not utr_invalid:
                    utr_invalid = True
                    _add_issue(
                        "bank:utr_format",
                        f"UTR '{utr}' is not a valid 12-digit reference number.",
                        "Invalid UTR format",
                        "medium",
                        row_f,
                    )

        # Monotonic date ordering (either ascending or descending).
        if len(row_dates) >= 2:
            dates_only = [d for d, _ in row_dates]
            is_asc = all(dates_only[i] <= dates_only[i + 1] for i in range(len(dates_only) - 1))
            is_desc = all(dates_only[i] >= dates_only[i + 1] for i in range(len(dates_only) - 1))
            if not (is_asc or is_desc):
                _add_issue(
                    "bank:date_ordering",
                    "Transaction dates are neither consistently ascending nor descending.",
                    "Inconsistent transaction date order",
                    "high",
                    row_dates[1][1],
                )
            else:
                checks.append(
                    CheckResult(
                        name="bank:date_ordering",
                        status="pass",
                        detail="Transaction dates are in consistent chronological order.",
                    )
                )

        if not tx_id_mismatch and any(r.get("tx_id") for r in tx_field.value):
            checks.append(
                CheckResult(
                    name="bank:upi_tx_date_match",
                    status="pass",
                    detail="UPI transaction IDs match their row dates.",
                )
            )
        if not period_violation and period_start and period_end:
            checks.append(
                CheckResult(
                    name="bank:statement_period",
                    status="pass",
                    detail="All transaction dates fall within the statement period.",
                )
            )

    # Pagination "Page X of N" consistency.
    page_markers_f = fields.get("page_markers")
    if page_markers_f and isinstance(page_markers_f.value, list):
        markers = page_markers_f.value
        total_ns = {int(m["n"]) for m in markers}
        bad_page = any(
            int(m["x"]) != int(m["page"]) or int(m["x"]) > int(m["n"]) for m in markers
        )
        if len(total_ns) > 1 or bad_page:
            first = markers[0]
            _add_issue(
                "bank:pagination",
                "Page numbering ('Page X of N') is inconsistent across the statement.",
                "Inconsistent statement pagination",
                "medium",
                ExtractedField(
                    value=first,
                    page=int(first.get("page", 1)),
                    bbox=first.get("bbox"),
                ),
            )
        else:
            checks.append(
                CheckResult(
                    name="bank:pagination",
                    status="pass",
                    detail="Page numbering ('Page X of N') is consistent.",
                )
            )

    return checks, findings, regions, signals
