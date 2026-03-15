# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**voc-agent-svc** is a FastAPI microservice that aggregates and analyzes customer feedback from internal (Odoo ERP) and external (reviews, social media, forums) channels into actionable Voice of Customer intelligence. It is the 5th and final agent in Workflow 1: Brand Discovery & Research.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Receives cumulative outputs from 4 upstream agents: MRA, CIA, APA, TCIA
- Produces: sentiment analysis, theme clusters, NPS trends, pain point rankings, VoC-to-strategy bridge
- Powered by Anthropic Claude Sonnet 4 for LLM analysis

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # adds pytest, black, mypy

# Run the service (port 8025)
uvicorn app.main:app --host 0.0.0.0 --port 8025 --reload

# Run tests
pytest tests/ -v                       # All tests
pytest tests/ -m "not integration" -v  # Unit only
pytest tests/test_health.py -v         # Single file
pytest tests/test_skills/ -v           # All skill tests

# Format & lint
black app/ tests/
mypy app/ --strict
```

## Architecture

### Directory Structure

```
app/
  main.py                    # FastAPI app + lifespan (DI wiring)
  api/
    routes.py                # /health, /v1/execute, /v1/voc
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with VOCA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 15)
  circuit_breaker/
    breaker.py               # CircuitBreaker (CLOSED/OPEN/HALF_OPEN)
  events/
    catalog.py               # EventType enum (EVT-001..021)
    emitter.py               # EventEmitter
  rbac/
    engine.py                # RBACEngine + 14-skill permission matrix
  messaging/
    kafka_producer.py        # Trace, Audit, Alert producers
    kafka_consumer.py        # ScheduledScanConsumer
    ingestion_consumer.py    # OdooEventConsumer (continuous ingestion)
    ingestion_poller.py      # Polling fallback
    ingestion_mode.py        # Kafka↔polling mode manager
    schemas.py               # Kafka message schemas
  registry/
    feedback_registry.py     # Redis Sorted Set + Hash feedback store
    models.py                # Domain models (FeedbackItem, etc.)
  services/
    voc_executor.py          # Executor (cache → analyze → cache → audit)
    api_clients.py           # TavilySearchClient, WebScraperClient
    odoo_rpc_client.py       # Odoo XML-RPC (read-only)
    gcs_client.py            # GCS report persistence
  logic/
    voc_analyzer.py          # PAOR engine (state machine)
    guardrails.py            # Three-layer guardrails (27 rules)
  skills/
    base.py                  # BaseSkill ABC
    models.py                # SkillMeta, SkillContext, SkillResult
    registry.py              # SkillRegistry
    # 14 skill implementations (SKL-VoCA-01..14)
```

### Key Components

**VoCAExecutor** (`app/services/voc_executor.py`): Thin wrapper — cache check → delegate to VoCAAnalyzer → cache result → emit audit/trace events.

**VoCAAnalyzer** (`app/logic/voc_analyzer.py`): PAOR engine with state machine: DETECTING_MODE → PLANNING → [INGESTING] → MINING → ANALYZING → OUTPUT_CHECK → PERSISTING → COMPLETED.

**14 Skills**: Odoo ingestion (01-04, Full Mode only), external research (05-08), LLM analysis (09-12), persistence/escalation (13-14).

**Operating Modes**: Full Mode (Odoo enabled, all 14 skills) vs External-Only Mode (skills 01-04 skipped, VoC health score capped at 70).

### Guardrails

- **Input (10 rules)**: Prompt injection, PII redaction, tenant validation, rate limiting, bot detection
- **Plan+Tool (9 rules)**: RBAC enforcement, budget guard (100K tokens), feedback cap (5K items), Odoo read-only
- **Output (8 rules)**: Grounding check, PII scrub, defamation prevention, customer privacy shield

### RBAC

4 roles (OWNER, ADMIN, EDITOR, VIEWER) × 14 skills. VIEWER denied on Odoo (01-03), analysis (09-12), persister (13).

## Environment Variables

All use `VOCA_` prefix. Key settings:
- `VOCA_REDIS_URL` — Redis DB 15
- `VOCA_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `VOCA_TAVILY_API_KEY` — Web search
- `VOCA_ODOO_ENABLED` — Full Mode toggle
- `VOCA_SERVICE_TOKEN` — X-Service-Token auth
- `VOCA_TOKEN_BUDGET_PER_SESSION` — 100K tokens
- `VOCA_MAX_FEEDBACK_ITEMS` — 5000 items
- `VOCA_VOC_HEALTH_NPS_WEIGHT` — 0.50 default

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `voc-audit-topic` | Produce | Audit trail |
| `voc-insights-topic` | Produce | VoC insight alerts |
| `agent.commands.voice-of-customer-agent` | Consume | Scheduled scans |
| `odoo.events.<tid>` | Consume | Continuous ingestion |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Type checking**: mypy strict mode
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Tavily: mocked search client
- Redis: fail-open mock
- Odoo: mocked XML-RPC client
- Kafka: not started in tests
