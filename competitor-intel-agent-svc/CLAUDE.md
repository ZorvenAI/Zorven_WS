# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Service Overview

Competitor Intelligence Agent (CIA) — Agent 1.2 in the Brand Discovery & Research workflow. FastAPI microservice providing structured competitive intelligence: competitor discovery, profiling (website, social, reviews, pricing), SWOT analysis, positioning gap analysis, and competitive benchmarking.

**Port**: 8022 | **Redis DB**: 12 | **Env prefix**: `CIA_` | **LLM**: Claude Sonnet 4

## Build & Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8022 --reload

# Tests
pytest tests/ -v                        # All tests
pytest tests/ -m "not integration" -v   # Unit only
pytest tests/test_guardrails.py -v      # Single file
pytest -k "test_ssrf" -v                # By name

# Format
black app/ tests/
```

## Architecture

### Two-Layer Skill System

**Layer 1 — Orchestrator `.md` skills** (`pipeline-orchestrator-svc/skills/`): Methodology guidelines injected as LLM context via `config["skill_context"]`. Auto-discovered by SkillLoader.

**Layer 2 — Agent Python skills** (`app/skills/`): 12 executable skill classes (SKL-CIA-01 through SKL-CIA-12) extending `BaseSkill` ABC. Each has RBAC, circuit breakers, timeouts.

### PAOR Engine (`app/logic/competitor_analyzer.py`)

Plan-Act-Observe-Reflect loop with Claude Sonnet 4:
1. **PLAN**: Discovery (SKL-CIA-01) + identify competitor set
2. **ACT**: Per-competitor profiling loop (SKL-CIA-02 through 06) + RAG (07)
3. **OBSERVE**: SWOT (08) + Positioning Gaps (09) + Benchmarking (10)
4. **REFLECT**: Persist (11), escalate if needed (12)

### 3-Layer Guardrails (`app/logic/guardrails.py`)

- **Input** (9 rules): Injection, scam, scope, PII, tenant, size, rate limit, SSRF, anti-scraping
- **Plan/Tool** (9 rules): Planning, allowlist, write RBAC, concurrency, RBAC, irreversible, budget, competitor cap, scrape depth
- **Output** (8 rules): Grounding, PII scrub, confidence, hallucination, isolation, size, defamation, trade secret

### Skill Map

| ID | Skill | Type | Dependencies |
|----|-------|------|-------------|
| SKL-CIA-01 | CompetitorDiscoverySearch | Read | Tavily |
| SKL-CIA-02 | CompetitorWebsiteProfiler | Read | httpx |
| SKL-CIA-03 | SocialMediaAnalyzer | Read | Tavily |
| SKL-CIA-04 | CustomerReviewAggregator | Read | Tavily |
| SKL-CIA-05 | PricingStrategyExtractor | Read | httpx, Tavily |
| SKL-CIA-06 | MarketShareEstimator | Read | Tavily |
| SKL-CIA-07 | RAGContextRetrieval | Read | RAG service |
| SKL-CIA-08 | SWOTAnalysisGenerator | Analysis | Anthropic |
| SKL-CIA-09 | PositioningGapAnalyzer | Analysis | Anthropic |
| SKL-CIA-10 | CompetitiveBenchmarkingSynthesizer | Analysis | Anthropic |
| SKL-CIA-11 | CompetitorReportPersister | Write | GCS, RAG |
| SKL-CIA-12 | HumanEscalation | Escalation | Kafka |

### MRA → CIA Data Flow

When in combined pipeline (`market-research-competitor-intel`), CIA receives MRA output via `previous_outputs["market_research"]`. Key fields consumed:
- `competitive_landscape` → Seeds SKL-CIA-01 discovery
- `market_sizing` (TAM/SAM/SOM) → Baselines SKL-CIA-06 share estimation
- `industry_trends` + `market_overview` → Enriches LLM analysis (08-10)

CIA works standalone when `previous_outputs` is empty.

### Competitor Registry (`app/registry/`)

Redis Hash `cia:<tid>:registry:competitors` for fast CRUD. Snapshots with 90-day TTL for change detection. PostgreSQL backup via Django models (`CompetitorProfile`, `CompetitorSnapshot`).

## Key Files

| Purpose | Path |
|---------|------|
| FastAPI app + lifespan | `app/main.py` |
| API routes | `app/api/routes.py` |
| Request/response schemas | `app/api/schemas.py` |
| PAOR engine | `app/logic/competitor_analyzer.py` |
| 3-layer guardrails | `app/logic/guardrails.py` |
| Config (CIA_ prefix) | `app/core/config.py` |
| Redis manager | `app/cache/redis_manager.py` |
| RBAC engine | `app/rbac/engine.py` |
| Skill base class | `app/skills/base.py` |
| Skill registry | `app/skills/registry.py` |
| CIA executor | `app/services/cia_executor.py` |
| Kafka consumer | `app/messaging/kafka_consumer.py` |
| Competitor registry | `app/registry/competitor_registry.py` |

## Adding a New Skill

1. Create `app/skills/<skill_name>.py` extending `BaseSkill`
2. Register in `app/main.py` lifespan
3. Add skill_id to `VALID_SKILL_IDS` in `app/logic/guardrails.py`
4. Add to RBAC matrix in `app/rbac/engine.py`
5. Wire into PAOR sequence in `app/logic/competitor_analyzer.py`
6. Create test in `tests/test_skills/test_<skill>.py`
7. Optionally add orchestrator `.md` skill in `pipeline-orchestrator-svc/skills/`

## Testing

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` needed
- Kafka mocked (no real broker required for unit tests)
- Redis mocked via `AsyncMock` in most tests
- Integration tests marked with `@pytest.mark.integration`
