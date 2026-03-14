# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Overview

Trend & Cultural Insights Agent (TCIA) — Agent 1.4 in the Brand Discovery & Research workflow. FastAPI microservice providing cultural trend monitoring, social media trend scanning, viral content pattern analysis, generational preference tracking, emerging slang detection, and cultural relevance scoring with brand-aware opportunity alerting.

**Port**: 8024 | **Redis DB**: 14 | **Env prefix**: `TCIA_` | **LLM**: Claude Sonnet 4

## Build & Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8024 --reload

# Tests
pytest tests/ -v                        # All tests
pytest tests/ -m "not integration" -v   # Unit only
pytest tests/test_guardrails.py -v      # Single file
pytest -k "test_harmful" -v             # By name

# Format
black app/ tests/
```

## Architecture

### Two-Layer Skill System

**Layer 1 — Orchestrator `.md` skills** (`pipeline-orchestrator-svc/skills/trend-cultural-insights.md`): Methodology guidelines injected as LLM context via `config["skill_context"]`. Describes the 10-step research + analysis methodology.

**Layer 2 — Agent Python skills** (`app/skills/`): 12 executable skill classes (SKL-TCIA-01 through SKL-TCIA-12) extending `BaseSkill` ABC. Each has RBAC, circuit breakers, timeouts.

### PAOR Engine (`app/logic/trend_analyzer.py`)

Plan-Act-Observe-Reflect pipeline with 10 steps:
1. **PLAN**: Extract upstream context (MRA market, CIA competitors, APA personas)
2. **ACT (Research)**: Parallel research via 5 Tavily-powered skills (01-05) + RAG (06)
3. **OBSERVE (Analysis)**: Sequential Claude Sonnet 4 analysis — scoring (07), persona mapping (08), alerting (09)
4. **REFLECT (Synthesis)**: Report synthesis (10), persistence (11), registry update, alert emission

### 3-Layer Guardrails (`app/logic/guardrails.py`)

- **Input** (10 rules): Injection, scam, scope, PII, tenant, size, rate limit, **harmful trend filter**, **political neutrality**, **upstream context validation**
- **Plan/Tool** (9 rules): Planning, allowlist, write RBAC, concurrency (max 8), RBAC, irreversible, budget (60K tokens), trend cap (25), alert throttle (5/day)
- **Output** (8 rules): Grounding, PII scrub, confidence, hallucination, isolation, size, **harmful trend shield**, **political balance check**

### Skill Map

| ID | Skill | Type | Dependencies |
|----|-------|------|-------------|
| SKL-TCIA-01 | SocialTrendScanner | Read | Tavily, httpx |
| SKL-TCIA-02 | CulturalShiftMonitor | Read | Tavily |
| SKL-TCIA-03 | ViralContentAnalyzer | Read | Tavily, httpx |
| SKL-TCIA-04 | GenerationalPreferenceTracker | Read | Tavily |
| SKL-TCIA-05 | SlangLanguageTracker | Read | Tavily, httpx, LLM |
| SKL-TCIA-06 | RAGContextRetrieval | Read | RAG service |
| SKL-TCIA-07 | CulturalRelevanceScorer | Analysis | Anthropic |
| SKL-TCIA-08 | TrendPersonaMapper | Analysis | Anthropic |
| SKL-TCIA-09 | OpportunityAlertGenerator | Analysis | Anthropic |
| SKL-TCIA-10 | TrendReportSynthesizer | Analysis | Anthropic |
| SKL-TCIA-11 | TrendReportPersister | Write | GCS, RAG, Kafka |
| SKL-TCIA-12 | HumanEscalation | Escalation | Kafka |

### Upstream Data Flow (MRA → CIA → APA → TCIA)

When in full pipeline (`brand-discovery-full`), TCIA receives all 3 upstream agents via `previous_outputs`:
- `market_research` → Industry context, market sizing for relevance scoring
- `competitor_intelligence` → Competitor landscape for competitive dimension scoring
- `audience_persona` → Personas for trend-persona mapping, age ranges, platform preferences

TCIA works standalone when `previous_outputs` is empty (degraded mode).

### Cultural Relevance Scoring (4-Dimension, 0-100)

- **Audience Alignment** (0-25): Overlap with APA personas
- **Competitive Landscape** (0-25): Competitor exploitation/ignoring (from CIA)
- **Brand Fit** (0-25): Alignment with brand values
- **Momentum** (0-25): Velocity and projected longevity

### Trend Registry (`app/registry/`)

Redis Hash `tcia:<tid>:registry:trends` for master trend list. Sorted Sets `tcia:<tid>:registry:scores:<slug>` for historical score tracking (90-day default retention). Velocity detection triggers events on significant score changes (±15 points).

### Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `tcia-trend-audit-topic` | Produce | Audit trail |
| `tcia-trend-alerts-topic` | Produce | Opportunity alert streaming |
| `agent.commands.trend-cultural-agent` | Consume | Scheduled scan commands (daily/weekly) |

## Key Files

| Purpose | Path |
|---------|------|
| FastAPI app + lifespan | `app/main.py` |
| API routes | `app/api/routes.py` |
| Request/response schemas | `app/api/schemas.py` |
| PAOR engine | `app/logic/trend_analyzer.py` |
| 3-layer guardrails | `app/logic/guardrails.py` |
| Config (TCIA_ prefix) | `app/core/config.py` |
| Redis manager | `app/cache/redis_manager.py` |
| RBAC engine | `app/rbac/engine.py` |
| Skill base class | `app/skills/base.py` |
| Skill registry | `app/skills/registry.py` |
| TCIA executor | `app/services/tcia_executor.py` |
| Kafka producers (trace, audit, alerts) | `app/messaging/kafka_producer.py` |
| Kafka consumer (scheduled scans) | `app/messaging/kafka_consumer.py` |
| Trend registry | `app/registry/trend_registry.py` |
| GCS client (report persistence) | `app/services/gcs_client.py` |
| API clients (Tavily, httpx, Odoo) | `app/services/api_clients.py` |

## Adding a New Skill

1. Create `app/skills/<skill_name>.py` extending `BaseSkill`
2. Register in `app/main.py` lifespan
3. Add skill_id to `VALID_SKILL_IDS` in `app/logic/guardrails.py`
4. Add to RBAC matrix in `app/rbac/engine.py`
5. Wire into pipeline in `app/logic/trend_analyzer.py`
6. Create test in `tests/test_skills.py`

## Testing

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` needed
- Kafka mocked at import time via `sys.modules` patching
- Redis mocked via `AsyncMock`
- Anthropic stubbed when API key absent
- GCS stubbed when credentials absent
- Integration tests marked with `@pytest.mark.integration`
