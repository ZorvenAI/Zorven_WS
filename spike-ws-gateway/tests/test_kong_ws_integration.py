"""AC-1 through a real Kong gateway.

Runs the same Kong image the fleet runs (`zorven-kong`, falling back to
`kong:3.4`) in DB-less mode against the spike's declarative config, with the
echo service as its upstream. Nothing is simulated: a real gateway, a real
upgrade, real JWT validation at the gateway.

The load-bearing assertion is not the close code — it is the echo's
`handshakes_seen` counter. A bad token that Kong rejects must never increment
it. Asserting on the client-visible failure alone cannot distinguish "the
gateway rejected it" from "the service rejected it", and A-01's spike showed
how expensive an unverified assumption is.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import websockets

from harness.jwt_util import mint, mint_expired, mint_wrong_secret
from tests.conftest import ROUTE, SECRET

pytestmark = [pytest.mark.integration]


def gw_url(kong, session_id: str, token: str | None) -> str:
    url = f"{kong['ws']}{ROUTE}/{session_id}"
    return f"{url}?jwt={token}" if token else url


def stats(echo_server) -> dict:
    return httpx.get(f"{echo_server['http']}/health/stats", timeout=5).json()


async def test_upgrade_completes_through_the_gateway(
    kong_gateway, echo_server, reset_stats
):
    """AC-1: the socket reaches OPEN and a 1 KB binary frame round-trips."""
    token = mint(SECRET, tenant_id="tenant-kong")
    payload = (7).to_bytes(8, "big") + b"\x00" * (1024 - 8)

    async with websockets.connect(
        gw_url(kong_gateway, "s-gw-open", token), open_timeout=30
    ) as ws:
        await ws.send(payload)
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))

    assert frame["type"] == "echo.ack"
    assert frame["echo_id"] == 7
    assert frame["bytes_received"] == 1024


async def test_tenant_claim_survives_the_gateway_hop(
    kong_gateway, echo_server, reset_stats
):
    """A socket that opens but arrives tenant-less is a spike failure."""
    token = mint(SECRET, tenant_id="tenant-charlie")
    async with websockets.connect(
        gw_url(kong_gateway, "s-gw-tenant", token), open_timeout=30
    ) as ws:
        await ws.send(json.dumps({"type": "start", "recording_id": "r_01"}))
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
    assert "tenant-charlie" in frame["text"]


@pytest.mark.parametrize("kind", ["absent", "expired", "forged"])
async def test_bad_token_never_reaches_the_service(
    kong_gateway, echo_server, reset_stats, kind
):
    """AC-1 negative: Kong rejects before the service sees the handshake."""
    tokens = {
        "absent": None,
        "expired": mint_expired(SECRET),
        "forged": mint_wrong_secret(),
    }
    before = stats(echo_server)["handshakes_seen"]

    with pytest.raises(
        (
            websockets.exceptions.InvalidStatus,
            websockets.exceptions.ConnectionClosed,
        )
    ) as exc:
        async with websockets.connect(
            gw_url(kong_gateway, "s-gw-bad", tokens[kind]), open_timeout=30
        ) as ws:
            await ws.recv()

    after = stats(echo_server)["handshakes_seen"]
    assert (
        after == before
    ), f"{kind} token reached the service — the gateway did not reject it"

    if isinstance(exc.value, websockets.exceptions.InvalidStatus):
        assert exc.value.response.status_code in (401, 403)


async def test_valid_token_does_reach_the_service(
    kong_gateway, echo_server, reset_stats
):
    """The counter moves for a good token — proving the negative test bites."""
    before = stats(echo_server)["handshakes_seen"]
    async with websockets.connect(
        gw_url(kong_gateway, "s-gw-good", mint(SECRET)), open_timeout=30
    ) as ws:
        await ws.send(json.dumps({"type": "heartbeat"}))
        await asyncio.wait_for(ws.recv(), timeout=15)
    assert stats(echo_server)["handshakes_seen"] == before + 1
