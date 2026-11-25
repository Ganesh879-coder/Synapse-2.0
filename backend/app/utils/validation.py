"""Magic-byte MIME validation and upload size checks."""

from __future__ import annotations

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "application/pdf",
    }
)


class UnsupportedMediaError(ValueError):
    """Raised when file magic bytes do not match an allowed MIME type."""


class FileTooLargeError(ValueError):
    """Raised when uploaded file exceeds the configured byte limit."""


def detect_mime_from_magic_bytes(data: bytes) -> str:
    """Identify MIME type strictly from leading magic bytes."""
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 5 and data[:5] == b"%PDF-":
        return "application/pdf"
    raise UnsupportedMediaError(
        "Unsupported file format. Only JPG, PNG, and PDF files are accepted."
    )


def validate_upload_bytes(data: bytes, max_bytes: int) -> str:
    """Validate upload size and magic-byte MIME type, returning the detected MIME."""
    if not data:
        raise UnsupportedMediaError("Uploaded file is empty.")
    if len(data) > max_bytes:
        raise FileTooLargeError(
            f"File exceeds maximum allowed size of {max_bytes // (1024 * 1024)} MB."
        )
    mime_type = detect_mime_from_magic_bytes(data)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise UnsupportedMediaError("Unsupported MIME type.")
    return mime_type
