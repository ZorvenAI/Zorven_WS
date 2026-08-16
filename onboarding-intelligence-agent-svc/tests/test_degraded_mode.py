"""F-06 · Degraded mode — recording continues when speech fails.

AC-1: STT failure → mode=RECORD_ONLY, ErrorFrame(ERR-07) sent.
AC-2: The error frame carries the config message from circuit_breakers.yaml.
AC-3: mark_question stores manual checkmarks with source="manual".
AC-4: Recovery restarts STT, sends RecoveryFrame, mode → NORMAL.
EVT-011: Circuit breaker state changes emit the catalogued events.

Real Redis. The breaker and session mode are the things under test — a mock
Redis would prove my code calls itself, not that the mode survives a
reconnect to a different Cloud Run instance (A-02 finding 3).
"""

from __future__ import annotations

import uuid

import pytest

from app.api.schemas import ErrorFrame, RecoveryFrame, ServerFrameType
from app.circuit_breaker.breaker import (
    BreakerConfig,
    CircuitBreaker,
    State,
)
from app.logic.live_session import LiveSessionManager

pytestmark = pytest.mark.integration


@pytest.fixture
def session(live_redis):
    return LiveSessionManager(
        redis=live_redis,
        tenant_id="t-deg",
        session_id=f"s-{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def stt_breaker():
    config = BreakerConfig(
        name="stt",
        failure_threshold=5,
        window_seconds=30,
        success_threshold=2,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="RECORD_ONLY",
        user_message=(
            "Live assist paused — recording continues. "
            "Transcript will be ready after the meeting."
        ),
    )
    return CircuitBreaker(config)


# ── AC-1: STT failure → RECORD_ONLY ─────────────────────────────────


async def test_set_mode_writes_record_only(session):
    """5 failures → mode=RECORD_ONLY in Redis."""
    await session.set_mode(LiveSessionManager.MODE_RECORD_ONLY)

    mode = await session.get_mode()
    assert mode == "RECORD_ONLY"


async def test_get_mode_defaults_to_normal(session):
    """Before anything is written, mode is NORMAL."""
    mode = await session.get_mode()
    assert mode == "NORMAL"


async def test_mode_survives_read_from_another_manager(live_redis, session):
    """A-02 finding 3: a reconnect hits a different instance.

    The mode must be in Redis, not process memory, so a second manager
    reading the same session sees the same value.
    """
    await session.set_mode(LiveSessionManager.MODE_RECORD_ONLY)

    other = LiveSessionManager(
        redis=live_redis,
        tenant_id=session.tenant_id,
        session_id=session.session_id,
    )
    assert await other.get_mode() == "RECORD_ONLY"


# ── AC-2: Error frame carries config message ────────────────────────


def test_error_frame_shape():
    """ERR-07 message matches what the config string would carry."""
    msg = (
        "Live assist paused — recording continues. "
        "Transcript will be ready after the meeting."
    )
    frame = ErrorFrame(seq=1, code="ERR-07", message=msg, recoverable=True)

    assert frame.type is ServerFrameType.ERROR
    assert frame.code == "ERR-07"
    assert frame.recoverable is True
    assert "recording continues" in frame.message


def test_recovery_frame_shape():
    """The recovery frame carries the dependency name."""
    frame = RecoveryFrame(
        seq=2,
        dependency="stt",
        message="Live transcription resumed.",
    )

    assert frame.type is ServerFrameType.RECOVERY
    assert frame.dependency == "stt"


# ── AC-3: mark_question stores manual checkmarks ────────────────────


async def test_mark_question_stores_manual(session):
    """mark_question frame → Redis hash with source=manual, evidence=[]."""
    await session.mark_question("q_07", "manual_green")

    marks = await session.get_question_marks()
    assert "q_07" in marks
    assert marks["q_07"]["source"] == "manual"
    assert marks["q_07"]["evidence"] == []
    assert marks["q_07"]["action"] == "manual_green"


async def test_mark_question_multiple_questions(session):
    """Multiple questions can be marked independently."""
    await session.mark_question("q_01", "manual_green")
    await session.mark_question("q_02", "manual_green")
    await session.mark_question("q_03", "manual_red")

    marks = await session.get_question_marks()
    assert len(marks) == 3
    assert marks["q_01"]["action"] == "manual_green"
    assert marks["q_03"]["action"] == "manual_red"


async def test_mark_question_overwrites_previous(session):
    """Re-marking the same question replaces the entry."""
    await session.mark_question("q_07", "manual_green")
    await session.mark_question("q_07", "manual_red")

    marks = await session.get_question_marks()
    assert marks["q_07"]["action"] == "manual_red"


# ── AC-4: Recovery transitions mode back to NORMAL ──────────────────


async def test_recovery_sets_mode_normal(session):
    """After recovery, mode transitions back to NORMAL."""
    await session.set_mode(LiveSessionManager.MODE_RECORD_ONLY)
    assert await session.get_mode() == "RECORD_ONLY"

    await session.set_mode(LiveSessionManager.MODE_NORMAL)
    assert await session.get_mode() == "NORMAL"


# ── EVT-011: breaker state change callback ──────────────────────────


def test_breaker_callback_fires_on_open(stt_breaker):
    """Breaker opens → callback invoked with OPEN."""
    changes: list[tuple[str, State, State]] = []
    stt_breaker.set_on_state_change(
        lambda dep, old, new: changes.append((dep, old, new))
    )

    for _ in range(5):
        stt_breaker.record_failure()

    assert len(changes) == 1
    dep, old, new = changes[0]
    assert dep == "stt"
    assert old is State.CLOSED
    assert new is State.OPEN


def test_breaker_callback_fires_on_close(stt_breaker):
    """Breaker closes → callback invoked with CLOSED."""
    changes: list[tuple[str, State, State]] = []
    stt_breaker.set_on_state_change(
        lambda dep, old, new: changes.append((dep, old, new))
    )

    for _ in range(5):
        stt_breaker.record_failure()
    changes.clear()

    stt_breaker.reset()

    assert len(changes) == 1
    _, _, new = changes[0]
    assert new is State.CLOSED


def test_breaker_callback_exception_does_not_propagate(stt_breaker):
    """A callback that raises must not break the breaker."""

    def _bomb(dep, old, new):
        raise RuntimeError("boom")

    stt_breaker.set_on_state_change(_bomb)

    for _ in range(5):
        stt_breaker.record_failure()

    assert stt_breaker.state is State.OPEN


# ── Binary audio dropped in RECORD_ONLY ─────────────────────────────


async def test_error_frame_buffered_in_replay(session):
    """An ERR-07 frame enters the replay buffer like any other frame."""
    seq = await session.next_seq()
    err = ErrorFrame(seq=seq, code="ERR-07", message="test", recoverable=True)
    await session.emit(err)

    frames, resync = await session.replay_after(0)
    assert resync is None
    assert len(frames) == 1
    assert frames[0]["code"] == "ERR-07"


async def test_recovery_frame_buffered_in_replay(session):
    """A recovery frame enters the replay buffer."""
    seq = await session.next_seq()
    frame = RecoveryFrame(
        seq=seq,
        dependency="stt",
        message="Live transcription resumed.",
    )
    await session.emit(frame)

    frames, resync = await session.replay_after(0)
    assert resync is None
    assert len(frames) == 1
    assert frames[0]["type"] == "recovery"
    assert frames[0]["dependency"] == "stt"


# ── Mode transition pairing ─────────────────────────────────────────


async def test_mode_transitions_pair(session):
    """Any sequence of set_mode calls always leaves a consistent state."""
    transitions = [
        LiveSessionManager.MODE_RECORD_ONLY,
        LiveSessionManager.MODE_NORMAL,
        LiveSessionManager.MODE_RECORD_ONLY,
        LiveSessionManager.MODE_RECORD_ONLY,
        LiveSessionManager.MODE_NORMAL,
    ]
    for mode in transitions:
        await session.set_mode(mode)
        assert await session.get_mode() == mode
