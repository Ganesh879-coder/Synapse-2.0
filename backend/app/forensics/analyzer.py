"""Forensics analyzer orchestrating visual, text-patch, and metadata checks."""

from __future__ import annotations

import uuid

from app.forensics.common import load_page_bgr
from app.forensics.copy_move import analyze_copy_move
from app.forensics.ela import analyze_ela
from app.forensics.fuse import merge_regions_by_iou, render_heatmap_overlay
from app.forensics.jpeg_ghost import analyze_jpeg_ghost
from app.forensics.metadata import analyze_metadata
from app.forensics.noise_inconsistency import analyze_noise_inconsistency
from app.forensics.quality import estimate_page_quality
from app.forensics.text_patch import analyze_text_patch
from app.models.schemas import (
    AnalysisContext,
    AnalyzerOutput,
    CheckResult,
    Finding,
    PageImage,
    Region,
    Signal,
)


class ForensicsAnalyzer:
    """Per-page visual and document metadata forensics analyzer."""

    name: str = "forensics"

    def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Run all forensics checks across pages and fuse top regions into a heatmap."""
        all_regions: list[Region] = []
        findings: list[Finding] = []
        checks: list[CheckResult] = []
        signals: list[Signal] = []
        readable_pages: list[PageImage] = []
        screenshot_votes = 0

        for page in ctx.pages:
            try:
                bgr = load_page_bgr(page)
            except ValueError:
                continue
            readable_pages.append(page)
            q_score, is_ss = estimate_page_quality(bgr, ctx.mime)
            ctx.quality[page.page] = q_score
            if is_ss:
                screenshot_votes += 1

        if readable_pages and screenshot_votes == len(readable_pages):
            ctx.is_screenshot_like = True

        for page in readable_pages:
            q_score = ctx.quality.get(page.page, 1.0)
            is_ss = ctx.is_screenshot_like

            # 1. Text patch (highest weight for edited amounts/names/dates/GSTINs)
            tp_regions, tp_score = analyze_text_patch(
                page, ctx.ocr_words.get(page.page, []), quality=q_score, is_screenshot_like=is_ss
            )
            if min(page.width, page.height) < 1000:
                tp_score = round(tp_score * 0.5, 4)
                for reg in tp_regions:
                    reg.score = round(reg.score * 0.5, 4)
            self._record_detector("text_patch", tp_regions, tp_score, 0.9, all_regions, signals)

            # 2. ELA
            ela_regions, ela_score = analyze_ela(
                page, mime=ctx.mime, is_screenshot_like=is_ss, quality=q_score
            )
            self._record_detector("ela", ela_regions, ela_score, 0.45, all_regions, signals)

            # 3. Copy-move
            cm_regions, cm_score = analyze_copy_move(
                page, quality=q_score, is_screenshot_like=is_ss
            )
            self._record_detector("copy_move", cm_regions, cm_score, 0.65, all_regions, signals)

            # 4. Noise inconsistency
            ns_regions, ns_score = analyze_noise_inconsistency(
                page, quality=q_score, is_screenshot_like=is_ss
            )
            self._record_detector("noise", ns_regions, ns_score, 0.45, all_regions, signals)

            # 5. JPEG ghost
            jg_regions, jg_score = analyze_jpeg_ghost(
                page, mime=ctx.mime, is_screenshot_like=is_ss, quality=q_score
            )
            self._record_detector("jpeg_ghost", jg_regions, jg_score, 0.45, all_regions, signals)

        # 6. Metadata (EXIF / PDF)
        if ctx.file_bytes:
            m_findings, m_checks, m_regions, m_score = analyze_metadata(
                ctx.file_bytes, ctx.mime, ctx.pages, ctx.ocr_words
            )
            findings.extend(m_findings)
            checks.extend(m_checks)
            all_regions.extend(m_regions)
            if m_score >= 0.3:
                signals.append(
                    Signal(
                        name="forensics:metadata",
                        category="metadata",
                        weight_hint=0.65,
                        confidence=m_score,
                        region_ids=[r.id for r in m_regions],
                    )
                )

        fused_regions = merge_regions_by_iou(all_regions, iou_threshold=0.35, max_regions=10)

        # Create summary finding when visual regions exceed threshold.
        high_visual = [r for r in fused_regions if r.score >= 0.35]
        if high_visual:
            findings.append(
                Finding(
                    id=uuid.uuid4().hex[:12],
                    category="visual",
                    severity="high" if high_visual[0].score >= 0.7 else "medium",
                    title="Visual tampering indicators detected",
                    plain_explanation=(
                        f"Detected {len(high_visual)} localized region(s) with visual anomalies "
                        "that may indicate editing or patching; manual verification is recommended."
                    ),
                    technical_detail="Fused forensics score exceeded threshold.",
                    evidence_region_ids=[r.id for r in high_visual],
                )
            )

        # Render combined heatmap PNG per readable page.
        for page in readable_pages:
            out_path = page.image_path.parent / f"heatmap_page_{page.page}.png"
            render_heatmap_overlay(page, fused_regions, out_path)
            if page.page == 1:
                ctx.heatmap_url = f"/api/artifacts/{ctx.doc_id}/heatmap_page_1.png"

        top_score = max((r.score for r in fused_regions), default=0.0)
        return AnalyzerOutput(
            analyzer_name=self.name,
            regions=fused_regions,
            findings=findings,
            checks=checks,
            score=round(top_score * 100.0, 2),
            signals=signals,
        )

    def _record_detector(
        self,
        detector_name: str,
        regions: list[Region],
        score: float,
        weight_hint: float,
        all_regions: list[Region],
        signals: list[Signal],
    ) -> None:
        """Append detector regions and emit a Signal if score is meaningful."""
        if not regions:
            return
        all_regions.extend(regions)
        if score >= 0.25:
            signals.append(
                Signal(
                    name=f"forensics:{detector_name}",
                    category="visual",
                    weight_hint=weight_hint,
                    confidence=min(1.0, max(0.0, score)),
                    region_ids=[r.id for r in regions],
                )
            )
