# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**intelligence-loop-agent-svc** is a FastAPI microservice that closes the feedback loop across WF1 (research), WF2 (strategy), and WF3 (campaigns) of the AI Brand Automator. It is **WF3.5 — Intelligence Loop Agent (ILA)**.

It consumes COA optimization learnings, CAA blueprints, CGA creative packages, and Meta Insights performance data, then extracts strategic learnings as RAG documents and (optionally) dispatches re-run requests back into WF1/WF2/WF3 — always with human approval for WF2.

Phase 3 status: **shipped** — the extractor calls Claude Sonnet 4 (with a deterministic mock fallback when no API key is configured), runs scoring + contradiction detection, and persists results + RAG documents through Django ingest endpoints. Auto-trigger (Phase 4) is gated by `ILA_DEFAULT_MODE=auto_trigger` and the `ILA_MIN_CONFIDENCE_AUTO_TRIGGER` threshold; WF2 always routes through human approval.

## Build, Run, Test

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8045 --reload
pytest tests/ -v
black app/ tests/
```

## Architecture

```
app/
  main.py                  # FastAPI app + lifespan (Redis, Kafka, extractor wiring)
  api/
    routes.py              # GET /health, POST /v1/execute (X-Service-Token)
    schemas.py             # ExecuteRequest, IntelligenceReport, LearningOut
    auth.py                # require_service_token dependency
  core/
    config.py              # Settings with ILA_ env prefix
    logging_config.py
  cache/
    redis_manager.py       # Async Redis (DB 25, fail-open) — dedup + status
  messaging/
    kafka_producer.py      # Audit + Event producers (fail-open)
  services/
    extractor.py           # IntelligenceExtractor (stub in Phase 2)
    django_client.py       # POSTs to /api/v1/intelligence-loop/ingest/...
```

## Environment Variables (ILA_ prefix)

| Var | Default | Purpose |
|-----|---------|---------|
| `ILA_PORT` | 8045 | HTTP port |
| `ILA_REDIS_URL` | `redis://localhost:6379/25` | Redis DB 25 (dedup, status) |
| `ILA_SERVICE_TOKEN` | `dev-service-token` | X-Service-Token validation |
| `ILA_BACKEND_URL` | `http://localhost:8001` | Django backend |
| `ILA_BACKEND_SERVICE_TOKEN` | `dev-service-token` | Token sent to Django ingest endpoints |
| `ILA_ANTHROPIC_API_KEY` | `""` | Claude Sonnet 4 (Phase 3) |
| `ILA_KAFKA_BOOTSTRAP_SERVERS` | `""` | Optional, fail-open if empty |
| `ILA_DEFAULT_MODE` | `store_only` | `store_only` or `auto_trigger` |
| `ILA_MIN_CONFIDENCE_AUTO_TRIGGER` | 75 | Min confidence to auto-fire WF1/WF3 |
| `ILA_WF2_APPROVAL_TIMEOUT_HOURS` | 72 | Pending WF2 request expiry |

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | Liveness |
| POST | `/v1/execute` | `X-Service-Token` | Orchestrator entry point — runs extractor, persists via Django ingest, returns `IntelligenceReport` |

`/v1/execute` is **synchronous** — the orchestrator wraps it in its own external-node handler.

## Idempotency

`RedisManager.set_dedup(tenant, job_id)` uses `SET NX` with 24h TTL on `ila:{tid}:dedup:{job_id}`. Duplicate jobs return `status=skipped` but still produce a fresh report (the orchestrator may retry).

## Persistence Path

ILA never writes to Postgres directly. It posts the intelligence report + learnings to Django:

```
POST /api/v1/intelligence-loop/ingest/intelligence-report/
Headers: X-Service-Token, X-Tenant-ID
```

Django creates `CampaignIntelligence`, `LearningRecord`, and `LearningDocument` rows. The `LearningDocument` post_save signal in `rag_index/signals.py` then queues a Celery task to sync to Vertex AI per-tenant data stores.

## Testing Patterns

- `TestClient` with `app.state` patched in `conftest.py` to bypass real Redis/Kafka/HTTP.
- Async services mocked with `unittest.mock.AsyncMock`.
- No `@pytest.mark.integration` tests yet — Phase 3+ will add them.

## Code Style

- Black, 88-char lines, Python 3.12.
- All FastAPI routes and service methods are async.
- Fail-open everywhere external (Redis, Kafka, Django HTTP) — never block extraction on infra hiccups.
