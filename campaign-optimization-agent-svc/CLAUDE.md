# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**campaign-optimization-agent-svc** is a FastAPI + Celery microservice that continuously monitors and optimizes live Meta Ads campaigns. It is **WF3 Agent 3.4** -- the fourth agent in Workflow 3: Meta Ads Campaign Management, and the platform's ONLY Celery Beat scheduled worker.

**SAFETY-CRITICAL**: This agent modifies live ad spend. A 3-layer guardrail system (Input/Decision/Output) with 24 named rules ensures no optimization action exceeds safety thresholds. Campaign-level changes always require manual human approval.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes: Live campaign performance data (Meta Insights API), campaign registry (Django backend), tenant optimization config
- Produces: Optimization recommendations, autonomous budget/status adjustments (within guardrails), creative refresh requests (to CGA :8042), performance reports
- Powered by Anthropic Claude Sonnet 4 (analysis narratives) + Meta Marketing API v21.0
- Three-process architecture: Celery Beat (scheduler) + Celery Worker (execution) + FastAPI (approval API + health)

## Build, Run, and Test

```bash
# Install dependencies
pip install -r requirements.txt

# Run the service (all 3 processes)
uvicorn app.main:app --host 0.0.0.0 --port 8044 --reload      # API server
celery -A app.celery_app worker -l info                         # Worker
celery -A app.celery_app beat -l info                           # Scheduler

# Run tests
pytest tests/ -v                       # All tests
pytest tests/ -m "not integration" -v  # Unit only
pytest tests/test_routes.py -v         # Single file

# Format
black app/ tests/
```

## Architecture

### Three-Process Model

```
Process 1: Celery Beat (scheduler)
  - optimization-tick-hourly: every 3600s (campaigns < 7 days old)
  - optimization-tick-4h: every 14400s (campaigns 7-30 days old)
  - optimization-tick-daily: crontab 06:00 UTC (campaigns > 30 days old)
  - expire-stale-recommendations: every 3600s

Process 2: Celery Worker
  - run_optimization_tick(campaign_age_min_days, campaign_age_max_days)
  - expire_stale_recommendations()

Process 3: FastAPI (port 8044)
  - GET /health
  - GET /v1/campaigns/{id}/recommendations
  - POST /v1/recommendations/{id}/approve
  - POST /v1/recommendations/{id}/reject
  - POST /v1/recommendations/{id}/modify
  - POST /v1/recommendations/batch-approve
  - GET /v1/campaigns/{id}/performance
  - POST /v1/tick/trigger (manual trigger for testing)
```

### Optimization Tick Flow

```
discover_active_campaigns → for each campaign:
  → input guardrails (IG-01..08)
  → fetch_campaign_insights (Meta Insights API)
  → analyze_campaign (CPA, ROAS, CTR trends, frequency, pacing)
  → detect_fatigue (rolling 3-day CTR vs peak)
  → analyze_budget (reallocation, dayparting)
  → generate_recommendations (action + rationale + projected impact)
  → decision guardrails (PG-01..10)
  → execute_autonomous OR queue for approval
  → verify_action (read-back from Meta API)
  → persist_tick_results (callback to Django)
```

### Directory Structure

```
app/
  main.py                        # FastAPI app + lifespan
  celery_app.py                  # Celery Beat + Worker configuration
  tasks.py                       # Celery task definitions
  api/
    routes.py                    # /health, /v1/* approval + performance endpoints
    schemas.py                   # Pydantic v2 request/response models
    auth.py                      # X-Service-Token + X-Tenant-ID verification
  core/
    config.py                    # Settings with COA_ env prefix
    logging_config.py
  cache/
    redis_manager.py             # Async Redis (fail-open, DB 24)
  messaging/
    kafka_producer.py            # Trace, Audit, Event producers
    kafka_consumer.py            # Spend milestone consumer (self-trigger)
    event_emitter.py             # Internal event bus (EVT-050..061)
  logic/
    guardrails.py                # 3-layer: Input (IG), Decision (PG), Output (OG)
    circuit_breaker.py           # 5 named breakers
    state_machine.py             # Per-campaign tick state machine
  services/
    tick_executor.py             # Main orchestration loop
    campaign_discovery.py        # SKL-COA-01: discover active campaigns
    meta_insights_client.py      # SKL-COA-02: fetch Meta Insights
    performance_analyzer.py      # SKL-COA-03: CPA/ROAS/CTR analysis
    fatigue_detector.py          # SKL-COA-04: creative fatigue detection
    budget_analyzer.py           # SKL-COA-05: budget reallocation
    recommendation_generator.py  # SKL-COA-06: generate recommendations
    autonomous_executor.py       # SKL-COA-07: execute within guardrails
    meta_management_client.py    # SKL-COA-07: Meta Management API writer
    approval_handler.py          # SKL-COA-09: human approval processing
    optimization_verifier.py     # SKL-COA-10: verify Meta API writes
    optimization_persister.py    # SKL-COA-11: persist outcomes + callbacks
    reporter.py                  # SKL-COA-13: performance report generation
    anthropic_client.py          # Claude Sonnet 4 wrapper
    callback_client.py           # HTTP callbacks to Django backend
```

### Circuit Breakers

| Name | Threshold | Action on Trip |
|------|-----------|----------------|
| meta_insights | 3 failures/60s | SKIP campaign |
| meta_management | 2 failures/30s | STOP autonomous + ESCALATE |
| llm | 3 failures/60s | SKIP narrative |
| kafka | 3 failures/60s | Buffer to Redis |
| campaign_registry | 3 failures/60s | Log + retry next tick |

### Guardrails (24 Rules)

**Input (IG-01..08):** Campaign discovery, Meta credentials, minimum data, campaign age (<48h), cooldown (24h), daily action counter, sandbox mode, tenant config.

**Decision (PG-01..10):** Budget change limits (+20%/-50%), spend threshold (>$500 manual), campaign-level always manual, zero active guard, CPA kill confirmation (>=10 conv), reallocation balance (+-5%), creative refresh rate limit (7d), frequency validation, audit trail, first-optimization-human.

**Output (OG-01..06):** Meta API write verification, spend impact (<30%), recommendation quality, tenant isolation, data freshness (<24h), learnings persistence.

### RBAC for Approval

| Role | Action |
|------|--------|
| VIEWER | Denied |
| EDITOR | Escalated to ADMIN |
| ADMIN/OWNER | Can approve |

## Environment Variables

All use `COA_` prefix. Key settings:
- `COA_REDIS_URL` -- Redis DB 24
- `COA_ANTHROPIC_API_KEY` -- Claude Sonnet 4 (analysis narratives)
- `COA_META_ADS_SANDBOX_MODE` -- Default: true (stub data)
- `COA_META_API_VERSION` -- Default: v21.0
- `COA_SERVICE_TOKEN` -- X-Service-Token auth
- `COA_BACKEND_URL` -- Django backend for callbacks + campaign discovery
- `COA_BACKEND_SERVICE_TOKEN` -- Token for callback auth
- `COA_CELERY_BROKER_URL` -- Redis DB 24 (Celery broker)
- `COA_CGA_SERVICE_URL` -- Creative Generation Agent for refresh requests
- `COA_MAX_DAILY_BUDGET_INCREASE_PCT` -- Default: 20
- `COA_MAX_DAILY_BUDGET_DECREASE_PCT` -- Default: 50
- `COA_CPA_KILL_MULTIPLIER` -- Default: 2.0
- `COA_ROAS_SCALE_THRESHOLD` -- Default: 1.5
- `COA_OPTIMIZATION_COOLDOWN_HOURS` -- Default: 24
- `COA_MAX_AUTO_ACTIONS_PER_DAY` -- Default: 10
- `COA_REQUIRE_APPROVAL_ABOVE_USD` -- Default: 500.0
- `COA_CAMPAIGN_LEVEL_ALWAYS_MANUAL` -- Default: true

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `coa-optimization-audit-topic` | Produce | Optimization audit trail |
| `coa-optimization-events-topic` | Produce | Optimization events |
| `agent.optimization.spend_milestone` | Consume | Self-trigger on spend milestone |

## 13 Skills (SKL-COA-01..13)

| Phase | Skills | Description |
|-------|--------|-------------|
| Discovery | SKL-COA-01 | Campaign discovery from Django registry |
| Insights | SKL-COA-02 | Meta Insights API fetcher |
| Analysis | SKL-COA-03..05 | Performance analyzer, fatigue detector, budget analyzer |
| Recommend | SKL-COA-06 | Recommendation generator |
| Execute | SKL-COA-07 | Autonomous executor + Meta Management API |
| Approve | SKL-COA-09 | Human approval handler |
| Verify | SKL-COA-10 | Meta API write verification |
| Persist | SKL-COA-11 | Outcome persistence + callbacks |
| Report | SKL-COA-13 | Performance report generation |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All FastAPI/service operations are async
- **Celery tasks**: Sync (Celery does not support async tasks natively)
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Meta API: Stub mode (facebook_business SDK not required for tests)
- Redis: fail-open mock
- Kafka: not started in tests
- Celery: tasks tested synchronously via `.apply()`
