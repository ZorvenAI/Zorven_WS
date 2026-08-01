# CLAUDE.md — onboarding-intelligence-agent-svc

Guidance for Claude Code when working in this service. Read this before
modifying anything here.

## What this service is

The Onboarding Intelligence Agent (OIA) turns a recorded onboarding
conversation, the documents shown during it, and the operator's prepared
questions into a complete, provenance-tracked brand profile — without the
operator typing it, and without the agent inventing it.

One deployable, three modes, decided by entry point rather than a runtime flag:

| Mode | Entry point | Latency class | Skills |
|---|---|---|---|
| PREP | `POST /v1/execute` | ≤60 s | SKL-OIA-01, 02, 03, 15 |
| LIVE | `WS /v1/live/{session_id}` | partial ≤2 s, feedback ≤5 s p95 | SKL-OIA-04, 05, 06, 07, 16 |
| PROCESS | `POST /v1/process` | ≤5 min p95 | SKL-OIA-08 … 14 |

- **Port** 8120 · **Env prefix** `OIA_` · **Redis** DB 2 (see below)
- Design: `docs/Onboarding_Intelligence/Onboarding_Intelligence_Agent_Design_Document_v2_2.md`
- Backlog: `…_User_Story_Backlog_v2_1.md`
- **Corrections that override both: `ERRATA-01-redis-allocation.md`**

## Current state — scaffold plus the event and Redis baseline

A-05 and A-03 have landed. Working: configuration, logging, telemetry with W3C
trace propagation, the Redis pool and tenant-scoped key builders, the Kafka
producer/consumer with topic provisioning and DLQ routing, the §12 event
catalogue and emitter, and the health, readiness and metrics surface.
Everything else is a stub that **raises `NotImplementedError` by design** — a
stub returning `None` would let a later story ship a silent no-op. When you
implement one, delete the raise; do not leave it returning nothing.

Owning stories are named in each stub's docstring.

## Non-negotiables in this service

### Eviction: the shared instance is `noeviction`, and must stay that way

**AC-5 finding, recorded here because A-03 requires it.**

Measured 2026-08-01 on Memorystore `zorven-redis` (1 GB, BASIC, shared by the
whole fleet):

| | |
|---|---|
| memory in use | 7.2 MB of 1 GB (`usage_ratio` 0.007) |
| policy before | `allkeys-lru` |
| policy now | **`noeviction`** |

`allkeys-lru` evicts *any* key once memory is full, regardless of TTL — there
is no per-key exemption in Redis — so a live meeting could have lost its
transcript and resume window under memory pressure. That is a correctness bug,
not a tuning problem, which is why AC-5 says escalate rather than proceed.

The instance was at 0.7% of capacity, so `noeviction` was free to switch on:
nothing was being evicted, and there is ~140× headroom. The residual risk is
the opposite one — a *full* instance under `noeviction` rejects writes
fleet-wide instead of dropping cache keys — covered by the Cloud Monitoring
alert **"Memorystore zorven-redis memory above 75%"**, whose runbook says
plainly that reverting to `allkeys-lru` is not a fix.

A dedicated Redis instance for OIA session state was considered and rejected as
premature at ~$35–50/month while the shared instance sits at 0.7%. It remains
the escalation path if usage climbs.

`tests/integration/test_redis_isolation_live.py::test_eviction_policy_is_noeviction`
asserts the live server's policy, not a constant. If it fails, session state is
evictable again and the fix is the policy.

### Redis is DB 2 and shared — never DB 27

ERRATA-01 supersedes the design here. Production Redis is Memorystore, fixed
at 16 databases (0–15); DB 27 cannot exist. OIA shares **DB 2** with ten other
services and is isolated only by its key prefix.

- Every key this service writes starts with `oia:v1:`. No exceptions.
- Build keys through `TenantKeys` in `app/cache/redis_manager.py`, obtained
  from `RedisManager.keys_for(tenant_id)`. The tenant is a **constructor**
  argument, so a tenant-less key cannot be written — that is deliberate, per
  A-03: "a helper that can be called without a tenant will eventually be
  called without one." Never format a key inline.
- Every key carries a TTL — `maxmemory-policy allkeys-lru` is instance-wide,
  so an untrimmed key evicts another service's data.
- The prompt cache (`poi:` prefix, same DB) is **read-only**. Never write there.
- `tests/test_redis_key_isolation.py` enforces all of this by reflection over
  every builder, so a new builder is covered automatically.

### Kafka is optional

No `deployment/gcp` script provisions a broker and every deployed service sets
`*_KAFKA_ENABLED=false`. An empty `OIA_KAFKA_BOOTSTRAP_SERVERS` means "this
environment has no Kafka" and is **not** a health failure. A *configured but
unreachable* broker is. Do not make Kafka a hard dependency of `/health`.

### The health probe must stay honest

`/health` returns 200 only when every required dependency answers, and must do
so within 2 s when one is down. Both underlying checks are bounded by 2 s
socket timeouts. Do not add an unbounded check to this path.

### WebSocket constraints (from spike A-02)

Before implementing `app/api/ws.py`, read
`docs/spikes/A-02-gateway-websocket-note.md`. Three findings bind F-04:

1. A close code cannot be delivered before `accept()` — a pre-accept close
   surfaces as plain HTTP 403 and §10.2.3's 4401/4403/4404/4409 never arrive.
   Decide before accept; deliver the verdict after.
2. The JWT arrives as `?jwt=`, not a header — browsers cannot set headers on a
   WebSocket handshake.
3. Sockets land on different Cloud Run instances, so session state and the
   single-writer lock must be in Redis, not process memory.

Cloud Run also caps a WebSocket at the service request timeout: this service
deploys with `--timeout=3600`, and the 300 s default would sever meetings at
five minutes.

## Commands

```bash
cd onboarding-intelligence-agent-svc
pip install -r requirements-dev.txt

# A broker for the Kafka integration tests. Redpanda rather than the compose
# broker: Kafka-API compatible, no ZooKeeper, ~400 MB, ready in ~30 s.
docker run -d --name oia-test-kafka -p 39092:9092 --memory=700m \
  redpandadata/redpanda:v24.2.7 redpanda start --smp 1 --memory 400M \
  --overprovisioned --node-id 0 --check=false \
  --kafka-addr PLAINTEXT://0.0.0.0:9092 \
  --advertise-kafka-addr PLAINTEXT://localhost:39092

uvicorn app.main:app --host 0.0.0.0 --port 8120 --reload

pytest -q                      # everything (integration needs Redis on :6379)
pytest -m unit -q              # no network
pytest -m property -q          # hypothesis
pytest -m integration -q       # real Redis and, if present, real Kafka
pytest -m e2e -q               # real container; needs Docker

black app/ tests/ && flake8 app/ tests/ && mypy app/
```

## Conventions

- Settings come from `app/core/config.py` only — never read `os.environ`
  directly, and never inline a secret.
- Structured logging via `app/core/logging.py`. Log secret *references*, never
  values.
- Tests: no mocks. Integration tests run against real Redis; the health-down
  case points at a genuinely closed port rather than a patched client.


## Local environment traps

**A native Redis can shadow the compose one.** On macOS a Homebrew
`redis-server` bound to `127.0.0.1:6379` wins over the container's published
port, so `redis://localhost:6379` may not be the Redis in `docker-compose.yml`
— with a different `maxmemory-policy`. This was observed on 2026-08-01 and made
the eviction test pass against the wrong server. Point tests explicitly with
`OIA_TEST_REDIS_URL`, and check `redis-cli info server` if a config assertion
behaves oddly.

**The compose Kafka is heavy.** It runs ZooKeeper mode with a JVM heap and
replays every persisted partition on boot; on a loaded machine it can time out
its ZooKeeper session and crash-loop. The tests use Redpanda instead and skip
cleanly when no broker is reachable.
