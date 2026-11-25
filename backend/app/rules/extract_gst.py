"""Regex and position-based field extractor for GST Registration Certificates (REG-06)."""

from __future__ import annotations

import re

from app.models.schemas import ExtractedField, OcrWord
from app.rules.common import (
    DATE_PATTERN,
    find_value_after_label,
    ocr_lines_with_text,
    optional_llm_structure,
)

_GSTIN_CANDIDATE_RE = re.compile(r"\b[0-9A-Z]{15}\b")
_FIELD_LABELS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gstin", re.compile(r"(?i)(?:gstin|registration\s*number|reglstrationnumber|uin)")),
    ("legal_name", re.compile(r"(?i)(?:legal\s*name|legai\s*name|legl\s*sane)")),
    ("trade_name", re.compile(r"(?i)(?:trade\s*name|tredenanie)")),
    ("constitution", re.compile(r"(?i)constitution\s*of\s*business")),
    ("address", re.compile(r"(?i)address\s*o[tf]\s*prind?cipal")),
    ("date_of_liability", re.compile(r"(?i)date\s*o[tf]\s*l[il]ab[il]l")),
    ("validity_from", re.compile(r"(?i)(?:per[il]od\s*o[fr]\s*val[il]d|val[il]d\s*from)")),
    ("date_of_issue", re.compile(r"(?i)date\s*o[ft]\s*[il]s+ue")),
)


def extract_gst_fields(ocr_words: dict[int, list[OcrWord]]) -> dict[str, ExtractedField]:
    """Extract GST REG-06 fields with normalized bounding boxes."""
    lines = ocr_lines_with_text(ocr_words)
    fields: dict[str, ExtractedField] = {}
    field_order: list[str] = []

    for page_num, text, _words, bbox in lines:
        for key, pat in _FIELD_LABELS:
            if pat.search(text) and key not in field_order:
                field_order.append(key)
        if "gstin" not in fields:
            m = _GSTIN_CANDIDATE_RE.search(text.upper())
            if m and m.group(0)[:2].isdigit():
                fields["gstin"] = ExtractedField(value=m.group(0), page=page_num, bbox=bbox)

    for key, pat in _FIELD_LABELS:
        if key in fields:
            continue
        val_pat = DATE_PATTERN if "date" in key or "validity" in key else None
        found = find_value_after_label(lines, pat, val_pat)
        if found is not None:
            fields[key] = found

    full_text = "\n".join(t for _, t, _, _ in lines)
    lowered = full_text.lower()
    if "digitally" in lowered or "signed" in lowered:
        fields["digitally_signed"] = ExtractedField(value=True, page=1, bbox=None)
    if (
        "not verified" in lowered
        or "nat yetled" in lowered
        or "signature not verified" in lowered
        or "sgnatue" in lowered
    ):
        fields["signature_not_verified"] = ExtractedField(value=True, page=1, bbox=None)
    if field_order:
        fields["field_order"] = ExtractedField(value=field_order, page=1, bbox=None)

    llm_data = optional_llm_structure("GST_CERT", lines)
    if llm_data:
        for k, v in llm_data.items():
            if k not in fields and v is not None:
                fields[k] = ExtractedField(value=v, page=1, bbox=None)

    return fields
