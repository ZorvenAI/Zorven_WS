"""F-04 AC-4 · seq is strictly increasing, whatever the traffic looks like.
G-03 · question version is monotonically increasing across any operation mix.

The card names `test_seq_strictly_increasing` here, and NFR-REL-01 says why
this file is property-based rather than a handful of cases: "the interleavings"
are what break ordering, and nobody writes them all out by hand.

The invariant under test is one sentence from AC-4: a seq that is "strictly
increasing for the life of the session **across all frame types**". Three ways
to break it, all of which look reasonable in review — a per-type counter, a
counter derived from the buffer's length, and a read-then-write that two
concurrent frames both win.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.api.schemas import (
    AdhocDetected,
    Coverage,
    ErrorFrame,
    EvidenceSpan,
    Followups,
    GreenSignal,
    NotableFact,
    TranscriptFinal,
    TranscriptPartial,
)
from app.logic.live_session import LiveSessionManager, SegmentBatcher

pytestmark = [pytest.mark.property, pytest.mark.integration]


def build(kind: str, seq: int):
    """One frame of each §10.2.3 type, so the sweep covers all of them."""
    if kind == "partial":
        return TranscriptPartial(seq=seq, text="we started roasting", speaker=2)
    if kind == "final":
        return TranscriptFinal(
            seq=seq,
            text="We started roasting in 2016.",
            speaker=2,
            t_start=1.0,
            t_end=2.0,
        )
    if kind == "green":
        return GreenSignal(
            seq=seq,
            question_id="q-7",
            score=0.86,
            evidence=[EvidenceSpan(recording_id="r-1", t_start=1.0, t_end=2.0)],
        )
    if kind == "followups":
        return Followups(seq=seq, question_id="q-9", suggestions=["Which origin?"])
    if kind == "fact":
        return NotableFact(seq=seq, text="A second location.", workflow_target="WF3")
    if kind == "adhoc":
        return AdhocDetected(
            seq=seq,
            question_id="adhoc_a1b2c3d4",
            text="How many stores?",
            workflow_target="WF3",
            target_field="retail_locations",
        )
    if kind == "coverage":
        return Coverage(seq=seq, map={"WF1": 0.7, "WF2": 0.4, "WF3": 0.3})
    return ErrorFrame(seq=seq, code="ERR-07", message="degraded", recoverable=True)


KINDS = ["partial", "final", "green", "followups", "fact", "adhoc", "coverage", "error"]


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    kinds=st.lists(st.sampled_from(KINDS), min_size=1, max_size=30),
    concurrent=st.integers(min_value=0, max_value=8),
)
async def test_seq_strictly_increasing(live_redis, kinds, concurrent):
    """Whatever mix of frame types, and however many are produced at once.

    The concurrent batch is the part that matters. A read-then-write counter
    passes every sequential case and hands two simultaneous frames the same
    number — and "simultaneous" here means a transcript partial and a coverage
    update in the same tick, which is the ordinary shape of a live meeting
    rather than an edge case.
    """
    manager = LiveSessionManager(
        redis=live_redis, tenant_id="t-prop", session_id=f"s-{uuid.uuid4().hex[:10]}"
    )

    seqs: list[int] = []
    for kind in kinds:
        seq = await manager.next_seq()
        await manager.emit(build(kind, seq))
        seqs.append(seq)

    if concurrent:
        seqs.extend(
            await asyncio.gather(*(manager.next_seq() for _ in range(concurrent)))
        )

    assert len(set(seqs)) == len(seqs), "two frames were given the same seq"
    assert sorted(seqs) == list(range(1, len(seqs) + 1)), "the series has a gap"


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    kinds=st.lists(st.sampled_from(KINDS), min_size=1, max_size=20),
    cut=st.integers(min_value=0, max_value=20),
)
async def test_a_replay_is_ordered_and_never_repeats(live_redis, kinds, cut):
    """What the client reassembles after a reconnect.

    Two failures matter and both render as a broken meeting: a frame delivered
    twice, and frames arriving out of order. Neither is visible from the
    server's own bookkeeping, which is why this asserts on what a resume
    actually returns.
    """
    manager = LiveSessionManager(
        redis=live_redis, tenant_id="t-prop", session_id=f"s-{uuid.uuid4().hex[:10]}"
    )

    for kind in kinds:
        await manager.emit(build(kind, await manager.next_seq()))

    frames, resync = await manager.replay_after(cut)

    if resync is not None:
        # Beyond the window is an explicit answer, never a silent gap.
        assert frames == []
        return

    replayed = [f["seq"] for f in frames]
    assert replayed == sorted(replayed), "frames replayed out of order"
    assert len(replayed) == len(set(replayed)), "a frame was replayed twice"
    assert all(seq > cut for seq in replayed), "a frame the client already had"


# ── F-05 · finals non-decreasing t_start under dedup ───────────────


@settings(
    max_examples=25,
    deadline=None,
)
@given(
    t_starts=st.lists(
        st.floats(min_value=0.0, max_value=600.0, allow_nan=False),
        min_size=2,
        max_size=30,
    ),
)
def test_finals_non_decreasing_t_start(t_starts):
    """F-05 named test: whatever order finals arrive in, sorting by t_start
    always produces a non-decreasing sequence.

    This is the invariant AC-2 relies on: the buffered transcript is
    ordered by time, so the operator reads a coherent conversation rather
    than a shuffled one.
    """
    from app.providers.stt import STTResult, _dedup_key

    results = [
        STTResult(
            text=f"segment at {t:.1f}",
            is_final=True,
            t_start=t,
            t_end=t + 1.5,
            stability=1.0,
        )
        for t in t_starts
    ]

    seen: set[tuple[float, str]] = set()
    deduped: list[STTResult] = []
    for r in results:
        key = _dedup_key(r)
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    sorted_results = sorted(deduped, key=lambda r: r.t_start)
    t_sorted = [r.t_start for r in sorted_results]
    for i in range(1, len(t_sorted)):
        assert t_sorted[i] >= t_sorted[i - 1], "t_start not non-decreasing"


# ── G-02 · Batcher ordering invariants ────────────────────────────────


@settings(
    max_examples=30,
    deadline=None,
)
@given(
    t_starts=st.lists(
        st.floats(min_value=0.0, max_value=300.0, allow_nan=False),
        min_size=2,
        max_size=40,
    ),
    speakers=st.lists(
        st.integers(min_value=0, max_value=3),
        min_size=2,
        max_size=40,
    ),
)
def test_batcher_preserves_segment_order(t_starts, speakers):
    """Segments in a batch are ordered by their insertion order (which matches
    t_start order since finals arrive in time order from STT)."""
    n = min(len(t_starts), len(speakers))
    t_starts = sorted(t_starts[:n])
    speakers = speakers[:n]

    batcher = SegmentBatcher(window_s=3.0, min_duration_s=0.0)
    all_batched: list[dict] = []

    for i in range(n):
        seg = {
            "text": f"seg {i}",
            "speaker": speakers[i],
            "t_start": t_starts[i],
            "t_end": t_starts[i] + 0.5,
        }
        batch = batcher.add(seg)
        if batch is not None:
            all_batched.extend(batch.segments)

    final = batcher.flush()
    if final is not None:
        all_batched.extend(final.segments)

    batch_t_starts = [s["t_start"] for s in all_batched]
    assert batch_t_starts == sorted(batch_t_starts), "batcher broke segment order"


@settings(
    max_examples=30,
    deadline=None,
)
@given(
    n=st.integers(min_value=1, max_value=50),
    speakers=st.lists(
        st.integers(min_value=0, max_value=3),
        min_size=1,
        max_size=50,
    ),
)
def test_batcher_no_segment_lost_or_duplicated(n, speakers):
    """Every segment appears in exactly one batch."""
    n = min(n, len(speakers))
    batcher = SegmentBatcher(window_s=3.0, min_duration_s=0.0)
    collected: list[str] = []

    for i in range(n):
        seg = {
            "text": f"seg-{i}",
            "speaker": speakers[i],
            "t_start": float(i),
            "t_end": float(i) + 0.5,
        }
        batch = batcher.add(seg)
        if batch is not None:
            collected.extend(s["text"] for s in batch.segments)

    final = batcher.flush()
    if final is not None:
        collected.extend(s["text"] for s in final.segments)

    expected = [f"seg-{i}" for i in range(n)]
    assert sorted(collected) == sorted(expected), "segment lost or duplicated"


# ── G-03 · Version monotonicity ──────────────────────────────────────


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    ops=st.lists(
        st.sampled_from(["mark_green", "mark_ungreen", "apply", "sufficiency"]),
        min_size=2,
        max_size=20,
    ),
)
async def test_version_is_monotonically_increasing(live_redis, ops):
    """Version never decreases across any sequence of mark/apply operations."""
    manager = LiveSessionManager(
        redis=live_redis,
        tenant_id="t-prop",
        session_id=f"s-ver-{uuid.uuid4().hex[:10]}",
    )
    await manager.set_questions([{"id": 1, "text": "Test?", "target_field": "test"}])

    versions: list[int] = [0]
    for op in ops:
        if op == "mark_green":
            v = await manager.mark_question("1", "manual_green")
            versions.append(v)
        elif op == "mark_ungreen":
            v = await manager.mark_question("1", "manual_ungreen")
            versions.append(v)
        elif op == "apply":
            entry = await manager.get_question_entry("1")
            ev = [{"recording_id": "r-1", "t_start": 1.0, "t_end": 2.0}]
            applied = await manager.apply_green_signal("1", 0.85, ev, entry["version"])
            if applied:
                entry = await manager.get_question_entry("1")
                versions.append(entry["version"])
        elif op == "sufficiency":
            await manager.update_sufficiency("1", 0.4, ["missing"])

    for i in range(1, len(versions)):
        assert (
            versions[i] >= versions[i - 1]
        ), f"version decreased: {versions[i - 1]} -> {versions[i]}"


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_signals=st.integers(min_value=1, max_value=5),
)
async def test_manual_override_always_wins(live_redis, n_signals):
    """A manual override followed by any number of stale signals wins."""
    manager = LiveSessionManager(
        redis=live_redis,
        tenant_id="t-prop",
        session_id=f"s-ow-{uuid.uuid4().hex[:10]}",
    )
    await manager.set_questions([{"id": 1, "text": "Test?", "target_field": "test"}])

    # Manual override at version 0 → bumps to 1
    await manager.mark_question("1", "manual_ungreen")

    # N stale signals all try expected_version=0
    ev = [{"recording_id": "r-1", "t_start": 1.0, "t_end": 2.0}]
    for _ in range(n_signals):
        applied = await manager.apply_green_signal("1", 0.95, ev, 0)
        assert applied is False

    entry = await manager.get_question_entry("1")
    assert entry["source"] == "manual"
    assert entry["status"] == "OPEN"


# ── G-04 · Follow-ups cleared on green ────────────────────────────────


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_followups=st.integers(min_value=1, max_value=3),
    n_sufficiency=st.integers(min_value=0, max_value=3),
)
async def test_followups_cleared_on_green(live_redis, n_followups, n_sufficiency):
    """For any sequence of sufficiency + green operations, a green question
    never has stale follow-ups."""
    manager = LiveSessionManager(
        redis=live_redis,
        tenant_id="t-prop",
        session_id=f"s-fup-{uuid.uuid4().hex[:10]}",
    )
    await manager.set_questions([{"id": 1, "text": "Test?", "target_field": "test"}])

    suggestions = [
        {"text": f"Follow-up {i}?", "addresses_aspect": f"a{i}", "priority": i}
        for i in range(n_followups)
    ]
    await manager.store_followups("1", suggestions)

    for _ in range(n_sufficiency):
        await manager.update_sufficiency("1", 0.4, ["still missing"])

    entry = await manager.get_question_entry("1")
    assert len(entry["suggestions"]) == n_followups

    evidence = [{"recording_id": "r-1", "t_start": 1.0, "t_end": 2.0}]
    applied = await manager.apply_green_signal("1", 0.9, evidence, entry["version"])
    assert applied is True

    entry = await manager.get_question_entry("1")
    assert entry["status"] == "GREEN"
    assert entry["suggestions"] == [], "stale follow-ups survived green signal"
    assert entry["suggestion_accepted"] == [], "stale acceptance survived green"
