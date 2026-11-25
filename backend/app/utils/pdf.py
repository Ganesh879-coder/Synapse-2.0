"""PDF and image page rendering utilities using PyMuPDF and Pillow."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

from app.models.schemas import PageImage


def render_document_pages(
    source_path: Path,
    mime_type: str,
    output_dir: Path,
    dpi: int = 200,
) -> list[PageImage]:
    """Render a PDF (at target DPI) or image into per-page PNG images."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if mime_type == "application/pdf":
        return _render_pdf_pages(source_path, output_dir, dpi)
    return _prepare_single_image_page(source_path, output_dir)


def _render_pdf_pages(pdf_path: Path, output_dir: Path, dpi: int) -> list[PageImage]:
    """Render every PDF page to PNG at the specified DPI using PyMuPDF."""
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    pages: list[PageImage] = []
    with pymupdf.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            out_path = output_dir / f"page_{index}.png"
            pixmap.save(str(out_path))
            pages.append(
                PageImage(
                    page=index,
                    image_path=out_path,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
    return pages


def _prepare_single_image_page(image_path: Path, output_dir: Path) -> list[PageImage]:
    """Normalize a single uploaded JPG/PNG into page_1.png."""
    out_path = output_dir / "page_1.png"
    with Image.open(image_path) as img:
        rgb_img = img.convert("RGB")
        width, height = rgb_img.size
        rgb_img.save(out_path, format="PNG")
    return [PageImage(page=1, image_path=out_path, width=width, height=height)]
