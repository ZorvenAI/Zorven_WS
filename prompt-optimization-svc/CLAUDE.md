# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

`prompt-optimization-svc` is the centralized prompt management and optimization platform for all 15 Zorven AI agent services. It stores every system prompt as a versioned MLflow artifact, automatically improves them over time using GEPA (Guided Evolutionary Prompt Architecture), and safely deploys improved prompts through mandatory canary deployments.

**Port:** 8110 | **Env Prefix:** `POI_` | **Redis:** DB 2 (prompt cache), DB 26 (general/Celery)

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the service (web)
uvicorn app.main:app --host 0.0.0.0 --port 8110 --reload

# Run Celery worker
celery -A app.celery_app worker -l info --concurrency=2 --max-tasks-per-child=50

# Run Celery Beat scheduler
celery -A app.celery_app beat -l info

# Run all tests
pytest tests/ -v

# Run unit tests only (no Redis/Kafka/MLflow needed)
pytest tests/ -m "not integration" -v

# Run E2E tests
pytest tests/ -m e2e -v

# Run a single test file
pytest tests/test_optimization_runner.py -v

# Run a single test by name
pytest tests/test_candidate_validator.py -k "test_rejects_below_threshold" -v

# Format code
black app/ tests/

# Database migrations
alembic upgrade head              # Apply all (also runs automatically on startup)
alembic downgrade -1              # Rollback last
alembic revision --autogenerate -m "desc"  # Auto-detect model changes
```

### Docker (PROCESS_TYPE selects mode)

```bash
PROCESS_TYPE=web docker run -p 8110:8110 prompt-optimization-svc      # FastAPI
PROCESS_TYPE=worker docker run prompt-optimization-svc                  # Celery worker
PROCESS_TYPE=beat docker run prompt-optimization-svc                    # Celery Beat
```

## Architecture

### How Prompts Flow Through the System

```
Day 1: Seed prompts registered → v1 PRODUCTION in MLflow
        ↓
Agents load prompts at runtime via AgentPromptClient:
  Redis cache (DB 2, sub-ms) → MLflow API (~50ms) → hardcoded fallback
        ↓
Weekly: Golden examples mined from high-quality production outputs
        ↓
Bi-weekly: GEPA optimization cycle runs (Celery Beat):
  1. Load golden dataset → split 80% train / 20% holdout
  2. GEPA reflection loop (Claude Sonnet 4.6 analyzes scorer feedback,
     generates improved prompt candidates, evaluates on Pareto frontier)
  3. Validate candidate on holdout set:
     - OPT-03: Must be ≥5% better aggregate score
     - OPT-04: No individual scorer can regress >3%
  4. If passes → 24h canary at 10% traffic → auto-promote or auto-rollback
```

### Directory Structure

```
app/
├── api/              # FastAPI routes (47 endpoints) + Pydantic schemas (14K LOC)
├── core/             # Config (POI_ prefix, 26 vars), logging
├── cache/            # RedisManager (DB 26), PromptCache (DB 2: cache + locks + progress)
├── models/           # SQLAlchemy: GoldenDataset, OptimizationRun, TenantConfig, SchemaSnapshot
├── services/         # MLflow registry, GEPA/joint optimizers, prompt loader, health checker
├── scorers/          # 41 scorer files across 9 families (common, caa, cga, coa, ila, wf1, wf2, baseline)
├── predict_fns/      # make_predict_fn (MLflow-backed) + make_predict_fn_from_text (inline eval)
├── logic/            # Lifecycle state machine, canary manager, approval gate, candidate validator,
│                     #   circuit breaker, guardrails (OPT-01 through OPT-12), rollback, debounce
├── registries/       # Prompt catalog (39+ prompts), context variables (~9000), optimization groups/budgets
├── datasets/         # Golden dataset seeding (56K LOC seed data), mining, sampling, synthetic context gen
├── kafka/            # Producers (Trace, Audit, Lifecycle), campaign trigger consumer
├── auth/             # RBAC (4 roles × 9 permissions via X-User-Role header)
├── tasks/            # Celery tasks: optimization runner, mining, health checks, canary checks
├── celery_app.py     # Beat schedule configuration (8 tasks)
└── main.py           # FastAPI app with 11-step async lifespan startup
```

### Lifecycle State Machine

```
DRAFT → STAGING → CANARY → PRODUCTION → ARCHIVED
                ↘ REJECTED        ↘ ROLLED_BACK
DRAFT → TENANT_OVERRIDE → ARCHIVED
```

Only one version per prompt can be PRODUCTION at a time. Servable states: `{PRODUCTION, CANARY, TENANT_OVERRIDE}`. Kafka lifecycle events emitted on every transition.

### GEPA Optimization Pipeline (optimization_runner.py)

The 15-step pipeline orchestrated as async state transitions:

```
QUEUED → ACQUIRING_LOCK → LOADING_DATA → OPTIMIZING → VALIDATING
  → PENDING_APPROVAL (critical agents or OPT-04 regression)
  → CANARY (10% traffic, 24h)
  → COMPLETED
```

Key guardrails enforced at each stage:
- **OPT-01**: Minimum 3 golden examples
- **OPT-02**: $25/agent cost cap
- **OPT-03**: ≥5% aggregate improvement required (candidate_validator.py)
- **OPT-04**: >3% individual scorer regression → PENDING_APPROVAL
- **OPT-06**: Prompt length < 3× original
- **OPT-07**: Redis distributed lock per optimization group
- **OPT-09**: 12-pattern prompt injection scan
- **OPT-10**: Tenant data isolation
- **OPT-11**: Template placeholder invariance
- **OPT-12**: Schema preamble protection

### Agent Integration

All 15 agent services have their own `app/prompts/loader.py` (AgentPromptClient) and `app/prompts/invalidator.py` (Kafka-based cache invalidation). The orchestrator doesn't interact with prompts — each agent loads its own prompt at execution time.

### Celery Beat Schedule

| Task | Schedule | Purpose |
|------|----------|---------|
| `mine-golden-examples-weekly` | Saturday 07:00 UTC | Mine quality examples from production |
| `optimize-wf1-pipeline-monthly` | 2nd Sunday 06:00 UTC | WF1 agents (MRA, CIA, APA, TCIA, VoCA) |
| `optimize-wf2-pipeline-monthly` | 3rd Sunday 06:00 UTC | WF2 agents (BPA, BAA, BPV, NTA, BSA) |
| `optimize-wf3-creative-pipeline` | Sunday 06:00 UTC | WF3 creative agents (CAA, CGA, ADPUB) |
| `optimize-wf3-optimization-loop` | Sunday 06:30 UTC | WF3 optimization agents (COA, ILA) |
| `optimize-oia-pipeline-monthly` | 4th Sunday 06:00 UTC | OIA onboarding agents |
| `prompt-health-check-daily` | Daily 10:00 UTC | Score PRODUCTION prompts, auto-rollback on >15% regression |
| `canary-health-check` | Every 15 min | Monitor active canaries, auto-promote/rollback |

Monthly tasks self-guard for the correct week (Celery crontab uses OR semantics).

## Key Environment Variables

```bash
POI_MLFLOW_TRACKING_URI=http://mlflow-server:5000    # MLflow server
POI_DATABASE_URL=postgresql://mlflow:mlflow@mlflow-db:5432/mlflow  # Shared MLflow DB
POI_REDIS_URL=redis://localhost:6379/26               # General cache + Celery broker
POI_PROMPT_CACHE_REDIS_URL=redis://localhost:6379/2   # Prompt cache, locks, progress
POI_KAFKA_BOOTSTRAP_SERVERS=                          # Empty = Kafka disabled
POI_ANTHROPIC_API_KEY=                                # Required for GEPA optimization
POI_CELERY_BROKER_URL=redis://localhost:6379/26       # Celery broker
POI_GEPA_MODEL_NAME=claude-sonnet-4-6                 # GEPA reflection model
POI_DEFAULT_OPTIMIZATION_BUDGET=200                   # Max metric calls per agent
POI_OPTIMIZATION_COST_CAP_USD=25.0                    # Per-agent cost cap (OPT-02)
POI_CANARY_TRAFFIC_PCT=0.10                           # 10% canary traffic
POI_CANARY_DURATION_HOURS=24                          # Canary window
POI_CRITICAL_AGENTS=adpub,coa                         # Require human approval
POI_VALIDATION_HOLDOUT_PCT=0.2                        # 20% holdout for validation
POI_VALIDATION_IMPROVEMENT_THRESHOLD=0.05             # OPT-03: 5% minimum improvement
POI_VALIDATION_REGRESSION_THRESHOLD=0.03              # OPT-04: 3% max regression
```

See the [Operational Runbook](docs/operational_runbook.md) for the full list of 26 variables.

## Database (Alembic)

Schema: `prompt_optimization` within the shared MLflow PostgreSQL database. 4 migrations (golden_datasets, optimization_runs, tenant_config, schema_snapshots). Migrations run automatically on startup via `_run_migrations()` in `main.py`.

## Testing Conventions

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorators needed
- Markers: `integration` (requires Redis/MLflow), `e2e` (full pipeline), `property` (Hypothesis)
- Coverage threshold: 60% (source: `app/`, excludes `alembic/`)
- 159 test files across unit, integration, and E2E suites

## Redis Key Patterns

- `poi:prompt:{name}:{version}` — Cached prompt templates (DB 2, 300s TTL)
- `poi:optimization_lock:{group_name}` — Distributed lock (DB 2, 2h TTL)
- `poi:optimization_progress:{group_name}` — Run progress hash (DB 2, 24h TTL)
- `poi:canary:{prompt_name}` — Active canary state (DB 2)
- `poi:canary_metrics:{prompt_name}:v{version}` — Per-version metrics (DB 2, 30d TTL)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `prompt-lifecycle-events` | Produce | State transitions (promoted, rolled_back, etc.) |
| `prompt-optimization-audit` | Produce | Optimization run audit trail |
| `agent-trace-topic` | Produce | GEPA run traces |
| `campaign-completion-events` | Consume | Trigger re-optimization on campaign completion |
