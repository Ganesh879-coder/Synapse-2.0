"""Unit tests for forensics detectors using synthetic tampered documents."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.forensics.common import compute_iou
from app.forensics.copy_move import analyze_copy_move
from app.forensics.ela import analyze_ela
from app.forensics.fuse import merge_regions_by_iou, render_heatmap_overlay
from app.forensics.jpeg_ghost import analyze_jpeg_ghost
from app.forensics.metadata import analyze_metadata
from app.forensics.noise_inconsistency import analyze_noise_inconsistency
from app.forensics.quality import estimate_page_quality, scale_confidence
from app.forensics.text_patch import analyze_text_patch
from app.models.schemas import OcrWord, PageImage, Region, Signal
from app.scoring.scorer import compute_risk


def _best_iou(
    regions: list[Region],
    target_bbox: tuple[float, float, float, float],
) -> float:
    return max((compute_iou(r.bbox, target_bbox) for r in regions), default=0.0)


def test_ela_detects_pasted_patch_and_skips_screenshot(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    base = np.full((320, 320, 3), 235, dtype=np.uint8)
    base += rng.integers(0, 12, size=base.shape, dtype=np.uint8)
    base_img = Image.fromarray(base)

    # Save at low JPEG quality first.
    q60_buf = io.BytesIO()
    base_img.save(q60_buf, format="JPEG", quality=55)
    q60_buf.seek(0)
    tampered = Image.open(q60_buf).convert("RGB")

    # Paste a textured high-contrast synthetic patch (x: 160..240, y: 120..200).
    patch_arr = rng.integers(180, 255, size=(80, 80, 3), dtype=np.uint8)
    patch_img = Image.fromarray(patch_arr)
    p_draw = ImageDraw.Draw(patch_img)
    p_draw.rectangle([0, 0, 79, 79], outline=(20, 20, 20), width=3)
    p_draw.text((12, 32), "99,999", fill=(0, 0, 0))
    tampered.paste(patch_img, (160, 120))

    page_path = tmp_path / "ela_tampered.png"
    tampered.save(page_path, format="PNG")
    page = PageImage(page=1, image_path=page_path, width=320, height=320)

    regions, score = analyze_ela(page, mime="image/jpeg", is_screenshot_like=False, quality=1.0)
    assert score > 0.0
    assert _best_iou(regions, (160 / 320, 120 / 320, 240 / 320, 200 / 320)) > 0.3

    # Screenshot-like PNG should be skipped.
    ss_regions, ss_score = analyze_ela(page, mime="image/png", is_screenshot_like=True, quality=1.0)
    assert ss_regions == []
    assert ss_score == 0.0


def test_copy_move_detects_cloned_stamp(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 400), color=(250, 250, 250))
    rng = np.random.default_rng(7)
    stamp = Image.new("RGB", (80, 80), color=(240, 240, 240))
    draw = ImageDraw.Draw(stamp)
    for _ in range(35):
        x0, y0 = int(rng.integers(4, 65)), int(rng.integers(4, 65))
        draw.line((x0, y0, x0 + 12, y0 + 8), fill=(20, 40, 160), width=2)
    draw.ellipse((6, 6, 74, 74), outline=(20, 40, 160), width=3)

    img.paste(stamp, (40, 50))
    img.paste(stamp, (260, 240))

    page_path = tmp_path / "copymove.png"
    img.save(page_path, format="PNG")
    page = PageImage(page=1, image_path=page_path, width=400, height=400)

    regions, score = analyze_copy_move(page, quality=1.0)
    assert score > 0.0
    iou_src = _best_iou(regions, (40 / 400, 50 / 400, 120 / 400, 130 / 400))
    iou_dst = _best_iou(regions, (260 / 400, 240 / 400, 340 / 400, 320 / 400))
    assert max(iou_src, iou_dst) > 0.3


def test_noise_inconsistency_detects_tampered_block(tmp_path: Path) -> None:
    rng = np.random.default_rng(123)
    arr = np.full((320, 320, 3), 220, dtype=np.uint8)
    noise = rng.normal(0, 2.0, size=arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)

    # Inject strong localized noise patch (64x64) at x: 128..192, y: 128..192.
    high_noise = rng.normal(0, 28.0, size=(64, 64, 3))
    arr[128:192, 128:192] = np.clip(220 + high_noise, 0, 255).astype(np.uint8)

    page_path = tmp_path / "noise.png"
    Image.fromarray(arr).save(page_path, format="PNG")
    page = PageImage(page=1, image_path=page_path, width=320, height=320)

    regions, score = analyze_noise_inconsistency(page, quality=1.0)
    assert score > 0.0
    assert _best_iou(regions, (128 / 320, 128 / 320, 192 / 320, 192 / 320)) > 0.3


def test_text_patch_detects_edited_amount_word(tmp_path: Path) -> None:
    w, h = 600, 200
    img = Image.new("RGB", (w, h), color=(248, 248, 248))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Render genuine words along the same line.
    words_spec = [
        ("Invoice", (40, 80, 130, 115)),
        ("Total:", (150, 80, 230, 115)),
        ("INR", (250, 80, 310, 115)),
        ("1500.00", (330, 80, 440, 115)),
    ]
    for text, box in words_spec[:3]:
        draw.text((box[0] + 4, box[1] + 8), text, fill=(15, 15, 15), font=font)

    # Tamper the last word: paste a shaded/blurred patch with altered background & size.
    patch_box = words_spec[3][1]
    patch = Image.new(
        "RGB",
        (patch_box[2] - patch_box[0], patch_box[3] - patch_box[1]),
        (195, 205, 190),
    )
    p_draw = ImageDraw.Draw(patch)
    p_draw.text((6, 10), "9500.00", fill=(0, 0, 0), font=font)
    patch = patch.filter(ImageFilter.GaussianBlur(radius=1.2))
    img.paste(patch, (patch_box[0], patch_box[1]))

    page_path = tmp_path / "text_patch.png"
    img.save(page_path, format="PNG")
    page = PageImage(page=1, image_path=page_path, width=w, height=h)

    ocr_words = [
        OcrWord(
            text=text,
            conf=0.95,
            bbox=(box[0] / w, box[1] / h, box[2] / w, box[3] / h),
        )
        for text, box in words_spec
    ]

    regions, score = analyze_text_patch(page, ocr_words, quality=1.0)
    assert score > 0.0
    target_norm = (patch_box[0] / w, patch_box[1] / h, patch_box[2] / w, patch_box[3] / h)
    assert _best_iou(regions, target_norm) > 0.3


def test_jpeg_ghost_detects_double_compressed_patch(tmp_path: Path) -> None:
    rng = np.random.default_rng(99)
    # Realistic smooth paper document background saved at Q=50.
    base = np.full((256, 256, 3), 240, dtype=np.uint8)
    base_img = Image.fromarray(base)
    b_draw = ImageDraw.Draw(base_img)
    b_draw.text((20, 30), "Original Invoice Header", fill=(30, 30, 30))
    buf = io.BytesIO()
    base_img.save(buf, format="JPEG", quality=50)
    buf.seek(0)
    tampered = Image.open(buf).convert("RGB")

    # Paste an uncompressed high-frequency textured patch at (96, 96, 160, 160).
    patch = rng.integers(40, 220, size=(64, 64, 3), dtype=np.uint8)
    tampered.paste(Image.fromarray(patch), (96, 96))

    page_path = tmp_path / "ghost.png"
    tampered.save(page_path, format="PNG")
    page = PageImage(page=1, image_path=page_path, width=256, height=256)

    regions, score = analyze_jpeg_ghost(page, mime="image/jpeg", is_screenshot_like=False)
    assert score > 0.0
    assert _best_iou(regions, (96 / 256, 96 / 256, 160 / 256, 160 / 256)) > 0.3


def test_metadata_detects_pdf_editor_updates_and_signature() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample GST Invoice")
    doc.set_metadata({"producer": "Canva", "creator": "Canva", "modDate": "D:20260102000000"})
    pdf_bytes = bytes(doc.tobytes())
    doc.close()

    # Append a simulated incremental update and signature dictionary marker.
    tampered_pdf = pdf_bytes + b"\n% /Type /Sig\n%%EOF\n"
    findings, checks, _regions, score = analyze_metadata(
        file_bytes=tampered_pdf,
        mime="application/pdf",
        pages=[],
        ocr_words={},
    )
    titles = {f.title for f in findings}
    assert "PDF editor metadata detected" in titles
    assert "PDF incremental updates detected" in titles
    assert "Digital signature present but not verified" in titles
    assert any(c.name == "metadata:pdf_signature" and c.status == "warn" for c in checks)
    assert score >= 0.5


def test_fuse_quality_and_single_weak_signal_guard(tmp_path: Path) -> None:
    img = Image.new("RGB", (200, 200), color=(240, 240, 240))
    page_path = tmp_path / "clean.png"
    img.save(page_path, format="PNG")
    page = PageImage(page=1, image_path=page_path, width=200, height=200)

    q, is_ss = estimate_page_quality(np.asarray(img), mime="image/png")
    assert 0.0 <= q <= 1.0
    assert isinstance(is_ss, bool)
    scaled = scale_confidence(0.8, quality=0.1, is_screenshot_like=True, screenshot_sensitive=True)
    assert scaled < 0.3

    many_regions = [
        Region(
            id=f"r{i}",
            page=1,
            bbox=(0.1, 0.1, 0.2, 0.2) if i < 2 else (0.05 * i, 0.5, 0.05 * i + 0.04, 0.6),
            score=0.5 + 0.02 * i,
            reason=f"reason {i}",
        )
        for i in range(14)
    ]
    fused = merge_regions_by_iou(many_regions, iou_threshold=0.35, max_regions=10)
    assert len(fused) <= 10

    heatmap_path = render_heatmap_overlay(page, fused, tmp_path / "heatmap_page_1.png")
    assert heatmap_path.is_file()

    # Single weak signal must never produce HIGH risk.
    weak_signal = Signal(
        name="forensics:ela",
        category="visual",
        weight_hint=0.45,
        confidence=0.6,
    )
    risk_score, risk_level = compute_risk(findings=[], checks=[], signals=[weak_signal])
    assert risk_score < 65
    assert risk_level != "HIGH"
