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
All three live in `docs/Onboarding_Intelligence/`:

- Design: `Onboarding_Intelligence_Agent_Design_Document_v2_2.docx`
- Backlog: `Onboarding_Intelligence_Agent_User_Story_Backlog_v2_1.docx`
- Requirements: `AI_Assisted_Onboarding_Requirements_v1_3.docx`
- **Corrections that override the design: `ERRATA-01-redis-allocation.md`** (the
  one that is genuinely Markdown)

The first three are **`.docx`, not `.md`** — grep finds nothing in them, which
reads as "the design does not mention this" when it does. Extract before
searching:

```python
import zipfile
from xml.etree import ElementTree as ET
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
doc = ET.fromstring(zipfile.ZipFile(PATH).read("word/document.xml"))
text = lambda el: "".join(t.text or "" for t in el.iter(W + "t"))
# paragraphs: [text(p) for p in doc.iter(W + "p")]
# tables:     [[text(c) for c in tr.iter(W + "tc")] for tr in doc.iter(W + "tr")]
```

Paragraph iteration *does* reach table cells — Word nests each cell's text in
its own `w:p` — but it flattens them, so you get "ERR-16" and "507" as
unrelated strings. §18.4 and §5's guardrail rules are tables, and reading them
needs the row grouping: iterate `w:tr` when you care which condition maps to
which status.

## Current state — scaffold, event baseline, agent skeleton

A-05, A-03 and A-06 have landed. Working: configuration, logging, telemetry
with W3C trace propagation, the Redis pool and tenant-scoped key builders, the
Kafka producer/consumer with topic provisioning and DLQ routing, the §12 event
catalogue and emitter, the health/readiness/metrics surface, and the agent
skeleton — SkillRegistry, the ordered guardrail chain, the RBAC evaluator and
the §18.4 error taxonomy.
Everything else is a stub that **raises `NotImplementedError` by design** — a
stub returning `None` would let a later story ship a silent no-op. When you
implement one, delete the raise; do not leave it returning nothing.

Owning stories are named in each stub's docstring.

## The registry is the only way to run a skill

`SkillRegistry.execute` and `execute_stream` are the entry points. `BaseSkill`
defines `run`, `StreamingSkill` defines `stream`, and neither class is
callable — there is deliberately no convenient way to invoke a skill and skip
IG → RBAC → PG → OG.

- Skills load from `config/skills.yaml`, not from imports. A declaration whose
  class is missing fails **at startup**, naming every missing skill at once.
- Guardrail rule *bodies* are no-op stubs; M-01 fills them in through
  `GuardrailChain.register`, which replaces a rule without changing the order.
- Output guardrails run **per yielded chunk** for streaming skills. A chunk
  already delivered to the browser cannot be recalled.
- RBAC has **four** verdicts — ALLOW, DENY, ESCALATE, VIEW_RESULT — because
  §15 uses all four. The matrix is data in `app/rbac/engine.py`; keep it that
  way, or `tests/test_rbac.py` cannot sweep it exhaustively.
- The role comes from the verified JWT claim only, never a body or header.

## Error codes

`app/core/errors.py` is the single source of truth for the §18.4 taxonomy
(ERR-01 … ERR-21). The original 16 codes from the design document are
extended with ERR-17 through ERR-21 for conditions the taxonomy had no row
for, and five backlog acceptance criteria that cited the wrong code are
corrected. The full reconciliation — including the reasoning behind each
deviation — is in `docs/Onboarding_Intelligence/ERRATA-02-error-taxonomy.md`.

When a card or design section names an error code, check `errors.py` before
using it — the cards were written before the taxonomy was finalised.

## Circuit breakers (§18.2)

`config/circuit_breakers.yaml` is §18.2 transcribed verbatim; `app/circuit_breaker/breaker.py` loads it. Both arrived with **C-02**, not A-06 — the scaffolded stub named A-06 as its implementer, but A-06's acceptance criteria cover the registry, guardrail chain, RBAC evaluator and skill interfaces and never mention breakers. No story in the backlog owned this. Check the ACs, not the stub docstring, before assuming something landed.

- All seven dependencies are declared. `tavily` and `llm` have providers (`app/providers/`); the skill that calls them arrives with C-02's second PR, so until that lands the providers are exercised only by their tests.
- **State is per-process.** Cloud Run runs several instances, so a failing dependency opens N breakers independently. A shared breaker in Redis would add a hop to the very call path it protects and would fail when Redis does.
- Call `before_call()`, never `is_open`, when you are about to use a dependency — the check and the half-open trial claim must be one atomic step or concurrent callers all slip through.
- `user_message` is config, not code (§18.2: "these strings are the entire user experience of a failure"). A `null` message means invisible by design, as with `poi`.
- A missing API key is **not** a breaker failure. It degrades with a distinct reason so an operator can tell a config gap from an outage.

Providers wrap dependencies: `app/providers/tavily.py` and `app/providers/llm.py`. Both differ from `discovery-agent-svc`'s Tavily code on purpose — they use the async client (the fleet's blocks the event loop, which would stall a live meeting) and they **do not swallow failures into an empty result**, because "we could not look" and "there is nothing to find" need different operator responses.

## PREP: how a turn becomes research (C-02)

`POST /v1/execute` → `PrepExecutor` (`app/logic/prep_executor.py`, on `app.state.prep`) → `SkillRegistry.execute("SKL-OIA-01")` → `ResearchBusiness`. The executor owns the registry and the brief cache because both are decisions that move as C-03 and C-04 land, and neither belongs in an HTTP handler.

- **The model never researches.** It only organises text Tavily retrieved. A model asked to research a small business produces fluent, plausible, unsourced claims — the exact failure AC-1 exists to prevent.
- **Two grounding checks, not one.** The skill drops any fact whose `source_url` was not in the retrieved set (an invented-but-plausible citation passes a URL-shape check), and OG-01 then demotes anything still unsourced.
- **OG-01 is a real registered rule**, not logic inside the skill — installed via `GuardrailChain.register`, which replaces a body in place without reordering the layer. M-01 will extend it rather than find a no-op plus a private copy.
- **Unsourced facts are demoted, never deleted.** SKL-OIA-02 turns `open_unknowns` into questions, so a claim the agent could not source is signal, not noise.
- **A degraded brief is never cached.** It is the *absence* of research; caching it would let a one-minute Tavily outage suppress real research for the next hour with nothing to tell the operator why.
- `output.detail` is load-bearing: Django renders it into the chat bubble and falls back to "Preparation is under way." if absent.

Skills receive shared dependencies through `SkillRegistry(providers={...})`, matched against each skill's `__init__` signature. A skill that grows a dependency picks it up by adding the parameter — there is no second place to register it.

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
- The prompt cache (`prompt:` prefix, same DB) is **read-only** except for
  cache-bust DELETEs during incident recovery (L-05, §20). The
  `POST /v1/admin/cache-bust` endpoint is the only writer.
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
pytest -m load --collect-only  # list load tests (skip without OIA_LOAD_TARGET)

# Load tests — NFR performance verification against a deployed target.
# Target must run with OIA_STT_PROVIDER=fake (silent audio → fixture transcripts).
OIA_LOAD_TARGET=wss://oia.zorven.dev \
  OIA_LOAD_ENVIRONMENT=kong_dev \
  OIA_LOAD_CONCURRENCY=5 \
  OIA_LOAD_TICKET=<valid-ticket> \
  OIA_LOAD_SERVICE_TOKEN=<valid-token> \
  pytest -m load -v

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

**Never size a read window through a consumer.**
`consumer.partitions_for_topic()` reads a *local* cache and returns `None`
when this client has never asked about the topic — which is not the same as
"no partitions". Locally the cache is usually warm by luck; on a GitHub runner
a fresh, unsubscribed consumer never populates it at all, not across 120 s of
retries, and `await consumer.topics()` does not help. That asymmetry is what
made these tests pass here and fail in CI for three rounds.

Ask the admin client instead — `partitions_for()` in
`tests/integration/test_kafka_roundtrip.py` uses `describe_topics`, which also
reports the **leader**. That is the signal worth waiting on: a partition is
listed as soon as the topic is created but cannot be produced to or read from
until a leader is elected, so the leader is what separates "the topic exists"
from "the topic works". Answers are cached per run, because standing up an
admin client per read stalls the suite.

Because a warm broker hides all of this, **re-create the container before
trusting a green Kafka run**, and start the tests as soon as `rpk cluster
info` answers — which is what CI does, and is earlier than `cluster health`:

```bash
docker rm -f oia-test-kafka   # then the docker run above
```

**A skipped Kafka test is a failure, not a pass.** The `broker` fixture waits
up to 120 s for a broker that can actually serve. If `OIA_TEST_KAFKA` is set,
as CI sets it, a missing broker **fails** rather than skips — a green run that
silently covers none of AC-1 is worse than an honest red. Without that
variable, as in production where no `deployment/gcp` script provisions a
broker, skipping is correct. If you change this, keep that asymmetry.

**`consumer.stop()` can raise `CancelledError`.** A consumer built without a
`group_id` gets aiokafka's `NoGroupCoordinator`, whose `close()` cancels an
internal task and awaits it; the task only swallows the cancellation once it
has run a step, so cancelling it before the loop ever schedules it lets the
error escape. It fires whenever nothing is awaited between `start()` and
`stop()` — reproduced 30/30 on aiokafka 0.12 and 0.13. Stop consumers through
the `stop()` helper in that same file, never `await consumer.stop()` directly.
