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

from app.api.ws import _report_only_if_the_write_was_lost

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


async def test_a_write_that_lands_says_nothing():
    """The false alarm this exists to prevent.

    structlog does not route through `caplog`, so an earlier version of this
    test asserted on an always-empty list and passed while proving nothing.
    `capture_logs` is the harness that actually sees these, and the two tests
    below are its control: they capture an ERROR through the same mechanism,
    so silence here means silence rather than a blind probe.
    """

    async def succeeds() -> str:
        return "written"

    with capture_logs() as logs:
        task = asyncio.ensure_future(succeeds())
        task.add_done_callback(_callback())

        # Abandon the await exactly as the teardown does, then let the
        # shielded task finish -- the sequence that used to log an ERROR.
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=0.001)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        await task
        await asyncio.sleep(0)

    assert task.result() == "written", "the write did not land; wrong scenario"
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
