"""Document quality and screenshot-like heuristic estimator."""

from __future__ import annotations

import cv2
import numpy as np


def estimate_page_quality(image_bgr: np.ndarray, mime: str) -> tuple[float, bool]:
    """Estimate normalized page quality [0.0, 1.0] and whether it looks like a screenshot."""
    if image_bgr.size == 0:
        return 0.0, False

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = min(1.0, lap_var / 400.0)

    p5, p95 = np.percentile(gray, [5, 95])
    contrast = min(1.0, float(p95 - p5) / 180.0)

    # Estimate high-frequency noise floor using median absolute deviation of Laplacian.
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    residual = np.abs(gray.astype(np.float32) - blur.astype(np.float32))
    noise_mad = float(np.median(residual))
    noise_penalty = min(0.5, max(0.0, (noise_mad - 4.0) / 20.0))

    quality = max(0.05, min(1.0, 0.55 * sharpness + 0.45 * contrast - noise_penalty))

    # Screenshot-like heuristic: PNG with large flat-color regions and crisp edges.
    edges = cv2.Canny(gray, 80, 160)
    flat_ratio = float(np.mean(residual < 1.0))
    edge_density = float(np.mean(edges > 0))
    is_screenshot_like = mime == "image/png" and flat_ratio > 0.78 and edge_density > 0.01

    return round(quality, 4), is_screenshot_like


def scale_confidence(
    raw_score: float,
    quality: float,
    is_screenshot_like: bool,
    screenshot_sensitive: bool = False,
) -> float:
    """Scale detector confidence down for low-quality or screenshot inputs."""
    clamped = max(0.0, min(1.0, raw_score))
    quality_factor = 0.4 + 0.6 * max(0.0, min(1.0, quality))
    scaled = clamped * quality_factor
    if is_screenshot_like and screenshot_sensitive:
        scaled *= 0.35
    return round(max(0.0, min(1.0, scaled)), 4)
