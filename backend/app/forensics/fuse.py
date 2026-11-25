"""Region fusion (IoU merge) and semi-transparent red heatmap overlay rendering."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.forensics.common import compute_iou, load_page_bgr
from app.models.schemas import PageImage, Region


def merge_regions_by_iou(
    regions: list[Region],
    iou_threshold: float = 0.35,
    max_regions: int = 10,
) -> list[Region]:
    """Merge overlapping regions per page by IoU and keep the top-scoring regions."""
    if not regions:
        return []

    ordered = sorted(regions, key=lambda r: r.score, reverse=True)
    merged: list[Region] = []

    for candidate in ordered:
        matched_idx: int | None = None
        for idx, existing in enumerate(merged):
            if existing.page == candidate.page and (
                compute_iou(existing.bbox, candidate.bbox) >= iou_threshold
            ):
                matched_idx = idx
                break

        if matched_idx is None:
            merged.append(candidate.model_copy())
        else:
            existing = merged[matched_idx]
            ax0, ay0, ax1, ay1 = existing.bbox
            bx0, by0, bx1, by1 = candidate.bbox
            combined_bbox = (
                min(ax0, bx0),
                min(ay0, by0),
                max(ax1, bx1),
                max(ay1, by1),
            )
            combined_reason = (
                existing.reason
                if candidate.reason in existing.reason
                else f"{existing.reason}; {candidate.reason}"
            )
            merged[matched_idx] = Region(
                id=existing.id,
                page=existing.page,
                bbox=combined_bbox,
                score=max(existing.score, candidate.score),
                reason=combined_reason,
            )

    merged.sort(key=lambda r: r.score, reverse=True)
    return merged[:max_regions]


def render_heatmap_overlay(
    page: PageImage,
    regions: list[Region],
    output_path: Path,
) -> Path:
    """Render a semi-transparent red heatmap overlay over the page image and save PNG."""
    bgr = load_page_bgr(page)
    height, width = bgr.shape[:2]

    heat = np.zeros((height, width), dtype=np.float32)
    for region in regions:
        if region.page != page.page:
            continue
        x0 = max(0, int(region.bbox[0] * width))
        y0 = max(0, int(region.bbox[1] * height))
        x1 = min(width, int(region.bbox[2] * width))
        y1 = min(height, int(region.bbox[3] * height))
        if x1 > x0 and y1 > y0:
            heat[y0:y1, x0:x1] = np.maximum(heat[y0:y1, x0:x1], float(region.score))

    if np.any(heat > 0):
        blurred = cv2.GaussianBlur(heat, (21, 21), 0)
        heat = np.clip(blurred, 0.0, 1.0).astype(np.float32)

    alpha = (heat * 0.55)[..., None]
    red_layer = np.zeros_like(bgr, dtype=np.float32)
    red_layer[:, :, 2] = 255.0  # BGR red channel

    blended = bgr.astype(np.float32) * (1.0 - alpha) + red_layer * alpha
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), np.clip(blended, 0, 255).astype(np.uint8))
    return output_path
