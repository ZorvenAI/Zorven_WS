"""Video snippet keyframe extraction, dedup and OCR merge.

Design §8.4 · implemented by story H-04.

Pipeline: ffmpeg keyframe extraction (1 fps + scene-change) → perceptual
hash dedup → per-frame OCR → text merge with frame timestamps.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import imagehash
from PIL import Image

logger = logging.getLogger(__name__)

SCENE_CHANGE_THRESHOLD = 0.3


@dataclass
class KeyFrame:
    """A single extracted frame with its timestamp."""

    frame_bytes: bytes
    timestamp_s: float
    source: str  # "fps" or "scene"


@dataclass
class FrameOCRResult:
    """OCR result for a single frame."""

    timestamp_s: float
    text: str
    confidence: float
    frame_bytes: bytes = field(repr=False)


async def extract_keyframes(
    video_bytes: bytes,
    fps: float = 1.0,
    max_frames: int = 30,
    max_duration_s: int = 120,
) -> list[KeyFrame]:
    """Extract keyframes from video at fixed fps plus scene changes.

    Writes video to a temp file, runs ffmpeg to extract frames at the
    configured rate and on scene changes, then reads the output PNGs.
    Capped at max_frames; scene-change frames are prioritised.
    """
    tmp_dir = tempfile.mkdtemp(prefix="oia_video_")
    try:
        video_path = os.path.join(tmp_dir, "input.mp4")
        fps_dir = os.path.join(tmp_dir, "fps")
        scene_dir = os.path.join(tmp_dir, "scene")
        os.makedirs(fps_dir)
        os.makedirs(scene_dir)

        with open(video_path, "wb") as f:
            f.write(video_bytes)

        duration = await _probe_duration(video_path)
        if duration is not None and duration > max_duration_s:
            logger.warning(
                "video_too_long duration_s=%s max_s=%s",
                duration,
                max_duration_s,
            )
            duration = float(max_duration_s)

        t_limit = (
            ["-t", str(max_duration_s)] if max_duration_s else []
        )

        fps_proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", video_path,
            *t_limit,
            "-vf", f"fps={fps}",
            "-vsync", "vfr",
            "-frame_pts", "1",
            os.path.join(fps_dir, "frame_%06d.png"),
            "-y", "-loglevel", "error",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await fps_proc.communicate()

        scene_proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", video_path,
            *t_limit,
            "-vf", f"select='gt(scene,{SCENE_CHANGE_THRESHOLD})',showinfo",
            "-vsync", "vfr",
            os.path.join(scene_dir, "frame_%06d.png"),
            "-y", "-loglevel", "error",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, scene_stderr = await scene_proc.communicate()

        scene_timestamps = _parse_showinfo_timestamps(
            scene_stderr.decode(errors="replace")
        )

        frames: list[KeyFrame] = []

        fps_files = sorted(Path(fps_dir).glob("frame_*.png"))
        for i, fp in enumerate(fps_files):
            ts = i / fps if fps > 0 else 0.0
            frames.append(KeyFrame(
                frame_bytes=fp.read_bytes(),
                timestamp_s=ts,
                source="fps",
            ))

        scene_files = sorted(Path(scene_dir).glob("frame_*.png"))
        for i, fp in enumerate(scene_files):
            ts = scene_timestamps[i] if i < len(scene_timestamps) else 0.0
            existing_ts = {f.timestamp_s for f in frames}
            if not any(abs(ts - et) < 0.5 for et in existing_ts):
                frames.append(KeyFrame(
                    frame_bytes=fp.read_bytes(),
                    timestamp_s=ts,
                    source="scene",
                ))

        frames.sort(key=lambda f: f.timestamp_s)

        if len(frames) > max_frames:
            scene_frames = [f for f in frames if f.source == "scene"]
            fps_frames = [f for f in frames if f.source == "fps"]
            combined = scene_frames + fps_frames
            frames = sorted(combined[:max_frames], key=lambda f: f.timestamp_s)

        logger.info(
            "keyframes_extracted total=%d fps_count=%d scene_count=%d",
            len(frames),
            sum(1 for f in frames if f.source == "fps"),
            sum(1 for f in frames if f.source == "scene"),
        )

        return frames
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _probe_duration(video_path: str) -> float | None:
    """Get video duration in seconds via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except (ValueError, AttributeError):
        return None


def _parse_showinfo_timestamps(stderr: str) -> list[float]:
    """Extract pts_time values from ffmpeg showinfo filter output."""
    timestamps: list[float] = []
    for line in stderr.split("\n"):
        if "pts_time:" not in line:
            continue
        for part in line.split():
            if part.startswith("pts_time:"):
                try:
                    timestamps.append(float(part.split(":")[1]))
                except (ValueError, IndexError):
                    pass
    return timestamps


def dedup_frames(
    frames: list[KeyFrame],
    threshold: int = 8,
) -> tuple[list[KeyFrame], float]:
    """Collapse near-duplicate frames by perceptual hashing.

    Returns (unique_frames, reduction_ratio) where
    reduction_ratio = 1 - (unique / total). A ratio of 0.6 means 60%
    of frames were duplicates.
    """
    if not frames:
        return [], 0.0

    if len(frames) == 1:
        return list(frames), 0.0

    kept: list[tuple[KeyFrame, imagehash.ImageHash]] = []

    for frame in frames:
        try:
            img = Image.open(io.BytesIO(frame.frame_bytes))
            h = imagehash.average_hash(img)
        except Exception:
            logger.warning(
                "frame_hash_failed timestamp_s=%s", frame.timestamp_s
            )
            kept.append((frame, imagehash.hex_to_hash("0" * 16)))
            continue

        is_dup = False
        for _, existing_hash in kept:
            if abs(h - existing_hash) < threshold:
                is_dup = True
                break

        if not is_dup:
            kept.append((frame, h))

    unique = [f for f, _ in kept]
    total = len(frames)
    ratio = 1.0 - (len(unique) / total) if total > 0 else 0.0

    logger.info(
        "frames_deduped total=%d unique=%d reduction_ratio=%.3f",
        total,
        len(unique),
        ratio,
    )

    return unique, ratio


def merge_ocr_texts(
    frame_results: list[FrameOCRResult],
) -> tuple[str, float]:
    """Merge per-frame OCR texts with timestamps, deduplicating lines.

    Each unique text block is prefixed with [MM:SS] of its first
    occurrence. Duplicate lines across frames are collapsed.
    Returns (merged_text, average_confidence).
    """
    if not frame_results:
        return "", 0.0

    seen_lines: dict[str, float] = {}
    blocks: list[tuple[float, str]] = []

    for result in sorted(frame_results, key=lambda r: r.timestamp_s):
        if not result.text.strip():
            continue

        for line in result.text.strip().split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped not in seen_lines:
                seen_lines[stripped] = result.timestamp_s
                blocks.append((result.timestamp_s, stripped))

    if not blocks:
        confidences = [r.confidence for r in frame_results]
        avg = sum(confidences) / len(confidences) if confidences else 0.0
        return "", avg

    current_ts: float | None = None
    lines: list[str] = []
    for ts, text in blocks:
        if current_ts is None or abs(ts - current_ts) > 0.01:
            minutes = int(ts) // 60
            seconds = int(ts) % 60
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")
            current_ts = ts
        else:
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

    merged = "\n".join(lines)

    confidences = [r.confidence for r in frame_results if r.text.strip()]
    avg_confidence = (
        sum(confidences) / len(confidences) if confidences else 0.0
    )

    return merged, avg_confidence
