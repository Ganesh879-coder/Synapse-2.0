"""Single rule-based document classifier used by the pipeline before rules run."""

from __future__ import annotations

from app.models.schemas import AnalysisContext, AnalyzerOutput, OcrWord

_DOC_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "GST_CERT",
        (
            "registration certificate",
            "registration certiffeate",
            "registration certifieate",
            "registrution certificate",
            "registration certificeate",
            "gst reg-06",
            "fotmgstreg",
            "form gst reg",
            "goods and services tax",
            "constitution of business",
            "constitutionofbusiness",
            "registrationnumber",
            "reglstrationnumber",
            "reglstratlonnumber",
        ),
    ),
    (
        "INVOICE_BILL",
        (
            "bill no",
            "billno",
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
            "transactionid",
        ),
    ),
    (
        "PAYMENT_RECEIPT",
        (
            "payment receipt",
            "paymentreceipt",
            "receipt no",
            "received with thanks",
            "cet no",
        ),
    ),
)


def classify_document(words: list[OcrWord], raw_text: str = "") -> str:
    """Classify document type from OCR words or raw text using keyword matching."""
    combined = " ".join([raw_text, *(w.text for w in words)]).lower()
    if not combined.strip():
        return "UNKNOWN"

    best_type = "UNKNOWN"
    best_hits = 0
    for doc_type, keywords in _DOC_TYPE_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in combined)
        if hits > best_hits:
            best_hits = hits
            best_type = doc_type
    return best_type


class ClassifyAnalyzer:
    """Pipeline stage that sets ctx.doc_type from OCR words before rules run."""

    name: str = "classify"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Classify ctx.doc_type when unknown/auto using OCR words."""
        if ctx.doc_type in {"unknown", "UNKNOWN", "auto", ""}:
            all_words = [w for page_words in ctx.ocr_words.values() for w in page_words]
            ctx.doc_type = classify_document(all_words)
        return AnalyzerOutput(analyzer_name=self.name)
