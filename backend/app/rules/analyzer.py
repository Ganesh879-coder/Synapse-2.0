"""Document field extraction and consistency rules analyzer."""

from __future__ import annotations

from app.models.schemas import (
    AnalysisContext,
    AnalyzerOutput,
    CheckResult,
    Finding,
    Region,
    Signal,
)
from app.rules.checks_bank import run_bank_checks
from app.rules.checks_gst import run_gst_checks
from app.rules.checks_invoice import run_invoice_checks
from app.rules.checks_receipt import run_receipt_checks
from app.rules.extract_bank import extract_bank_fields
from app.rules.extract_gst import extract_gst_fields
from app.rules.extract_invoice import extract_invoice_fields
from app.rules.extract_receipt import extract_receipt_fields

_DOC_TYPE_ALIASES: dict[str, str] = {
    "gst_certificate": "GST_CERT",
    "GST_CERT": "GST_CERT",
    "invoice": "INVOICE_BILL",
    "INVOICE_BILL": "INVOICE_BILL",
    "bank_statement": "BANK_UPI_STATEMENT",
    "BANK_UPI_STATEMENT": "BANK_UPI_STATEMENT",
    "payment_receipt": "PAYMENT_RECEIPT",
    "PAYMENT_RECEIPT": "PAYMENT_RECEIPT",
}


class RulesAnalyzer:
    """Extracts structured fields and runs document-type consistency checks."""

    name: str = "rules"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Extract fields with bounding boxes and run consistency checks for ctx.doc_type."""
        canonical_type = _DOC_TYPE_ALIASES.get(ctx.doc_type, ctx.doc_type)
        if not ctx.ocr_words:
            return AnalyzerOutput(analyzer_name=self.name)

        checks: list[CheckResult] = []
        findings: list[Finding] = []
        regions: list[Region] = []
        signals: list[Signal] = []

        if canonical_type == "GST_CERT":
            extracted = extract_gst_fields(ctx.ocr_words, pages=ctx.pages)
            checks, findings, regions, signals = run_gst_checks(extracted)
        elif canonical_type == "INVOICE_BILL":
            extracted = extract_invoice_fields(ctx.ocr_words)
            checks, findings, regions, signals = run_invoice_checks(extracted)
        elif canonical_type == "BANK_UPI_STATEMENT":
            extracted = extract_bank_fields(ctx.ocr_words)
            checks, findings, regions, signals = run_bank_checks(extracted)
        elif canonical_type == "PAYMENT_RECEIPT":
            extracted = extract_receipt_fields(ctx.ocr_words)
            checks, findings, regions, signals = run_receipt_checks(extracted)
        else:
            extracted = {}

        top_conf = max((s.confidence for s in signals), default=0.0)
        return AnalyzerOutput(
            analyzer_name=self.name,
            regions=regions,
            findings=findings,
            checks=checks,
            extracted_fields=extracted,
            score=round(top_conf * 100.0, 2),
            signals=signals,
        )
