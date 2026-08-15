"""F-04 AC-4 · seq is strictly increasing, whatever the traffic looks like.

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
    Coverage,
    ErrorFrame,
    Followups,
    GreenSignal,
    NotableFact,
    TranscriptFinal,
    TranscriptPartial,
)
from app.logic.live_session import LiveSessionManager

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
        return GreenSignal(seq=seq, question_id="q-7", score=0.86, evidence=[])
    if kind == "followups":
        return Followups(seq=seq, question_id="q-9", suggestions=["Which origin?"])
    if kind == "fact":
        return NotableFact(seq=seq, text="A second location.", workflow_target="WF3")
    if kind == "coverage":
        return Coverage(seq=seq, map={"WF1": 0.7, "WF2": 0.4, "WF3": 0.3})
    return ErrorFrame(seq=seq, code="ERR-07", message="degraded", recoverable=True)


KINDS = ["partial", "final", "green", "followups", "fact", "coverage", "error"]


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
