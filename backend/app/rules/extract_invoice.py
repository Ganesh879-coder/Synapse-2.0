"""Regex and position-based field extractor for invoices and restaurant bills."""

from __future__ import annotations

import re
from typing import Any

from app.models.schemas import ExtractedField, OcrWord
from app.rules.common import (
    DATE_PATTERN,
    find_value_after_label,
    ocr_lines_with_text,
    optional_llm_structure,
    parse_amount_with_confusion,
)

_BILL_NO_LABEL = re.compile(r"(?i)\b(?:bill\s*no\.?|invoice\s*no\.?|inv\s*no\.?)\s*")
_BILL_NO_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/-]{1,24}")
_DATE_LABEL = re.compile(r"(?i)\b(?:date|bill\s*date|invoice\s*date)\b")
_NET_TOTAL_LABEL = re.compile(r"(?i)\b(?:net\s*total|grand\s*total|total\s*amount)\b")
_TAXABLE_LABEL = re.compile(r"(?i)\b(?:taxable(?:\s+value|\s+amount)?|sub\s*total)\b")
_CGST_LABEL = re.compile(r"(?i)\bcgst\b(?:\s*@?\s*(\d+(?:\.\d+)?)\s*%)?")
_SGST_LABEL = re.compile(r"(?i)\bsgst\b(?:\s*@?\s*(\d+(?:\.\d+)?)\s*%)?")
_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([0-9OIlSB][0-9OIlSB,]*(?:\.[0-9OIlSB]{1,2})?)", re.I
)

# Line item: "[name] <qty> [x|@] <rate> <total>" (name must start with a letter)
_LINE_ITEM_RE = re.compile(
    r"^(?:(?P<name>[A-Za-z].*?)\s+)?(?P<qty>\d+(?:\.\d+)?)\s*(?:[xX×@]\s*)?"
    r"(?P<rate>\d+(?:\.\d+)?)\s+(?P<total>\d[\d,]*(?:\.\d+)?)$"
)


def _extract_last_amount(text: str) -> tuple[float | None, bool]:
    matches = _AMOUNT_RE.findall(text)
    if not matches:
        return None, False
    return parse_amount_with_confusion(matches[-1])


def _extract_all_amounts(text: str) -> list[float]:
    results: list[float] = []
    for raw in _AMOUNT_RE.findall(text):
        val, _ = parse_amount_with_confusion(raw)
        if val is not None:
            results.append(val)
    return results


def extract_invoice_fields(ocr_words: dict[int, list[OcrWord]]) -> dict[str, ExtractedField]:
    """Extract bill/invoice fields and line items with bounding boxes."""
    lines = ocr_lines_with_text(ocr_words)
    fields: dict[str, ExtractedField] = {}

    bill_no = find_value_after_label(lines, _BILL_NO_LABEL, _BILL_NO_VALUE)
    if bill_no:
        fields["bill_no"] = bill_no

    bill_date = find_value_after_label(lines, _DATE_LABEL, DATE_PATTERN)
    if bill_date:
        fields["bill_date"] = bill_date

    line_items: list[dict[str, Any]] = []
    tax_section_idx: int | None = None

    for idx, (page_num, text, _words, bbox) in enumerate(lines):
        if "net_total" not in fields and _NET_TOTAL_LABEL.search(text):
            amt, corrected = _extract_last_amount(text)
            if amt is None and idx > 0:
                amt, corrected = _extract_last_amount(lines[idx - 1][1])
            if amt is None and idx + 1 < len(lines):
                amt, corrected = _extract_last_amount(lines[idx + 1][1])
            if amt is not None:
                fields["net_total"] = ExtractedField(value=amt, page=page_num, bbox=bbox)
                if corrected:
                    fields["amount_ocr_corrected"] = ExtractedField(
                        value=True, page=page_num, bbox=bbox
                    )

        if "taxable_amount" not in fields and _TAXABLE_LABEL.search(text):
            amt, corrected = _extract_last_amount(text)
            if amt is not None:
                fields["taxable_amount"] = ExtractedField(value=amt, page=page_num, bbox=bbox)
                if corrected:
                    fields["amount_ocr_corrected"] = ExtractedField(
                        value=True, page=page_num, bbox=bbox
                    )

        if tax_section_idx is None and (
            "tax details" in text.lower() or ("taxable" in text.lower() and "cgst" in text.lower())
        ):
            tax_section_idx = idx

        cgst_m = _CGST_LABEL.search(text)
        if cgst_m and "cgst" not in fields:
            amt, _ = _extract_last_amount(text[cgst_m.end() :])
            if amt is not None:
                fields["cgst"] = ExtractedField(value=amt, page=page_num, bbox=bbox)
            if cgst_m.group(1) and "tax_rate" not in fields:
                fields["tax_rate"] = ExtractedField(
                    value=float(cgst_m.group(1)) * 2.0 / 100.0, page=page_num, bbox=bbox
                )

        sgst_m = _SGST_LABEL.search(text)
        if sgst_m and "sgst" not in fields:
            amt, _ = _extract_last_amount(text[sgst_m.end() :])
            if amt is not None:
                fields["sgst"] = ExtractedField(value=amt, page=page_num, bbox=bbox)

        if tax_section_idx is None:
            item_m = _LINE_ITEM_RE.match(text.strip())
            if item_m and not any(
                lbl.search(text)
                for lbl in (_NET_TOTAL_LABEL, _CGST_LABEL, _SGST_LABEL, _TAXABLE_LABEL)
            ):
                qty = float(item_m.group("qty"))
                rate = float(item_m.group("rate"))
                total, _ = parse_amount_with_confusion(item_m.group("total"))
                if total is not None:
                    line_items.append(
                        {
                            "name": (item_m.group("name") or "Item").strip(),
                            "qty": qty,
                            "rate": rate,
                            "total": total,
                            "page": page_num,
                            "bbox": bbox,
                        }
                    )

    # Parse tabular tax summary block if CGST/SGST/taxable weren't inline on label lines.
    if tax_section_idx is not None and ("cgst" not in fields or "taxable_amount" not in fields):
        net_val = float(fields["net_total"].value) if "net_total" in fields else None
        tax_nums: list[tuple[float, int, tuple[float, float, float, float]]] = []
        for page_num, text, _w, bbox in lines[tax_section_idx:]:
            for num in _extract_all_amounts(text):
                tax_nums.append((num, page_num, bbox))
        if "tax_rate" not in fields:
            for num, pg, bb in tax_nums:
                if 1.0 <= num <= 28.0 and abs(num - round(num)) < 0.01:
                    fields["tax_rate"] = ExtractedField(value=num / 100.0, page=pg, bbox=bb)
                    break
        if "taxable_amount" not in fields and net_val is not None:
            for num, pg, bb in tax_nums:
                if 0.5 * net_val < num < net_val:
                    fields["taxable_amount"] = ExtractedField(value=num, page=pg, bbox=bb)
                    break
        if "cgst" not in fields and "sgst" not in fields and "taxable_amount" in fields:
            taxable_v = float(fields["taxable_amount"].value)
            expected_half = round((net_val - taxable_v) / 2.0, 2) if net_val else None
            for num, pg, bb in tax_nums:
                if expected_half is not None and abs(num - expected_half) <= 0.1:
                    fields["cgst"] = ExtractedField(value=num, page=pg, bbox=bb)
                    fields["sgst"] = ExtractedField(value=num, page=pg, bbox=bb)
                    break

    if line_items:
        fields["line_items"] = ExtractedField(
            value=line_items,
            page=int(line_items[0]["page"]),
            bbox=line_items[0]["bbox"],
        )

    llm_data = optional_llm_structure("INVOICE_BILL", lines)
    if llm_data:
        for k, v in llm_data.items():
            if k not in fields and v is not None:
                fields[k] = ExtractedField(value=v, page=1, bbox=None)

    return fields
