# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ad-publishing-agent-svc** is a FastAPI microservice that translates approved creative packages and campaign blueprints into live Meta Ads API objects. It is **WF3 Agent 3.3** — the third and final agent in Workflow 3: Meta Ads Campaign Management.

**SAFETY-CRITICAL**: This is the ONLY agent in the platform that spends real money. A mandatory, hardcoded human approval gate ensures no ad goes live without explicit human confirmation.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes: CAA campaign blueprint (:8041) + CGA creative packages (:8042) + APA personas (:8023) + Company model + Meta credentials
- Produces: Live Meta Ads campaigns (PAUSED → approved → ACTIVE), targeting specs, uploaded creatives, published ads
- Powered by Anthropic Claude Sonnet 4 (targeting translation) + Meta Marketing API v21.0
- Two-phase execution: Phase A (execute → awaiting_approval), Phase B (approve → publish + verify)

## Build, Run, and Test

```bash
# Install dependencies
pip install -r requirements.txt

# Run the service (port 8043)
uvicorn app.main:app --host 0.0.0.0 --port 8043 --reload

# Run tests
pytest tests/ -v                       # All tests
pytest tests/ -m "not integration" -v  # Unit only
pytest tests/test_routes.py -v         # Single file

# Format
black app/ tests/
```

## Architecture

### Two-Phase Execution Model

```
Phase A: POST /v1/execute
  → Context load (CAA + CGA + personas + credentials)
  → Input guardrails (IG-08..12)
  → Create campaign PAUSED
  → Translate targeting (Claude Sonnet 4)
  → Upload creatives (GCS → Meta)
  → Assemble ads + generate previews
  → Create approval request (24h TTL)
  → Return status="awaiting_approval"

Phase B: POST /v1/approve
  → RBAC check (VIEWER denied, EDITOR escalated, ADMIN approves)
  → Production double-confirm if not sandbox
  → Activate campaign + ad sets
  → Verify entities
  → Write registry + callback
```

### Directory Structure

```
app/
  main.py                    # FastAPI app + lifespan
  api/
    routes.py                # /health, /v1/execute, /v1/approve, /v1/approvals/*
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with ADPUB_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 23)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus (EVT-APA33-001..026)
  services/
    adpub_executor.py        # Executor (Phase A: execute, Phase B: resume_after_approval)
    adpub_analyzer.py        # 7-phase engine (phases 1-4 prepare, 6-7 publish)
    approval_manager.py      # Approval lifecycle, RBAC, expiry, partial approval
    meta_api_client.py       # Meta Marketing API wrapper (facebook_business SDK)
    anthropic_client.py      # Claude Sonnet 4 wrapper (targeting translation)
    context_loader.py        # Load CAA + CGA + persona + credentials from previous_outputs
    targeting_translator.py  # Persona → Meta targeting spec (LLM + rule-based fallback)
  logic/
    guardrails.py            # Input/Plan/Output guardrails
    circuit_breaker.py       # Per-API circuit breakers (4 named)
    rollback.py              # Entity tracker + pause-in-reverse-order rollback
```

### Circuit Breakers

| Name | Threshold | Action on Trip |
|------|-----------|----------------|
| meta_campaign | 3 failures/60s | ESCALATE |
| meta_ad_set | 3 failures/60s | ROLLBACK + ESCALATE |
| meta_ad_image | 5 failures/60s | RETRY |
| meta_ad | 2 failures/30s | ROLLBACK ALL + ESCALATE (strictest) |

### RBAC for Approval

| Role | Action |
|------|--------|
| VIEWER | Denied |
| EDITOR | Escalated to ADMIN |
| ADMIN | Can approve (production requires double-confirm) |

## Environment Variables

All use `ADPUB_` prefix. Key settings:
- `ADPUB_REDIS_URL` — Redis DB 23
- `ADPUB_ANTHROPIC_API_KEY` — Claude Sonnet 4 (targeting translation)
- `ADPUB_META_ADS_SANDBOX_MODE` — Default: true (no real spend)
- `ADPUB_META_APP_ID`, `ADPUB_META_APP_SECRET` — Meta Marketing API
- `ADPUB_META_API_VERSION` — Default: v21.0
- `ADPUB_SERVICE_TOKEN` — X-Service-Token auth
- `ADPUB_BACKEND_URL` — Django backend for callbacks
- `ADPUB_BACKEND_SERVICE_TOKEN` — Token for callback auth
- `ADPUB_GCS_PROJECT_ID`, `ADPUB_GCS_BUCKET_NAME` — GCS (read creative images)
- `ADPUB_DAILY_SPEND_CAP_USD` — Default: 500.0
- `ADPUB_MAX_CAMPAIGN_BUDGET_USD` — Default: 10000.0
- `ADPUB_APPROVAL_EXPIRY_SECONDS` — Default: 86400 (24h)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `apa33-publishing-audit-topic` | Produce | Publishing audit trail |
| `apa33-publishing-events-topic` | Produce | Publishing events |

## 12 Skills (SKL-APA33-01..12)

| Phase | Skills | Description |
|-------|--------|-------------|
| Context | SKL-APA33-01..02 | Context loader, account validator |
| Campaign | SKL-APA33-03..04 | Campaign creator (PAUSED), ad set creator |
| Targeting | SKL-APA33-05 | Persona → Meta targeting translation |
| Creative | SKL-APA33-06..07 | Creative uploader, ad assembler |
| Approval | SKL-APA33-08 | MANDATORY human approval gate |
| Publish | SKL-APA33-09..10 | Meta publisher, verifier |
| Registry | SKL-APA33-11..12 | Registry writer, human escalation |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Meta API: Stub mode (facebook_business SDK not required for tests)
- Redis: fail-open mock
- Kafka: not started in tests
