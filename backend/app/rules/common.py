"""Shared regex, date/amount parsing, and optional LLM extraction helpers."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime
from typing import Any

import httpx

from app.models.schemas import (
    CheckResult,
    ExtractedField,
    Finding,
    FindingCategory,
    OcrWord,
    Region,
    SeverityLevel,
)
from app.ocr.engine import group_ocr_lines

_DATE_FORMATS: tuple[str, ...] = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%b %d, %Y",
    "%b %d,%Y",
    "%d %b, %Y",
    "%d %b,%Y",
    "%d%m%Y",
)

DATE_PATTERN = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r"|\d{1,2}\s+[A-Za-z0]{3,9},?\s+\d{4}|\d{1,2}-[A-Za-z]{3}-\d{4}"
    r"|[A-Za-z]{3}\s*\d{1,2},?\s*\d{4})\b"
)


def parse_date(text: str) -> date | None:
    """Parse common Indian business document date formats."""
    cleaned = text.strip().rstrip(".,;:")
    cleaned = re.sub(r"\b0ct\b", "Oct", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^([A-Za-z]{3})(\d{1,2},)", r"\1 \2", cleaned)
    cleaned = re.sub(r"^(\d{2})/(\d{6})$", r"\1\2", cleaned)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(text: str) -> float | None:
    """Parse numeric currency amount, stripping commas and currency symbols."""
    cleaned = re.sub(r"[₹$,\s]|\b(?:inr|rs\.?)\b", "", text, flags=re.IGNORECASE).strip()
    if not cleaned:
        return None
    if not re.fullmatch(r"-?\d+(?:\.\d{1,4})?", cleaned):
        return None
    return float(cleaned)


_AMOUNT_CONFUSION_TABLE = str.maketrans(
    {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"}
)


def parse_amount_with_confusion(text: str) -> tuple[float | None, bool]:
    """Parse amount, retrying once with O/0, I/1, S/5, B/8 OCR confusion mapping."""
    direct = parse_amount(text)
    if direct is not None:
        return direct, False
    cleaned = re.sub(r"[₹$,\s]|\b(?:inr|rs\.?)\b", "", text, flags=re.IGNORECASE).strip()
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None, False
    corrected = cleaned.translate(_AMOUNT_CONFUSION_TABLE)
    if corrected != cleaned:
        retried = parse_amount(corrected)
        if retried is not None:
            return retried, True
    return None, False


def ocr_lines_with_text(
    ocr_words: dict[int, list[OcrWord]],
) -> list[tuple[int, str, list[OcrWord], tuple[float, float, float, float]]]:
    """Return (page, joined_line_text, words, line_bbox) across all pages."""
    rows: list[tuple[int, str, list[OcrWord], tuple[float, float, float, float]]] = []
    for page_num in sorted(ocr_words):
        for line in group_ocr_lines(ocr_words[page_num]):
            text = " ".join(w.text for w in line)
            bbox = (
                min(w.bbox[0] for w in line),
                min(w.bbox[1] for w in line),
                max(w.bbox[2] for w in line),
                max(w.bbox[3] for w in line),
            )
            rows.append((page_num, text, line, bbox))
    return rows


def find_value_after_label(
    lines: list[tuple[int, str, list[OcrWord], tuple[float, float, float, float]]],
    label_pattern: re.Pattern[str],
    value_pattern: re.Pattern[str] | None = None,
) -> ExtractedField | None:
    """Find a field value on the same line after a label (or on the immediately following line)."""
    for idx, (page_num, text, _words, bbox) in enumerate(lines):
        match = label_pattern.search(text)
        if not match:
            continue
        remainder = text[match.end() :].strip(" :-\t")
        if remainder:
            if value_pattern is not None:
                val_match = value_pattern.search(remainder)
                if val_match:
                    return ExtractedField(
                        value=val_match.group(0).strip(), page=page_num, bbox=bbox
                    )
            else:
                return ExtractedField(value=remainder, page=page_num, bbox=bbox)
        if idx + 1 < len(lines):
            next_page, next_text, _nw, next_bbox = lines[idx + 1]
            if value_pattern is not None:
                val_match = value_pattern.search(next_text)
                if val_match:
                    return ExtractedField(
                        value=val_match.group(0).strip(), page=next_page, bbox=next_bbox
                    )
            elif next_text.strip():
                return ExtractedField(value=next_text.strip(), page=next_page, bbox=next_bbox)
    return None


def make_failure(
    check_name: str,
    detail: str,
    title: str,
    category: FindingCategory,
    severity: SeverityLevel,
    field: ExtractedField | None = None,
    status: str = "fail",
) -> tuple[CheckResult, Finding, Region | None]:
    """Build a CheckResult, Finding, and optional Region from a failed/warned rule."""
    region: Region | None = None
    region_ids: list[str] = []
    if field is not None and field.bbox is not None:
        region = Region(
            id=uuid.uuid4().hex[:12],
            page=field.page,
            bbox=field.bbox,
            score=0.8 if status == "fail" else 0.45,
            reason=detail,
        )
        region_ids.append(region.id)

    check = CheckResult(
        name=check_name,
        status="warn" if status == "warn" else "fail",
        detail=detail,
    )
    finding = Finding(
        id=uuid.uuid4().hex[:12],
        category=category,
        severity=severity,
        title=title,
        plain_explanation=detail,
        technical_detail=f"Rule '{check_name}' reported {status}: {detail}",
        evidence_region_ids=region_ids,
    )
    return check, finding, region


def optional_llm_structure(
    doc_type: str,
    lines: list[tuple[int, str, list[OcrWord], tuple[float, float, float, float]]],
) -> dict[str, Any] | None:
    """Optionally structure OCR text via an env-configured LLM endpoint; returns None if unset."""
    api_url = os.getenv("KAVACH_LLM_API_URL", "").strip()
    api_key = os.getenv("KAVACH_LLM_API_KEY", "").strip()
    model = os.getenv("KAVACH_LLM_MODEL", "gpt-4o-mini").strip()
    if not api_url or not api_key:
        return None

    joined_text = "\n".join(text for _, text, _, _ in lines)[:6000]
    try:
        resp = httpx.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": f"Extract key fields from this {doc_type} as flat JSON.",
                    },
                    {"role": "user", "content": joined_text},
                ],
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
