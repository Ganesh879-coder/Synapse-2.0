"""Block-wise noise residual and local variance inconsistency detector."""

from __future__ import annotations

import cv2
import numpy as np

from app.forensics.common import cluster_mask_to_regions, load_page_bgr
from app.forensics.quality import scale_confidence
from app.models.schemas import PageImage, Region


def analyze_noise_inconsistency(
    page: PageImage,
    quality: float = 1.0,
    is_screenshot_like: bool = False,
    block_size: int = 32,
) -> tuple[list[Region], float]:
    """Compare block-wise high-pass noise variance against page median."""
    bgr = load_page_bgr(page)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    height, width = gray.shape[:2]
    if height < block_size * 2 or width < block_size * 2:
        return [], 0.0

    # High-pass noise residual.
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray - denoised

    rows = height // block_size
    cols = width // block_size
    block_vars = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            patch = residual[
                r * block_size : (r + 1) * block_size,
                c * block_size : (c + 1) * block_size,
            ]
            block_vars[r, c] = float(np.var(patch))

    median_var = float(np.median(block_vars))
    mad = float(np.median(np.abs(block_vars - median_var)))
    if mad < 1e-3 and float(np.max(block_vars) - median_var) < 8.0:
        return [], 0.0

    robust_z = np.abs(block_vars - median_var) / max(mad * 1.4826, 2.5)
    flagged = robust_z >= 4.0
    if not np.any(flagged):
        return [], 0.0

    mask = np.zeros((height, width), dtype=np.uint8)
    score_map = np.zeros((height, width), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            if flagged[r, c]:
                y0, y1 = r * block_size, (r + 1) * block_size
                x0, x1 = c * block_size, (c + 1) * block_size
                mask[y0:y1, x0:x1] = 1
                score_map[y0:y1, x0:x1] = min(1.0, float(robust_z[r, c]) / 10.0)

    regions = cluster_mask_to_regions(
        mask=mask,
        score_map=score_map,
        page_num=page.page,
        reason="Local noise variance deviates strongly from the page baseline.",
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
