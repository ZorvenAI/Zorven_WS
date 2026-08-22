"""Tests for the video keyframe extraction, dedup and merge pipeline.

H-04 AC-1: keyframes from fixed rate (1 fps) AND scene changes
H-04 AC-2: near-duplicate frames collapsed; reduction ratio logged
H-04 AC-3: merged text retains frame timestamps; no duplicate lines
"""

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess

import pytest
from PIL import Image

from app.logic.video_pipeline import (
    FrameOCRResult,
    KeyFrame,
    dedup_frames,
    extract_keyframes,
    merge_ocr_texts,
)

pytestmark = pytest.mark.unit


def _make_frame(
    width: int = 100,
    height: int = 100,
    color: tuple[int, int, int] = (255, 0, 0),
    pattern: str = "solid",
) -> bytes:
    """Create a PNG frame with a visually distinct pattern.

    Patterns: solid, checkerboard, stripes, diagonal — each produces
    a structurally different image that perceptual hashing can tell apart.
    """
    img = Image.new("RGB", (width, height), color)
    pixels = img.load()
    assert pixels is not None

    if pattern == "checkerboard":
        for y in range(height):
            for x in range(width):
                if (x // 10 + y // 10) % 2 == 0:
                    pixels[x, y] = (0, 0, 0)
    elif pattern == "stripes":
        for y in range(height):
            if (y // 10) % 2 == 0:
                for x in range(width):
                    pixels[x, y] = (0, 0, 0)
    elif pattern == "diagonal":
        for y in range(height):
            for x in range(width):
                if (x + y) % 20 < 10:
                    pixels[x, y] = (0, 0, 0)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_keyframe(
    timestamp_s: float = 0.0,
    source: str = "fps",
    color: tuple[int, int, int] = (255, 0, 0),
    pattern: str = "solid",
) -> KeyFrame:
    return KeyFrame(
        frame_bytes=_make_frame(color=color, pattern=pattern),
        timestamp_s=timestamp_s,
        source=source,
    )


def _make_video(duration_s: float = 3.0, fps: int = 10) -> bytes:
    """Create a minimal test video using ffmpeg."""
    import tempfile
    import os

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-f", "lavfi",
                "-i", f"color=c=red:s=64x64:d={duration_s}:r={fps}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-t", str(duration_s),
                "-y",
                tmp_path,
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip(
                f"ffmpeg video generation failed: "
                f"{result.stderr.decode()[:200]}"
            )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── extract_keyframes (AC-1) ───────────────────────────────────────


class TestExtractKeyframes:
    def test_extracts_frames_from_video(self) -> None:
        video = _make_video(duration_s=3.0)
        frames = asyncio.run(
            extract_keyframes(video, fps=1.0, max_frames=30)
        )
        assert len(frames) >= 1
        for f in frames:
            assert f.frame_bytes
            assert f.timestamp_s >= 0.0
            assert f.source in ("fps", "scene")

    def test_frame_cap_enforced(self) -> None:
        video = _make_video(duration_s=5.0)
        frames = asyncio.run(
            extract_keyframes(video, fps=1.0, max_frames=3)
        )
        assert len(frames) <= 3

    def test_empty_video_returns_empty(self) -> None:
        frames = asyncio.run(
            extract_keyframes(b"", fps=1.0, max_frames=30)
        )
        assert frames == []

    def test_max_duration_respected(self) -> None:
        video = _make_video(duration_s=5.0)
        frames = asyncio.run(
            extract_keyframes(video, fps=1.0, max_frames=30, max_duration_s=2)
        )
        for f in frames:
            assert f.timestamp_s <= 3.0

    def test_timestamps_are_sorted(self) -> None:
        video = _make_video(duration_s=4.0)
        frames = asyncio.run(
            extract_keyframes(video, fps=1.0, max_frames=30)
        )
        timestamps = [f.timestamp_s for f in frames]
        assert timestamps == sorted(timestamps)


# ── dedup_frames (AC-2) ───────────────────────────────────────────


class TestDedupFrames:
    def test_identical_frames_collapsed(self) -> None:
        frames = [
            _make_keyframe(0.0, color=(255, 0, 0)),
            _make_keyframe(1.0, color=(255, 0, 0)),
            _make_keyframe(2.0, color=(255, 0, 0)),
        ]
        unique, ratio = dedup_frames(frames, threshold=8)
        assert len(unique) == 1
        assert ratio > 0.0

    def test_different_frames_kept(self) -> None:
        frames = [
            _make_keyframe(0.0, pattern="solid"),
            _make_keyframe(1.0, pattern="checkerboard"),
            _make_keyframe(2.0, pattern="stripes"),
        ]
        unique, ratio = dedup_frames(frames, threshold=8)
        assert len(unique) == 3
        assert ratio == 0.0

    def test_reduction_ratio_correct(self) -> None:
        frames = [
            _make_keyframe(0.0, pattern="solid"),
            _make_keyframe(1.0, pattern="solid"),
            _make_keyframe(2.0, pattern="checkerboard"),
            _make_keyframe(3.0, pattern="checkerboard"),
        ]
        unique, ratio = dedup_frames(frames, threshold=8)
        assert len(unique) == 2
        assert abs(ratio - 0.5) < 0.01

    def test_single_frame_returns_zero_ratio(self) -> None:
        frames = [_make_keyframe(0.0)]
        unique, ratio = dedup_frames(frames, threshold=8)
        assert len(unique) == 1
        assert ratio == 0.0

    def test_empty_returns_empty(self) -> None:
        unique, ratio = dedup_frames([], threshold=8)
        assert unique == []
        assert ratio == 0.0

    def test_threshold_boundary(self) -> None:
        f1 = _make_keyframe(0.0, pattern="solid")
        f2 = _make_keyframe(1.0, pattern="diagonal")
        unique_tight, _ = dedup_frames([f1, f2], threshold=1)
        unique_loose, _ = dedup_frames([f1, f2], threshold=64)
        assert len(unique_tight) >= len(unique_loose)


# ── merge_ocr_texts (AC-3) ────────────────────────────────────────


class TestMergeOcrTexts:
    def test_prefixes_timestamps(self) -> None:
        results = [
            FrameOCRResult(
                timestamp_s=5.0,
                text="Hello world",
                confidence=0.9,
                frame_bytes=b"",
            ),
        ]
        merged, _ = merge_ocr_texts(results)
        assert merged.startswith("[00:05]")
        assert "Hello world" in merged

    def test_no_duplicate_lines(self) -> None:
        results = [
            FrameOCRResult(0.0, "Line one\nLine two", 0.9, b""),
            FrameOCRResult(1.0, "Line two\nLine three", 0.8, b""),
        ]
        merged, _ = merge_ocr_texts(results)
        lines_text = [l.split("] ", 1)[1] if "] " in l else l for l in merged.split("\n")]
        assert len(lines_text) == len(set(lines_text))

    def test_preserves_all_unique_lines(self) -> None:
        results = [
            FrameOCRResult(0.0, "Alpha\nBeta", 0.9, b""),
            FrameOCRResult(1.0, "Gamma\nDelta", 0.8, b""),
        ]
        merged, _ = merge_ocr_texts(results)
        assert "Alpha" in merged
        assert "Beta" in merged
        assert "Gamma" in merged
        assert "Delta" in merged

    def test_timestamp_format_mm_ss(self) -> None:
        results = [
            FrameOCRResult(65.0, "At one minute five", 0.9, b""),
        ]
        merged, _ = merge_ocr_texts(results)
        assert "[01:05]" in merged

    def test_confidence_averaged(self) -> None:
        results = [
            FrameOCRResult(0.0, "A", 0.8, b""),
            FrameOCRResult(1.0, "B", 0.6, b""),
        ]
        _, avg = merge_ocr_texts(results)
        assert abs(avg - 0.7) < 0.01

    def test_empty_text_frames_excluded(self) -> None:
        results = [
            FrameOCRResult(0.0, "", 0.5, b""),
            FrameOCRResult(1.0, "Real text", 0.9, b""),
        ]
        merged, avg = merge_ocr_texts(results)
        assert "Real text" in merged
        assert avg == 0.9

    def test_empty_results_returns_empty(self) -> None:
        merged, avg = merge_ocr_texts([])
        assert merged == ""
        assert avg == 0.0

    def test_sorted_by_timestamp(self) -> None:
        results = [
            FrameOCRResult(2.0, "Second", 0.9, b""),
            FrameOCRResult(0.0, "First", 0.8, b""),
        ]
        merged, _ = merge_ocr_texts(results)
        lines = merged.split("\n")
        assert "First" in lines[0]
        assert "Second" in lines[1]
