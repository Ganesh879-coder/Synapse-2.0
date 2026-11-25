"""Double JPEG compression / quantization inconsistency (JPEG ghost) detector."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from app.forensics.common import cluster_mask_to_regions, load_page_bgr
from app.forensics.quality import scale_confidence
from app.models.schemas import PageImage, Region

_QUALITY_GRID: tuple[int, ...] = (60, 75, 90)


def analyze_jpeg_ghost(
    page: PageImage,
    mime: str = "image/jpeg",
    is_screenshot_like: bool = False,
    quality: float = 1.0,
) -> tuple[list[Region], float]:
    """Detect localized double-JPEG compression inconsistencies across quality levels."""
    if is_screenshot_like:
        return [], 0.0

    bgr = load_page_bgr(page)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    height, width = rgb.shape[:2]

    diffs: list[np.ndarray] = []
    for q in _QUALITY_GRID:
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=q)
        buf.seek(0)
        with Image.open(buf) as recomp:
            recomp_rgb = np.asarray(recomp.convert("RGB"), dtype=np.float32)
        diff = np.mean(np.abs(rgb.astype(np.float32) - recomp_rgb), axis=2)
        smoothed = cv2.GaussianBlur(diff, (15, 15), 0)
        diffs.append(smoothed)

    stacked = np.stack(diffs, axis=0)  # (Q, H, W)
    # Ghost contrast: spread between max and min recompression error per pixel.
    spread = np.max(stacked, axis=0) - np.min(stacked, axis=0)
    median_spread = float(np.median(spread))
    mad_spread = float(np.median(np.abs(spread - median_spread)))
    if float(np.max(spread)) < 5.5:
        return [], 0.0

    z_map = (spread - median_spread) / max(mad_spread * 1.4826, 1.2)
    mask = z_map >= 3.3
    if not np.any(mask):
        return [], 0.0

    score_map = np.clip(z_map / 8.0, 0.0, 1.0)
    regions = cluster_mask_to_regions(
        mask=mask,
        score_map=score_map,
        page_num=page.page,
        reason="JPEG recompression response differs locally from surrounding regions.",
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
