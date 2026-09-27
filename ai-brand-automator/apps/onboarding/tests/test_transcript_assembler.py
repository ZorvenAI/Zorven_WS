"""O-06 · transcript_assembler unit tests.

Tests the legal header assembly, speaker name resolution,
segment enrichment, and plain-text rendering.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from apps.onboarding.transcript_assembler import (
    assemble_header,
    build_speaker_map,
    enrich_segments,
    render_plain_text,
)


@pytest.fixture
def attendees():
    return [
        {
            "name": "John Smith",
            "role": "operator",
            "mic_label": "Built-in Microphone",
            "stream_index": 0,
            "checked_in_at": "2026-09-12T14:30:05Z",
        },
        {
            "name": "Mario Rossi",
            "role": "participant",
            "mic_label": "External USB Mic",
            "stream_index": 1,
            "checked_in_at": "2026-09-12T14:30:12Z",
        },
    ]


@pytest.fixture
def consent():
    return {
        "subject_name": "Pomodoro Owner",
        "method": "CHECKBOX",
        "granted_at": "2026-09-09T10:15:00Z",
        "scope": {"audio": True, "transcript": True, "captured_media": True},
    }


@pytest.fixture
def segments():
    return [
        {
            "text": "Good afternoon, thanks for joining.",
            "speaker": 0,
            "t_start": 0.5,
            "t_end": 3.2,
            "redaction_applied": False,
        },
        {
            "text": "Thank you, happy to be here.",
            "speaker": 1,
            "t_start": 4.0,
            "t_end": 6.5,
            "redaction_applied": False,
        },
    ]


@pytest.fixture
def recording():
    rec = MagicMock()
    rec.started_at = datetime(2026, 9, 12, 14, 30, 0, tzinfo=timezone.utc)
    rec.stopped_at = datetime(2026, 9, 12, 15, 30, 0, tzinfo=timezone.utc)
    rec.session_id = 6
    return rec


class TestBuildSpeakerMap:
    def test_maps_stream_index_to_name(self, attendees):
        result = build_speaker_map(attendees)
        assert result == {0: "John Smith", 1: "Mario Rossi"}

    def test_empty_attendees(self):
        assert build_speaker_map([]) == {}

    def test_skips_empty_name(self):
        result = build_speaker_map([{"stream_index": 0, "name": ""}])
        assert result == {}


class TestEnrichSegments:
    def test_adds_speaker_name(self, segments, attendees):
        speaker_map = build_speaker_map(attendees)
        enriched = enrich_segments(segments, speaker_map)
        assert enriched[0]["speaker_name"] == "John Smith"
        assert enriched[1]["speaker_name"] == "Mario Rossi"

    def test_null_for_unknown_speaker(self, segments):
        enriched = enrich_segments(segments, {})
        assert enriched[0]["speaker_name"] is None
        assert enriched[1]["speaker_name"] is None

    def test_preserves_existing_speaker_name(self):
        segs = [
            {"text": "Hello", "speaker": 0, "speaker_name": "Already Set"},
        ]
        enriched = enrich_segments(segs, {})
        assert enriched[0]["speaker_name"] == "Already Set"

    def test_does_not_mutate_original(self, segments, attendees):
        speaker_map = build_speaker_map(attendees)
        enrich_segments(segments, speaker_map)
        assert "speaker_name" not in segments[0]


class TestAssembleHeader:
    def test_includes_all_fields(self, recording, attendees, consent):
        header = assemble_header(
            recording=recording,
            attendees=attendees,
            consent=consent,
            session_company="Pomodoro Pizza",
        )
        assert header["date"] == "2026-09-12"
        assert header["time_utc"] == "14:30 UTC"
        assert header["session_company"] == "Pomodoro Pizza"
        assert len(header["attendees"]) == 2
        assert header["attendees"][0]["name"] == "John Smith"
        assert header["consent"]["subject_name"] == "Pomodoro Owner"

    def test_no_consent(self, recording, attendees):
        header = assemble_header(
            recording=recording,
            attendees=attendees,
            consent=None,
        )
        assert header["consent"] is None

    def test_no_attendees(self, recording, consent):
        header = assemble_header(
            recording=recording,
            attendees=[],
            consent=consent,
        )
        assert header["attendees"] == []

    def test_missing_started_at(self, consent):
        rec = MagicMock()
        rec.started_at = None
        rec.stopped_at = None
        rec.session_id = 1
        header = assemble_header(
            recording=rec,
            attendees=[],
            consent=consent,
        )
        assert header["date"] is None
        assert header["time_utc"] is None


class TestRenderPlainText:
    def test_full_render(self, recording, attendees, consent, segments):
        speaker_map = build_speaker_map(attendees)
        enriched = enrich_segments(segments, speaker_map)
        header = assemble_header(
            recording=recording,
            attendees=attendees,
            consent=consent,
            session_company="Pomodoro Pizza",
        )
        text = render_plain_text(header, enriched)
        assert "MEETING TRANSCRIPT" in text
        assert "Pomodoro Pizza" in text
        assert "John Smith" in text
        assert "Mario Rossi" in text
        assert "ATTENDEES" in text
        assert "CONSENT" in text
        assert "Pomodoro Owner" in text
        assert "TRANSCRIPT" in text
        assert "[00:00] John Smith: Good afternoon" in text
        assert "[00:04] Mario Rossi: Thank you" in text

    def test_no_speaker_name_falls_back(self, recording):
        segments = [
            {"text": "Hello", "speaker": 0, "t_start": 0.0, "t_end": 1.0},
        ]
        header = assemble_header(
            recording=recording,
            attendees=[],
            consent=None,
        )
        text = render_plain_text(header, segments)
        assert "[00:00] Speaker 1: Hello" in text

    def test_empty_segments(self, recording):
        header = assemble_header(
            recording=recording,
            attendees=[],
            consent=None,
        )
        text = render_plain_text(header, [])
        assert "MEETING TRANSCRIPT" in text
        assert "TRANSCRIPT" not in text.split("MEETING TRANSCRIPT")[1]
