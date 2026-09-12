"""Measurement drivers for spike A-02.

Three probes, one per acceptance criterion:

``handshake``  AC-1 — the upgrade completes and a 1 KB binary frame round-trips,
               and a bad token is rejected.
``soak``       AC-2 — audio-sized frames for 45 minutes with a 20 s application
               heartbeat, recording any disconnect and its source.
``reconnect``  AC-3 — drop the socket, reconnect with ``last_seq``, and record
               what was preserved and how long re-establishment took.

Every probe appends JSON records to a JSONL file so ``analyze.py`` can produce
the percentiles that go into the note. Nothing here is mocked: real sockets,
real tokens, real wall-clock timing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import time
from dataclasses import dataclass
from pathlib import Path

import websockets

# 20 ms of Opus at a typical bitrate. Design §4.3 streams these at 50/s.
AUDIO_FRAME_BYTES = 160
FRAMES_PER_SECOND = 50
HEARTBEAT_SECONDS = 20
ONE_KB = 1024


@dataclass
class Recorder:
    """Append-only JSONL sink. Flushed per record so a kill loses nothing."""

    path: Path

    def write(self, **record) -> None:
        record.setdefault("t", time.time())
        with self.path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
            fh.flush()


# The public path differs by environment: the service exposes /v1/live
# directly, while the gateway publishes it under the fleet's agent prefix.
DIRECT_PATH = "/v1/live"
GATEWAY_PATH = "/api/v1/agents/onboarding/live"


def _url(base: str, session_id: str, token: str | None, path: str = DIRECT_PATH) -> str:
    url = f"{base.rstrip('/')}{path}/{session_id}"
    return f"{url}?jwt={token}" if token else url


def _ssl_context(url: str) -> ssl.SSLContext | None:
    return ssl.create_default_context() if url.startswith("wss://") else None


def _frame(echo_id: int, size: int = AUDIO_FRAME_BYTES) -> bytes:
    """An audio-sized frame carrying an 8-byte id for exact RTT pairing."""
    return echo_id.to_bytes(8, "big") + b"\x00" * max(0, size - 8)


async def probe_handshake(
    base: str,
    token: str,
    rec: Recorder,
    session_id: str = "spike-handshake",
    path: str = DIRECT_PATH,
) -> None:
    """AC-1: open, round-trip 1 KB, confirm the tenant survived the hop."""
    url = _url(base, session_id, token, path)
    started = time.perf_counter()
    async with websockets.connect(url, ssl=_ssl_context(url), open_timeout=30) as ws:
        open_ms = (time.perf_counter() - started) * 1000
        rec.write(event="open", rtt_ms=round(open_ms, 2), url=base)

        await ws.send(json.dumps({"type": "start", "recording_id": "r_spike"}))
        started_frame = time.perf_counter()
        reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        rec.write(
            event="start_ack",
            rtt_ms=round((time.perf_counter() - started_frame) * 1000, 2),
            frame=reply,
        )

        started_frame = time.perf_counter()
        await ws.send(_frame(1, ONE_KB))
        reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        rec.write(
            event="rtt",
            rtt_ms=round((time.perf_counter() - started_frame) * 1000, 2),
            bytes_sent=ONE_KB,
            bytes_echoed=reply.get("bytes_received"),
            echo_id=reply.get("echo_id"),
        )


async def probe_rejected(
    base: str,
    token: str | None,
    rec: Recorder,
    label: str,
    path: str = DIRECT_PATH,
) -> None:
    """AC-1 negative: a bad or absent token must not open a socket."""
    url = _url(base, "spike-reject", token, path)
    try:
        async with websockets.connect(
            url, ssl=_ssl_context(url), open_timeout=30
        ) as ws:
            # The socket must be read before a verdict is recorded. Where the
            # service rejects (Cloud Run, no gateway) the handshake completes
            # and the close frame arrives only on the next read; recording
            # "opened" without reading would call a rejection a success.
            await asyncio.wait_for(ws.recv(), timeout=15)
            rec.write(event="reject", label=label, outcome="OPENED", close_code=None)
    except websockets.exceptions.InvalidStatus as exc:
        # Kong rejects at the HTTP layer, before the upgrade completes.
        rec.write(
            event="reject",
            label=label,
            outcome="http_rejected",
            status=exc.response.status_code,
        )
    except websockets.exceptions.ConnectionClosed as exc:
        # The service rejects after the upgrade, with a close code.
        rec.write(
            event="reject", label=label, outcome="closed", close_code=exc.rcvd.code
        )


async def probe_soak(
    base: str,
    token: str,
    rec: Recorder,
    minutes: float,
    session_id: str,
    path: str = DIRECT_PATH,
) -> None:
    """AC-2: sustain the socket for a full meeting and record any disconnect."""
    url = _url(base, session_id, token, path)
    deadline = time.monotonic() + minutes * 60
    last_heartbeat = time.monotonic()
    echo_id = 0
    sent = acked = 0

    rec.write(event="soak_start", minutes=minutes, url=base)
    started = time.monotonic()

    try:
        async with websockets.connect(
            url, ssl=_ssl_context(url), open_timeout=30, ping_interval=None
        ) as ws:

            async def drain() -> None:
                nonlocal acked
                async for raw in ws:
                    frame = json.loads(raw)
                    acked += 1
                    if frame.get("echo_id") is not None and frame["echo_id"] >= 0:
                        pending.pop(frame["echo_id"], None)

            pending: dict[int, float] = {}
            reader = asyncio.create_task(drain())

            while time.monotonic() < deadline:
                cycle = time.monotonic()
                for _ in range(FRAMES_PER_SECOND):
                    echo_id += 1
                    pending[echo_id] = time.perf_counter()
                    await ws.send(_frame(echo_id))
                    sent += 1

                if time.monotonic() - last_heartbeat >= HEARTBEAT_SECONDS:
                    await ws.send(json.dumps({"type": "heartbeat"}))
                    last_heartbeat = time.monotonic()
                    rec.write(
                        event="heartbeat",
                        elapsed_s=round(time.monotonic() - started, 1),
                        sent=sent,
                        acked=acked,
                    )

                await asyncio.sleep(max(0.0, 1.0 - (time.monotonic() - cycle)))

            reader.cancel()
            rec.write(
                event="soak_end",
                outcome="survived",
                elapsed_s=round(time.monotonic() - started, 1),
                sent=sent,
                acked=acked,
            )
    except Exception as exc:  # noqa: BLE001 — the failure itself is the datum
        rec.write(
            event="soak_end",
            outcome="disconnected",
            elapsed_s=round(time.monotonic() - started, 1),
            sent=sent,
            acked=acked,
            error=type(exc).__name__,
            detail=str(exc)[:400],
            close_code=getattr(getattr(exc, "rcvd", None), "code", None),
        )
        raise


async def probe_reconnect(
    base: str,
    token: str,
    rec: Recorder,
    interrupt_seconds: float = 10.0,
    path: str = DIRECT_PATH,
) -> None:
    """AC-3: characterise what a reconnect preserves and what it costs."""
    session_id = "spike-reconnect"
    url = _url(base, session_id, token, path)

    async with websockets.connect(url, ssl=_ssl_context(url)) as ws:
        await ws.send(json.dumps({"type": "start", "recording_id": "r_spike"}))
        last_seq = json.loads(await ws.recv())["seq"]
        instance_before = None
        for echo_id in range(1, 21):
            await ws.send(_frame(echo_id))
            ack = json.loads(await ws.recv())
            last_seq = ack["seq"]
            instance_before = ack.get("instance") or instance_before
        rec.write(event="pre_drop", last_seq=last_seq, instance=instance_before)

    rec.write(event="interrupt", seconds=interrupt_seconds)
    await asyncio.sleep(interrupt_seconds)

    started = time.perf_counter()
    async with websockets.connect(url, ssl=_ssl_context(url)) as ws:
        reestablish_ms = (time.perf_counter() - started) * 1000
        await ws.send(json.dumps({"type": "resume", "last_seq": last_seq}))
        replayed = []
        try:
            while True:
                replayed.append(
                    json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
                )
        except asyncio.TimeoutError:
            pass

        # Ask for one ack so the answering instance identifies itself.
        await ws.send(_frame(999))
        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        instance_after = ack.get("instance")

        rec.write(
            event="reconnect",
            reestablish_ms=round(reestablish_ms, 2),
            resumed_from=last_seq,
            frames_replayed=len(replayed),
            first_replayed_seq=replayed[0]["seq"] if replayed else None,
            resync_required=any(f.get("type") == "resync" for f in replayed),
            instance_before=instance_before,
            instance_after=instance_after,
            same_instance=(
                None
                if not (instance_before and instance_after)
                else instance_before == instance_after
            ),
            seq_continued=ack["seq"] > last_seq,
        )


async def probe_concurrency(
    base: str, token: str, rec: Recorder, sockets: int = 20, path: str = DIRECT_PATH
) -> None:
    """How many instances answer N concurrent sockets?

    Decides whether in-process session state is viable at all. If two sockets
    for the same tenant can land on different instances, the single-writer
    lock and the replay buffer must be shared state — which is what Design
    §14 and ERRATA-01 already require, but this measures it rather than
    assuming it.
    """
    instances: list[str] = []
    refused: list[str] = []

    async def one(index: int) -> None:
        url = _url(base, f"spike-conc-{index}", token, path)
        try:
            async with websockets.connect(
                url, ssl=_ssl_context(url), open_timeout=30
            ) as ws:
                await ws.send(_frame(index))
                ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                instances.append(ack.get("instance", ""))
                # Hold the socket so the platform is actually asked to scale.
                await asyncio.sleep(10)
        except Exception as exc:  # noqa: BLE001 — a refusal is a measurement
            status = getattr(getattr(exc, "response", None), "status_code", None)
            refused.append(f"{type(exc).__name__}:{status}")

    await asyncio.gather(*(one(i) for i in range(sockets)))
    rec.write(
        event="concurrency",
        sockets=sockets,
        opened=len(instances),
        refused=len(refused),
        refusals=sorted(set(refused)),
        distinct_instances=len(set(instances)),
        instances=sorted(set(instances)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="A-02 gateway WebSocket probes")
    parser.add_argument(
        "probe",
        choices=["handshake", "soak", "reconnect", "reject", "concurrency"],
    )
    parser.add_argument("--url", required=True, help="ws://host or wss://host")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--minutes", type=float, default=45.0)
    parser.add_argument("--session", default="spike-soak")
    parser.add_argument(
        "--path",
        default=DIRECT_PATH,
        help=f"public path prefix; use {GATEWAY_PATH} through Kong",
    )
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from .jwt_util import mint, mint_expired, mint_wrong_secret

    rec = Recorder(args.out)
    token = mint(args.secret)

    if args.probe == "handshake":
        asyncio.run(probe_handshake(args.url, token, rec, path=args.path))
    elif args.probe == "soak":
        asyncio.run(
            probe_soak(args.url, token, rec, args.minutes, args.session, args.path)
        )
    elif args.probe == "reconnect":
        asyncio.run(probe_reconnect(args.url, token, rec, path=args.path))
    elif args.probe == "concurrency":
        asyncio.run(probe_concurrency(args.url, token, rec, path=args.path))
    else:
        asyncio.run(probe_rejected(args.url, None, rec, "absent", args.path))
        asyncio.run(
            probe_rejected(
                args.url, mint_expired(args.secret), rec, "expired", args.path
            )
        )
        asyncio.run(
            probe_rejected(args.url, mint_wrong_secret(), rec, "forged", args.path)
        )


if __name__ == "__main__":
    main()
