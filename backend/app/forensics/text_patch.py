"""Pasted text patch detector comparing per-word visual features along text lines."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from app.forensics.common import load_page_bgr
from app.forensics.quality import scale_confidence
from app.models.schemas import OcrWord, PageImage, Region


@dataclass(frozen=True)
class _WordFeatures:
    word: OcrWord
    bg_rgb: tuple[float, float, float]
    sharpness: float
    stroke_thickness: float
    font_height: float


def _group_words_into_lines(words: list[OcrWord]) -> list[list[OcrWord]]:
    """Group OCR words into horizontal lines by vertical center overlap."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: ((w.bbox[1] + w.bbox[3]) * 0.5, w.bbox[0]))
    lines: list[list[OcrWord]] = []
    for word in sorted_words:
        yc = (word.bbox[1] + word.bbox[3]) * 0.5
        wh = max(1e-4, word.bbox[3] - word.bbox[1])
        placed = False
        for line in lines:
            ref = line[0]
            ref_yc = (ref.bbox[1] + ref.bbox[3]) * 0.5
            ref_h = max(1e-4, ref.bbox[3] - ref.bbox[1])
            if abs(yc - ref_yc) <= 0.65 * max(wh, ref_h):
                line.append(word)
                placed = True
                break
        if not placed:
            lines.append([word])
    return lines


def _extract_word_features(bgr: np.ndarray, word: OcrWord) -> _WordFeatures | None:
    """Compute background color, sharpness, stroke thickness, and font height."""
    h_img, w_img = bgr.shape[:2]
    x0 = max(0, int(word.bbox[0] * w_img))
    y0 = max(0, int(word.bbox[1] * h_img))
    x1 = min(w_img, int(word.bbox[2] * w_img))
    y1 = min(h_img, int(word.bbox[3] * h_img))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None

    patch = bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)

    # Background color: 85th percentile brightness pixels (paper/background) in patch.
    bright_mask = gray >= np.percentile(gray, 70)
    if np.any(bright_mask):
        bg_vals = np.median(patch[bright_mask], axis=0)
    else:
        bg_vals = np.median(patch.reshape(-1, 3), axis=0)

    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Stroke thickness via Otsu binary foreground + distance transform.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    fg_pixels = int(np.sum(binary > 0))
    if fg_pixels > 0:
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
        stroke = float(np.median(dist[binary > 0]))
    else:
        stroke = 0.0

    return _WordFeatures(
        word=word,
        bg_rgb=(float(bg_vals[2]), float(bg_vals[1]), float(bg_vals[0])),
        sharpness=sharpness,
        stroke_thickness=stroke,
        font_height=max(1e-4, word.bbox[3] - word.bbox[1]),
    )


def _robust_z(values: np.ndarray, min_scale: float) -> np.ndarray:
    """Compute robust MAD-based z-scores across a 1D array."""
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    scale = max(mad * 1.4826, min_scale)
    return np.abs(values - med) / scale


def analyze_text_patch(
    page: PageImage,
    ocr_words: list[OcrWord],
    quality: float = 1.0,
    is_screenshot_like: bool = False,
) -> tuple[list[Region], float]:
    """Flag OCR words whose visual traits deviate strongly from same-line neighbours."""
    if len(ocr_words) < 2:
        return [], 0.0

    bgr = load_page_bgr(page)
    lines = _group_words_into_lines(ocr_words)
    flagged_regions: list[Region] = []

    for line in lines:
        feats = [f for w in line if (f := _extract_word_features(bgr, w)) is not None]
        if len(feats) < 2:
            continue

        bg_arr = np.array([f.bg_rgb for f in feats], dtype=np.float32)
        bg_med = np.median(bg_arr, axis=0)
        bg_dist = np.linalg.norm(bg_arr - bg_med, axis=1)
        bg_z = bg_dist / max(float(np.median(bg_dist)) * 1.4826, 6.0)

        sharp_z = _robust_z(
            np.array([f.sharpness for f in feats], dtype=np.float32), min_scale=25.0
        )
        stroke_z = _robust_z(
            np.array([f.stroke_thickness for f in feats], dtype=np.float32), min_scale=0.35
        )
        height_z = _robust_z(
            np.array([f.font_height for f in feats], dtype=np.float32), min_scale=0.004
        )

        for idx, feat in enumerate(feats):
            combined = max(
                float(bg_z[idx]),
                float(sharp_z[idx]) * 0.8,
                float(stroke_z[idx]) * 0.9,
                float(height_z[idx]) * 0.9,
            )
            if combined < 3.0:
                continue

            raw_score = min(1.0, combined / 6.5)
            scaled = scale_confidence(raw_score, quality, is_screenshot_like)
            flagged_regions.append(
                Region(
                    id=uuid.uuid4().hex[:12],
                    page=page.page,
                    bbox=feat.word.bbox,
                    score=scaled,
                    reason=(
                        "Word visual properties (background, sharpness, stroke, or size) "
                        "differ from neighbouring text on the same line."
                    ),
                )
            )

    if not flagged_regions:
        return [], 0.0

    flagged_regions.sort(key=lambda r: r.score, reverse=True)
    return flagged_regions, flagged_regions[0].score
