"""H-04 property tests — video OCR pipeline invariants.

Hypothesis-driven checks that hold regardless of input:
- merged text never contains duplicate lines
- every line has [MM:SS] prefix
- reduction_ratio always in [0.0, 1.0]
- frame count after dedup <= frame count before
"""

from __future__ import annotations

import io

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from app.logic.video_pipeline import (
    FrameOCRResult,
    KeyFrame,
    dedup_frames,
    merge_ocr_texts,
)

pytestmark = [pytest.mark.property, pytest.mark.hypothesis]


def _frame_bytes(r: int = 128, g: int = 128, b: int = 128) -> bytes:
    img = Image.new("RGB", (8, 8), (r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@given(
    texts=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
            min_size=1,
            max_size=50,
        ),
        min_size=1,
        max_size=10,
    ),
    timestamps=st.lists(
        st.floats(min_value=0.0, max_value=3600.0, allow_nan=False),
        min_size=1,
        max_size=10,
    ),
)
@settings(max_examples=50)
def test_merged_text_no_duplicate_lines(texts, timestamps):
    """No line appears more than once in merged output."""
    n = min(len(texts), len(timestamps))
    results = [
        FrameOCRResult(
            timestamp_s=timestamps[i],
            text=texts[i],
            confidence=0.8,
            frame_bytes=b"",
        )
        for i in range(n)
    ]

    merged, _ = merge_ocr_texts(results)

    if merged:
        lines = merged.strip().split("\n")
        text_parts = []
        for line in lines:
            if "] " in line:
                text_parts.append(line.split("] ", 1)[1])
            else:
                text_parts.append(line)
        assert len(text_parts) == len(set(text_parts))


@given(
    texts=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
        min_size=1,
        max_size=5,
    ),
)
@settings(max_examples=50)
def test_every_line_has_timestamp_prefix(texts):
    """Every non-empty line starts with [MM:SS]."""
    results = [
        FrameOCRResult(
            timestamp_s=float(i),
            text=t,
            confidence=0.8,
            frame_bytes=b"",
        )
        for i, t in enumerate(texts)
    ]

    merged, _ = merge_ocr_texts(results)

    if merged:
        import re

        for line in merged.strip().split("\n"):
            if line.strip():
                assert re.match(
                    r"\[\d{2}:\d{2}\]", line
                ), f"Line missing timestamp: {line!r}"


@given(
    n_frames=st.integers(min_value=0, max_value=20),
    threshold=st.integers(min_value=1, max_value=64),
)
@settings(max_examples=50)
def test_reduction_ratio_bounds(n_frames, threshold):
    """reduction_ratio is always in [0.0, 1.0]."""
    frames = [
        KeyFrame(
            frame_bytes=_frame_bytes(r=i * 13 % 256),
            timestamp_s=float(i),
            source="fps",
        )
        for i in range(n_frames)
    ]

    _, ratio = dedup_frames(frames, threshold=threshold)

    assert 0.0 <= ratio <= 1.0


@given(
    n_frames=st.integers(min_value=0, max_value=20),
    threshold=st.integers(min_value=1, max_value=64),
)
@settings(max_examples=50)
def test_dedup_never_increases_count(n_frames, threshold):
    """Frame count after dedup <= frame count before."""
    frames = [
        KeyFrame(
            frame_bytes=_frame_bytes(r=i * 37 % 256, g=i * 71 % 256),
            timestamp_s=float(i),
            source="fps",
        )
        for i in range(n_frames)
    ]

    unique, _ = dedup_frames(frames, threshold=threshold)

    assert len(unique) <= len(frames)
