"""Regex and position-based field extractor for payment receipts."""

from __future__ import annotations

import re

from app.models.schemas import ExtractedField, OcrWord
from app.rules.common import (
    DATE_PATTERN,
    find_value_after_label,
    ocr_lines_with_text,
    optional_llm_structure,
    parse_amount_with_confusion,
)

_RECEIPT_NO_LABEL = re.compile(r"(?i)\b(?:receipt\s*no\.?|rcpt\s*no\.?)\b")
_RECEIPT_NO_VAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]{2,32}")
_CET_NO_LABEL = re.compile(r"(?i)\b(?:cet\s*no\.?|ref(?:erence)?\s*no\.?)\b")
_CET_NO_VAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]{2,24}")
_AMOUNT_LABEL = re.compile(r"(?i)(?:payment\s*amount|total\s+paid|paid\s+amount|\bamount\b)")
_AMOUNT_VAL = re.compile(r"(?:₹|rs\.?|inr)?\s*[0-9OIlSB][0-9OIlSB,]*(?:\.[0-9OIlSB]{1,2})?", re.I)
_DATE_LABEL = re.compile(r"(?i)\b(?:date|payment\s*date|receipt\s*date)\b")


def extract_receipt_fields(ocr_words: dict[int, list[OcrWord]]) -> dict[str, ExtractedField]:
    """Extract payment receipt fields with normalized bounding boxes."""
    lines = ocr_lines_with_text(ocr_words)
    fields: dict[str, ExtractedField] = {}

    rcpt = find_value_after_label(lines, _RECEIPT_NO_LABEL, _RECEIPT_NO_VAL)
    if rcpt:
        fields["receipt_no"] = rcpt

    cet = find_value_after_label(lines, _CET_NO_LABEL, _CET_NO_VAL)
    if cet:
        fields["cet_no"] = cet

    amt = find_value_after_label(lines, _AMOUNT_LABEL, _AMOUNT_VAL)
    if amt:
        parsed, _ = parse_amount_with_confusion(str(amt.value))
        if parsed is not None:
            fields["amount"] = ExtractedField(value=parsed, page=amt.page, bbox=amt.bbox)

    r_date = find_value_after_label(lines, _DATE_LABEL, DATE_PATTERN)
    if r_date:
        fields["date"] = r_date
    else:
        for page_num, text, _w, bbox in lines:
            m = DATE_PATTERN.search(text)
            if m:
                fields["date"] = ExtractedField(value=m.group(1), page=page_num, bbox=bbox)
                break

    llm_data = optional_llm_structure("PAYMENT_RECEIPT", lines)
    if llm_data:
        for k, v in llm_data.items():
            if k not in fields and v is not None:
                fields[k] = ExtractedField(value=v, page=1, bbox=None)

    return fields
