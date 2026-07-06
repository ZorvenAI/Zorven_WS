# Operational Runbook: prompt-optimization-svc

> For on-call engineers, SRE, and platform leads.
> Covers incident response, recovery procedures, and operational reference.

---

## 1. Service Overview

| Attribute | Value |
|-----------|-------|
| **Service** | prompt-optimization-svc |
| **Port** | 8110 |
| **Env Prefix** | `POI_` |
| **Redis DB 2** | Prompt cache, optimization locks, progress tracking |
| **Redis DB 26** | General service cache, rate-limiting, Celery broker |
| **Agents Served** | 15 Zorven agents across WF1, WF2, WF3 |

### Three-Tier Prompt Resolution

```mermaid
flowchart LR
    A[Agent Request] --> B{Tier 1: Redis Cache}
    B -->|HIT| C[Return Template]
    B -->|MISS| D{Tier 2: MLflow API}
    D -->|HIT| E[Cache + Return]
    D -->|MISS / Circuit Open| F[Tier 3: Fallback Template]
    F --> G[Return Fallback + Warning]
```

- **Tier 1** — Redis cache (sub-ms). Checks tenant override first (`prompt:<name>:tenant:<tid>`), then global (`prompt:<name>:production`).
- **Tier 2** — MLflow API (~50ms). Protected by circuit breaker. On success, writes to cache.
- **Tier 3** — Hardcoded fallback template. Increments `poi_prompt_fallback_usage` counter.

### Health Endpoint

```bash
curl http://localhost:8110/health
```

```json
{
  "status": "healthy",
  "dependencies": [
    {"name": "mlflow", "status": "up", "latency_ms": 12.3},
    {"name": "redis", "status": "up", "latency_ms": 1.2},
    {"name": "kafka", "status": "disabled"},
    {"name": "postgres", "status": "up", "latency_ms": 8.5}
  ]
}
```

- `status`: `healthy` (all required up), `degraded` (optional down), `unhealthy` (required down)
- **Required:** MLflow, Redis
- **Optional:** Kafka, PostgreSQL

---

## 2. MLflow Recovery and Circuit Breaker

### Circuit Breaker States

The circuit breaker is an in-memory, per-process state machine that protects MLflow tier 2 resolution.

```mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN : Failures >= 5 min
    OPEN --> HALF_OPEN : After 60s probe interval
    HALF_OPEN --> CLOSED : Probe success
    HALF_OPEN --> OPEN : Probe failure
```

| Parameter | Default | Env Var |
|-----------|---------|---------|
| Failure threshold | 300s (5 min) | `POI_CIRCUIT_BREAKER_FAILURE_THRESHOLD_SECONDS` |
| Probe interval | 60s | `POI_CIRCUIT_BREAKER_HALF_OPEN_INTERVAL_SECONDS` |

### MLflow Down — Incident Response

1. **Detection**: `poi_circuit_breaker_state` gauge = 1.0 (OPEN), or `poi_mlflow_server_health` = 0
2. **Impact**: Tier 2 resolution skipped. Agents served from Redis cache (Tier 1) or fallback (Tier 3). No data loss.
3. **Triage**:
   ```bash
   # Check MLflow health
   curl $POI_MLFLOW_TRACKING_URI/health

   # Check circuit breaker state
   curl http://localhost:8110/metrics | grep poi_circuit_breaker_state

   # Check fallback usage spike
   curl http://localhost:8110/metrics | grep poi_prompt_fallback_usage
   ```
4. **Recovery**: Once MLflow is back, the circuit breaker automatically transitions OPEN -> HALF_OPEN (after 60s) -> CLOSED (on successful probe). No manual intervention needed.
5. **Manual reset**: Restart the service process to reset the in-memory breaker to CLOSED.

### MLflow Connection Details

- **URI**: `POI_MLFLOW_TRACKING_URI` (default: `http://mlflow-server:5000`)
- **Backend store**: `POI_DATABASE_URL` (shared PostgreSQL)
- **Client timeout**: 5s (httpx)
- **Fail-open**: All registry methods return None on exception

---

## 3. Redis Cache Flush

### Key Patterns (Redis DB 2)

| Pattern | Purpose | Default TTL |
|---------|---------|-------------|
| `prompt:<name>:production` | Global production prompt | 300s |
| `prompt:<name>:tenant:<tid>` | Tenant-specific override | 300s |
| `prompt:canary:<name>` | Canary deployment state | 86400s (24h) |
| `prompt:metrics:<name>:v<version>` | Scorer metrics per version | 30 days |
| `prompt:optimization:lock:<group>` | Distributed optimization lock | 7200s (2h) |
| `prompt:optimization:progress:<run_id>` | Optimization run progress | 86400s (24h) |

### Flush Procedures

**Flush a single prompt (invalidate all cached versions):**

```bash
# Via API (recommended)
# Triggers invalidate_prompt() which deletes production + all tenant overrides
curl -X DELETE http://localhost:8110/v1/prompts/<name>/cache

# Via Redis CLI (manual, uses SCAN to avoid blocking)
redis-cli -n 2 --scan --pattern "prompt:<name>:*" | xargs redis-cli -n 2 DEL
```

**Flush all cached prompts (emergency):**

```bash
# Scan and delete all prompt keys
redis-cli -n 2 --scan --pattern "prompt:*:production" | xargs redis-cli -n 2 DEL
redis-cli -n 2 --scan --pattern "prompt:*:tenant:*" | xargs redis-cli -n 2 DEL
```

**Clear stuck optimization locks:**

```bash
# Check who holds the lock
redis-cli -n 2 GET "prompt:optimization:lock:<group>"

# Force-release (use only if owner process is dead)
redis-cli -n 2 DEL "prompt:optimization:lock:<group>"
```

**Clear canary state (force-end canary):**

```bash
redis-cli -n 2 DEL "prompt:canary:<name>"
```

### Connection Details

- **URL**: `POI_PROMPT_CACHE_REDIS_URL` (default: `redis://localhost:6379/2`)
- **Client**: `redis.asyncio` with `decode_responses=True`
- **Lock mechanism**: Atomic `SET NX EX` with Lua compare-and-delete for release

---

## 4. Kafka Consumer Lag Handling

### Topics

| Topic | Retention | Producer | Purpose |
|-------|-----------|----------|---------|
| `prompt-lifecycle-events` | 30 days | LifecycleProducer | State transitions |
| `poi-optimization-audit-topic` | 90 days | AuditProducer | Audit trail |
| `agent-trace-topic` | 7 days | TraceProducer | Trace/debug events |

### Consumer

| Consumer | Topic | Group | Purpose |
|----------|-------|-------|---------|
| CampaignCompletionTrigger | `agent.optimization.action_executed` | `prompt-reoptimization-trigger` | Trigger re-optimization on WF3 campaign events |

### Kafka Down — Impact

- **Producers**: Switch to no-op mode. Lifecycle events, audit trail, and traces are lost but do not block the pipeline. Log at INFO level.
- **Consumer**: CampaignCompletionTrigger stops receiving events. Re-optimization triggers are delayed until Kafka recovers.
- **Auto-offset-reset**: `latest` — on consumer restart, only processes new messages (no replay).

### Lag Monitoring

```bash
# Check consumer group lag
kafka-consumer-groups.sh --bootstrap-server $POI_KAFKA_BOOTSTRAP_SERVERS \
  --group prompt-reoptimization-trigger --describe

# Monitor lifecycle events
kafka-console-consumer.sh --bootstrap-server $POI_KAFKA_BOOTSTRAP_SERVERS \
  --topic prompt-lifecycle-events --from-beginning
```

### Lag Remediation

1. **High lag on `agent.optimization.action_executed`**: Consumer may be slow or stuck. Check logs for errors in CampaignCompletionTrigger.
2. **Debounce**: Re-optimization is debounced to 24 hours per tenant (`POI_REOPT_DEBOUNCE_HOURS`). High lag may cause a burst of re-optimization triggers; the debounce prevents storms.
3. **Reset consumer offset** (last resort):
   ```bash
   kafka-consumer-groups.sh --bootstrap-server $POI_KAFKA_BOOTSTRAP_SERVERS \
     --group prompt-reoptimization-trigger --reset-offsets --to-latest --execute
   ```

### Connection Details

- **Bootstrap servers**: `POI_KAFKA_BOOTSTRAP_SERVERS` (default: `""` = disabled)
- **Serialization**: JSON, UTF-8
- **If empty**: All producers and consumers disabled (no-op mode)

---

## 5. Rollback Procedure (7-Step)

The `rollback_to_version()` function in `app/logic/rollback_manager.py` implements a 7-step rollback with compensation logic.

### Prerequisites

- Target version must exist and be in `ARCHIVED` state
- Target version must be within 30-day retention window (`ARCHIVE_RETENTION_DAYS = 30`)

### Steps

```
Step 1: Verify target version exists and is ARCHIVED
        → Fail if not found or wrong state

Step 2: Check retention window (30 days)
        → Fail if archived_at > 30 days ago

Step 3: Archive current PRODUCTION version
        → Set state to ARCHIVED

Step 4: Promote target version to PRODUCTION
        → On failure: COMPENSATE — restore old version to PRODUCTION
        → On compensation failure: log CRITICAL alert

Step 5: Emit prompt.rolled_back Kafka event
        → Fire-and-forget (non-blocking)

Step 6: Invalidate Redis cache
        → Delete all cached versions via invalidate_prompt()

Step 7: Return RollbackResult
        → success=True if steps 1-4 pass
```

### Triggering Rollback

**Manual (API):**

```bash
curl -X PUT http://localhost:8110/v1/prompts/<name>/versions/<version>/rollback \
  -H "Content-Type: application/json"
```

**Automatic (health check):**

Triggered when the daily health check detects >15% regression within 48 hours of promotion. See Section 9.

### Monitoring

- `poi_auto_rollback` counter increments on auto-rollback
- ADMIN ALERT logged at ERROR level

---

## 6. Approval Workflow (CRITICAL Agents)

### Critical Agents

Two agents require mandatory human approval before promotion:

| Agent | Code | Reason |
|-------|------|--------|
| Ad Publishing | `adpub` | Controls live ad spend |
| Campaign Optimization | `coa` | Modifies campaign budgets/bids |

Auto-promotion is permanently disabled for these agents (`CRITICAL_AGENTS = ("adpub", "coa")`).

### Approval Flow

```
Optimization completes
  → requires_approval(agent_code) check
  → If True: run state → PENDING_APPROVAL
  → Human reviews candidate prompt
  → Approve: PENDING_APPROVAL → CANARY → 24h canary deployment
  → Reject: PENDING_APPROVAL → REJECTED (with reason)
```

### API Endpoints

**Approve:**

```bash
curl -X POST http://localhost:8110/v1/optimize/runs/<run_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin@zorven.ai"}'
```

**Reject:**

```bash
curl -X POST http://localhost:8110/v1/optimize/runs/<run_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin@zorven.ai", "reason": "Regression in cost efficiency"}'
```

### Kafka Events

- `optimization.run.approved` — emitted on approval
- `optimization.run.approval_rejected` — emitted on rejection

### Monitoring

Monitor runs stuck in `PENDING_APPROVAL` state. Set up an alert if any run remains pending >24 hours.

---

## 7. Lifecycle State Machine

### State Diagram

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> STAGING
    DRAFT --> TENANT_OVERRIDE
    STAGING --> CANARY
    STAGING --> REJECTED
    CANARY --> PRODUCTION
    CANARY --> ROLLED_BACK
    PRODUCTION --> ARCHIVED
    PRODUCTION --> ROLLED_BACK
    ARCHIVED --> PRODUCTION : Rollback
    TENANT_OVERRIDE --> ARCHIVED
    REJECTED --> [*]
    ROLLED_BACK --> [*]
```

### States

| State | Description | Servable |
|-------|-------------|----------|
| `DRAFT` | Initial state after registration | No |
| `STAGING` | Post-optimization, pre-validation | No |
| `CANARY` | 10% traffic for 24 hours | Yes |
| `PRODUCTION` | 100% traffic | Yes |
| `ARCHIVED` | Retained for 30 days (rollback target) | No |
| `REJECTED` | Failed validation (terminal) | No |
| `ROLLED_BACK` | Regression detected (terminal) | No |
| `TENANT_OVERRIDE` | Tenant-specific override | Yes |

### Valid Transitions

| From | To |
|------|----|
| DRAFT | STAGING, TENANT_OVERRIDE |
| STAGING | CANARY, REJECTED |
| CANARY | PRODUCTION, ROLLED_BACK |
| PRODUCTION | ARCHIVED, ROLLED_BACK |
| ARCHIVED | PRODUCTION |
| TENANT_OVERRIDE | ARCHIVED |
| REJECTED | _(terminal)_ |
| ROLLED_BACK | _(terminal)_ |

---

## 8. Canary Deployment Flow

### Canary Parameters

| Parameter | Value | Configurable |
|-----------|-------|-------------|
| Traffic split | 10% canary / 90% production | No (hardcoded) |
| Duration | 24 hours | No (hardcoded) |
| Regression threshold | 5% | Yes (`POI_CANARY_REGRESSION_THRESHOLD`) |
| Metrics retention | 30 days | Yes (`POI_CANARY_METRICS_TTL_DAYS`) |

### Canary Flow Diagram

```mermaid
flowchart TD
    A[Optimization Complete] --> B[Start Canary]
    B --> C[Store canary state in Redis]
    C --> D{Incoming Request}
    D -->|SHA-256 hash < 10%| E[Serve Canary Version]
    D -->|SHA-256 hash >= 10%| F[Serve Production Version]
    E --> G[Record Canary Metrics]
    F --> H[Record Production Metrics]
    G --> I{Check Regression}
    H --> I
    I -->|No regression| J{24h elapsed?}
    I -->|Regression > 5%| K[Auto-Rollback Canary]
    J -->|No| D
    J -->|Yes| L[Promote to Production]
    K --> M[ROLLED_BACK state]
    L --> N[Archive old Production]
```

### Traffic Routing

Deterministic via SHA-256 hash of `tenant_id`. Same tenant always gets the same routing decision for a given canary percentage.

```
bucket = int(SHA256(tenant_id)[:8], 16) % 100
is_canary = bucket < (canary_pct * 100)
```

### Redis Keys

- `prompt:canary:<name>` — canary state hash (TTL: 24h)
- `prompt:metrics:<name>:v<version>` — scorer metrics hash (TTL: 30 days)

---

## 9. Health Check and Auto-Rollback

### Schedule

| Task | Schedule | Purpose |
|------|----------|---------|
| `prompt_health_check` | Daily 10:00 UTC (06:00 ET) | Verify PRODUCTION prompts |

### Health Check Flow

1. List all registered prompts from MLflow
2. For each PRODUCTION prompt:
   - Verify loadability (can template be retrieved?)
   - Check `score_after` tag or OptimizationRun metrics for regression
3. Actions based on regression severity:

| Regression | Action | Config |
|------------|--------|--------|
| Not loadable | Trigger re-optimization | N/A |
| > 10% | Trigger re-optimization | `POI_HEALTH_CHECK_REGRESSION_THRESHOLD` |
| > 15% within 48h | **Auto-rollback** + re-optimization | `POI_AUTO_ROLLBACK_REGRESSION_THRESHOLD`, `POI_AUTO_ROLLBACK_WINDOW_HOURS` |

### Auto-Rollback Logic

When regression > 15% is detected within 48 hours of promotion:

1. Find previous ARCHIVED version (highest version below current)
2. Execute 7-step rollback (see Section 5)
3. Increment `poi_auto_rollback` Prometheus counter
4. Log ERROR: `ADMIN ALERT: Auto-rollback triggered for <name> v<old> -> v<target>`

### Monitoring

```bash
# Check auto-rollback events
curl http://localhost:8110/metrics | grep poi_auto_rollback

# Check health check results (Celery result backend)
redis-cli -n 26 --scan --pattern "celery-task-meta-*" | head -5
```

---

## 10. Prometheus Metrics and Alerting

### Metrics Endpoint

```bash
curl http://localhost:8110/metrics
```

### Metrics Reference

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `poi_prompt_load_latency_ms` | Histogram | name, tier, tenant_id | Prompt load latency |
| `poi_prompt_cache_hit` | Counter | tier, result | Cache hit/miss by tier |
| `poi_optimization_run_duration_seconds` | Histogram | agent_code, group_name | Optimization run duration |
| `poi_optimization_run_cost_usd` | Histogram | agent_code | Optimization run cost |
| `poi_prompt_improvement_pct` | Gauge | agent_code, prompt_name | Latest improvement % |
| `poi_scorer_regression_pct` | Gauge | agent_code, prompt_name | Latest regression % |
| `poi_mlflow_server_health` | Gauge | — | MLflow health (1=up, 0=down) |
| `poi_prompt_fallback_usage` | Counter | name | Fallback template usage |
| `poi_circuit_breaker_state` | Gauge | — | Circuit breaker (0=CLOSED, 1=OPEN, 2=HALF_OPEN) |
| `poi_auto_rollback` | Counter | prompt_name | Auto-rollback events |

### Recommended Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| MLflow Down | `poi_mlflow_server_health == 0` for 5+ min | P1 |
| Circuit Breaker Open | `poi_circuit_breaker_state == 1.0` | P1 |
| Auto-Rollback Triggered | `increase(poi_auto_rollback[1h]) > 0` | P1 |
| Cache Latency High | P95 of `poi_prompt_load_latency_ms` > 5ms | P2 |
| Cost Over Budget | `poi_optimization_run_cost_usd > 25.0` | P2 |
| Regression Detected | `poi_scorer_regression_pct > 10.0` | P2 |
| High Fallback Usage | `increase(poi_prompt_fallback_usage[1h]) > 100` | P2 |
| Approval Gate Backlog | Runs in PENDING_APPROVAL > 24h | P3 |

---

## 11. Celery Beat Schedule

All scheduled tasks are defined in `app/celery_app.py`.

| Task | Schedule | Time (UTC) | Time (ET) | Purpose |
|------|----------|-----------|-----------|---------|
| `mine-golden-examples-weekly` | Saturday | 07:00 | 03:00 | Mine production data for golden examples |
| `optimize-wf1-pipeline-monthly` | Sunday | 06:00 | 02:00 | Optimize WF1 discovery pipeline |
| `optimize-wf2-pipeline-monthly` | Sunday | 06:00 | 02:00 | Optimize WF2 brand strategy pipeline |
| `optimize-wf3-creative-pipeline` | Sunday | 06:00 | 02:00 | Optimize WF3 creative pipeline |
| `optimize-wf3-optimization-loop` | Sunday | 06:30 | 02:30 | Optimize WF3 optimization loop |
| `prompt-health-check-daily` | Daily | 10:00 | 06:00 | Verify PRODUCTION prompts |

### Celery Configuration

- **Broker**: `POI_CELERY_BROKER_URL` (Redis DB 26)
- **Prefetch multiplier**: 1 (one task per worker)
- **Acks late**: True (acknowledge after completion)
- **Reject on worker lost**: True

### Monitoring Celery

```bash
# Check active workers
celery -A app.celery_app inspect active

# Check scheduled tasks
celery -A app.celery_app inspect scheduled

# Check registered tasks
celery -A app.celery_app inspect registered
```

---

## 12. Configuration Reference

All environment variables use the `POI_` prefix.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `POI_HOST` | str | `0.0.0.0` | Server bind address |
| `POI_PORT` | int | `8110` | Server port |
| `POI_MLFLOW_TRACKING_URI` | str | `http://mlflow-server:5000` | MLflow tracking server |
| `POI_DATABASE_URL` | str | `postgresql://mlflow:mlflow@mlflow-db:5432/mlflow` | PostgreSQL connection |
| `POI_REDIS_URL` | str | `redis://localhost:6379/26` | General cache (DB 26) |
| `POI_PROMPT_CACHE_REDIS_URL` | str | `redis://localhost:6379/2` | Prompt cache (DB 2) |
| `POI_KAFKA_BOOTSTRAP_SERVERS` | str | `""` | Kafka (empty=disabled) |
| `POI_ANTHROPIC_API_KEY` | str | `""` | Anthropic API key |
| `POI_CORS_ORIGINS` | str | `http://localhost:3000,http://localhost:8000` | CORS origins |
| `POI_CELERY_BROKER_URL` | str | `redis://localhost:6379/26` | Celery broker |
| `POI_MINING_QUALITY_THRESHOLD` | float | `0.8` | Golden example mining quality |
| `POI_MINING_LOOKBACK_DAYS` | int | `7` | Mining lookback window |
| `POI_REOPT_QUALITY_THRESHOLD` | float | `0.7` | Re-optimization trigger threshold |
| `POI_REOPT_DEBOUNCE_HOURS` | int | `24` | Re-optimization debounce |
| `POI_CANARY_REGRESSION_THRESHOLD` | float | `0.05` | Canary regression threshold (5%) |
| `POI_CANARY_METRICS_TTL_DAYS` | int | `30` | Canary metrics retention |
| `POI_HEALTH_CHECK_REGRESSION_THRESHOLD` | float | `0.10` | Health check regression (10%) |
| `POI_VALIDATION_HOLDOUT_PCT` | float | `0.2` | Validation holdout set (20%) |
| `POI_VALIDATION_IMPROVEMENT_THRESHOLD` | float | `0.05` | Min improvement (5%) |
| `POI_VALIDATION_REGRESSION_THRESHOLD` | float | `0.03` | Max individual regression (3%) |
| `POI_OPTIMIZATION_COST_CAP_USD` | float | `25.0` | Cost cap per optimization |
| `POI_LENGTH_MULTIPLIER_LIMIT` | float | `3.0` | Length sanity multiplier |
| `POI_CIRCUIT_BREAKER_FAILURE_THRESHOLD_SECONDS` | int | `300` | Circuit breaker threshold (5 min) |
| `POI_CIRCUIT_BREAKER_HALF_OPEN_INTERVAL_SECONDS` | int | `60` | Probe interval (60s) |
| `POI_AUTO_ROLLBACK_REGRESSION_THRESHOLD` | float | `0.15` | Auto-rollback threshold (15%) |
| `POI_AUTO_ROLLBACK_WINDOW_HOURS` | int | `48` | Auto-rollback window (48h) |
| `POI_LOG_LEVEL` | str | `INFO` | Logging level |
| `POI_SERVICE_TOKEN` | str | `""` | Service authentication token |
| `POI_JWT_SECRET` | str | `""` | JWT signing secret |
