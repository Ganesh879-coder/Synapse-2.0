"""Error Level Analysis (ELA) detector for localized compression anomalies."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from app.forensics.common import cluster_mask_to_regions, load_page_bgr
from app.forensics.quality import scale_confidence
from app.models.schemas import PageImage, Region


def analyze_ela(
    page: PageImage,
    mime: str = "image/jpeg",
    is_screenshot_like: bool = False,
    quality: float = 1.0,
) -> tuple[list[Region], float]:
    """Re-save as JPEG Q=90, amplify difference, threshold, and cluster hot regions."""
    if is_screenshot_like and mime == "image/png":
        return [], 0.0

    bgr = load_page_bgr(page)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    with Image.open(buf) as resaved_pil:
        resaved_rgb = np.asarray(resaved_pil.convert("RGB"), dtype=np.int16)

    diff = np.abs(rgb.astype(np.int16) - resaved_rgb).astype(np.float32)
    diff_gray = np.mean(diff, axis=2)

    max_diff = float(np.max(diff_gray))
    if max_diff < 3.0:
        return [], 0.0

    # Amplify and normalize to [0, 1].
    p99 = float(np.percentile(diff_gray, 99.5))
    denom = max(p99, 12.0)
    norm = np.clip(diff_gray / denom, 0.0, 1.0)

    # Adaptive percentile threshold with noise floor.
    thresh = max(0.35, float(np.percentile(norm, 98.5)))
    hot_mask = (norm >= thresh) & (diff_gray >= 6.0)
    if not np.any(hot_mask):
        return [], 0.0

    regions = cluster_mask_to_regions(
        mask=hot_mask,
        score_map=norm,
        page_num=page.page,
        reason="Error Level Analysis detected localized recompression differences.",
    )
    if not regions:
        return [], 0.0

    raw_score = max(r.score for r in regions)
    scaled = scale_confidence(raw_score, quality, is_screenshot_like, screenshot_sensitive=True)
    for region in regions:
        region.score = scale_confidence(
            region.score, quality, is_screenshot_like, screenshot_sensitive=True
        )
    return regions, scaled
