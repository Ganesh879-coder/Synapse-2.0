"""Consistency checks for invoices and restaurant bills."""

from __future__ import annotations

import re
from datetime import date

from app.models.schemas import CheckResult, ExtractedField, Finding, Region, Signal
from app.rules.common import make_failure, parse_date

_TOLERANCE = 0.05
_BILL_NO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/-]{1,24}$")


def run_invoice_checks(
    fields: dict[str, ExtractedField],
    today: date | None = None,
) -> tuple[list[CheckResult], list[Finding], list[Region], list[Signal]]:
    """Verify line-item math, tax-inclusive/exclusive CGST+SGST math, and bill metadata."""
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

    # 1. Line items: sum(qty * rate) == line totals == net_total (or taxable_amount)
    items_field = fields.get("line_items")
    net_field = fields.get("net_total")
    taxable_field = fields.get("taxable_amount")
    cgst_field = fields.get("cgst")
    sgst_field = fields.get("sgst")
    rate_field = fields.get("tax_rate")

    if items_field and isinstance(items_field.value, list):
        line_sum = 0.0
        item_mismatch = False
        for item in items_field.value:
            qty = float(item["qty"])
            rate = float(item["rate"])
            total = float(item["total"])
            if abs(qty * rate - total) > _TOLERANCE:
                item_mismatch = True
                item_field = ExtractedField(
                    value=total,
                    page=int(item.get("page", 1)),
                    bbox=item.get("bbox"),
                )
                _add_issue(
                    "invoice:line_item_math",
                    (
                        f"Line item '{item.get('name', 'item')}' shows {qty} x {rate} = "
                        f"{qty * rate:.2f}, which does not match line total {total:.2f}."
                    ),
                    "Line item calculation mismatch",
                    "high",
                    item_field,
                )
            line_sum += total
        if not item_mismatch:
            checks.append(
                CheckResult(
                    name="invoice:line_item_math",
                    status="pass",
                    detail="All line item quantities and rates match their line totals.",
                )
            )

        # Compare sum of line totals against taxable_amount (exclusive) or net_total (inclusive).
        candidates = [f for f in (taxable_field, net_field) if f is not None]
        if candidates:
            matches_any = any(abs(line_sum - float(f.value)) <= _TOLERANCE for f in candidates)
            if not matches_any:
                target_field = net_field or taxable_field
                expected_target = float(target_field.value)  # type: ignore[union-attr]
                _add_issue(
                    "invoice:line_sum_vs_total",
                    (
                        f"The sum of line items ({line_sum:.2f}) does not match the "
                        f"stated subtotal/total ({expected_target:.2f})."
                    ),
                    "Line item sum mismatch",
                    "high",
                    target_field,
                )
            else:
                checks.append(
                    CheckResult(
                        name="invoice:line_sum_vs_total",
                        status="pass",
                        detail="Sum of line items matches the stated subtotal/net total.",
                    )
                )

    # 2. Tax math: CGST == SGST == taxable * rate/2, taxable + tax == net_total
    if net_field is not None and cgst_field is not None and sgst_field is not None:
        net_total = float(net_field.value)
        cgst = float(cgst_field.value)
        sgst = float(sgst_field.value)
        tax_sum = cgst + sgst

        if abs(cgst - sgst) > _TOLERANCE:
            _add_issue(
                "invoice:cgst_sgst_symmetry",
                f"CGST ({cgst:.2f}) and SGST ({sgst:.2f}) should be equal but differ.",
                "CGST and SGST mismatch",
                "high",
                cgst_field,
            )
        else:
            checks.append(
                CheckResult(
                    name="invoice:cgst_sgst_symmetry",
                    status="pass",
                    detail="CGST and SGST amounts are equal.",
                )
            )

        if taxable_field is not None:
            taxable = float(taxable_field.value)
        elif rate_field is not None:
            rate_val = float(rate_field.value)
            taxable = net_total / (1.0 + rate_val)
        else:
            taxable = net_total - tax_sum

        if abs((taxable + tax_sum) - net_total) > _TOLERANCE:
            _add_issue(
                "invoice:tax_total_math",
                "The CGST and SGST amounts don't add up to the tax shown against the net total.",
                "Tax and net total mismatch",
                "high",
                net_field,
            )
        elif rate_field is not None:
            half_rate_tax = taxable * (float(rate_field.value) / 2.0)
            if abs(cgst - half_rate_tax) > _TOLERANCE or abs(sgst - half_rate_tax) > _TOLERANCE:
                _add_issue(
                    "invoice:tax_rate_math",
                    (
                        f"CGST/SGST ({cgst:.2f}/{sgst:.2f}) do not match half of the "
                        f"taxable amount ({taxable:.2f}) at the stated tax rate."
                    ),
                    "Tax rate calculation mismatch",
                    "high",
                    cgst_field,
                )
            else:
                checks.append(
                    CheckResult(
                        name="invoice:tax_total_math",
                        status="pass",
                        detail=(
                            "Taxable amount, CGST, SGST, and net total are consistent."
                        ),
                    )
                )
        else:
            corr_note = (
                " (OCR confusion correction applied)"
                if fields.get("amount_ocr_corrected")
                else ""
            )
            checks.append(
                CheckResult(
                    name="invoice:tax_total_math",
                    status="pass",
                    detail=(
                        f"Taxable amount, CGST, SGST, and net total are consistent.{corr_note}"
                    ),
                )
            )

    # 3. Bill number format and date plausibility
    bill_no_field = fields.get("bill_no")
    if bill_no_field is not None:
        bill_no = str(bill_no_field.value).strip()
        if not _BILL_NO_RE.fullmatch(bill_no):
            _add_issue(
                "invoice:bill_no_format",
                f"Bill number '{bill_no}' has an unusual format.",
                "Unusual bill number format",
                "low",
                bill_no_field,
                weight=0.35,
            )
        else:
            checks.append(
                CheckResult(
                    name="invoice:bill_no_format",
                    status="pass",
                    detail="Bill number format is valid.",
                )
            )

    bill_date_field = fields.get("bill_date")
    if bill_date_field is not None:
        parsed_d = parse_date(str(bill_date_field.value))
        if parsed_d is not None and parsed_d > current_date:
            _add_issue(
                "invoice:bill_date_plausibility",
                f"The bill date ({parsed_d.isoformat()}) is in the future.",
                "Future bill date",
                "high",
                bill_date_field,
            )
        elif parsed_d is not None:
            checks.append(
                CheckResult(
                    name="invoice:bill_date_plausibility",
                    status="pass",
                    detail="Bill date is plausible.",
                )
            )

    return checks, findings, regions, signals
