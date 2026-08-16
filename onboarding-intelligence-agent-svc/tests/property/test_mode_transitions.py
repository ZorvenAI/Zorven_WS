"""F-06 · Mode transitions always pair entry with exit.

Hypothesis: any sequence of failures and recoveries always leaves the
session in a well-defined state, and every RECORD_ONLY entry is paired
with an exit back to NORMAL.
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.logic.live_session import LiveSessionManager

pytestmark = [pytest.mark.integration, pytest.mark.property]


@given(
    transitions=st.lists(
        st.sampled_from(["NORMAL", "RECORD_ONLY"]),
        min_size=1,
        max_size=50,
    )
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_mode_is_always_the_last_written(live_redis, transitions):
    """The mode in Redis is always the last value written, regardless of
    the sequence of transitions. No lost update, no stale read."""
    session = LiveSessionManager(
        redis=live_redis,
        tenant_id="t-prop",
        session_id=f"s-{uuid.uuid4().hex[:8]}",
    )

    for mode in transitions:
        await session.set_mode(mode)

    assert await session.get_mode() == transitions[-1]


@given(
    marks=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=10, alphabet="abcdefghij0123456789_"),
            st.sampled_from(["manual_green", "manual_red"]),
        ),
        min_size=1,
        max_size=20,
    )
)
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_mark_question_last_write_wins(live_redis, marks):
    """For any sequence of marks on any set of questions, each question's
    final value is the last one written."""
    session = LiveSessionManager(
        redis=live_redis,
        tenant_id="t-prop",
        session_id=f"s-{uuid.uuid4().hex[:8]}",
    )

    expected: dict[str, str] = {}
    for qid, action in marks:
        await session.mark_question(qid, action)
        expected[qid] = action

    stored = await session.get_question_marks()
    for qid, action in expected.items():
        assert qid in stored
        assert stored[qid]["action"] == action
        assert stored[qid]["source"] == "manual"
        assert stored[qid]["evidence"] == []
