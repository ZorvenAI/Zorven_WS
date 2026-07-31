"""Integration tests against the real echo service over real sockets.

These prove the service-side half of AC-1 and AC-3: the close codes, the
single-writer guarantee, the seq series and reconnect replay. The gateway half
lives in test_kong_ws_integration.py.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import websockets

from harness.jwt_util import mint, mint_expired, mint_tenantless, mint_wrong_secret

pytestmark = [pytest.mark.integration]

ONE_KB = 1024


def url(server, session_id: str, token: str | None) -> str:
    base = f"{server['ws']}/v1/live/{session_id}"
    return f"{base}?jwt={token}" if token else base


def audio_frame(echo_id: int, size: int = 160) -> bytes:
    return echo_id.to_bytes(8, "big") + b"\x00" * max(0, size - 8)


async def close_code_for(server, session_id: str, token: str | None) -> int:
    """Open, expect a close, and return the code the server used."""
    with pytest.raises(websockets.exceptions.ConnectionClosed) as exc:
        async with websockets.connect(url(server, session_id, token)) as ws:
            await ws.recv()
    return exc.value.rcvd.code


async def test_handshake_opens_and_1kb_frame_round_trips(
    echo_server, secret, reset_stats
):
    """AC-1: the socket reaches OPEN and a 1 KB binary frame round-trips."""
    token = mint(secret, tenant_id="tenant-alpha")
    async with websockets.connect(url(echo_server, "s-open", token)) as ws:
        await ws.send(audio_frame(7, ONE_KB))
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

    assert frame["type"] == "echo.ack"
    assert frame["echo_id"] == 7
    assert frame["bytes_received"] == ONE_KB
    assert frame["seq"] >= 0


async def test_tenant_claim_survives_to_the_service(echo_server, secret, reset_stats):
    """A socket that opens but arrives tenant-less is a failure, not a pass."""
    token = mint(secret, tenant_id="tenant-bravo")
    async with websockets.connect(url(echo_server, "s-tenant", token)) as ws:
        await ws.send(json.dumps({"type": "start", "recording_id": "r_01"}))
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
    assert "tenant-bravo" in frame["text"]


@pytest.mark.parametrize(
    "token_kind", ["absent", "expired", "forged", "tenantless", "garbage"]
)
async def test_bad_tokens_are_closed_with_4401(
    echo_server, secret, reset_stats, token_kind
):
    tokens = {
        "absent": None,
        "expired": mint_expired(secret),
        "forged": mint_wrong_secret(),
        "tenantless": mint_tenantless(secret),
        "garbage": "not-a-jwt",
    }
    assert await close_code_for(echo_server, "s-bad", tokens[token_kind]) == 4401


async def test_unknown_session_closed_with_4404(echo_server, secret, reset_stats):
    token = mint(secret)
    assert await close_code_for(echo_server, "missing-session", token) == 4404


async def test_second_socket_rejected_4409_and_first_untouched(
    echo_server, secret, reset_stats
):
    """AC-2 of F-04: the newcomer loses, the incumbent is undisturbed."""
    token = mint(secret)
    async with websockets.connect(url(echo_server, "s-single", token)) as first:
        with pytest.raises(websockets.exceptions.ConnectionClosed) as exc:
            async with websockets.connect(
                url(echo_server, "s-single", token)
            ) as second:
                await second.recv()
        assert exc.value.rcvd.code == 4409

        # The incumbent still works.
        await first.send(audio_frame(99))
        frame = json.loads(await asyncio.wait_for(first.recv(), timeout=10))
        assert frame["echo_id"] == 99


async def test_seq_strictly_increases_across_frame_types(
    echo_server, secret, reset_stats
):
    token = mint(secret)
    seqs = []
    async with websockets.connect(url(echo_server, "s-seq", token)) as ws:
        await ws.send(json.dumps({"type": "start", "recording_id": "r_01"}))
        seqs.append(json.loads(await ws.recv())["seq"])
        for echo_id in range(1, 11):
            await ws.send(audio_frame(echo_id))
            seqs.append(json.loads(await ws.recv())["seq"])
        await ws.send(json.dumps({"type": "heartbeat"}))
        seqs.append(json.loads(await ws.recv())["seq"])

    assert all(b > a for a, b in zip(seqs, seqs[1:])), seqs


async def test_resume_replays_after_last_seq(echo_server, secret, reset_stats):
    """AC-3: reconnection resumes rather than restarts, at zero token cost."""
    token = mint(secret)
    session = "s-resume"

    async with websockets.connect(url(echo_server, session, token)) as ws:
        await ws.send(json.dumps({"type": "start", "recording_id": "r_01"}))
        last_seq = json.loads(await ws.recv())["seq"]
        for echo_id in range(1, 6):
            await ws.send(audio_frame(echo_id))
            last_seq = json.loads(await ws.recv())["seq"]

        # Frames the client will miss because it is about to drop.
        drop_point = last_seq
        for echo_id in range(6, 9):
            await ws.send(audio_frame(echo_id))
            await ws.recv()

    async with websockets.connect(url(echo_server, session, token)) as ws:
        await ws.send(json.dumps({"type": "resume", "last_seq": drop_point}))
        replayed = []
        try:
            while True:
                replayed.append(
                    json.loads(await asyncio.wait_for(ws.recv(), timeout=1.5))
                )
        except asyncio.TimeoutError:
            pass

    seqs = [f["seq"] for f in replayed]
    assert seqs, "nothing was replayed"
    assert seqs[0] == drop_point + 1, "replay did not start after last_seq"
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), "gap in replay"
    assert not any(f.get("type") == "resync" for f in replayed)


async def test_resume_beyond_window_answers_with_resync(
    echo_server, secret, reset_stats
):
    """An out-of-window resume gets an explicit resync, not a silent gap."""
    token = mint(secret)
    session = "s-window"
    async with websockets.connect(url(echo_server, session, token)) as ws:
        # Capacity is 64 in the fixture; overflow it decisively.
        for echo_id in range(1, 120):
            await ws.send(audio_frame(echo_id))
            await ws.recv()

    async with websockets.connect(url(echo_server, session, token)) as ws:
        await ws.send(json.dumps({"type": "resume", "last_seq": 0}))
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))

    assert frame["type"] == "resync"
    assert frame["oldest_available_seq"] is not None


async def test_seq_series_continues_across_reconnect(echo_server, secret, reset_stats):
    token = mint(secret)
    session = "s-continuity"
    async with websockets.connect(url(echo_server, session, token)) as ws:
        await ws.send(audio_frame(1))
        first = json.loads(await ws.recv())["seq"]

    async with websockets.connect(url(echo_server, session, token)) as ws:
        await ws.send(audio_frame(2))
        second = json.loads(await ws.recv())["seq"]

    assert second > first, "seq restarted on reconnect instead of continuing"


async def test_stats_counts_handshakes_that_reached_the_service(
    echo_server, secret, reset_stats
):
    """The counter that lets the Kong test prove where a rejection happened."""
    before = httpx.get(f"{echo_server['http']}/health/stats", timeout=5).json()
    await close_code_for(echo_server, "s-count", mint_wrong_secret())
    after = httpx.get(f"{echo_server['http']}/health/stats", timeout=5).json()

    assert after["handshakes_seen"] == before["handshakes_seen"] + 1
    assert after["rejected_4401"] == before["rejected_4401"] + 1
