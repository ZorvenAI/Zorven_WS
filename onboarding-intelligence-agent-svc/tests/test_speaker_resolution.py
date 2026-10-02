"""O-09 · resolving a transcript's speaker on the single gated STT stream.

O-03 routed each mic to its own STT stream, so attribution was free — the
stream was the speaker. That code had no test referencing `stream_index`
anywhere, so this file is also the coverage O-03 never got: it pins the
behaviour that replaced it.
"""

from __future__ import annotations

import pytest

from app.api.schemas import StreamDescriptor
from app.api.ws import _resolve_speaker
from app.logic.speaker_timeline import SpeakerTimeline

pytestmark = pytest.mark.unit


def descriptors() -> dict[int, StreamDescriptor]:
    return {
        0: StreamDescriptor(
            stream_index=0, speaker_name="Devan Roy", speaker_role="operator"
        ),
        1: StreamDescriptor(
            stream_index=1, speaker_name="Sarah Kelso", speaker_role="participant"
        ),
    }


def multi_mic_state() -> dict:
    timeline = SpeakerTimeline()
    timeline.record(0.0, 0)
    timeline.record(4.0, 1)
    return {"speaker_timeline": timeline, "stream_map": descriptors()}


def test_the_single_mic_path_is_unchanged():
    """No timeline means no mic map, which is the pre-O-09 recording. It must
    keep whatever the caller passed rather than acquiring a speaker."""
    who, name, role = _resolve_speaker(
        12.0, {}, speaker=0, speaker_name=None, speaker_role=None
    )

    assert (who, name, role) == (0, None, None)


def test_resolves_the_speaker_and_their_name_and_role():
    who, name, role = _resolve_speaker(
        5.0, multi_mic_state(), speaker=0, speaker_name=None, speaker_role=None
    )

    assert who == 1
    assert name == "Sarah Kelso"
    assert role == "participant"


def test_a_late_arriving_final_keeps_its_own_speaker():
    """The reason resolution is by t_start.

    STT finals lag their audio by about a second, so the operator's question
    arrives after the participant's mic has opened. Attributing on arrival would
    credit the question to whoever answered it — and O-08 would then persist
    that into the legal transcript.
    """
    who, name, _ = _resolve_speaker(
        1.0, multi_mic_state(), speaker=9, speaker_name=None, speaker_role=None
    )

    assert who == 0
    assert name == "Devan Roy"


def test_audio_before_the_first_transition_falls_back():
    """Nothing is known about who was speaking, so the caller's value stands
    rather than the first mic to open being credited."""
    timeline = SpeakerTimeline()
    timeline.record(6.0, 1)

    who, name, role = _resolve_speaker(
        2.0,
        {"speaker_timeline": timeline, "stream_map": descriptors()},
        speaker=0,
        speaker_name=None,
        speaker_role=None,
    )

    assert (who, name, role) == (0, None, None)


def test_an_index_with_no_descriptor_still_attributes_the_channel():
    """A mic the START frame never described can still be identified as a
    distinct speaker; only its name and role are unknown."""
    timeline = SpeakerTimeline()
    timeline.record(0.0, 7)

    who, name, role = _resolve_speaker(
        1.0,
        {"speaker_timeline": timeline, "stream_map": descriptors()},
        speaker=0,
        speaker_name=None,
        speaker_role=None,
    )

    assert who == 7
    assert name is None
    assert role is None


def test_alternating_turns_each_keep_their_speaker():
    timeline = SpeakerTimeline()
    for at, index in [(0.0, 0), (3.0, 1), (8.0, 0)]:
        timeline.record(at, index)
    state = {"speaker_timeline": timeline, "stream_map": descriptors()}

    names = [
        _resolve_speaker(t, state, speaker=0, speaker_name=None, speaker_role=None)[1]
        for t in (1.0, 4.0, 9.0)
    ]

    assert names == ["Devan Roy", "Sarah Kelso", "Devan Roy"]
