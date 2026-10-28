"""A shielded teardown write reports its real outcome, not its abandonment.

#679 and #681 logged an ERROR at the moment the `await` gave up. Measuring
that (#680) showed the cancellation arrives in under a millisecond while the
shielded write completes 1-4 ms later, every time -- 22 abandoned awaits, 22
completed writes, slowest 22 ms, across a four-file suite run. So both ERROR
lines fired on every dropped socket, each claiming operator-visible harm that
had not happened.

These tests pin both directions: silence when the write lands, and an ERROR
naming the consequence when it genuinely does not.
"""

from __future__ import annotations

import asyncio

import pytest
from structlog.testing import capture_logs

from app.api.ws import (
    _await_shielded_teardown_write,
    _report_only_if_the_write_was_lost,
)

pytestmark = [pytest.mark.unit]


#: The detail string the production call site passes, so the assertions below
#: check the message an operator would actually read.
DETAIL = (
    "the live lock was not released; the company waits up to the lock TTL "
    "before it can start again"
)


def _callback():
    return _report_only_if_the_write_was_lost("lock_release", "sess-under-test", DETAIL)


def _errors(logs) -> list[dict]:
    return [e for e in logs if e.get("log_level") == "error"]


async def test_a_write_that_lands_after_the_wait_is_abandoned_says_nothing():
    """The false alarm this exists to prevent.

    Two things made an earlier version of this test prove nothing, and both
    are worth naming because each looked fine:

    1. structlog does not route through `caplog`, so it asserted on an
       always-empty list. `capture_logs` is the harness that sees these, and
       the two failure tests below are its control -- they capture an ERROR
       through the same mechanism, so silence here is silence rather than a
       blind probe.
    2. the write completed on the first loop pass, so `wait_for` returned
       normally and the abandoned-wait branch was never entered at all
       (`except entered: False, task done: True`). Re-adding the old
       `if not task.done(): logger.error(...)` would have left it green,
       because `done()` was already True.

    The write now lands *after* the deadline, which is both the branch under
    test and the ordering measured in production: the wait is abandoned in
    under a millisecond, the write completes a few milliseconds later.
    """
    landed = asyncio.Event()

    async def succeeds_after_the_deadline() -> str:
        await asyncio.sleep(0.05)
        landed.set()
        return "written"

    with capture_logs() as logs:
        task = asyncio.ensure_future(succeeds_after_the_deadline())
        task.add_done_callback(_callback())

        abandoned = False
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=0.001)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            abandoned = True

        await task
        await asyncio.sleep(0)

    # Positive assertions first: without these, a run where the scenario did
    # not happen would pass on an empty error list.
    assert abandoned, "the wait was not abandoned, so the branch is untested"
    assert landed.is_set() and task.result() == "written"
    assert _errors(logs) == [], f"a landed write was reported as lost: {logs}"


async def test_a_write_that_fails_is_reported_with_its_consequence():
    """The signal that has to survive: a write that genuinely did not land."""

    async def raises() -> None:
        raise RuntimeError("redis is gone")

    with capture_logs() as logs:
        task = asyncio.ensure_future(raises())
        task.add_done_callback(_callback())
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)

    errors = _errors(logs)
    assert len(errors) == 1, errors
    assert errors[0]["event"] == "live_lock_release_lost"
    assert "RuntimeError" in errors[0]["error"]
    # The consequence, not just the failure: this is what an operator acts on.
    assert errors[0]["detail"] == DETAIL
    assert "lock TTL" in errors[0]["detail"]


async def test_a_cancelled_write_is_reported():
    """Cancellation of the write itself is real loss, unlike cancellation of
    the wait -- the distinction the old code could not draw."""

    async def never() -> None:
        await asyncio.sleep(3600)

    with capture_logs() as logs:
        task = asyncio.ensure_future(never())
        task.add_done_callback(_callback())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    errors = _errors(logs)
    assert errors, "a cancelled write went unreported"
    assert errors[0]["event"] == "live_lock_release_lost"


async def test_a_redis_failure_does_not_escape_the_teardown():
    """#685 review, high: the guard used to be too narrow to hold.

    `except (CancelledError, TimeoutError)` does not catch a Redis error --
    on the installed redis 5.2.1 both `ConnectionError` and `TimeoutError`
    descend from `RedisError`, not from `asyncio.TimeoutError`. Since
    `LiveLock.release` calls `client.eval` against a client with a 2 s
    socket timeout, a slow or down Redis during teardown raised through
    `shield`, out of `wait_for`, and out of the `finally` -- skipping the
    STT drain and re-opening the leaked `_stt_loop` and live, billed STT
    stream that #679 closed.

    The caller must therefore survive this, and the loss must still be
    reported.
    """
    from redis.exceptions import ConnectionError as RedisConnectionError

    assert not issubclass(RedisConnectionError, asyncio.TimeoutError), (
        "this test's premise is gone: a Redis error is now an asyncio "
        "timeout, so the narrow guard would have been sufficient"
    )

    async def redis_is_down() -> None:
        raise RedisConnectionError("Error 61 connecting to localhost:6379")

    reached_the_rest_of_teardown = False
    with capture_logs() as logs:
        await _await_shielded_teardown_write(
            asyncio.ensure_future(redis_is_down()),
            what="lock_release",
            session_id="sess-under-test",
            detail=DETAIL,
        )
        reached_the_rest_of_teardown = True
        await asyncio.sleep(0)

    assert reached_the_rest_of_teardown, "the Redis error escaped the teardown"
    errors = _errors(logs)
    assert errors, "the failed write went unreported"
    assert errors[0]["event"] == "live_lock_release_lost"
    assert "ConnectionError" in errors[0]["error"]


async def test_exceeding_the_budget_is_visible():
    """A write slower than its budget must not be silent.

    The abandonment path is deliberately quiet because it fires on every
    client-initiated close. A *budget* overrun is different: it has never
    been observed in practice, and it is the one case where a hard kill
    would stop the done-callback from ever reporting the loss.
    """

    async def slower_than_the_budget() -> None:
        await asyncio.sleep(0.2)

    task = asyncio.ensure_future(slower_than_the_budget())
    with capture_logs() as logs:
        await _await_shielded_teardown_write(
            task,
            what="lock_release",
            session_id="sess-under-test",
            detail=DETAIL,
            budget_s=0.01,
        )

    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert warnings, f"a budget overrun was silent: {logs}"
    assert warnings[0]["event"] == "live_lock_release_slow"
    assert _errors(logs) == [], "an overrun is not yet a loss"
    await task
