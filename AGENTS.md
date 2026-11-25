# AGENTS.md — Kavach Project Rules

Kavach is a defence-only AI system for detecting tampering indicators in business documents (GST certificates, invoices/bills, bank/UPI statements, payment receipts).

## Core Engineering Rules

1. **Type Hints Everywhere**: All Python functions, methods, and module-level interfaces must have complete type annotations. TypeScript code must use strict typing (no `any`).
2. **Small, Single-Purpose Functions**: Keep functions concise and focused with shallow nesting and early returns.
3. **Shared Pydantic Contract**: Every analyzer and pipeline stage must return data using the shared schemas in `backend/app/models/schemas.py` (`AnalysisResult`, `Finding`, `Region`, `CheckResult`, or analyzer-specific outputs composed of those types). Never invent ad-hoc response dicts.
4. **Test Every Analyzer**: Every analyzer module must have a corresponding `pytest` file in `backend/tests/` covering normal execution, empty/edge inputs, and failure isolation.
5. **Never Claim Certainty**: Language in verdicts, findings, explanations, and UI copy must **never** state that a document is "proven fake", "guaranteed forged", or "100% fraudulent". Always use probabilistic, evidence-based phrasing such as *"indicators of tampering"*, *"anomalies detected"*, or *"requires manual verification"*.
6. **Privacy & Logging**:
   - Never log raw document content, extracted text, PII, or base64/binary payloads.
   - Only log structured operational metadata (`doc_id`, `mime_type`, `page_count`, `analyzer_name`, `processing_ms`, error class/message).
   - Uploaded files and rendered page artifacts must be stored in a temporary directory and automatically purged after 1 hour.
7. **Fault-Tolerant Pipeline**: Every pluggable analyzer in `app/pipeline.py` must be wrapped in `try/except` so a single failing analyzer never crashes the `/api/analyze` request.
8. **Input Validation**: Always validate uploaded files by magic bytes (not file extension) and enforce the 15 MB size limit before processing.
