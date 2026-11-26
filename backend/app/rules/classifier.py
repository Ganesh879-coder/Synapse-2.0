"""Single fuzzy rule-based document classifier used by the pipeline before rules run."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models.schemas import AnalysisContext, AnalyzerOutput, OcrWord
from app.ocr.engine import reocr_upscaled_page

_GSTIN_CUE_RE = re.compile(r"\b\d{2}[A-Z0-9]{10,13}\b")

_DOC_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "GST_CERT",
        (
            "registration certificate",
            "gst reg-06",
            "form gst reg-06",
            "government of india",
            "legal name",
            "trade name",
            "goods and services tax",
            "constitution of business",
        ),
    ),
    (
        "INVOICE_BILL",
        (
            "bill no",
            "net total",
            "cgst",
            "sgst",
            "tax invoice",
            "grand total",
            "taxable",
        ),
    ),
    (
        "BANK_UPI_STATEMENT",
        (
            "transaction statement",
            "utr",
            "debit",
            "credit",
            "account statement",
            "transaction id",
        ),
    ),
    (
        "PAYMENT_RECEIPT",
        (
            "payment receipt",
            "receipt no",
            "received with thanks",
            "cet no",
            "payment amount",
        ),
    ),
)


def _fuzzy_contains(text: str, keyword: str, threshold: float = 0.80) -> bool:
    """Return True if keyword appears directly or with SequenceMatcher ratio >= threshold."""
    if keyword in text:
        return True
    kw_len = len(keyword)
    if len(text) < kw_len - 2:
        return False
    tokens = text.split()
    kw_words = keyword.split()
    n_kw = len(kw_words)
    if len(tokens) < n_kw:
        return SequenceMatcher(None, text, keyword).ratio() >= threshold
    for i in range(len(tokens) - n_kw + 1):
        window = " ".join(tokens[i : i + n_kw])
        if SequenceMatcher(None, window, keyword).ratio() >= threshold:
            return True
    # Also check spaceless concatenation against spaceless keyword.
    compact_kw = keyword.replace(" ", "")
    for tok in tokens:
        if len(tok) >= len(compact_kw) - 3:
            if SequenceMatcher(None, tok[: len(compact_kw) + 2], compact_kw).ratio() >= threshold:
                return True
    return False


def classify_document(words: list[OcrWord], raw_text: str = "") -> str:
    """Classify document type from OCR words or raw text using fuzzy keyword matching."""
    combined_raw = " ".join([raw_text, *(w.text for w in words)])
    combined = combined_raw.lower()
    if not combined.strip():
        return "UNKNOWN"

    scores: dict[str, int] = {}
    for doc_type, keywords in _DOC_TYPE_KEYWORDS:
        hits = sum(1 for kw in keywords if _fuzzy_contains(combined, kw))
        scores[doc_type] = hits

    # Strong GST_CERT cue: GSTIN-like 12-15 char alphanumeric token starting with 2 digits.
    if _GSTIN_CUE_RE.search(combined_raw.upper()):
        scores["GST_CERT"] = scores.get("GST_CERT", 0) + 2

    best_type = max(scores, key=lambda k: scores[k])
    return best_type if scores[best_type] > 0 else "UNKNOWN"


class ClassifyAnalyzer:
    """Pipeline stage that sets ctx.doc_type from OCR words before rules run."""

    name: str = "classify"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Classify ctx.doc_type; retry OCR on 2x upscaled page if first pass is UNKNOWN."""
        if ctx.doc_type in {"unknown", "UNKNOWN", "auto", ""}:
            all_words = [w for page_words in ctx.ocr_words.values() for w in page_words]
            detected = classify_document(all_words)
            if detected == "UNKNOWN" and ctx.pages:
                retry_words = reocr_upscaled_page(ctx.pages[0], scale=2.0)
                if retry_words:
                    detected = classify_document(retry_words)
                    if not ctx.ocr_words.get(ctx.pages[0].page):
                        ctx.ocr_words[ctx.pages[0].page] = retry_words
            ctx.doc_type = detected
        return AnalyzerOutput(analyzer_name=self.name)
