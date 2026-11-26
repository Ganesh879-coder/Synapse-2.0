"""Generate realistic tampered variants (plus WhatsApp-compressed copies) of samples/."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import OcrWord, PageImage  # noqa: E402
from app.ocr.engine import extract_ocr_words  # noqa: E402
from app.utils.pdf import render_document_pages  # noqa: E402
from app.utils.validation import detect_mime_from_magic_bytes  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
SAMPLES_DIR = REPO_ROOT / "samples"
TAMPERED_DIR = SAMPLES_DIR / "tampered"
FALLBACKS_PATH = Path(__file__).resolve().parent / "tamper_fallbacks.json"

_PREFIXES: tuple[str, ...] = (
    "bill_clean",
    "gst_2018",
    "gst_2023",
    "phonepe_stmt",
    "kea_receipt",
)


def _discover_samples(samples_dir: Path) -> dict[str, Path]:
    """Discover sample files by name prefix without hardcoding double extensions."""
    found: dict[str, Path] = {}
    if not samples_dir.exists():
        return found
    for path in sorted(samples_dir.glob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        for prefix in _PREFIXES:
            if path.name.startswith(prefix) and prefix not in found:
                found[prefix] = path
                break
    return found


def _load_font(pixel_height: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(10, int(round(pixel_height * 0.82)))
    for candidate in ("arial.ttf", "DejaVuSans.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _find_word_bbox(
    words: list[OcrWord],
    predicate: Any,
) -> tuple[float, float, float, float] | None:
    for word in words:
        if predicate(word.text):
            return word.bbox
    return None


def _apply_realistic_text_edit(
    img: Image.Image,
    norm_bbox: tuple[float, float, float, float],
    replacement_text: str,
) -> Image.Image:
    """Replace text inside norm_bbox using sampled local background, font size, and soft blur."""
    edited = img.copy().convert("RGB")
    arr = np.asarray(edited, dtype=np.uint8)
    h, w = arr.shape[:2]

    x0 = max(0, min(w - 4, int(norm_bbox[0] * w)))
    y0 = max(0, min(h - 4, int(norm_bbox[1] * h)))
    x1 = max(x0 + 4, min(w, int(norm_bbox[2] * w)))
    y1 = max(y0 + 4, min(h, int(norm_bbox[3] * h)))

    patch_arr = arr[y0:y1, x0:x1]
    gray_patch = np.mean(patch_arr, axis=2)
    bright_mask = gray_patch >= np.percentile(gray_patch, 70)
    if np.any(bright_mask):
        bg_rgb = tuple(int(v) for v in np.median(patch_arr[bright_mask], axis=0))
    else:
        bg_rgb = tuple(int(v) for v in np.median(patch_arr.reshape(-1, 3), axis=0))

    dark_mask = gray_patch <= np.percentile(gray_patch, 20)
    if np.any(dark_mask):
        fg_rgb = tuple(int(v) for v in np.median(patch_arr[dark_mask], axis=0))
    else:
        fg_rgb = (20, 20, 20)

    pw, ph = x1 - x0, y1 - y0
    patch_img = Image.new("RGB", (pw, ph), color=bg_rgb)
    draw = ImageDraw.Draw(patch_img)
    font = _load_font(ph)
    draw.text((2, max(0, int(ph * 0.1))), replacement_text, fill=fg_rgb, font=font)
    patch_img = patch_img.filter(ImageFilter.GaussianBlur(radius=0.55))

    edited.paste(patch_img, (x0, y0))
    return edited


def _save_whatsapp_variant(img: Image.Image, out_path: Path) -> None:
    """Save WhatsApp-style variant: max 1280px long side, JPEG quality 70."""
    wa = img.copy().convert("RGB")
    w, h = wa.size
    long_side = max(w, h)
    if long_side > 1280:
        scale = 1280.0 / long_side
        wa = wa.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    wa.save(out_path, format="JPEG", quality=70)


def generate_tampered_dataset(
    samples_dir: Path = SAMPLES_DIR,
    tampered_dir: Path = TAMPERED_DIR,
) -> list[dict[str, Any]]:
    """Generate all tampered variants + WhatsApp copies and ground_truth.json."""
    tampered_dir.mkdir(parents=True, exist_ok=True)
    fallbacks: dict[str, dict[str, list[float]]] = json.loads(FALLBACKS_PATH.read_text())
    sources = _discover_samples(samples_dir)
    if not sources:
        print("No sample files discovered in", samples_dir)
        return []

    records: list[dict[str, Any]] = []
    render_tmp = tampered_dir / "_tmp_pages"
    render_tmp.mkdir(parents=True, exist_ok=True)

    edit_specs: dict[str, list[tuple[str, str, str, Any, str]]] = {
        "bill_clean": [
            (
                "net_total",
                "bill_clean_a_net_total",
                "Change net total 2,560.00 -> 3,560.00",
                lambda t: "2,560" in t or "2560" in t,
                "3,560.00",
            ),
            (
                "line_total_500",
                "bill_clean_b_line_total",
                "Change line total 500.00 -> 800.00",
                lambda t: t.strip() == "500.00",
                "800.00",
            ),
        ],
        "gst_2018": [
            (
                "gstin",
                "gst_2018_a_gstin",
                "Change one character in GSTIN",
                lambda t: "27CTNPK" in t.upper(),
                "27CTNPK7497R1Z4",
            ),
            (
                "legal_name",
                "gst_2018_b_legal_name",
                "Replace legal name",
                lambda t: "SUMIT" in t.upper() or "KULKANT" in t.upper(),
                "RAMESH SHARMA",
            ),
            (
                "date_of_issue",
                "gst_2018_c_issue_date",
                "Change date of issue",
                lambda t: "02/072018" in t or "02/07/2018" in t,
                "19/08/2021",
            ),
        ],
        "gst_2023": [
            (
                "gstin",
                "gst_2023_a_gstin",
                "Change one character in GSTIN",
                lambda t: "09CDIPA" in t.upper(),
                "09CDIPA9960E1Z5",
            ),
            (
                "legal_name",
                "gst_2023_b_legal_name",
                "Replace legal name",
                lambda t: "AJROOODIN" in t.upper() or "ANSARI" in t.upper(),
                "VIKRAM PATEL",
            ),
            (
                "date_of_issue",
                "gst_2023_c_issue_date",
                "Change date of issue",
                lambda t: "17032023" in t or "17/03/2023" in t,
                "25/09/2024",
            ),
        ],
        "phonepe_stmt": [
            (
                "amount_90",
                "phonepe_stmt_a_amount",
                "Change amount 90 -> 900 on one row",
                lambda t: t.strip() == "90",
                "900",
            ),
            (
                "row_date",
                "phonepe_stmt_b_row_date",
                "Change row date to disagree with Transaction ID",
                lambda t: "Nov 22, 2026" in t or "Nov22,2026" in t,
                "Nov 19, 2026",
            ),
        ],
        "kea_receipt": [
            (
                "amount",
                "kea_receipt_a_amount",
                "Change payment amount 121610 -> 21610",
                lambda t: "121610" in t,
                "21610",
            ),
        ],
    }

    for prefix, src_path in sources.items():
        specs = edit_specs.get(prefix, [])
        if not specs:
            continue
        raw_bytes = src_path.read_bytes()
        mime = detect_mime_from_magic_bytes(raw_bytes)
        pages = render_document_pages(src_path, mime, render_tmp / prefix, dpi=200)
        page: PageImage = pages[0]
        words = extract_ocr_words(page)
        base_img = Image.open(page.image_path).convert("RGB")

        for fb_key, out_stem, desc, matcher, replacement in specs:
            bbox = _find_word_bbox(words, matcher)
            used_fallback = False
            if bbox is None:
                fb_coords = fallbacks.get(prefix, {}).get(fb_key)
                if fb_coords is None:
                    print(f"[SKIP] {src_path.name} ({out_stem}): target not found and no fallback.")
                    continue
                bbox = (
                    float(fb_coords[0]),
                    float(fb_coords[1]),
                    float(fb_coords[2]),
                    float(fb_coords[3]),
                )
                used_fallback = True
                print(f"[FALLBACK] {out_stem}: used tamper_fallbacks.json[{prefix}][{fb_key}]")
            else:
                print(f"[OCR] {out_stem}: located target bbox={bbox}")

            tampered_img = _apply_realistic_text_edit(base_img, bbox, replacement)

            orig_out = tampered_dir / f"{out_stem}.jpg"
            tampered_img.save(orig_out, format="JPEG", quality=92)
            records.append(
                {
                    "file": orig_out.name,
                    "source_file": src_path.name,
                    "variant": "original",
                    "edit_description": desc,
                    "bbox": list(bbox),
                    "used_fallback": used_fallback,
                }
            )

            wa_out = tampered_dir / f"{out_stem}_wa.jpg"
            _save_whatsapp_variant(tampered_img, wa_out)
            records.append(
                {
                    "file": wa_out.name,
                    "source_file": src_path.name,
                    "variant": "whatsapp",
                    "edit_description": f"{desc} (WhatsApp compressed)",
                    "bbox": list(bbox),
                    "used_fallback": used_fallback,
                }
            )

    gt_path = tampered_dir / "ground_truth.json"
    gt_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Generated {len(records)} tampered variants -> {gt_path}")
    return records


def main() -> None:
    """CLI entrypoint."""
    generate_tampered_dataset()


if __name__ == "__main__":
    main()
