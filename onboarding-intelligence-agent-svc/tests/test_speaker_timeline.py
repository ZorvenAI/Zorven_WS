"""O-09 · resolving which mic was open at a moment of audio."""

from __future__ import annotations

import pytest

from app.logic.speaker_timeline import SpeakerTimeline

pytestmark = pytest.mark.unit


def test_resolves_the_channel_open_at_that_moment():
    timeline = SpeakerTimeline()
    timeline.record(0.0, 0)
    timeline.record(5.0, 1)

    assert timeline.resolve(0.0) == 0
    assert timeline.resolve(4.9) == 0
    assert timeline.resolve(5.0) == 1
    assert timeline.resolve(90.0) == 1


def test_a_handover_is_not_attributed_to_whoever_spoke_next():
    """The reason resolution is by t_start and not by "current speaker".

    STT finals lag their audio by around a second, so an utterance that ended
    just before a handover arrives after it. Attributing by arrival time would
    credit the operator's question to the participant who answered it.
    """
    timeline = SpeakerTimeline()
    timeline.record(0.0, 0)  # operator asks
    timeline.record(4.0, 1)  # participant answers

    # The final for the operator's question arrives while mic 1 is open.
    assert timeline.resolve(1.2) == 0


def test_audio_before_the_first_transition_is_unattributed():
    """A legal transcript should not guess. Returning the first channel to
    speak would put words in the mouth of whoever happened to talk first."""
    timeline = SpeakerTimeline()
    timeline.record(3.0, 1)

    assert timeline.resolve(0.5) is None


def test_an_empty_timeline_attributes_nothing():
    """A single-mic recording records no transitions, and must not acquire a
    speaker by accident."""
    assert SpeakerTimeline().resolve(12.0) is None


def test_a_repeated_channel_is_not_recorded_twice():
    """The gate re-evaluates every analysis window — about ten times a second —
    so without this the timeline would grow without saying anything new."""
    timeline = SpeakerTimeline()
    for t in (0.0, 0.1, 0.2, 0.3):
        timeline.record(t, 0)

    assert len(timeline) == 1
    assert timeline.resolve(0.3) == 0


def test_a_backwards_timestamp_is_ignored():
    """Audio arrives in order, so a time that moves backwards means a clock
    that moved. Inserting it would let resolve() answer for a moment that never
    existed."""
    timeline = SpeakerTimeline()
    timeline.record(10.0, 0)
    timeline.record(2.0, 1)

    assert len(timeline) == 1
    # The surviving transition still answers for its own moment, and 2.0 is
    # unattributed because it predates it — not because it was recorded.
    assert timeline.resolve(10.0) == 0
    assert timeline.resolve(2.0) is None


def test_alternating_speakers_each_keep_their_own_words():
    timeline = SpeakerTimeline()
    for at, index in [(0.0, 0), (2.0, 1), (6.0, 0), (9.0, 1)]:
        timeline.record(at, index)

    assert [timeline.resolve(t) for t in (0.5, 3.0, 7.0, 10.0)] == [0, 1, 0, 1]
    assert len(timeline) == 4
