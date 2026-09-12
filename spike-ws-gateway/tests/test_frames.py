"""Unit tests for the §10.2.3 frame contracts and the seq series."""

import pytest
from pydantic import TypeAdapter, ValidationError

from echo.frames import (
    CloseCode,
    Coverage,
    EchoAck,
    ErrorFrame,
    Followups,
    GreenSignal,
    NotableFact,
    Resync,
    SeqAllocator,
    ServerFrame,
    TranscriptFinal,
    TranscriptPartial,
)

pytestmark = pytest.mark.unit

adapter = TypeAdapter(ServerFrame)


def test_close_codes_map_one_to_one():
    """Every close code in Design §10.2.3 is present and distinct."""
    assert CloseCode.INVALID_JWT == 4401
    assert CloseCode.CONSENT_MISSING == 4403
    assert CloseCode.SESSION_NOT_FOUND == 4404
    assert CloseCode.ALREADY_LIVE == 4409
    assert CloseCode.RATE_LIMITED == 4429
    assert CloseCode.INTERNAL_ERROR == 1011
    values = [c.value for c in CloseCode]
    assert len(values) == len(set(values))


def test_transcript_partial_matches_design_shape():
    frame = TranscriptPartial(seq=813, text="we started roasting in twenty", speaker=2)
    assert frame.model_dump() == {
        "type": "transcript.partial",
        "seq": 813,
        "text": "we started roasting in twenty",
        "speaker": 2,
    }


def test_transcript_final_carries_timing_and_redaction_flag():
    frame = TranscriptFinal(
        seq=814,
        text="We started roasting in 2016.",
        speaker=2,
        t_start=812.4,
        t_end=815.9,
    )
    dumped = frame.model_dump()
    assert dumped["redaction_applied"] is False
    assert dumped["t_start"] == 812.4 and dumped["t_end"] == 815.9


def test_green_signal_carries_evidence_spans():
    frame = GreenSignal(
        seq=815,
        question_id="q_07",
        score=0.86,
        evidence=[{"recording_id": "r_01", "t_start": 812.4, "t_end": 815.9}],
    )
    assert frame.model_dump()["evidence"][0]["recording_id"] == "r_01"


@pytest.mark.parametrize(
    "frame",
    [
        TranscriptPartial(seq=1, text="x", speaker=1),
        TranscriptFinal(seq=2, text="x", speaker=1, t_start=0.0, t_end=1.0),
        GreenSignal(seq=3, question_id="q", score=0.5),
        Followups(seq=4, question_id="q", suggestions=["a"]),
        NotableFact(seq=5, text="x", workflow_target="WF3"),
        Coverage(seq=6, map={"WF1": 0.71}),
        ErrorFrame(seq=7, code="ERR-07", message="degraded", recoverable=True),
        Resync(seq=8, reason="out of window", oldest_available_seq=100),
        EchoAck(seq=9, echo_id=42, bytes_received=160),
    ],
)
def test_every_frame_round_trips_through_the_discriminated_union(frame):
    """A frame-shape change must break here rather than in a browser."""
    assert adapter.validate_python(frame.model_dump()) == frame


def test_frame_without_seq_is_rejected():
    with pytest.raises(ValidationError):
        TranscriptPartial(text="x", speaker=1)


def test_negative_seq_is_rejected():
    with pytest.raises(ValidationError):
        TranscriptPartial(seq=-1, text="x", speaker=1)


def test_seq_is_strictly_increasing_across_frame_types():
    alloc = SeqAllocator()
    seqs = [alloc.next() for _ in range(100)]
    assert seqs == list(range(100))
    assert all(b > a for a, b in zip(seqs, seqs[1:]))


def test_seq_allocator_reports_last_issued():
    alloc = SeqAllocator()
    assert alloc.last == -1
    alloc.next()
    alloc.next()
    assert alloc.last == 1


def test_seq_series_continues_rather_than_restarting():
    """Design §9.2: the series survives a reconnect."""
    alloc = SeqAllocator()
    for _ in range(5):
        alloc.next()
    resumed_from = alloc.last
    assert alloc.next() == resumed_from + 1
