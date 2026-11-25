"""OCR preprocessing and word extraction (RapidOCR primary, Tesseract fallback)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from app.models.schemas import OcrWord, PageImage

try:  # Optional Tesseract fallback
    import pytesseract as _pytesseract
except ImportError:
    _pytesseract = None


def is_tesseract_available() -> bool:
    """Return True if the optional pytesseract package is importable."""
    return _pytesseract is not None


@lru_cache(maxsize=1)
def _get_rapid_ocr() -> RapidOCR:
    """Return a cached RapidOCR engine instance."""
    return RapidOCR()


def _estimate_skew_angle(gray: np.ndarray) -> float:
    """Estimate small skew angle in degrees from foreground text pixels."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) < 200:
        return 0.0
    # Subsample for speed on large pages.
    if len(coords) > 15000:
        step = len(coords) // 15000
        coords = coords[::step]
    rect = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))
    angle = float(rect[-1])
    if angle < -45.0:
        angle = 90.0 + angle
    elif angle > 45.0:
        angle = angle - 90.0
    if abs(angle) < 0.5 or abs(angle) > 15.0:
        return 0.0
    return angle


def preprocess_for_ocr(image_bgr: np.ndarray) -> np.ndarray:
    """Preprocess document image: upscale small text, deskew, and apply CLAHE if low-contrast."""
    if image_bgr.size == 0:
        return image_bgr

    img = image_bgr
    height, width = img.shape[:2]

    # Gently upscale very small images without over-blurring JPEG text.
    if min(height, width) < 700:
        scale = min(1.5, 720.0 / max(1, min(height, width)))
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply CLAHE only when contrast is low (e.g., dimly-lit phone photos).
    p5, p95 = np.percentile(gray, [5, 95])
    if float(p95 - p5) < 120.0:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_chan)
        img = cv2.cvtColor(cv2.merge((l_enhanced, a_chan, b_chan)), cv2.COLOR_LAB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Deskew small rotational tilts.
    angle = _estimate_skew_angle(gray)
    if angle != 0.0:
        h, w = img.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
        img = cv2.warpAffine(
            img,
            matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    return img


def _normalize_box(
    xs: list[float],
    ys: list[float],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    """Clamp pixel coordinates to normalized [0.0, 1.0] (x0, y0, x1, y1)."""
    x0 = max(0.0, min(1.0, min(xs) / max(1, width)))
    y0 = max(0.0, min(1.0, min(ys) / max(1, height)))
    x1 = max(0.0, min(1.0, max(xs) / max(1, width)))
    y1 = max(0.0, min(1.0, max(ys) / max(1, height)))
    return (round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4))


def _run_rapidocr(image_bgr: np.ndarray) -> list[OcrWord]:
    """Run RapidOCR and convert line/box detections into normalized OcrWord items."""
    height, width = image_bgr.shape[:2]
    engine = _get_rapid_ocr()
    result, _ = engine(image_bgr)
    if not result:
        return []

    words: list[OcrWord] = []
    for item in result:
        if len(item) < 3:
            continue
        poly, text, conf = item[0], str(item[1]).strip(), float(item[2])
        if not text:
            continue
        xs = [float(pt[0]) for pt in poly]
        ys = [float(pt[1]) for pt in poly]
        bbox = _normalize_box(xs, ys, width, height)
        words.append(
            OcrWord(
                text=text,
                conf=max(0.0, min(1.0, conf)),
                bbox=bbox,
            )
        )
    return words


def _run_tesseract_fallback(image_bgr: np.ndarray) -> list[OcrWord]:
    """Run optional pytesseract fallback if installed."""
    if _pytesseract is None:
        return []
    height, width = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    data: dict[str, list[Any]] = _pytesseract.image_to_data(
        rgb, output_type=_pytesseract.Output.DICT
    )
    words: list[OcrWord] = []
    n = len(data.get("text", []))
    for i in range(n):
        text = str(data["text"][i]).strip()
        if not text:
            continue
        conf_raw = float(data["conf"][i])
        if conf_raw < 0:
            continue
        x = float(data["left"][i])
        y = float(data["top"][i])
        w = float(data["width"][i])
        h = float(data["height"][i])
        bbox = _normalize_box([x, x + w], [y, y + h], width, height)
        words.append(OcrWord(text=text, conf=min(1.0, conf_raw / 100.0), bbox=bbox))
    return words


def extract_ocr_words(page: PageImage, use_preprocessing: bool = True) -> list[OcrWord]:
    """Extract normalized OcrWord tokens from a page image."""
    bgr = cv2.imread(str(page.image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        return []
    processed = preprocess_for_ocr(bgr) if use_preprocessing else bgr
    words = _run_rapidocr(processed)
    if not words:
        words = _run_tesseract_fallback(processed)
    return words


def group_ocr_lines(words: list[OcrWord]) -> list[list[OcrWord]]:
    """Group OCR words into reading-order horizontal lines."""
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
    for line in lines:
        line.sort(key=lambda w: w.bbox[0])
    return lines
