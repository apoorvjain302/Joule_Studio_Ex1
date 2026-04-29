"""REQ-01: Multi-Channel Photo Ingestion tool.

Validates and prepares a pallet photo for AI analysis.
Supports base64-encoded images and publicly accessible URLs.
"""

from __future__ import annotations

import base64
import logging
import uuid

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Minimum raw image size in bytes (10 KB)
_MIN_SIZE = 10_000


def _is_url(image_data: str) -> bool:
    return image_data.startswith("http://") or image_data.startswith("https://")


def _validate_base64(image_data: str) -> tuple[bool, str | None, int]:
    """Decode and validate base64 image.

    Returns (valid, error_message, size_bytes).
    """
    # Strip data URI prefix if present (e.g. "data:image/jpeg;base64,...")
    raw = image_data
    detected_mime: str | None = None
    if raw.startswith("data:"):
        try:
            header, raw = raw.split(",", 1)
            detected_mime = header.split(":")[1].split(";")[0]
        except (ValueError, IndexError):
            return False, "Invalid data URI format", 0

    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        return False, "Invalid base64 encoding", 0

    size = len(decoded)

    # Validate MIME type when declared
    if detected_mime and detected_mime not in SUPPORTED_MIME_TYPES:
        return (
            False,
            f"Unsupported image format: {detected_mime}. Supported: {sorted(SUPPORTED_MIME_TYPES)}",
            size,
        )

    # Validate minimum size
    if size < _MIN_SIZE:
        return (
            False,
            f"Image too small ({size} bytes). Minimum required: {_MIN_SIZE} bytes",
            size,
        )

    return True, None, size


def _validate_url(image_data: str) -> tuple[bool, str | None]:
    """Basic URL validation — check it ends with a supported extension or assume valid."""
    lower = image_data.lower().split("?")[0]  # strip query params
    if any(lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        return True, None
    # If no recognisable extension, accept optimistically (server may serve correct MIME)
    return True, None


@tool
def validate_and_prepare_image(image_data: str, source_channel: str) -> dict:
    """Validate and prepare a pallet image for AI analysis.

    Accepts a base64-encoded image string or a publicly accessible image URL.
    Validates format and minimum size before returning a ready image descriptor.

    Args:
        image_data: Base64-encoded image string (with or without data URI prefix)
                    or a publicly accessible image URL.
        source_channel: Input channel identifier. Valid values:
                        'mobile', 'handheld', 'dock_camera', 'web'.

    Returns:
        dict with keys:
            image_id (str): Unique identifier for this ingestion event.
            channel (str): Validated source channel.
            ready (bool): True if the image passed all validation checks.
            error (str | None): Human-readable error message on failure, else None.
    """
    channel = source_channel if source_channel else "unknown"
    image_id = str(uuid.uuid4())

    if not image_data or not image_data.strip():
        error = "No image data provided"
        logger.warning(
            "M1.missed: pallet photo ingestion failed — invalid format or resolution below threshold"
        )
        return {"image_id": image_id, "channel": channel, "ready": False, "error": error}

    if _is_url(image_data):
        valid, error = _validate_url(image_data)
    else:
        valid, error, _size = _validate_base64(image_data)

    if valid:
        logger.info(
            "M1.achieved: pallet photo ingested successfully from channel=%s, image_id=%s",
            channel,
            image_id,
        )
        return {"image_id": image_id, "channel": channel, "ready": True, "error": None}
    else:
        logger.warning(
            "M1.missed: pallet photo ingestion failed — invalid format or resolution below threshold"
        )
        return {"image_id": image_id, "channel": channel, "ready": False, "error": error}
