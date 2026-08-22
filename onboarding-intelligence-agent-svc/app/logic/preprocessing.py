"""Image preprocessing for Cloud Vision OCR.

Design §8.4 · implemented by story H-03.

Applies autocontrast and basic orientation correction before sending an
image to Cloud Vision. Falls through to the original bytes on any
failure (corrupt file, unsupported format) — a degraded read is better
than no read.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def preprocess_image(image_bytes: bytes) -> bytes:
    """Autocontrast + EXIF rotation, returned as PNG bytes.

    Returns the original bytes unchanged if Pillow cannot open the image
    or any processing step fails.
    """
    try:
        from PIL import Image, ImageOps

        img: Image.Image = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img) or img

        if img.mode == "RGBA":
            img = img.convert("RGB")

        img = ImageOps.autocontrast(img)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        logger.warning("preprocessing failed — using original image bytes")
        return image_bytes
