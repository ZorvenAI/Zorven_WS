"""H-03 · image preprocessing.

Real Pillow operations on real image bytes — no mocks.
"""

from __future__ import annotations

import io

from PIL import Image

from app.logic.preprocessing import preprocess_image


def _make_image(width: int = 100, height: int = 50, mode: str = "RGB") -> bytes:
    """Create a minimal valid image in memory."""
    img = Image.new(mode, (width, height), color="gray")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestPreprocessImage:
    def test_returns_valid_png(self):
        raw = _make_image()
        result = preprocess_image(raw)
        img = Image.open(io.BytesIO(result))
        assert img.format == "PNG"

    def test_output_dimensions_match_input(self):
        raw = _make_image(200, 150)
        result = preprocess_image(raw)
        img = Image.open(io.BytesIO(result))
        assert img.size == (200, 150)

    def test_rgba_converted_to_rgb(self):
        raw = _make_image(mode="RGBA")
        result = preprocess_image(raw)
        img = Image.open(io.BytesIO(result))
        assert img.mode == "RGB"

    def test_corrupt_bytes_returns_original(self):
        garbage = b"not an image at all"
        result = preprocess_image(garbage)
        assert result == garbage

    def test_empty_bytes_returns_original(self):
        result = preprocess_image(b"")
        assert result == b""

    def test_autocontrast_changes_pixel_values(self):
        img = Image.new("L", (10, 10), color=128)
        img.putpixel((0, 0), 100)
        img.putpixel((9, 9), 200)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()

        result = preprocess_image(raw)
        result_img = Image.open(io.BytesIO(result))
        pixels = list(result_img.getdata())
        assert min(pixels) < 100 or max(pixels) > 200
