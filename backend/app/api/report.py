"""One-page ReportLab PDF verification report generator."""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.schemas import AnalysisResult


def build_pdf_report(result: AnalysisResult, annotated_image_path: Path | None) -> bytes:
    """Render a compact one-page PDF report with verdict, score, image, reasons, and checks."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "KavachTitle",
        parent=styles["Heading1"],
        fontSize=15,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "KavachSub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#475569"),
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "KavachBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
    )
    disclaimer_style = ParagraphStyle(
        "KavachDisclaimer",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )

    story: list[object] = []
    story.append(Paragraph("Kavach Document Verification Report", heading))
    story.append(
        Paragraph(
            f"Document ID: {result.doc_id} | Type: {result.doc_type} | "
            f"Risk Score: {result.risk_score}/100 ({result.risk_level}) | "
            f"Confidence: {int(round(result.confidence * 100))}%",
            sub_style,
        )
    )
    story.append(Paragraph(f"<b>Verdict:</b> {result.verdict}", body_style))

    if annotated_image_path is not None and annotated_image_path.is_file():
        img = RLImage(str(annotated_image_path), width=85 * mm, height=60 * mm, kind="proportional")
        story.append(Spacer(1, 3 * mm))
        story.append(img)
        story.append(Spacer(1, 3 * mm))

    top_reasons = (
        result.summary.top_reasons
        if result.summary and result.summary.top_reasons
        else [f.plain_explanation for f in result.findings[:4]]
    )
    if top_reasons:
        story.append(Paragraph("<b>Top Reasons:</b>", body_style))
        for reason in top_reasons[:4]:
            story.append(Paragraph(f"&bull; {reason}", body_style))

    if result.checks:
        story.append(Spacer(1, 2 * mm))
        table_data = [["Check", "Status", "Detail"]]
        for chk in result.checks[:8]:
            detail_short = (chk.detail[:95] + "...") if len(chk.detail) > 95 else chk.detail
            table_data.append([chk.name, chk.status.upper(), detail_short])
        tbl = Table(table_data, colWidths=[45 * mm, 22 * mm, 112 * mm])
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(tbl)

    disclaimer = (
        result.summary.disclaimer
        if result.summary
        else "This automated report highlights statistical and structural indicators only."
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Disclaimer:</b> {disclaimer}", disclaimer_style))

    doc.build(story)  # type: ignore[arg-type]
    return buf.getvalue()
