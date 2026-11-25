"""Shared image loading, connected-component clustering, and IoU helpers."""

from __future__ import annotations

import uuid

import cv2
import numpy as np

from app.models.schemas import PageImage, Region


def load_page_bgr(page: PageImage) -> np.ndarray:
    """Load a rendered page image as BGR uint8 array."""
    img = cv2.imread(str(page.image_path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Unable to read page image: {page.image_path}")
    return img


def compute_iou(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
) -> float:
    """Compute Intersection-over-Union for two normalized (x0, y0, x1, y1) boxes."""
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    inter_w = max(0.0, ix1 - ix0)
    inter_h = max(0.0, iy1 - iy0)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


def cluster_mask_to_regions(
    mask: np.ndarray,
    score_map: np.ndarray,
    page_num: int,
    reason: str,
    min_area_ratio: float = 0.0004,
    max_regions: int = 8,
) -> list[Region]:
    """Cluster a binary anomaly mask into normalized Region bounding boxes."""
    height, width = mask.shape[:2]
    total_area = float(height * width)
    if total_area <= 0:
        return []

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)

    candidates: list[Region] = []
    min_pixels = max(16, int(total_area * min_area_ratio))
    for label_idx in range(1, num_labels):
        x, y, w, h, area = stats[label_idx]
        if area < min_pixels:
            continue
        component_mask = labels == label_idx
        local_score = float(np.percentile(score_map[component_mask], 90))
        clamped_score = round(max(0.0, min(1.0, local_score)), 4)
        bbox = (
            round(max(0.0, x / width), 4),
            round(max(0.0, y / height), 4),
            round(min(1.0, (x + w) / width), 4),
            round(min(1.0, (y + h) / height), 4),
        )
        candidates.append(
            Region(
                id=uuid.uuid4().hex[:12],
                page=page_num,
                bbox=bbox,
                score=clamped_score,
                reason=reason,
            )
        )

    candidates.sort(key=lambda r: r.score, reverse=True)
    return candidates[:max_regions]
