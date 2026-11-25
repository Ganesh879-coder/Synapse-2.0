"""EXIF and PDF metadata, incremental update, font, and signature forensics."""

from __future__ import annotations

import io
import uuid

import pymupdf
from PIL import ExifTags, Image

from app.models.schemas import CheckResult, Finding, OcrWord, PageImage, Region

_SUSPICIOUS_EDITORS: tuple[str, ...] = (
    "photoshop",
    "canva",
    "gimp",
    "ilovepdf",
    "smallpdf",
    "sejda",
    "pdf24",
    "pixlr",
    "snapseed",
    "lightroom",
    "microsoft word",
)


def _check_editor_tag(value: str | None) -> str | None:
    """Return matching suspicious editor keyword if present."""
    if not value:
        return None
    lowered = value.lower()
    for editor in _SUSPICIOUS_EDITORS:
        if editor in lowered:
            return editor
    return None


def _analyze_image_metadata(
    file_bytes: bytes,
) -> tuple[list[Finding], list[CheckResult], float]:
    """Inspect JPEG/PNG EXIF and text chunks for editing software tags."""
    findings: list[Finding] = []
    checks: list[CheckResult] = []
    score = 0.0

    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            software_tags: list[str] = []
            exif = img.getexif()
            if exif:
                for tag_id, val in exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if tag_name in {"Software", "ProcessingSoftware"} and isinstance(val, str):
                        software_tags.append(val)
            for key in ("Software", "software", "Creator", "Producer"):
                info_val = img.info.get(key)
                if isinstance(info_val, str):
                    software_tags.append(info_val)

            matched = next(
                (_check_editor_tag(tag) for tag in software_tags if _check_editor_tag(tag)),
                None,
            )
            if matched:
                findings.append(
                    Finding(
                        id=uuid.uuid4().hex[:12],
                        category="metadata",
                        severity="medium",
                        title="Image editing software tag detected",
                        plain_explanation=(
                            f"File metadata references an image editor ({matched}), which may "
                            "indicate post-capture modification."
                        ),
                        technical_detail=f"Matched editor keyword '{matched}' in image metadata.",
                    )
                )
                checks.append(
                    CheckResult(
                        name="metadata:image_software",
                        status="warn",
                        detail=f"Editor tag '{matched}' found in metadata.",
                    )
                )
                score = max(score, 0.55)
            else:
                checks.append(
                    CheckResult(
                        name="metadata:image_software",
                        status="pass",
                        detail="No known image-editor tags found in metadata.",
                    )
                )
    except Exception:
        checks.append(
            CheckResult(
                name="metadata:image_software",
                status="skipped",
                detail="Could not parse image metadata.",
            )
        )

    return findings, checks, score


def _analyze_pdf_metadata(
    file_bytes: bytes,
    ocr_words: dict[int, list[OcrWord]],
) -> tuple[list[Finding], list[CheckResult], list[Region], float]:
    """Inspect PDF metadata, %%EOF updates, font mismatches, OCR parity, and signatures."""
    findings: list[Finding] = []
    checks: list[CheckResult] = []
    regions: list[Region] = []
    score = 0.0

    # 1. Incremental updates (multiple %%EOF markers).
    eof_count = file_bytes.count(b"%%EOF")
    if eof_count > 1:
        findings.append(
            Finding(
                id=uuid.uuid4().hex[:12],
                category="metadata",
                severity="medium",
                title="PDF incremental updates detected",
                plain_explanation=(
                    f"This PDF contains {eof_count} revision markers, suggesting it was "
                    "modified and re-saved after initial creation."
                ),
                technical_detail=f"Detected {eof_count} '%%EOF' markers in PDF byte stream.",
            )
        )
        checks.append(
            CheckResult(
                name="metadata:pdf_incremental_updates",
                status="warn",
                detail=f"Multiple %%EOF markers ({eof_count}) found.",
            )
        )
        score = max(score, 0.5)
    else:
        checks.append(
            CheckResult(
                name="metadata:pdf_incremental_updates",
                status="pass",
                detail="Single %%EOF marker.",
            )
        )

    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        meta = doc.metadata or {}
        producer = meta.get("producer") or ""
        creator = meta.get("creator") or ""
        creation_date = meta.get("creationDate") or ""
        mod_date = meta.get("modDate") or ""

        if not producer and not creator:
            checks.append(
                CheckResult(
                    name="metadata:pdf_fields",
                    status="warn",
                    detail="PDF Producer and Creator metadata are missing.",
                )
            )
            score = max(score, 0.25)
        else:
            editor = _check_editor_tag(producer) or _check_editor_tag(creator)
            if editor:
                findings.append(
                    Finding(
                        id=uuid.uuid4().hex[:12],
                        category="metadata",
                        severity="medium",
                        title="PDF editor metadata detected",
                        plain_explanation=(
                            f"PDF metadata references '{editor}', indicating the file was "
                            "processed with a document or image editor."
                        ),
                        technical_detail="Matched suspicious Producer/Creator tag in PDF info.",
                    )
                )
                checks.append(
                    CheckResult(
                        name="metadata:pdf_fields",
                        status="warn",
                        detail=f"Editor '{editor}' referenced in PDF metadata.",
                    )
                )
                score = max(score, 0.55)
            else:
                checks.append(
                    CheckResult(
                        name="metadata:pdf_fields",
                        status="pass",
                        detail="PDF Producer/Creator metadata present without editor flags.",
                    )
                )

        if creation_date and mod_date and mod_date > creation_date:
            findings.append(
                Finding(
                    id=uuid.uuid4().hex[:12],
                    category="metadata",
                    severity="low",
                    title="PDF modified after creation date",
                    plain_explanation=(
                        "The PDF modification timestamp is later than its creation timestamp."
                    ),
                    technical_detail="PDF ModDate is chronologically after CreationDate.",
                )
            )
            score = max(score, 0.35)

        # 2. Digital signature presence (not cryptographically verified).
        has_sig = b"/Type /Sig" in file_bytes or b"/adbe.pkcs7" in file_bytes
        if not has_sig:
            for page in doc:
                if any(getattr(w, "field_type", None) == 7 for w in page.widgets()):
                    has_sig = True
                    break
        if has_sig:
            findings.append(
                Finding(
                    id=uuid.uuid4().hex[:12],
                    category="metadata",
                    severity="low",
                    title="Digital signature present but not verified",
                    plain_explanation=(
                        "This PDF contains a digital signature block, which has not been "
                        "cryptographically verified against a trusted certificate authority."
                    ),
                    technical_detail="Signature dictionary/widget detected; verification skipped.",
                )
            )
            checks.append(
                CheckResult(
                    name="metadata:pdf_signature",
                    status="warn",
                    detail="Digital signature present but not verified.",
                )
            )

        # 3. Embedded font mismatch within the same line + text-layer vs OCR check.
        font_mismatch_found = False
        for page_idx, page in enumerate(doc, start=1):
            pw = max(1.0, float(page.rect.width))
            ph = max(1.0, float(page.rect.height))
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = [s for s in line.get("spans", []) if str(s.get("text", "")).strip()]
                    fonts = {str(s.get("font", "")) for s in spans if s.get("font")}
                    if len(fonts) > 2:
                        font_mismatch_found = True
                        bbox = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
                        regions.append(
                            Region(
                                id=uuid.uuid4().hex[:12],
                                page=page_idx,
                                bbox=(
                                    round(max(0.0, bbox[0] / pw), 4),
                                    round(max(0.0, bbox[1] / ph), 4),
                                    round(min(1.0, bbox[2] / pw), 4),
                                    round(min(1.0, bbox[3] / ph), 4),
                                ),
                                score=0.55,
                                reason="Multiple distinct embedded fonts appear on the same line.",
                            )
                        )

            # Text-layer vs rendered-image OCR mismatch when OCR words are available.
            page_ocr = ocr_words.get(page_idx, [])
            if page_ocr:
                pdf_words = {
                    str(w[4]).strip().lower()
                    for w in page.get_text("words")
                    if len(w) >= 5 and str(w[4]).strip()
                }
                ocr_tokens = {w.text.strip().lower() for w in page_ocr if w.text.strip()}
                if pdf_words and ocr_tokens:
                    overlap = len(pdf_words & ocr_tokens) / max(1, len(ocr_tokens))
                    if overlap < 0.35:
                        findings.append(
                            Finding(
                                id=uuid.uuid4().hex[:12],
                                category="consistency",
                                severity="high",
                                title="PDF text layer differs from rendered image",
                                plain_explanation=(
                                    "The invisible text stored inside the PDF does not match the "
                                    "visible text on the page image."
                                ),
                                technical_detail=(
                                    f"Page {page_idx} PDF/OCR token overlap={overlap:.2f}."
                                ),
                            )
                        )
                        score = max(score, 0.75)

        if font_mismatch_found:
            findings.append(
                Finding(
                    id=uuid.uuid4().hex[:12],
                    category="format",
                    severity="medium",
                    title="Mixed embedded fonts on the same line",
                    plain_explanation=(
                        "Multiple unrelated fonts were found within a single line of text, "
                        "which can be an indicator of text replacement."
                    ),
                    technical_detail="Line contains >2 distinct embedded PDF font families.",
                )
            )
            score = max(score, 0.55)

    return findings, checks, regions, score


def analyze_metadata(
    file_bytes: bytes,
    mime: str,
    pages: list[PageImage],
    ocr_words: dict[int, list[OcrWord]],
) -> tuple[list[Finding], list[CheckResult], list[Region], float]:
    """Run EXIF or PDF metadata forensics depending on validated MIME type."""
    _ = pages
    if mime == "application/pdf":
        return _analyze_pdf_metadata(file_bytes, ocr_words)
    findings, checks, score = _analyze_image_metadata(file_bytes)
    return findings, checks, [], score
