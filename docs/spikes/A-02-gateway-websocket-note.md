# A-02 — Gateway WebSocket Measurement Note

**Date**: 2026-07-30
**Spike**: A-02 — WebSocket upgrade through the gateway, on Cloud Run and on the Kong dev tier
**Status**: Complete
**Blocks**: F-04 (WebSocket session lifecycle)
**Resolves**: OD-1

## Summary

**Go.** A WebSocket upgrade completes, authenticates and holds for a full
45-minute meeting on both paths — measured, not inferred: 2700.7 s through
Cloud Run and 2700.6 s through Kong, ~134,800 frames each. Neither topology forces a redesign, but each
needs a named configuration and they do **not** behave the same way, so OD-1
resolves per environment rather than globally.

Three findings change F-04's shape and one is an existing production defect
outside this story. They are in [Findings](#findings); read them before
starting F-04.

## Environment

- **OS**: macOS Darwin 25.3.0 · **Python**: 3.12.0 · **websockets**: 15.0.1
- **Gateway**: Kong 3.4.2, DB-less declarative config, image
  `ghcr.io/zorvenai/zorven-kong:development_main` — the same image the fleet runs
- **Cloud Run**: `zorven-spike-ws-echo`, revision `…-00002-9js`, us-central1,
  project `zorven-503517`, 512Mi / 1 vCPU, `--session-affinity`
- **Upstream**: throwaway FastAPI echo (`spike-ws-gateway/echo/`) implementing
  the §10.2.3 handshake, close codes, seq series and reconnect replay
- **Frames**: 160 B (20 ms Opus) at 50/s ≈ 8 KB/s, per Design §4.3

Both Cloud Run services were deleted when the spike closed.

## Why this story changed shape

The backlog wrote A-02 as "Kong WebSocket upgrade on Railway". Railway is
retired, and — the load-bearing discovery — **Kong is not deployed to Cloud
Run at all**. `deploy-gcp.yml` maps 31 images to Cloud Run services and none of
them is Kong; the `zorven-kong` image is built by `docker-publish.yml` but only
ever runs under docker-compose. Production is therefore:

```
browser → Google Front End → Cloud Run service          (no gateway)
browser → Kong → service :8120                          (dev tier, local)
```

Backlog v2.1 and design v2.2 were corrected accordingly (PR #527) before this
spike ran.

## AC-1 · The upgrade completes on both paths, authenticated

| | Cloud Run (production) | Kong (dev tier / local) |
|---|---|---|
| Handshake reaches OPEN | yes | yes |
| Handshake open time | 1361.85 ms (TLS + cold start) | 444.18 ms (loopback) |
| 1 KB binary frame round-trip | **30.65 ms** | **7.35 ms** |
| Bytes echoed | 1024 / 1024 | 1024 / 1024 |
| Tenant claim arrives at service | yes | yes |
| Absent token | service closes **4401** | Kong **HTTP 401** |
| Expired token | service closes **4401** | Kong **HTTP 401** |
| Forged signature | service closes **4401** | Kong **HTTP 401** |

On the Kong path the rejection is proven to happen *at the gateway*, not at the
service: the echo exposes a `handshakes_seen` counter incremented before any
authentication, and it does not move for any of the three bad tokens
(`test_bad_token_never_reaches_the_service`). A companion test with a valid
token confirms the counter does move, so the assertion bites.

On Cloud Run there is no gateway, so all three bad tokens reach the service and
are rejected in-process. **This is the cost AC-1 asked us to quantify**: IG-05
tenant validation and rate limiting have nowhere to run in production except
`app/api/ws.py`, and F-04 must carry them.

## AC-2 · The connection survives a realistic meeting

| Path | Configuration | Outcome |
|---|---|---|
| Cloud Run | `--timeout=300` (the **default**) | **disconnected at 301.9 s** — "no close frame received or sent" |
| Cloud Run | `--timeout=3600` | **survived 45 min** (2700.7 s), 134,800 frames sent / 134,934 acked, 134 heartbeats |
| Kong dev tier | `read_timeout: 60000`, 20 s app heartbeat | **survived 45 min** (2700.6 s), 134,750 frames sent / 134,884 acked |

(Acked slightly exceeds sent because the acked counter includes every inbound
frame — the heartbeat replies and the session-start frame as well as the
per-audio-frame acks. It is a liveness signal, not a delivery ratio.)

The 300 s result is the important one. **A WebSocket on Cloud Run is one
long-lived request, so the service's `--timeout` caps the socket outright.** The
cut at 301.9 s is abrupt — no close frame, no warning — which is what a dropped
meeting looks like to an operator. The maximum permitted value is 3600 s, which
covers a 45–60 minute meeting with no headroom to spare for a session that
overruns.

Kong's 60 s `read_timeout` is not a problem: the design's 20 s application
heartbeat keeps the socket inside the idle window with room to spare. No
gateway-imposed timeout was observed in 45 minutes.

## AC-3 · Reconnect behaviour

| Measurement | Result |
|---|---|
| Re-establishment after a 10 s interruption | **169.73 ms** |
| JWT re-validated on reconnect | yes — a reconnect is a fresh handshake |
| seq series continued (did not restart) | yes |
| Replay after `last_seq` | correct; zero model calls |
| Landed on the same Cloud Run instance | yes, in this run — but see below |

**Zero-token replay as specified in Design §9.2 is implementable**, with one
condition that the design already anticipates and this spike now proves is
mandatory rather than merely tidy.

A concurrency probe opened parallel sockets against the Cloud Run service:

| Concurrent sockets | Opened | Refused | Distinct instances |
|---|---|---|---|
| 8 | 8 | 0 | **3** |
| 20 | 16 | 4 (HTTP 500) | 3 |

Eight sockets were served by three different instances even with
`--session-affinity` set. Two caveats on that number, stated precisely because
the conclusion rests on it:

- Cloud Run session affinity is cookie-based and best-effort. The probe is a
  Python client that does not persist cookies, so a **browser** would stand a
  better chance of returning to the same instance than this measurement shows.
- What the measurement does establish beyond doubt is that *concurrent* sockets
  spread across instances, and Cloud Run may reclaim an instance at any time.

Either caveat alone is enough for the same conclusion: in-process session state
cannot be relied on to survive a reconnect in production. The replay buffer and
the single-writer lock belong in Redis (DB 2 with the `oia:v1:` prefix, per
ERRATA-01), not in a Python dict — and the single-writer 4409 check must be a
cross-instance lock, since two sockets for one session can be held by two
different processes that cannot see each other's memory.

The refusals at 20 sockets are the second half of that story: a WebSocket
occupies a Cloud Run concurrency slot for its entire life, so live-session
capacity is `max-instances × concurrency`, and exceeding it fails the handshake
with **HTTP 500** rather than queueing.

## AC-4 · OD-1 resolved

> **OD-1 — WebSocket transport differs by environment: Google Front End on
> Cloud Run, Kong on the dev tier.**
>
> **Resolution: proceed on both paths, with a named configuration for each.**

**Production (Cloud Run) — proceed direct, with compensation.** There is no
gateway to route through, so the "through Kong" option does not exist here. The
service must be deployed with:

```
--timeout=3600          # mandatory; the 300s default cuts meetings at 5 minutes
--session-affinity      # best-effort only; do not rely on it for correctness
--min-instances=1       # avoids a cold start on the first socket of a meeting
--concurrency=<n>       # live capacity is max-instances × concurrency
```

and `app/api/ws.py` must carry the auth and rate limiting that Kong performs on
the other path: JWT validation, IG-05 tenant resolution, and a per-tenant
connection rate limit. This is the "explicitly documented auth compensation"
branch of AC-4, and its cost lands on F-04.

**Dev tier and local — proceed through Kong.** The route block is in
`spike-ws-gateway/kong/oia-live.yaml`, ready to merge into
`deployment/docker/kong/kong.yaml`. It mirrors the existing
`workspace-ws-service` block and adds the JWT plugin that block lacks. Two
details are load-bearing:

- the service URL must end in `/v1/live` so that Kong's path join produces
  `/v1/live/{session_id}` upstream — without it every socket 404s;
- the JWT plugin needs `uri_param_names: [jwt]`, because of finding 2 below.

## Findings

### 1. A close code cannot be delivered before `accept()`

Design §10.2.3 mandates 4401/4403/4404/4409/4429, and F-04 AC-1 requires every
check to happen "before `accept()`". Those two requirements conflict: closing a
Starlette WebSocket before accepting makes the framework answer the handshake
with plain **HTTP 403**, and the client never sees a code — the protocol has
nowhere to put one until the upgrade has completed.

The resolution used in the echo (`echo/main.py::_reject`) is to keep the
*decision* before `accept()` and move only the *delivery of the verdict* after
it: accept, then immediately close with the code. No frame is ever read from or
written to a rejected socket. F-04 should adopt this and the wording of its
AC-1 should be read as "authorised before any data is exchanged" rather than
"before the handshake completes".

### 2. Browsers cannot authenticate a WebSocket with a header

The browser WebSocket API accepts no custom headers, so `Authorization: Bearer`
is unavailable. The token must travel as a query parameter (`?jwt=`) or as a
`Sec-WebSocket-Protocol` value. Only the query parameter works at the gateway —
Kong's JWT plugin reads `uri_param_names`, and the subprotocol form would need a
custom plugin. Both carriers are implemented in `echo/auth.py`; the spike
measured the query-parameter form end to end.

Consequence: the token appears in gateway access logs and browser history.
F-04 and the frontend should use short-lived, single-purpose tokens for the
socket rather than the long-lived session JWT.

### 3. The rejection shape differs by environment

The same bad token produces **HTTP 401 before the upgrade** on the Kong path and
**close code 4401 after the upgrade** on Cloud Run. The frontend must handle
both — a client that only listens for close codes will see a Cloud Run
rejection but silently miss a Kong one, and vice versa. `MeetingView`'s
reconnect logic should treat a 401/403 handshake failure and a 4401 close as
the same condition.

### 4. Pre-existing: `zorven-backend-ws` is capped at 300 s

`deployment/gcp/08-deploy-services.sh` deploys `zorven-backend-ws` with no
`--timeout` flag, so it inherits the 300 s default. Every Django Channels
WebSocket in production — the workspace real-time progress feed — is therefore
cut at five minutes, by the same mechanism measured above. This is outside
A-02's scope and is **not** fixed here; it wants its own PR adding
`--timeout=3600` to that service.

## Deliverables

| Artefact | Location |
|---|---|
| Echo service + harness + tests | `spike-ws-gateway/` |
| Kong route block for F-04 | `spike-ws-gateway/kong/oia-live.yaml` |
| `test_ws_handshake.py` stub (committed, skipped) | `spike-ws-gateway/tests/` |
| Raw measurements | `spike-ws-gateway/results/*.jsonl` (gitignored) |
| OD-1 resolution | design v2.2 §23 |

**Test coverage**: 83 tests — 47 unit (frame contracts, auth, analysis), 8
property (hypothesis: replay returns exactly the suffix with no gaps or
duplicates, buffer cap holds, seq strictly increases under interleaved
reconnects), 23 integration (real uvicorn process, real Kong container, real
JWTs, real sockets), 1 full-length soak, plus the 5 skipped F-04 stubs. A
normal run is `77 passed, 5 skipped, 1 deselected`. No mocks anywhere — there
is no `unittest.mock` import in the spike.

## What F-04 should do differently because of this spike

1. Deploy with `--timeout=3600`; treat the 300 s default as a meeting-killer.
2. Put the replay buffer and the single-writer lock in Redis from the start —
   sockets for one tenant land on different instances.
3. Reject with accept-then-close so the §10.2.3 codes actually arrive.
4. Take the JWT from `?jwt=`, and prefer a short-lived socket token.
5. Carry auth and rate limiting in `app/api/ws.py` — production has no gateway
   to inherit them from.
6. Size `concurrency` against expected simultaneous meetings; over-capacity
   fails the handshake with HTTP 500.
