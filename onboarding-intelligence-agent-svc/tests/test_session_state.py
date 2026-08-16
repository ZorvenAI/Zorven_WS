"""F-04 PR 2 · seq, the replay buffer and resume (AC-3, AC-4).

The card names `test_resume_replays_after_last_seq` here.

Real Redis, per this service's rule. Both things under test *are* Redis
semantics — an atomic INCR and a capped list — and a substitute would assert
that my arithmetic is my arithmetic while proving nothing about the operations
the guarantees rest on.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.api.schemas import (
    Coverage,
    NotableFact,
    ServerFrameType,
    TranscriptFinal,
    TranscriptPartial,
)
from app.logic.live_session import (
    BUFFER_FRAMES,
    LiveSessionManager,
    SegmentBatcher,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def manager(live_redis):
    """A manager on a session id no other test uses.

    Redis outlives a test, and the seq counter is deliberately monotonic for
    the life of a session — sharing an id between tests would make the
    "strictly increasing" assertions depend on execution order.
    """
    return LiveSessionManager(
        redis=live_redis, tenant_id="t-seq", session_id=f"s-{uuid.uuid4().hex[:8]}"
    )


def partial(
    text: str = "we started roasting in twenty", speaker: int = 2, seq: int = 1
):
    return TranscriptPartial(seq=seq, text=text, speaker=speaker)


# ── AC-4 · a monotonic seq across all frame types ────────────────────


async def test_seq_starts_at_one(manager):
    """Not zero. `resume` carries `last_seq: 0` before a client has received
    anything, so a frame numbered 0 would be indistinguishable from that."""
    assert await manager.next_seq() == 1


async def test_seq_increases_across_frame_types(manager):
    """AC-4: "strictly increasing for the life of the session **across all
    frame types**". A per-type counter would satisfy a careless reading and
    give the client two frames numbered 7."""
    seqs = [await manager.next_seq() for _ in range(5)]

    assert seqs == [1, 2, 3, 4, 5]


async def test_concurrent_frames_never_share_a_seq(manager):
    """The case a read-then-write loses.

    A transcript partial and a coverage update produced in the same moment is
    the ordinary case, not a rare one — and two frames claiming seq 7 is the
    failure AC-4 exists to prevent. INCR is atomic; `get` then `set` is not,
    and the difference only ever shows up under concurrency.
    """
    seqs = await asyncio.gather(*(manager.next_seq() for _ in range(50)))

    assert len(set(seqs)) == 50
    assert sorted(seqs) == list(range(1, 51))


async def test_the_counter_survives_the_buffer_being_trimmed(manager):
    """seq is its own key for this reason.

    Derived from the buffer's length it would restart every time the cap
    evicted a frame, and a client that had seen seq 2100 would be sent seq 5
    next — which its own ordering check would reject.
    """
    for _ in range(5):
        await manager.emit(partial(seq=await manager.next_seq()))

    before = await manager.next_seq()
    key = manager.redis.keys_for("t-seq").live_frames(manager.session_id)
    await manager.redis.client.delete(key)

    assert await manager.next_seq() == before + 1


# ── AC-3 · resume replays rather than restarts ───────────────────────


async def test_resume_replays_after_last_seq(manager):
    """The card's named case.

    A client that dropped at seq 812 gets 813 onward and nothing it has
    already rendered. Replaying from the start would duplicate the meeting on
    screen; replaying nothing would lose it.
    """
    for index in range(1, 11):
        await manager.emit(partial(text=f"chunk {index}", seq=await manager.next_seq()))

    frames, resync = await manager.replay_after(6)

    assert resync is None
    assert [f["seq"] for f in frames] == [7, 8, 9, 10]
    assert frames[0]["text"] == "chunk 7"


async def test_resume_from_zero_replays_everything(manager):
    """A client that connected, missed everything and knows it."""
    for index in range(1, 4):
        await manager.emit(partial(text=f"chunk {index}", seq=await manager.next_seq()))

    frames, resync = await manager.replay_after(0)

    assert resync is None
    assert [f["seq"] for f in frames] == [1, 2, 3]


async def test_resume_at_the_head_replays_nothing(manager):
    """The control. A resume that always replayed something would duplicate
    frames on every reconnect."""
    for index in range(1, 4):
        await manager.emit(partial(text=f"chunk {index}", seq=await manager.next_seq()))

    frames, resync = await manager.replay_after(3)

    assert resync is None
    assert frames == []


async def test_a_resume_beyond_the_window_gets_an_explicit_resync(manager):
    """AC-3: "a resume attempt beyond the window is answered with an explicit
    resync frame, **not a silent gap in seq**".

    The client is told where the record now starts. Sent nothing, it cannot
    tell "you missed nothing" from "we no longer have what you missed", and
    renders a meeting with a hole in it either way.
    """
    for index in range(1, 6):
        await manager.emit(partial(text=f"chunk {index}", seq=await manager.next_seq()))

    # Trim the buffer to the newest two, as the cap would.
    key = manager.redis.keys_for("t-seq").live_frames(manager.session_id)
    await manager.redis.client.ltrim(key, -2, -1)

    frames, resync = await manager.replay_after(1)

    assert frames == []
    assert resync is not None
    assert resync.type is ServerFrameType.RESYNC
    assert resync.from_seq == 4, "the client should be told where the record starts"


async def test_a_resume_beyond_the_newest_frame_gets_a_resync(manager):
    """The client claims a seq the server never produced.

    Possible after a counter reset (Redis flush) or a session id collision.
    An empty "nothing to replay" is indistinguishable from "you are up to
    date" on the client side, so a resync is the honest answer.
    """
    for index in range(1, 5):
        await manager.emit(partial(text=f"chunk {index}", seq=await manager.next_seq()))

    frames, resync = await manager.replay_after(900)

    assert frames == []
    assert resync is not None
    assert resync.type is ServerFrameType.RESYNC


async def test_an_empty_buffer_answers_with_a_resync(manager):
    """Nothing buffered is not the same as nothing missed — the server cannot
    say which, so it says so."""
    frames, resync = await manager.replay_after(12)

    assert frames == []
    assert resync is not None


async def test_the_buffer_is_capped(manager):
    """A shared Redis: an untrimmed list evicts another service's data, which
    this service's eviction note makes non-negotiable."""
    for _ in range(BUFFER_FRAMES + 25):
        await manager.emit(partial(seq=await manager.next_seq()))

    key = manager.redis.keys_for("t-seq").live_frames(manager.session_id)
    assert await manager.redis.client.llen(key) == BUFFER_FRAMES


async def test_every_frame_type_round_trips_through_the_buffer(manager):
    """AC-4 asks for shapes "validated against a shared schema module rather
    than hand-built dicts". The buffer stores JSON, so the shapes have to
    survive the trip — a model that serialised lossily would replay a frame
    the client cannot parse."""
    await manager.emit(
        TranscriptFinal(
            seq=await manager.next_seq(),
            text="We started roasting in 2016.",
            speaker=2,
            t_start=812.4,
            t_end=815.9,
        )
    )
    await manager.emit(
        Coverage(
            seq=await manager.next_seq(), map={"WF1": 0.71, "WF2": 0.44, "WF3": 0.3}
        )
    )
    await manager.emit(
        NotableFact(
            seq=await manager.next_seq(),
            text="Owns a second retail location opening in October.",
            workflow_target="WF3",
        )
    )

    frames, _ = await manager.replay_after(0)

    assert [f["type"] for f in frames] == [
        "transcript.final",
        "coverage",
        "notable_fact",
    ]
    # FR-LIVE-09: three fractions, never blended into one number.
    assert frames[1]["map"] == {"WF1": 0.71, "WF2": 0.44, "WF3": 0.3}


async def test_concurrent_emits_replay_in_seq_order(manager):
    """Two coroutines emitting concurrently can rpush in wrong order.

    The replay must sort by seq regardless of insertion order — a client that
    receives frame 6 before frame 5 cannot render the transcript correctly,
    and "strictly increasing" would be false for the frames it actually sees.
    """
    seqs = [await manager.next_seq() for _ in range(10)]
    await asyncio.gather(
        *(manager.emit(partial(text=f"chunk {s}", seq=s)) for s in seqs)
    )

    frames, resync = await manager.replay_after(0)

    assert resync is None
    replayed = [f["seq"] for f in frames]
    assert replayed == sorted(replayed), "concurrent emit broke replay order"
    assert replayed == list(range(1, 11))


# ── G-02 · SegmentBatcher ────────────────────────────────────────────


def _seg(text="hello", speaker=0, t_start=0.0, t_end=1.0):
    return {"text": text, "speaker": speaker, "t_start": t_start, "t_end": t_end}


def test_batch_fires_on_speaker_change():
    """AC-1: a speaker change flushes the previous speaker's segments."""
    batcher = SegmentBatcher(window_s=10.0, min_duration_s=0.4)

    assert batcher.add(_seg(speaker=1, t_start=0.0, t_end=1.0)) is None
    assert batcher.add(_seg(speaker=1, t_start=1.0, t_end=2.0)) is None

    batch = batcher.add(_seg(speaker=2, t_start=2.5, t_end=3.5))
    assert batch is not None
    assert len(batch.segments) == 2
    assert all(s["speaker"] == 1 for s in batch.segments)


def test_fragment_not_dispatched_alone():
    """AC-1: a batch shorter than 400 ms is never dispatched alone."""
    batcher = SegmentBatcher(window_s=10.0, min_duration_s=0.4)

    assert batcher.add(_seg(speaker=1, t_start=0.0, t_end=0.3)) is None
    batch = batcher.add(_seg(speaker=2, t_start=0.5, t_end=1.0))
    assert batch is None, "a 300 ms batch must not be dispatched"


def test_batch_carries_evidence_spans():
    """Batch segments carry t_start/t_end for evidence."""
    batcher = SegmentBatcher(recording_id="rec-42", window_s=10.0, min_duration_s=0.1)
    batcher.add(_seg(t_start=10.0, t_end=11.0))
    batcher.add(_seg(t_start=11.0, t_end=12.5))
    batch = batcher.flush()

    assert batch is not None
    assert batch.recording_id == "rec-42"
    assert batch.first_t == 10.0
    assert batch.last_t == 12.5


def test_batch_flush_on_session_end():
    """Remaining segments are not lost when the session ends."""
    batcher = SegmentBatcher(window_s=10.0, min_duration_s=0.1)
    batcher.add(_seg(t_start=5.0, t_end=6.0))
    batcher.add(_seg(t_start=6.0, t_end=7.0))

    batch = batcher.flush()
    assert batch is not None
    assert len(batch.segments) == 2

    assert batcher.flush() is None


def test_check_timer_fires_when_window_expired(monkeypatch):
    """check_timer() fires the batch when the window has elapsed."""
    import time as time_mod

    fake_time = [100.0]
    monkeypatch.setattr(time_mod, "monotonic", lambda: fake_time[0])

    batcher = SegmentBatcher(window_s=3.0, min_duration_s=0.1)
    batcher.add(_seg(t_start=0.0, t_end=1.0))

    assert batcher.check_timer() is None

    fake_time[0] = 104.0
    batch = batcher.check_timer()
    assert batch is not None
    assert len(batch.segments) == 1


def test_recording_id_setter():
    """The batcher's recording_id can be updated after construction."""
    batcher = SegmentBatcher()
    assert batcher.recording_id == ""
    batcher.recording_id = "rec-99"
    batcher.add(_seg(t_start=0.0, t_end=1.0))
    batch = batcher.flush()
    assert batch.recording_id == "rec-99"


# ── G-02 · Question state in Redis ───────────────────────────────────


async def test_set_and_get_questions(manager):
    """Redis round-trip for question state."""
    questions = [
        {
            "id": 10,
            "text": "What is your company name?",
            "target_field": "name",
            "workflow_target": "WF1",
            "status": "OPEN",
        },
        {
            "id": 20,
            "text": "What is your founding year?",
            "target_field": "founded_year",
            "workflow_target": "WF1",
            "status": "OPEN",
        },
    ]
    await manager.set_questions(questions)
    result = await manager.get_questions()

    assert len(result) == 2
    ids = {q["id"] for q in result}
    assert ids == {"10", "20"}
    texts = {q["text"] for q in result}
    assert "What is your company name?" in texts
    assert "What is your founding year?" in texts


async def test_store_analysis_result_updates_evidence(manager):
    """Evidence is written to the question hash by analysis."""
    await manager.set_questions(
        [
            {"id": 10, "text": "What is your company name?", "target_field": "name"},
        ]
    )

    evidence = [{"recording_id": "r-1", "t_start": 10.0, "t_end": 12.0}]
    await manager.store_analysis_result("10", evidence, 0.85)

    questions = await manager.get_questions()
    q = questions[0]
    assert q["source"] == "analysis"
    assert q["relevance"] == 0.85
    assert len(q["evidence"]) == 1
    assert q["evidence"][0]["recording_id"] == "r-1"


async def test_question_state_survives_reconnect(manager):
    """Questions stored in Redis survive a socket drop (new manager instance)."""
    await manager.set_questions(
        [
            {"id": 5, "text": "Target audience?", "target_field": "audience"},
        ]
    )

    manager2 = LiveSessionManager(
        redis=manager.redis,
        tenant_id=manager.tenant_id,
        session_id=manager.session_id,
    )
    questions = await manager2.get_questions()
    assert len(questions) == 1
    assert questions[0]["text"] == "Target audience?"


async def test_store_unmapped_batch(manager):
    """Unmapped batch stored for G-05."""
    segments = [{"text": "We also sell online.", "t_start": 5.0, "t_end": 6.0}]
    await manager.store_unmapped_batch(segments)

    key = manager._keys().unmapped(manager.session_id)
    length = await manager.redis.client.llen(key)
    assert length == 1


# ── G-03 · Version-based question state ─────────────────────────────


async def test_set_questions_initializes_version(manager):
    """set_questions creates entries with version 0."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )
    entry = await manager.get_question_entry("1")
    assert entry is not None
    assert entry["version"] == 0
    assert entry["missing_aspects"] == []


async def test_mark_question_bumps_version(manager):
    """Manual override increments the version counter."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )

    new_version = await manager.mark_question("1", "manual_green")
    assert new_version == 1

    entry = await manager.get_question_entry("1")
    assert entry["version"] == 1
    assert entry["source"] == "manual"
    assert entry["status"] == "GREEN"


async def test_mark_question_ungreen(manager):
    """manual_ungreen sets status back to OPEN."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )
    await manager.mark_question("1", "manual_green")
    await manager.mark_question("1", "manual_ungreen")

    entry = await manager.get_question_entry("1")
    assert entry["status"] == "OPEN"
    assert entry["version"] == 2


async def test_apply_green_signal_bumps_version(manager):
    """Successful apply increments version."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )
    evidence = [{"recording_id": "r-1", "t_start": 10.0, "t_end": 12.0}]

    applied = await manager.apply_green_signal("1", 0.85, evidence, 0)
    assert applied is True

    entry = await manager.get_question_entry("1")
    assert entry["status"] == "GREEN"
    assert entry["score"] == 0.85
    assert entry["source"] == "analysis"
    assert entry["version"] == 1
    assert len(entry["evidence"]) == 1


async def test_apply_green_signal_rejected_on_version_mismatch(manager):
    """Stale signal discarded when version doesn't match."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )
    evidence = [{"recording_id": "r-1", "t_start": 10.0, "t_end": 12.0}]

    applied = await manager.apply_green_signal("1", 0.85, evidence, 999)
    assert applied is False

    entry = await manager.get_question_entry("1")
    assert entry["status"] == "OPEN"
    assert entry["version"] == 0


async def test_manual_override_survives_stale_signal(manager):
    """AC-3: manual uncheck followed by in-flight green signal.

    The ordering hazard from the G-03 tech notes: a manual uncheck at
    version N, then an apply_green_signal with expected_version=N-1.
    The signal must be discarded.
    """
    await manager.set_questions(
        [{"id": 7, "text": "Founding year?", "target_field": "founded_year"}]
    )

    # Analysis reads version 0
    expected_version = 0

    # Operator manually overrides (bumps to version 1)
    await manager.mark_question("7", "manual_ungreen")

    # In-flight green signal arrives with stale version 0
    evidence = [{"recording_id": "r-1", "t_start": 5.0, "t_end": 8.0}]
    applied = await manager.apply_green_signal("7", 0.88, evidence, expected_version)

    assert applied is False
    entry = await manager.get_question_entry("7")
    assert entry["status"] == "OPEN"
    assert entry["source"] == "manual"
    assert entry["version"] == 1


async def test_refresh_restores_server_state(manager):
    """AC-2: page refresh mid-meeting restores exact same state.

    get_questions returns the server-authoritative state including
    GREEN status, score, and evidence.
    """
    await manager.set_questions(
        [
            {"id": 1, "text": "Company name?", "target_field": "name"},
            {"id": 2, "text": "Founding year?", "target_field": "founded_year"},
        ]
    )

    evidence = [{"recording_id": "r-1", "t_start": 10.0, "t_end": 12.0}]
    await manager.apply_green_signal("1", 0.9, evidence, 0)

    # Simulate page refresh: new manager instance, same session
    manager2 = LiveSessionManager(
        redis=manager.redis,
        tenant_id=manager.tenant_id,
        session_id=manager.session_id,
    )
    questions = await manager2.get_questions()
    by_id = {q["id"]: q for q in questions}

    assert by_id["1"]["status"] == "GREEN"
    assert by_id["1"]["score"] == 0.9
    assert by_id["2"]["status"] == "OPEN"


async def test_score_below_threshold_stores_missing_aspects(manager):
    """Sub-threshold score stores data for G-04."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )

    await manager.update_sufficiency("1", 0.45, ["name not mentioned"])

    entry = await manager.get_question_entry("1")
    assert entry["score"] == 0.45
    assert entry["missing_aspects"] == ["name not mentioned"]
    assert entry["status"] == "OPEN"  # Not promoted to GREEN


async def test_green_signal_requires_evidence():
    """OG-06: GreenSignal model rejects empty evidence at construction time."""
    from pydantic import ValidationError
    from app.api.schemas import GreenSignal

    with pytest.raises(ValidationError, match="OG-06"):
        GreenSignal(seq=1, question_id="q-1", score=0.9, evidence=[])


async def test_green_signal_roundtrip_redis(manager):
    """apply_green_signal writes + get_questions reads GREEN status."""
    await manager.set_questions(
        [{"id": 42, "text": "Brand values?", "target_field": "values"}]
    )
    evidence = [{"recording_id": "r-2", "t_start": 20.0, "t_end": 25.0}]
    await manager.apply_green_signal("42", 0.78, evidence, 0)

    questions = await manager.get_questions()
    q = [q for q in questions if q["id"] == "42"][0]
    assert q["status"] == "GREEN"
    assert q["score"] == 0.78
    assert q["evidence"][0]["recording_id"] == "r-2"


async def test_concurrent_mark_and_signal(manager):
    """Lua atomicity: concurrent mark_question and apply_green_signal.

    Only one should win; the state must be consistent.
    """
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )

    evidence = [{"recording_id": "r-1", "t_start": 1.0, "t_end": 2.0}]

    # Run both concurrently — one will win, one will lose
    await asyncio.gather(
        manager.mark_question("1", "manual_green"),
        manager.apply_green_signal("1", 0.85, evidence, 0),
    )

    entry = await manager.get_question_entry("1")
    # Whichever won, the entry must be consistent
    assert entry["version"] >= 1
    if entry["source"] == "manual":
        assert entry["status"] == "GREEN"
    elif entry["source"] == "analysis":
        assert entry["status"] == "GREEN"
        assert entry["score"] == 0.85
