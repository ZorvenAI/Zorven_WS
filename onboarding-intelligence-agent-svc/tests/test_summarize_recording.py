"""Tests for SKL-OIA-08 — SummarizeRecording skill (I-02).

Covers transcript extraction, LLM response parsing, timestamp snapping,
idempotency, redaction awareness, and edge cases.
"""

from __future__ import annotations

import json

import pytest

from app.skills.summarize_recording import (
    SummarizeRecording,
    _snap_to_boundary,
    extract_transcript_segments,
)

pytestmark = pytest.mark.unit


# ── extract_transcript_segments ──────────────────────────────────────


class TestExtractTranscriptSegments:
    """Filter and sort TranscriptFinal frames from a mixed buffer."""

    def _frame(self, type_: str, t_start: float, t_end: float, **kw):
        return json.dumps(
            {
                "type": type_,
                "text": kw.get("text", "hello"),
                "speaker": 0,
                "t_start": t_start,
                "t_end": t_end,
                "seq": 1,
                "redaction_applied": kw.get("redaction_applied", False),
            }
        ).encode()

    def test_filters_by_type(self):
        frames = [
            self._frame("transcript.final", 1.0, 2.0, text="good"),
            self._frame("transcript.partial", 2.0, 3.0, text="skip"),
            self._frame("green_signal", 3.0, 4.0, text="skip"),
            self._frame("transcript.final", 5.0, 6.0, text="also good"),
        ]
        result = extract_transcript_segments(frames, 0.0, 10.0)
        assert len(result) == 2
        assert result[0]["text"] == "good"
        assert result[1]["text"] == "also good"

    def test_filters_by_time_window(self):
        frames = [
            self._frame("transcript.final", 1.0, 2.0, text="before"),
            self._frame("transcript.final", 5.0, 6.0, text="inside"),
            self._frame("transcript.final", 9.0, 10.0, text="inside2"),
            self._frame("transcript.final", 10.0, 11.0, text="after"),
        ]
        result = extract_transcript_segments(frames, 4.0, 10.0)
        assert len(result) == 2
        assert result[0]["text"] == "inside"
        assert result[1]["text"] == "inside2"

    def test_sorts_by_t_start(self):
        frames = [
            self._frame("transcript.final", 5.0, 6.0, text="second"),
            self._frame("transcript.final", 1.0, 2.0, text="first"),
            self._frame("transcript.final", 3.0, 4.0, text="middle"),
        ]
        result = extract_transcript_segments(frames, 0.0, 10.0)
        assert [s["text"] for s in result] == ["first", "middle", "second"]

    def test_preserves_redaction_flag(self):
        frames = [
            self._frame(
                "transcript.final",
                1.0,
                2.0,
                text="[PHONE_NUMBER]",
                redaction_applied=True,
            ),
        ]
        result = extract_transcript_segments(frames, 0.0, 10.0)
        assert result[0]["redaction_applied"] is True

    def test_empty_buffer_returns_empty(self):
        assert extract_transcript_segments([], 0.0, 10.0) == []

    def test_malformed_json_skipped(self):
        frames = [b"not json", self._frame("transcript.final", 1.0, 2.0)]
        result = extract_transcript_segments(frames, 0.0, 10.0)
        assert len(result) == 1

    def test_missing_timestamps_skipped(self):
        frames = [json.dumps({"type": "transcript.final", "text": "no ts"}).encode()]
        result = extract_transcript_segments(frames, 0.0, 10.0)
        assert len(result) == 0


# ── _snap_to_boundary ────────────────────────────────────────────────


class TestSnapToBoundary:
    def test_snaps_to_nearest(self):
        assert _snap_to_boundary(4.7, [1.0, 3.0, 5.0, 8.0]) == 5.0

    def test_exact_match(self):
        assert _snap_to_boundary(3.0, [1.0, 3.0, 5.0]) == 3.0

    def test_empty_times_returns_original(self):
        assert _snap_to_boundary(4.7, []) == 4.7

    def test_single_boundary(self):
        assert _snap_to_boundary(100.0, [5.0]) == 5.0


# ── _parse_response ──────────────────────────────────────────────────


class TestParseResponse:
    segments = [
        {"text": "hello", "t_start": 1.0, "t_end": 2.0},
        {"text": "world", "t_start": 3.0, "t_end": 4.0},
    ]

    def test_valid_json(self):
        raw = json.dumps(
            {
                "text": "Summary text.",
                "key_moments": [{"t": 1.0, "label": "intro"}],
            }
        )
        result = SummarizeRecording._parse_response(raw, self.segments)
        assert result["text"] == "Summary text."
        assert len(result["key_moments"]) == 1
        assert result["key_moments"][0]["label"] == "intro"

    def test_markdown_fenced_json(self):
        raw = (
            "```json\n"
            + json.dumps(
                {
                    "text": "Fenced.",
                    "key_moments": [],
                }
            )
            + "\n```"
        )
        result = SummarizeRecording._parse_response(raw, self.segments)
        assert result["text"] == "Fenced."

    def test_malformed_degrades(self):
        result = SummarizeRecording._parse_response(
            "not valid json at all", self.segments
        )
        assert "hello" in result["text"]
        assert result["key_moments"] == []

    def test_key_moment_without_label_skipped(self):
        raw = json.dumps(
            {
                "text": "Ok",
                "key_moments": [{"t": 1.0}, {"t": 3.0, "label": "good"}],
            }
        )
        result = SummarizeRecording._parse_response(raw, self.segments)
        assert len(result["key_moments"]) == 1
        assert result["key_moments"][0]["label"] == "good"

    def test_key_moment_snapped_to_segment_boundary(self):
        raw = json.dumps(
            {
                "text": "Ok",
                "key_moments": [{"t": 2.5, "label": "between"}],
            }
        )
        result = SummarizeRecording._parse_response(raw, self.segments)
        assert result["key_moments"][0]["t"] == 3.0


# ── _format_transcript ───────────────────────────────────────────────


class TestFormatTranscript:
    def test_formats_with_timestamps(self):
        segments = [
            {"text": "hello", "t_start": 65.0, "t_end": 66.0},
            {"text": "world", "t_start": 125.0, "t_end": 126.0},
        ]
        result = SummarizeRecording._format_transcript(segments)
        assert "[01:05]" in result
        assert "[02:05]" in result

    def test_redaction_marker(self):
        segments = [
            {
                "text": "[PHONE]",
                "t_start": 1.0,
                "t_end": 2.0,
                "redaction_applied": True,
            },
        ]
        result = SummarizeRecording._format_transcript(segments)
        assert "[REDACTED]" in result
