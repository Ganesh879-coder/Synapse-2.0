"""Regex and position-based field extractor for GST Registration Certificates (REG-06)."""

from __future__ import annotations

import re

from app.models.schemas import ExtractedField, OcrWord, PageImage
from app.ocr.engine import reocr_cropped_region
from app.rules.common import (
    DATE_PATTERN,
    find_value_after_label,
    ocr_lines_with_text,
    optional_llm_structure,
)

_GSTIN_CANDIDATE_RE = re.compile(r"\b[0-9A-Za-z]{14,15}\b")
_GSTIN_STRICT_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_FIELD_LABELS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gstin", re.compile(r"(?i)(?:gstin|reg[il]strat[il1o]on\s*n[a-z0-9]{2,8}er|uin)")),
    ("legal_name", re.compile(r"(?i)(?:legal\s*name|legai\s*name|legl\s*sane)")),
    ("trade_name", re.compile(r"(?i)(?:trade\s*name|tredenanie)")),
    ("constitution", re.compile(r"(?i)constitution\s*of\s*business")),
    ("address", re.compile(r"(?i)address\s*o[tf]\s*prind?cipal")),
    ("date_of_liability", re.compile(r"(?i)date\s*o[tf]\s*l[il]ab[il]l")),
    ("validity_from", re.compile(r"(?i)(?:per[il]od\s*o[fr]\s*val[il]d|val[il]d\s*from)")),
    ("date_of_issue", re.compile(r"(?i)date\s*o[ft]\s*[il]s+ue")),
)


def extract_gst_fields(
    ocr_words: dict[int, list[OcrWord]],
    pages: list[PageImage] | None = None,
) -> dict[str, ExtractedField]:
    """Extract GST REG-06 fields with normalized bounding boxes."""
    lines = ocr_lines_with_text(ocr_words)
    fields: dict[str, ExtractedField] = {}
    field_order: list[str] = []
    gstin_label_loc: tuple[int, tuple[float, float, float, float]] | None = None

    for page_num, text, _words, bbox in lines:
        for key, pat in _FIELD_LABELS:
            if pat.search(text):
                if key not in field_order:
                    field_order.append(key)
                if key == "gstin" and gstin_label_loc is None:
                    gstin_label_loc = (page_num, bbox)
        if "gstin" not in fields:
            m = _GSTIN_CANDIDATE_RE.search(text.upper())
            if m and m.group(0)[:2].isdigit():
                fields["gstin"] = ExtractedField(value=m.group(0), page=page_num, bbox=bbox)

    # Re-OCR cropped GSTIN cell at 3x Lanczos if missing or not strictly 15-char valid format.
    reocr_loc = gstin_label_loc or (
        (fields["gstin"].page, fields["gstin"].bbox)
        if "gstin" in fields and fields["gstin"].bbox is not None
        else None
    )
    if pages and reocr_loc is not None:
        cur_gstin = str(fields["gstin"].value).upper() if "gstin" in fields else ""
        if not _GSTIN_STRICT_RE.fullmatch(cur_gstin):
            pg_num, lbbox = reocr_loc
            target_page = next((p for p in pages if p.page == pg_num), None)
            if target_page is not None:
                re_words = reocr_cropped_region(target_page, lbbox)
                re_text = " ".join(w.text for w in re_words).upper()
                print(f"[RE-OCR GSTIN] before='{cur_gstin}' after='{re_text}'")
                m = re.search(r"\b[0-9A-Z]{14,15}\b", re_text)
                if m and m.group(0)[:2].isdigit():
                    fields["gstin"] = ExtractedField(value=m.group(0), page=pg_num, bbox=lbbox)

    for key, pat in _FIELD_LABELS:
        if key in fields:
            continue
        val_pat = DATE_PATTERN if "date" in key or "validity" in key else None
        found = find_value_after_label(lines, pat, val_pat)
        if found is not None:
            if key == "address":
                for idx, (_pg, txt, _w, _bb) in enumerate(lines):
                    if pat.search(txt) and idx + 1 < len(lines):
                        found = ExtractedField(
                            value=f"{found.value} {lines[idx + 1][1]}".strip(),
                            page=found.page,
                            bbox=found.bbox,
                        )
                        break
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
