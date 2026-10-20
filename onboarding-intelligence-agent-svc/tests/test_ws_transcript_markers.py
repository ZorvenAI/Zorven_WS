"""#662 markers, driven through a real socket.

Review of #673 found that **nothing in production wrote**
``transcript.resumed``. The marker type existed, coverage consumed it, and
every test that exercised it put it in Redis by hand — so the suites were
green while the only path that mattered was missing.

This file drives `start`, `stop` and an abrupt disconnect through the real
handler over a real ``TestClient`` socket, then reads what the handler left in
Redis. A test that writes its own input cannot catch an input nobody produces.

Two things this file had to learn, recorded so the next person does not repeat
them:

* **Let the server read the frame before closing.** ``TestClient`` queues
  sends and the receive loop polls on a timer, so a test that sends `start`
  and leaves the ``with`` block immediately closes the socket first and the
  frame is never handled. Nothing fails; the markers are simply absent. These
  tests wait on the effect instead of sleeping a fixed time.
* **Install an STT adapter.** The start handler returns at
  ``stt_not_configured`` without one, long before any marker is written, and
  the test app has none that works offline.

An earlier attempt at this file concluded that control frames never reach
``_handle_control`` through this harness and fell back to inspecting the
module source. That conclusion was wrong: it came from a probe that silently
failed to install, and the harness works. The source-inspection test for the
two `start` branches is kept below, because it covers a case a socket test
cannot reach cheaply, but the behaviour is proved here.

The drop case was absent here when this file first landed, tracked as #677.
The cause turned out to be real and in production code, not in the harness: a
client-initiated close cancels the handler task, so every `await` in the
teardown after the first one raises CancelledError, and the marker write sat
at the end of that teardown. It is written first and shielded now, and the
test below covers it.
"""

from __future__ import annotations

import inspect
import json
import re
import time

import pytest
import redis as redis_sync

from app.cache.redis_manager import TenantKeys

from tests.conftest import REDIS_URL, redis_available
from tests.test_ws_handshake import (  # noqa: F401 - fixtures used by name
    client,
    django_stub,
    live_company,
    open_socket,
)

pytestmark = pytest.mark.integration

#: The tenant the handshake stub authorises, so the keys line up.
TENANT = "t-1"


def start_frame(recording_id="rec-1"):
    return json.dumps(
        {
            "type": "start",
            "recording_id": recording_id,
            "codec": "audio/webm;codecs=opus",
            "sample_rate": 48000,
        }
    )


@pytest.fixture
def redis_client():
    """A synchronous connection of our own.

    Synchronous because ``TestClient`` drives the app through its own portal,
    so an ``async def`` test would block the loop the app needs. Our own,
    because reading the markers back through the object that wrote them would
    prove less.
    """
    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")
    conn = redis_sync.from_url(REDIS_URL, decode_responses=True)
    yield conn
    conn.close()


@pytest.fixture
def hob(client, django_stub, redis_client):  # noqa: F811
    """A socket-ready app with an STT adapter, and a clean marker key."""
    from app.providers.stt import FakeSTTAdapter

    # One event, far enough out that it never fires: with no events the fake's
    # stream returns at once, the STT task completes, and nothing is
    # "transcribing" when the socket closes — so a drop would record no
    # interruption for a reason that has nothing to do with the code under
    # test. A live stream is what the interruption marker is about.
    client.app.state.stt = FakeSTTAdapter(
        events=[
            {
                "text": "unused",
                "is_final": True,
                "t_start": 0.0,
                "t_end": 0.1,
                "delay_ms": 600000,
            }
        ]
    )
    django_stub["body"] = {"approved": True, "questionnaire_status": "APPROVED"}
    sessions: list[str] = []

    def session_id(name):
        sid = f"markers-{name}-{int(time.time() * 1000) % 100000}"
        sessions.append(sid)
        return sid

    yield client, session_id
    for sid in sessions:
        redis_client.delete(TenantKeys(TENANT).live_markers(sid))


def markers_of(redis_client, session_id):
    raw = redis_client.lrange(TenantKeys(TENANT).live_markers(session_id), 0, -1)
    return [json.loads(item) for item in raw or []]


def wait_for_markers(redis_client, session_id, count, timeout=20.0):
    """Wait for the handler to have written `count` markers.

    Polling the effect rather than sleeping a fixed time: the receive loop
    runs on its own timer, so any constant is either flaky or slow.
    """
    deadline = time.monotonic() + timeout
    seen: list[dict] = []
    while time.monotonic() < deadline:
        seen = markers_of(redis_client, session_id)
        if len(seen) >= count:
            return seen
        time.sleep(0.05)
    return seen


def kinds(markers):
    return [m["type"] for m in markers]


def test_starting_transcription_records_a_resume(hob, redis_client):
    """The write review of #673 found missing, proved over a socket."""
    hob_client, session_id = hob
    sid = session_id("start")

    with open_socket(hob_client, session_id=sid) as socket:
        socket.send_text(start_frame())
        markers = wait_for_markers(redis_client, sid, 1)

    assert kinds(markers) == ["transcript.resumed"]


def test_a_clean_stop_records_the_stop(hob, redis_client):
    """The positive evidence completeness rests on. Without it, coverage
    cannot tell a finished meeting from a failed marker write."""
    hob_client, session_id = hob
    sid = session_id("stop")

    with open_socket(hob_client, session_id=sid) as socket:
        socket.send_text(start_frame())
        wait_for_markers(redis_client, sid, 1)
        socket.send_text(json.dumps({"type": "stop"}))
        markers = wait_for_markers(redis_client, sid, 2)

    assert kinds(markers) == ["transcript.resumed", "transcript.stopped"]


def test_a_drop_while_recording_records_an_interruption(hob, redis_client):
    """#662's own scenario: no `stop` frame, the socket just goes away.

    This is the case #677 was filed for. It failed because the marker write
    was the last thing in a teardown whose awaits stop working the moment the
    task is cancelled, which is exactly what a client-initiated close does.
    """
    hob_client, session_id = hob
    sid = session_id("drop")

    with open_socket(hob_client, session_id=sid) as socket:
        socket.send_text(start_frame())
        wait_for_markers(redis_client, sid, 1)
        # Leaving the block without stopping is the drop.

    markers = wait_for_markers(redis_client, sid, 2)

    assert kinds(markers) == ["transcript.resumed", "transcript.interrupted"]
    assert markers[-1]["reason"] == "socket_closed"


def test_a_clean_stop_does_not_record_an_interruption(hob, redis_client):
    """The guard that keeps every finished meeting from reading as truncated.

    The teardown runs on every socket close, including this one; only the
    live-STT check keeps it quiet.
    """
    hob_client, session_id = hob
    sid = session_id("clean")

    with open_socket(hob_client, session_id=sid) as socket:
        socket.send_text(start_frame())
        wait_for_markers(redis_client, sid, 1)
        socket.send_text(json.dumps({"type": "stop"}))
        wait_for_markers(redis_client, sid, 2)

    markers = wait_for_markers(redis_client, sid, 3, timeout=1.5)

    assert "transcript.interrupted" not in kinds(markers)


# ── One case a socket test cannot reach cheaply ──────────────────────

FLAT_SOURCE = " ".join(
    inspect.getsource(__import__("app.api.ws", fromlist=["ws"])).split()
)


def test_both_start_branches_resume():
    """`start` has a multi-stream branch and a single-stream branch, and only
    one runs per recording. The socket tests above drive the single-stream
    one; marking only that branch would leave coverage correct for single-mic
    meetings and silently wrong for every multi-mic one."""
    calls = re.findall(r"record_marker\(\s*[\"']transcript\.resumed[\"']", FLAT_SOURCE)

    assert len(calls) >= 2, (
        "only one resume writer found; the multi-stream and single-stream "
        "start paths each need their own"
    )
