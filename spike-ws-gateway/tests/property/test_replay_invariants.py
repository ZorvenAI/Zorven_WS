"""Property tests for the replay buffer and the seq series.

These are the invariants F-04 AC-3 and AC-4 depend on. Example-based tests
check the cases we thought of; these check the ones we did not.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from echo.frames import SeqAllocator
from echo.replay import ReplayBuffer

pytestmark = [pytest.mark.property]

capacities = st.integers(min_value=1, max_value=64)
frame_counts = st.integers(min_value=0, max_value=200)


def fill(buffer: ReplayBuffer, count: int, start: int = 0) -> list[dict]:
    frames = [{"seq": start + i, "type": "echo.ack"} for i in range(count)]
    for frame in frames:
        buffer.append(frame)
    return frames


@given(capacity=capacities, count=frame_counts)
def test_buffer_never_exceeds_capacity(capacity, count):
    buffer = ReplayBuffer(capacity)
    fill(buffer, count)
    assert len(buffer) <= capacity


@given(capacity=capacities, count=frame_counts, last_seq=st.integers(-1, 250))
def test_replay_returns_exactly_the_suffix(capacity, count, last_seq):
    """Replay is every retained frame after last_seq — no gaps, no dupes."""
    buffer = ReplayBuffer(capacity)
    fill(buffer, count)
    result = buffer.resume(last_seq)

    if result.resync_required:
        return

    seqs = [f["seq"] for f in result.frames]
    assert seqs == sorted(set(seqs)), "replay contains dupes or is unordered"
    assert all(s > last_seq for s in seqs), "replay includes already-seen frames"
    if len(seqs) > 1:
        assert seqs == list(
            range(seqs[0], seqs[0] + len(seqs))
        ), "replay has a gap in the seq series"


@given(capacity=capacities, count=st.integers(min_value=1, max_value=200))
def test_caught_up_client_gets_empty_replay_not_resync(capacity, count):
    """Being fully caught up is success, not a resync."""
    buffer = ReplayBuffer(capacity)
    frames = fill(buffer, count)
    result = buffer.resume(frames[-1]["seq"])
    assert result.frames == []
    assert result.resync_required is False


@given(capacity=capacities, count=st.integers(min_value=1, max_value=200))
def test_resume_from_before_the_window_demands_resync(capacity, count):
    """An out-of-window resume is answered explicitly, never with a gap."""
    buffer = ReplayBuffer(capacity)
    fill(buffer, count, start=100)
    assume(count > capacity)  # only then has anything been trimmed
    result = buffer.resume(50)
    assert result.resync_required is True
    assert result.oldest_available_seq is not None


@given(count=st.integers(min_value=1, max_value=300))
def test_seq_strictly_increasing(count):
    alloc = SeqAllocator()
    seqs = [alloc.next() for _ in range(count)]
    assert all(b == a + 1 for a, b in zip(seqs, seqs[1:]))


@given(
    capacity=capacities,
    counts=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=10),
)
@settings(max_examples=50)
def test_seq_never_repeats_across_interleaved_reconnects(capacity, counts):
    """Frames minted across many reconnects still form one strict series."""
    buffer = ReplayBuffer(capacity)
    alloc = SeqAllocator()
    minted = []
    for burst in counts:
        for _ in range(burst):
            seq = alloc.next()
            minted.append(seq)
            buffer.append({"seq": seq, "type": "echo.ack"})
        buffer.resume(alloc.last)  # a reconnect between bursts
    assert minted == sorted(set(minted))


@given(capacity=capacities)
def test_out_of_order_append_is_rejected(capacity):
    buffer = ReplayBuffer(capacity)
    buffer.append({"seq": 10})
    with pytest.raises(ValueError):
        buffer.append({"seq": 10})
    with pytest.raises(ValueError):
        buffer.append({"seq": 9})


def test_zero_capacity_is_rejected():
    with pytest.raises(ValueError):
        ReplayBuffer(0)
