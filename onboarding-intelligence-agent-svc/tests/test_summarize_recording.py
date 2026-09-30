"""Tests for SKL-OIA-08 — SummarizeRecording skill (I-02, I-03).

Covers transcript extraction, LLM response parsing, timestamp snapping,
idempotency, redaction awareness, transcript segment persistence, and
edge cases.
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
        frame = {
            "type": type_,
            "text": kw.get("text", "hello"),
            "speaker": kw.get("speaker", 0),
            "t_start": t_start,
            "t_end": t_end,
            "seq": 1,
            "redaction_applied": kw.get("redaction_applied", False),
        }
        # Omitted entirely unless asked for, so the single-mic shape — a frame
        # with no speaker_name key at all — is what the AC-2 test exercises.
        if "speaker_name" in kw:
            frame["speaker_name"] = kw["speaker_name"]
        return json.dumps(frame).encode()

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

    def test_carries_the_speaker_name_into_the_persisted_segment(self):
        """O-08 AC-1.

        The buffered frame has carried speaker_name since O-03; this function
        dropped it, so every persisted transcript held integer indices and
        nothing downstream could name a speaker. The legal header O-06
        assembles had to source names from MeetingAttendee instead.
        """
        frames = [
            self._frame(
                "transcript.final",
                1.0,
                2.0,
                text="we roast in Kalyani",
                speaker=1,
                speaker_name="Sarah Kelso",
            ),
            self._frame(
                "transcript.final",
                3.0,
                4.0,
                text="and who buys it?",
                speaker=0,
                speaker_name="Devan Roy",
            ),
        ]

        result = extract_transcript_segments(frames, 0.0, 10.0)

        assert [s["speaker_name"] for s in result] == ["Sarah Kelso", "Devan Roy"]
        assert [s["speaker"] for s in result] == [1, 0]

    def test_a_single_mic_segment_persists_a_null_speaker_name(self):
        """O-08 AC-2.

        A legacy recording has no mic-to-attendee map, so the key must be
        present and null rather than absent or invented — consumers check the
        field, and a fabricated name in a legal transcript is worse than none.
        """
        frames = [self._frame("transcript.final", 1.0, 2.0, text="hello")]

        result = extract_transcript_segments(frames, 0.0, 10.0)

        assert "speaker_name" in result[0]
        assert result[0]["speaker_name"] is None

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

    def test_attributes_lines_by_role(self):
        """O-08: the summary prompt must distinguish question from answer.

        The summary becomes an evidence block of its own, so an unattributed
        prompt lets "so you focus on wholesale?" be summarised as "the business
        focuses on wholesale" — which then competes with the correctly
        attributed transcript block in extraction.
        """
        segments = [
            {
                "text": "so you focus on wholesale?",
                "speaker": 0,
                "speaker_role": "operator",
                "t_start": 1.0,
                "t_end": 2.0,
            },
            {
                "text": "no, direct to consumer",
                "speaker": 1,
                "speaker_role": "participant",
                "t_start": 3.0,
                "t_end": 4.0,
            },
        ]

        result = SummarizeRecording._format_transcript(segments)

        assert "Operator: so you focus on wholesale?" in result
        assert "Participant: no, direct to consumer" in result

    def test_no_speaker_name_reaches_the_summary_prompt(self):
        """Roles, never names — the body has already had PERSON redacted."""
        segments = [
            {
                "text": "we roast in Kalyani",
                "speaker": 1,
                "speaker_name": "Sarah Kelso",
                "speaker_role": "participant",
                "t_start": 1.0,
                "t_end": 2.0,
            },
        ]

        result = SummarizeRecording._format_transcript(segments)

        assert "Sarah Kelso" not in result
        assert "Participant: we roast in Kalyani" in result

    def test_a_single_mic_transcript_is_unlabelled(self):
        """AC-2: no role map, so no labels."""
        segments = [{"text": "we started in 2019", "speaker": 0, "t_start": 1.0}]

        result = SummarizeRecording._format_transcript(segments)

        assert result == "[00:01] we started in 2019"

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


# ── Transcript segment output contract (I-03) ──────────────────────


class TestTranscriptSegmentOutput:
    """Verify that extracted segments carry the fields I-03's frontend needs."""

    def test_segment_has_required_fields(self):
        raw = [
            json.dumps(
                {
                    "type": "transcript.final",
                    "text": "hello world",
                    "speaker": 1,
                    "t_start": 2.0,
                    "t_end": 3.5,
                    "seq": 1,
                    "redaction_applied": False,
                }
            ).encode()
        ]
        segments = extract_transcript_segments(raw, 0.0, 10.0)
        seg = segments[0]
        assert set(seg.keys()) == {
            "text",
            "speaker",
            # O-08: both present on every segment, null when there is no mic
            # map, so a consumer reads the field rather than testing for it.
            # speaker_name is the legal record; speaker_role is what prompts
            # are attributed by, so no name reaches a model provider.
            "speaker_name",
            "speaker_role",
            "t_start",
            "t_end",
            "redaction_applied",
        }

    def test_segments_are_post_redaction(self):
        raw = [
            json.dumps(
                {
                    "type": "transcript.final",
                    "text": "Call me at [PHONE_NUMBER]",
                    "speaker": 0,
                    "t_start": 1.0,
                    "t_end": 2.0,
                    "seq": 1,
                    "redaction_applied": True,
                }
            ).encode()
        ]
        segments = extract_transcript_segments(raw, 0.0, 10.0)
        assert segments[0]["redaction_applied"] is True
        assert "[PHONE_NUMBER]" in segments[0]["text"]

    def test_speaker_field_preserved(self):
        raw = [
            json.dumps(
                {
                    "type": "transcript.final",
                    "text": "speaker zero",
                    "speaker": 0,
                    "t_start": 1.0,
                    "t_end": 2.0,
                    "seq": 1,
                }
            ).encode(),
            json.dumps(
                {
                    "type": "transcript.final",
                    "text": "speaker one",
                    "speaker": 1,
                    "t_start": 3.0,
                    "t_end": 4.0,
                    "seq": 2,
                }
            ).encode(),
        ]
        segments = extract_transcript_segments(raw, 0.0, 10.0)
        assert segments[0]["speaker"] == 0
        assert segments[1]["speaker"] == 1
