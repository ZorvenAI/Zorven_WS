"""The live slot is given back when a socket drops (#680).

Filed as test-harness instability: `test_ws_transcript_markers.py` failed
intermittently with no markers at all. The cause was in production code. A
client-initiated close cancels the handler task, so the `await` inside
`LiveLock.release` was cut short and the key survived; for the next ninety
seconds the company's slot was still claimed by a socket that no longer
existed, and the operator who dropped was refused with "another socket is
already live" -- their own.

The suite showed it first because `live_company` is derived from the test
name and so is identical across runs, which makes every run after a drop the
victim of the one before. A real operator hits the same wall by reconnecting.
"""

from __future__ import annotations

import json
import time

import pytest
import redis as redis_sync

from app.cache.redis_manager import TenantKeys
from app.logic import live_lock
from tests.conftest import REDIS_URL
from tests.test_ws_handshake import (  # noqa: F401
    client,
    django_stub,
    live_company,
    open_socket,
)

pytestmark = pytest.mark.integration


def _lock_held(conn, company: str) -> bool:
    """Is *this test's* slot claimed?

    Scoped to the company under test, not the tenant. Watching every
    `lock:live:*` key in the tenant made these tests fail whenever another
    test's socket was still unwinding and holding its own, legitimate lock --
    which is why they passed alone and failed in a combined run. `live_company`
    is unique per test precisely so these do not collide; the first version of
    this helper threw that away.
    """
    return conn.exists(TenantKeys("t-1").live_lock(company)) == 1


def _start(socket, recording_id: str = "r1") -> None:
    socket.send_text(
        json.dumps(
            {
                "type": "start",
                "recording_id": recording_id,
                "codec": "audio/webm;codecs=opus",
                "sample_rate": 48000,
            }
        )
    )


def test_a_dropped_socket_gives_the_slot_back(
    client, django_stub, live_company  # noqa: F811
):
    """The regression: the lock must not outlive the socket that held it."""
    from app.providers.stt import FakeSTTAdapter

    client.app.state.stt = FakeSTTAdapter(
        events=[
            {
                "text": "x",
                "is_final": True,
                "t_start": 0.0,
                "t_end": 0.1,
                "delay_ms": 600000,
            }
        ]
    )
    django_stub["body"] = {"approved": True, "questionnaire_status": "APPROVED"}
    conn = redis_sync.from_url(REDIS_URL, decode_responses=True)
    conn.delete(TenantKeys("t-1").live_lock(live_company))

    sid = f"lock-drop-{int(time.time() * 1000) % 100000}"
    mkey = TenantKeys("t-1").live_markers(sid)
    with open_socket(client, session_id=sid) as socket:
        _start(socket)
        for _ in range(200):
            if conn.lrange(mkey, 0, -1):
                break
            time.sleep(0.05)
        # Assert the positive first: on a run where the frame was never
        # processed, an empty lock list proves nothing about the release.
        assert conn.lrange(mkey, 0, -1), "the start frame was never processed"
        assert _lock_held(
            conn, live_company
        ), "the lock should be held while the socket is open"

    for _ in range(40):
        if not _lock_held(conn, live_company):
            break
        time.sleep(0.05)

    still_claimed = _lock_held(conn, live_company)
    conn.delete(mkey)
    conn.close()
    assert not still_claimed, (
        "the live slot is still claimed after the drop. The operator who "
        f"dropped cannot restart for up to {live_lock.LOCK_TTL_S}s."
    )


def test_the_operator_can_start_again_right_after_a_drop(
    client, django_stub, live_company  # noqa: F811
):
    """What the leaked lock actually cost: the reconnect, not the key."""
    from app.providers.stt import FakeSTTAdapter

    client.app.state.stt = FakeSTTAdapter(
        events=[
            {
                "text": "x",
                "is_final": True,
                "t_start": 0.0,
                "t_end": 0.1,
                "delay_ms": 600000,
            }
        ]
    )
    django_stub["body"] = {"approved": True, "questionnaire_status": "APPROVED"}
    conn = redis_sync.from_url(REDIS_URL, decode_responses=True)
    conn.delete(TenantKeys("t-1").live_lock(live_company))

    first = f"lock-again-a-{int(time.time() * 1000) % 100000}"
    mkey_first = TenantKeys("t-1").live_markers(first)
    with open_socket(client, session_id=first) as socket:
        _start(socket)
        for _ in range(200):
            if conn.lrange(mkey_first, 0, -1):
                break
            time.sleep(0.05)
        assert conn.lrange(mkey_first, 0, -1), "the start frame was never processed"

    # Wait for the slot, as a reconnecting client would, and hold the wait to
    # a budget far below the TTL. The guarantee is not "free in the same
    # millisecond" -- the previous socket's teardown is still unwinding -- it
    # is that the operator is not locked out for the full ninety seconds.
    budget_s = 5.0
    waited = 0.0
    while _lock_held(conn, live_company) and waited < budget_s:
        time.sleep(0.05)
        waited += 0.05
    assert waited < budget_s, (
        f"the slot was still claimed after {budget_s}s; before the fix it "
        f"stayed claimed for the full {live_lock.LOCK_TTL_S}s TTL"
    )

    second = f"lock-again-b-{int(time.time() * 1000) % 100000}"
    mkey_second = TenantKeys("t-1").live_markers(second)
    with open_socket(client, session_id=second) as socket:
        _start(socket, recording_id="r2")
        for _ in range(200):
            if conn.lrange(mkey_second, 0, -1):
                break
            time.sleep(0.05)
        reconnected = [json.loads(m)["type"] for m in conn.lrange(mkey_second, 0, -1)]

    conn.delete(mkey_first, mkey_second, TenantKeys("t-1").live_lock(live_company))
    conn.close()
    # Before the fix this socket was refused 4409 and wrote nothing at all.
    assert (
        reconnected
    ), "the reconnect was refused: the previous socket's lock outlived it"
