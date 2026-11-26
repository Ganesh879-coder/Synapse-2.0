"""PDF and image page rendering utilities with memory and page-count guards."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

from app.models.schemas import PageImage


class EncryptedPdfError(ValueError):
    """Raised when an uploaded PDF is encrypted or password-protected."""


class DocumentLimitError(ValueError):
    """Raised when an uploaded document exceeds page or pixel limits."""


def render_document_pages(
    source_path: Path,
    mime_type: str,
    output_dir: Path,
    dpi: int = 200,
    max_pdf_pages: int = 10,
    max_pixels: int = 25_000_000,
) -> list[PageImage]:
    """Render a PDF (at target DPI) or image into per-page PNG images."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if mime_type == "application/pdf":
        return _render_pdf_pages(source_path, output_dir, dpi, max_pdf_pages, max_pixels)
    return _prepare_single_image_page(source_path, output_dir, max_pixels)


def _render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    max_pdf_pages: int,
    max_pixels: int,
) -> list[PageImage]:
    """Render every PDF page to PNG at the specified DPI using PyMuPDF."""
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    pages: list[PageImage] = []
    with pymupdf.open(pdf_path) as doc:
        if doc.is_encrypted or doc.needs_pass:
            raise EncryptedPdfError("Encrypted or password-protected PDFs are not supported.")
        if len(doc) > max_pdf_pages:
            raise DocumentLimitError(
                f"PDF exceeds the maximum allowed {max_pdf_pages} pages."
            )
        for index, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            if pixmap.width * pixmap.height > max_pixels:
                raise DocumentLimitError("Rendered PDF page exceeds maximum pixel limit.")
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


def _prepare_single_image_page(
    image_path: Path,
    output_dir: Path,
    max_pixels: int,
) -> list[PageImage]:
    """Normalize a single uploaded JPG/PNG into page_1.png."""
    out_path = output_dir / "page_1.png"
    with Image.open(image_path) as img:
        width, height = img.size
        if width * height > max_pixels:
            raise DocumentLimitError(
                f"Image exceeds the maximum allowed {max_pixels:,} pixels."
            )
        rgb_img = img.convert("RGB")
        rgb_img.save(out_path, format="PNG")
    return [PageImage(page=1, image_path=out_path, width=width, height=height)]
