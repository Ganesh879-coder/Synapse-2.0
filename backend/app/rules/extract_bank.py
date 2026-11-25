"""Regex and position-based field extractor for bank and UPI statements."""

from __future__ import annotations

import re
from typing import Any

from app.models.schemas import ExtractedField, OcrWord
from app.rules.common import (
    DATE_PATTERN,
    ocr_lines_with_text,
    optional_llm_structure,
    parse_amount,
    parse_date,
)

_PERIOD_RE = re.compile(
    r"(?i)(?:statement\s+period|period|from)?\s*"
    r"(\d{1,2}\s+[A-Za-z0]{3},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})"
    r"\s*(?:to|-)\s*"
    r"(\d{1,2}\s+[A-Za-z0]{3},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})"
)
_PAGE_X_OF_N_RE = re.compile(r"(?i)\bpage\s*(\d+)\s*of\s*(\d+)\b")
_UPI_TX_RE = re.compile(r"(?:Transaction\s*ID\s*)?(T\d{8,24})\b", re.I)
_UTR_RE = re.compile(r"(?:UTR\s*No\.?\s*)?(\d{12})\b", re.I)
_AMOUNT_TOKEN_RE = re.compile(r"\b\d[\d,]*(?:\.\d{1,2})?\b")


def extract_bank_fields(ocr_words: dict[int, list[OcrWord]]) -> dict[str, ExtractedField]:
    """Extract statement period, pagination, and multi-line transaction rows."""
    lines = ocr_lines_with_text(ocr_words)
    fields: dict[str, ExtractedField] = {}
    transactions: list[dict[str, Any]] = []
    page_markers: list[dict[str, Any]] = []
    current_row: dict[str, Any] | None = None

    for page_num, text, _words, bbox in lines:
        if "statement_period" not in fields:
            period_m = _PERIOD_RE.search(text)
            if period_m and (
                parse_date(period_m.group(1)) is not None
                and parse_date(period_m.group(2)) is not None
            ):
                fields["statement_period"] = ExtractedField(
                    value={"start": period_m.group(1), "end": period_m.group(2)},
                    page=page_num,
                    bbox=bbox,
                )
                continue

        page_m = _PAGE_X_OF_N_RE.search(text)
        if page_m:
            page_markers.append(
                {
                    "page": page_num,
                    "x": int(page_m.group(1)),
                    "n": int(page_m.group(2)),
                    "bbox": bbox,
                }
            )

        date_m = DATE_PATTERN.search(text)
        if date_m and parse_date(date_m.group(1)) is not None:
            tx_m = _UPI_TX_RE.search(text)
            utr_m = _UTR_RE.search(text)
            has_type = bool(re.search(r"\b(?:DEBIT|CREDIT)\b", text, re.I))
            amt_matches = _AMOUNT_TOKEN_RE.findall(text)
            valid_amounts = [
                a for raw in amt_matches if (a := parse_amount(raw)) is not None
            ]
            if tx_m or utr_m or has_type or valid_amounts:
                current_row = {
                    "date_str": date_m.group(1),
                    "tx_id": tx_m.group(1) if tx_m else None,
                    "utr": utr_m.group(1) if utr_m else None,
                    "amounts": valid_amounts,
                    "raw_amounts": amt_matches,
                    "page": page_num,
                    "bbox": bbox,
                }
                transactions.append(current_row)
                continue

        if current_row is not None:
            if current_row.get("tx_id") is None:
                tx_m = _UPI_TX_RE.search(text)
                if tx_m:
                    current_row["tx_id"] = tx_m.group(1)
            if current_row.get("utr") is None:
                utr_m = _UTR_RE.search(text)
                if utr_m:
                    current_row["utr"] = utr_m.group(1)

    if transactions:
        fields["transactions"] = ExtractedField(
            value=transactions,
            page=int(transactions[0]["page"]),
            bbox=transactions[0]["bbox"],
        )
    if page_markers:
        fields["page_markers"] = ExtractedField(
            value=page_markers,
            page=int(page_markers[0]["page"]),
            bbox=page_markers[0]["bbox"],
        )

    llm_data = optional_llm_structure("BANK_UPI_STATEMENT", lines)
    if llm_data:
        for k, v in llm_data.items():
            if k not in fields and v is not None:
                fields[k] = ExtractedField(value=v, page=1, bbox=None)

    return fields
