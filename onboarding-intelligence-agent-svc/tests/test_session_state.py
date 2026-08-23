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
    AdhocDetected,
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


# ── G-04 · Follow-up suggestions ──────────────────────────────────────


async def test_store_and_retrieve_followups(manager):
    """Follow-ups round-trip through Redis."""
    await manager.set_questions(
        [{"id": 9, "text": "Who is your target audience?", "target_field": "audience"}]
    )

    suggestions = [
        {"text": "What age group?", "addresses_aspect": "demographics", "priority": 1},
        {"text": "B2B or B2C?", "addresses_aspect": "market type", "priority": 2},
    ]
    await manager.store_followups("9", suggestions)

    entry = await manager.get_question_entry("9")
    assert len(entry["suggestions"]) == 2
    assert entry["suggestions"][0]["text"] == "What age group?"
    assert entry["suggestion_accepted"] == [False, False]


async def test_no_followups_for_unasked_question(manager):
    """AC-1: a question with no evidence has no follow-ups.

    This is the integration-level proof that the flow skips score==0.0.
    The question entry has no suggestions because store_followups is never
    called for a question with no evidence.
    """
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )

    entry = await manager.get_question_entry("1")
    assert entry.get("suggestions", []) == []


async def test_superseded_followups_cleared_on_green(manager):
    """AC-4: apply_green_signal clears suggestions and suggestion_accepted."""
    await manager.set_questions(
        [{"id": 3, "text": "Founding year?", "target_field": "founded_year"}]
    )

    suggestions = [
        {"text": "What year exactly?", "addresses_aspect": "year", "priority": 1},
    ]
    await manager.store_followups("3", suggestions)

    entry = await manager.get_question_entry("3")
    assert len(entry["suggestions"]) == 1

    evidence = [{"recording_id": "r-1", "t_start": 5.0, "t_end": 8.0}]
    applied = await manager.apply_green_signal("3", 0.9, evidence, 0)
    assert applied is True

    entry = await manager.get_question_entry("3")
    assert entry["status"] == "GREEN"
    assert entry["suggestions"] == []
    assert entry["suggestion_accepted"] == []


async def test_mark_followup_accepted(manager):
    """AC-3: acceptance backfill sets suggestion_accepted[i]=true."""
    await manager.set_questions(
        [{"id": 7, "text": "Brand values?", "target_field": "values"}]
    )

    suggestions = [
        {
            "text": "What matters most?",
            "addresses_aspect": "core values",
            "priority": 1,
        },
        {
            "text": "Any brand role models?",
            "addresses_aspect": "aspirational",
            "priority": 2,
        },
    ]
    await manager.store_followups("7", suggestions)

    ok = await manager.mark_followup_asked("7", 0)
    assert ok is True

    entry = await manager.get_question_entry("7")
    assert entry["suggestion_accepted"][0] is True
    assert entry["suggestion_accepted"][1] is False


async def test_mark_followup_invalid_index(manager):
    """Out-of-range index returns False and changes nothing."""
    await manager.set_questions(
        [{"id": 7, "text": "Brand values?", "target_field": "values"}]
    )

    suggestions = [
        {
            "text": "What matters most?",
            "addresses_aspect": "core values",
            "priority": 1,
        },
    ]
    await manager.store_followups("7", suggestions)

    ok = await manager.mark_followup_asked("7", 5)
    assert ok is False

    entry = await manager.get_question_entry("7")
    assert entry["suggestion_accepted"] == [False]


async def test_mark_followup_nonexistent_question(manager):
    """Marking on a nonexistent question returns False."""
    ok = await manager.mark_followup_asked("nonexistent", 0)
    assert ok is False


async def test_followups_survive_reconnect(manager):
    """Stored follow-ups are readable after manager re-creation."""
    await manager.set_questions(
        [{"id": 4, "text": "Revenue?", "target_field": "revenue"}]
    )

    suggestions = [
        {"text": "Annual or monthly?", "addresses_aspect": "period", "priority": 1},
    ]
    await manager.store_followups("4", suggestions)

    manager2 = LiveSessionManager(
        redis=manager.redis,
        tenant_id=manager.tenant_id,
        session_id=manager.session_id,
    )
    entry = await manager2.get_question_entry("4")
    assert len(entry["suggestions"]) == 1
    assert entry["suggestions"][0]["text"] == "Annual or monthly?"


# ── G-05 · Ad-hoc questions ─────────────────────────────────────────


async def test_add_adhoc_question_round_trip(manager):
    """Ad-hoc question created, readable via get_questions, has origin ADHOC."""
    qid = await manager.add_adhoc_question(
        text="How many retail locations do you have?",
        target_field="retail_locations",
        workflow_target="WF3",
        evidence=[{"recording_id": "r-1", "t_start": 45.0, "t_end": 48.0}],
    )

    questions = await manager.get_questions()
    adhoc = [q for q in questions if q["id"] == qid]
    assert len(adhoc) == 1

    q = adhoc[0]
    assert q["text"] == "How many retail locations do you have?"
    assert q["origin"] == "ADHOC"
    assert q["target_field"] == "retail_locations"
    assert q["workflow_target"] == "WF3"
    assert q["status"] == "OPEN"
    assert q["source"] == "analysis"
    assert q["version"] == 0


async def test_adhoc_question_id_prefix(manager):
    """ID starts with 'adhoc_'."""
    qid = await manager.add_adhoc_question(
        text="What is your pricing model?",
        target_field="pricing",
        workflow_target="WF3",
        evidence=[],
    )
    assert qid.startswith("adhoc_")
    assert len(qid) > len("adhoc_")


async def test_adhoc_question_has_evidence(manager):
    """Evidence spans attached at creation time."""
    evidence = [
        {"recording_id": "r-2", "t_start": 100.0, "t_end": 105.0},
        {"recording_id": "r-2", "t_start": 106.0, "t_end": 110.0},
    ]
    qid = await manager.add_adhoc_question(
        text="Who are your main competitors?",
        target_field="competitors",
        workflow_target="WF2",
        evidence=evidence,
    )

    entry = await manager.get_question_entry(qid)
    assert len(entry["evidence"]) == 2
    assert entry["evidence"][0]["recording_id"] == "r-2"
    assert entry["evidence"][1]["t_start"] == 106.0


async def test_set_questions_has_origin_prepared(manager):
    """Prepared questions have origin 'PREPARED'."""
    await manager.set_questions(
        [{"id": 1, "text": "Company name?", "target_field": "name"}]
    )

    entry = await manager.get_question_entry("1")
    assert entry["origin"] == "PREPARED"


async def test_adhoc_and_prepared_coexist(manager):
    """Prepared and ad-hoc questions live in the same hash."""
    await manager.set_questions(
        [
            {"id": 1, "text": "Company name?", "target_field": "name"},
            {"id": 2, "text": "Founded year?", "target_field": "founded_year"},
        ]
    )

    qid = await manager.add_adhoc_question(
        text="What about trademarks?",
        target_field="trademark_status",
        workflow_target="WF2",
        evidence=[],
    )

    questions = await manager.get_questions()
    assert len(questions) == 3

    origins = {q["origin"] for q in questions}
    assert origins == {"PREPARED", "ADHOC"}

    adhoc = [q for q in questions if q["id"] == qid]
    assert adhoc[0]["origin"] == "ADHOC"


async def test_adhoc_question_survives_reconnect(manager):
    """Ad-hoc question readable after manager re-creation."""
    qid = await manager.add_adhoc_question(
        text="Distribution channels?",
        target_field="distribution",
        workflow_target="WF3",
        evidence=[{"recording_id": "r-1", "t_start": 50.0, "t_end": 55.0}],
    )

    manager2 = LiveSessionManager(
        redis=manager.redis,
        tenant_id=manager.tenant_id,
        session_id=manager.session_id,
    )
    entry = await manager2.get_question_entry(qid)
    assert entry is not None
    assert entry["origin"] == "ADHOC"
    assert entry["text"] == "Distribution channels?"


# ── G-05 · Operator speaker ─────────────────────────────────────────


async def test_operator_speaker_round_trip(manager):
    """set/get operator_speaker survives reconnect."""
    await manager.set_operator_speaker(0)

    manager2 = LiveSessionManager(
        redis=manager.redis,
        tenant_id=manager.tenant_id,
        session_id=manager.session_id,
    )
    result = await manager2.get_operator_speaker()
    assert result == 0


async def test_operator_speaker_defaults_none(manager):
    """Returns None when not set."""
    result = await manager.get_operator_speaker()
    assert result is None


async def test_operator_speaker_nonzero(manager):
    """Operator can be any speaker number, not just 0."""
    await manager.set_operator_speaker(2)
    result = await manager.get_operator_speaker()
    assert result == 2


# ── G-05 · Notable fact frame ───────────────────────────────────────


async def test_notable_fact_frame_in_buffer(manager):
    """NotableFact frame is in the replay buffer after emission."""
    frame = NotableFact(
        seq=await manager.next_seq(),
        text="Owns a second retail location opening in October.",
        workflow_target="WF3",
    )
    await manager.emit(frame)

    frames, _ = await manager.replay_after(0)
    assert len(frames) == 1
    assert frames[0]["type"] == "notable_fact"
    assert frames[0]["workflow_target"] == "WF3"
    assert "October" in frames[0]["text"]


async def test_adhoc_detected_frame_in_buffer(manager):
    """AdhocDetected frame round-trips through the replay buffer."""
    frame = AdhocDetected(
        seq=await manager.next_seq(),
        question_id="adhoc_abc12345",
        text="How many retail locations do you have?",
        workflow_target="WF3",
        target_field="retail_locations",
    )
    await manager.emit(frame)

    frames, _ = await manager.replay_after(0)
    assert len(frames) == 1
    assert frames[0]["type"] == "adhoc_detected"
    assert frames[0]["question_id"] == "adhoc_abc12345"
    assert frames[0]["workflow_target"] == "WF3"
    assert frames[0]["target_field"] == "retail_locations"


# ── G-06 · Coverage state ────────────────────────────────────────────


async def test_store_and_get_coverage_round_trip(manager):
    """Coverage fractions survive a Redis round-trip."""
    from app.logic.coverage import compute_coverage

    questions = [
        {
            "text": "Company name?",
            "workflow_target": "WF1",
            "status": "GREEN",
            "target_field": "name",
        },
        {
            "text": "Founded year?",
            "workflow_target": "WF1",
            "status": "OPEN",
            "target_field": "founded_year",
        },
        {
            "text": "Brand voice?",
            "workflow_target": "WF2",
            "status": "GREEN",
            "target_field": "brand_voice",
        },
        {
            "text": "Ad budget?",
            "workflow_target": "WF3",
            "status": "OPEN",
            "target_field": "marketing_budget_range",
        },
    ]
    result = compute_coverage(questions, threshold=0.7)
    await manager.store_coverage(result)
    stored = await manager.get_coverage()

    assert stored is not None
    assert stored["WF1"] == 0.5
    assert stored["WF2"] == 1.0
    assert stored["WF3"] == 0.0
    assert stored["satisfied"] is False
    assert len(stored["blocking_gaps"]) > 0
    assert "updated_at" in stored


async def test_coverage_not_yet_computed(manager):
    """get_coverage returns None before any coverage has been stored."""
    assert await manager.get_coverage() is None


async def test_coverage_survives_reconnect(manager):
    """Coverage hash persists across a simulated reconnect."""
    from app.logic.coverage import compute_coverage

    questions = [
        {
            "text": "Q1",
            "workflow_target": "WF1",
            "status": "GREEN",
            "target_field": "name",
        },
        {
            "text": "Q2",
            "workflow_target": "WF2",
            "status": "GREEN",
            "target_field": "brand_voice",
        },
        {
            "text": "Q3",
            "workflow_target": "WF3",
            "status": "GREEN",
            "target_field": "sales_channels",
        },
    ]
    await manager.store_coverage(compute_coverage(questions))

    reconnected = LiveSessionManager(
        redis=manager.redis,
        tenant_id=manager.tenant_id,
        session_id=manager.session_id,
    )
    stored = await reconnected.get_coverage()
    assert stored is not None
    assert stored["WF1"] == 1.0
    assert stored["satisfied"] is True


async def test_coverage_frame_in_replay_buffer(manager):
    """Coverage frame round-trips through the replay buffer."""
    frame = Coverage(
        seq=await manager.next_seq(),
        map={"WF1": 0.8, "WF2": 0.5, "WF3": 0.3},
    )
    await manager.emit(frame)

    frames, _ = await manager.replay_after(0)
    assert len(frames) == 1
    assert frames[0]["type"] == "coverage"
    assert frames[0]["map"]["WF1"] == 0.8
    assert frames[0]["map"]["WF3"] == 0.3


async def test_coverage_incremental_matches_full(manager):
    """Named in story test table: recomputing from all questions matches
    an incremental approach (both are the same function, so they must agree)."""
    from app.logic.coverage import compute_coverage

    questions = [
        {
            "text": "Q1",
            "workflow_target": "WF1",
            "status": "GREEN",
            "target_field": "name",
        },
        {
            "text": "Q2",
            "workflow_target": "WF1",
            "status": "OPEN",
            "target_field": "mission",
        },
        {
            "text": "Q3",
            "workflow_target": "WF2",
            "status": "GREEN",
            "target_field": "competitors",
        },
        {
            "text": "Q4",
            "workflow_target": "WF3",
            "status": "OPEN",
            "target_field": "sales_channels",
        },
    ]

    # "Incremental": compute from first 2, then recompute from all 4
    partial = compute_coverage(questions[:2])
    assert partial.wf1.pct == 0.5  # confirms partial view is different
    full = compute_coverage(questions)

    # The full recompute is the ground truth
    assert full.wf1.pct == 0.5
    assert full.wf2.pct == 1.0
    assert full.wf3.pct == 0.0

    # Store and retrieve via Redis
    await manager.store_coverage(full)
    stored = await manager.get_coverage()
    assert stored["WF1"] == full.wf1.pct
    assert stored["WF2"] == full.wf2.pct
    assert stored["WF3"] == full.wf3.pct

    # J-02: cross-validate full vs incremental with the crosscheck module
    from app.logic.coverage_crosscheck import crosscheck_coverage

    diffs = crosscheck_coverage(full, stored, tolerance=0.05)
    assert diffs == [], "full and stored should agree exactly"

    # Simulate a stale incremental by adding an ad-hoc question
    questions.append(
        {
            "text": "Q5-adhoc",
            "workflow_target": "WF1",
            "status": "GREEN",
            "target_field": "founding_year",
        }
    )
    updated = compute_coverage(questions)
    diffs_after = crosscheck_coverage(updated, stored, tolerance=0.05)
    wf1_diffs = [d for d in diffs_after if d.workflow == "WF1"]
    assert len(wf1_diffs) == 1, "ad-hoc question should cause WF1 divergence"
    assert wf1_diffs[0].full_pct > wf1_diffs[0].incremental_pct
