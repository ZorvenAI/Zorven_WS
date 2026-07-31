"""AC-2 — the connection survives a realistic meeting.

Two lengths of the same test. The smoke run is short enough to sit in a normal
test pass; the full run is the 45-minute meeting the acceptance criterion
actually names and is opt-in:

    pytest tests/test_soak.py -m slow --soak-minutes=45

Both drive the real probe against a real gateway. A disconnect is not an error
to be retried — it is the measurement, and the record says which layer closed
the socket and after how long.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness.jwt_util import mint
from harness.probe import DIRECT_PATH, GATEWAY_PATH, Recorder, probe_soak
from tests.conftest import SECRET

pytestmark = [pytest.mark.integration]

SMOKE_MINUTES = float(os.environ.get("SPIKE_SMOKE_MINUTES", "3"))
FULL_MINUTES = float(os.environ.get("SPIKE_SOAK_MINUTES", "45"))
RESULTS = Path(__file__).resolve().parents[1] / "results"


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run_soak(
    target_ws: str, minutes: float, label: str, path: str = DIRECT_PATH
) -> list[dict]:
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"soak-{label}.jsonl"
    out.unlink(missing_ok=True)
    rec = Recorder(out)
    await probe_soak(target_ws, mint(SECRET), rec, minutes, f"s-soak-{label}", path)
    return records(out)


def assert_survived(rows: list[dict], minutes: float) -> None:
    end = next(r for r in rows if r["event"] == "soak_end")
    assert end["outcome"] == "survived", (
        f"socket closed after {end['elapsed_s']}s: "
        f"{end.get('error')} {end.get('detail')} code={end.get('close_code')}"
    )
    assert end["elapsed_s"] >= minutes * 60 - 5
    assert end["acked"] > 0, "no frames were acknowledged"
    heartbeats = [r for r in rows if r["event"] == "heartbeat"]
    assert heartbeats, "the 20 s application heartbeat never fired"


async def test_soak_smoke_through_kong(kong_gateway):
    """Short run through the gateway — catches an immediate idle cutoff."""
    rows = await run_soak(kong_gateway["ws"], SMOKE_MINUTES, "kong-smoke", GATEWAY_PATH)
    assert_survived(rows, SMOKE_MINUTES)


async def test_soak_smoke_direct(echo_server):
    """The same run with no gateway — isolates which layer imposes a limit."""
    rows = await run_soak(echo_server["ws"], SMOKE_MINUTES, "direct-smoke")
    assert_survived(rows, SMOKE_MINUTES)


@pytest.mark.slow
async def test_soak_full_meeting_through_kong(kong_gateway):
    """AC-2 proper: 45 minutes of audio-sized frames through the gateway."""
    rows = await run_soak(kong_gateway["ws"], FULL_MINUTES, "kong-full", GATEWAY_PATH)
    assert_survived(rows, FULL_MINUTES)
