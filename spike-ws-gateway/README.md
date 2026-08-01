# spike-ws-gateway — A-02

Timeboxed spike proving that an authenticated WebSocket upgrade reaches a
FastAPI service and holds open for a full meeting, on both deployment paths.
Deliverable is `docs/spikes/A-02-gateway-websocket-note.md` plus a resolved
OD-1 in the design document.

**This directory is disposable.** It is not in `docker-compose.yml`, not in
`docker-publish.yml`, not in the `deploy-gcp.yml` matrix. Delete it once F-04
has taken what it needs.

## Why two paths

| Path | Topology | Gateway |
|---|---|---|
| Production | browser → Google Front End → Cloud Run | none — Kong is not deployed to Cloud Run |
| Dev tier / local | browser → Kong → service :8120 | Kong, DB-less declarative config |

`deploy-gcp.yml` maps 31 images to Cloud Run services and none of them is
Kong, so auth and rate limiting have nowhere to run in production except the
service itself. The two paths therefore answer AC-1 differently and OD-1 needs
an answer per environment.

## Layout

```
echo/       throwaway service — the §10.2.3 handshake, close codes, seq series
            and reconnect replay, with no STT, Redis or model behind them
harness/    probes (handshake, reject, soak, reconnect, concurrency) and the
            summariser that turns their JSONL into the note's percentiles
kong/       declarative fragment — the block F-04 merges into
            deployment/docker/kong/kong.yaml
tests/      unit, property, integration and soak; nothing is mocked
results/    measurement JSONL (gitignored)
```

## Running it

```bash
cd spike-ws-gateway
pip install -r requirements.txt

# Everything except the 45-minute soak. Starts a real uvicorn and a real
# Kong container; skips the Kong tests if docker is unavailable.
pytest -q -m "not slow"

# The full 45-minute meeting, through Kong
pytest tests/test_soak.py -m slow -q

# Probe a deployed target directly
python -m harness.probe handshake --url wss://<host> --secret <jwt-secret> \
    --out results/run.jsonl
python -m harness.probe soak --url ws://127.0.0.1:8000 \
    --path /api/v1/agents/onboarding/live --minutes 45 \
    --secret <jwt-secret> --out results/kong.jsonl
python -m harness.analyze results/run.jsonl --budget-ms 2000
```

`--path` matters: the service publishes `/v1/live`, the gateway publishes
`/api/v1/agents/onboarding/live`. Pointing a probe at the wrong one produces a
404 from Kong (no route matched) or a 403 from Starlette (no WebSocket route
matched), neither of which is an authentication result.

## What F-04 inherits

- `tests/test_ws_handshake.py` — the stub the backlog asks A-02 to commit.
- `echo/frames.py` — the §10.2.3 frame models and close codes.
- `echo/replay.py` — the resume/replay interface, to be re-backed by a capped
  Redis list under `oia:v1:{tenant}:live:{session_id}:frames` (DB 2 per
  ERRATA-01, not DB 27).
- `echo/auth.py` — token extraction for both carriers.
- `kong/oia-live.yaml` — the gateway block, already carrying the JWT plugin
  that the existing `workspace-ws-service` block lacks.

Three findings in the note change F-04's shape; read it before starting.
