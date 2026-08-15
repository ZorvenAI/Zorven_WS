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
from app.logic.live_session import BUFFER_FRAMES, LiveSessionManager

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
