# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**campaign-architecture-agent-svc** is a FastAPI microservice that designs complete Meta Ads campaign structures. It is **WF3 Agent 3.1** — the first agent in Workflow 3: Meta Ads Campaign Management.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes outputs from WF1 agents (min APA+CIA) + WF2 agents (min BPA) + Company model
- Optional inputs: Tavily benchmarks, Odoo CRM customer data, RAG prior campaign learnings
- Produces: CampaignBlueprint (Meta API-compatible), Funnel-Objective Map, Audience Targeting Specs, Placement Strategy, Budget Allocation, CBO/ABO Recommendation, A/B Test Plan, KPI Targets, Creative Briefs
- Powered by Anthropic Claude Sonnet 4 (two LLM calls: architecture synthesis + blueprint synthesis)
- Persists results to Redis + GCS

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8041)
uvicorn app.main:app --host 0.0.0.0 --port 8041 --reload

# Run tests
pytest tests/ -v                       # All tests
pytest tests/ -m "not integration" -v  # Unit only
pytest tests/test_routes.py -v         # Single file

# Format
black app/ tests/
```

## Architecture

### Directory Structure

```
app/
  main.py                    # FastAPI app + lifespan (DI wiring)
  api/
    routes.py                # /health, /v1/execute, /v1/campaign-blueprint
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with CAA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 21)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus (EVT-CAA-001..024)
  services/
    caa_executor.py          # Executor (cache -> context load -> analyze -> GCS -> cache -> audit)
    caa_analyzer.py          # 5-phase PAOR engine (2 Claude calls)
    context_loader.py        # HTTP client for WF1 + WF2 + Company + BAA + Odoo + RAG context
    anthropic_client.py      # Claude Sonnet 4 wrapper
    gcs_client.py            # GCS blueprint persistence (3-tier auth)
    tavily_client.py         # Tavily web research (benchmarks + competitor ads)
    odoo_client.py           # Optional Odoo CRM customer data
    rag_client.py            # Optional RAG Intelligence Loop
  logic/
    strategy_context_loader.py       # SKL-CAA-01
    market_benchmark_researcher.py   # SKL-CAA-02
    competitor_ad_analyzer.py        # SKL-CAA-03
    odoo_customer_loader.py          # SKL-CAA-04
    rag_intelligence_retriever.py    # SKL-CAA-05
    funnel_objective_mapper.py       # SKL-CAA-06
    audience_targeting_builder.py    # SKL-CAA-07
    placement_budget_builder.py      # SKL-CAA-08
    ab_test_planner.py               # SKL-CAA-09
    blueprint_synthesizer.py         # SKL-CAA-10
    blueprint_persister.py           # SKL-CAA-11
    human_escalation.py              # SKL-CAA-12
    guardrails.py                    # Input/Plan/Output guardrails
  skills/
    registry.py              # SkillRegistry with 12 skills
```

### Key Components

**CAAExecutor**: Thin wrapper — cache check -> load WF1+WF2+Company+Odoo+RAG context (parallel) -> prerequisite check (WF1 min APA+CIA + WF2 min BPA + Company required) -> delegate to CAAAnalyzer -> GCS persist -> cache result -> emit audit/trace events.

**CAAAnalyzer**: 5-phase PAOR engine:
1. Research (parallel): Strategy context, Tavily benchmarks, competitor ads, Odoo customer data, RAG learnings + input guardrails (budget sanity, Special Ad Category)
2. Architecture Synthesis (Claude call 1): Funnel-objective mapping + audience targeting + placement/budget (SKL-06..08 build prompt sections)
3. Blueprint Synthesis (Claude call 2): A/B test plan + full blueprint assembly (SKL-09..10 build prompt sections) + output guardrails (Meta API compat, budget cap)
4. Validation: Budget totals, targeting completeness, Meta objective enums
5. Persist + Escalation: Redis + GCS, human escalation if confidence < 0.7

**CAAContextLoader**: HTTP client that calls 7 endpoints in parallel:
- WF1 context (Analytics Layer)
- BPA context (Brand Positioning)
- WF2 chain (BPV+NTA+BSA)
- Company model
- BAA context (optional)
- Odoo customer data (optional, via odoo-mcp-server-svc)
- RAG learnings (optional, via Vertex AI RAG)

**TavilyClient**: Direct httpx-based Tavily search. `search_benchmarks(industry)` (24h cache) and `search_competitor_ads(competitors)` (12h cache). Stub mode when `CAA_TAVILY_API_KEY` is empty.

**Guardrails**: IG-11 budget sanity ($10 min, cap max), IG-12 Special Ad Category detection, PG-06 budget allocation (100% ±1%), PG-07 audience overlap (>50%), PG-08 KPI realism, PG-09 test sample size, PG-10 placement-objective compat, OG-06 Meta API schema, OG-08 budget cap.

### 12 Skills

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-CAA-01..05 | Strategy context, benchmarks (Tavily), competitor ads (Tavily), Odoo customers, RAG learnings |
| Synthesis | SKL-CAA-06..10 | Funnel mapper, audience targeting, placement/budget, A/B test, blueprint synthesizer |
| Persist | SKL-CAA-11..12 | Blueprint persistence (Redis + GCS), human escalation |

## Environment Variables

All use `CAA_` prefix. Key settings:
- `CAA_REDIS_URL` — Redis DB 21
- `CAA_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `CAA_SERVICE_TOKEN` — X-Service-Token auth
- `CAA_BACKEND_URL` — Django backend for context loading
- `CAA_BACKEND_SERVICE_TOKEN` — Token for context API calls
- `CAA_GCS_PROJECT_ID`, `CAA_GCS_BUCKET_NAME`, `CAA_GCS_CREDENTIALS_JSON` — GCS
- `CAA_TAVILY_API_KEY` — Tavily web research (empty = stub mode)
- `CAA_ODOO_MCP_URL` — Odoo CRM (empty = skip)
- `CAA_RAG_DATA_STORE_ID` — Vertex AI RAG (empty = skip)
- `CAA_DEFAULT_DAILY_BUDGET_CAP` — Max daily budget cap (default $10,000)
- `CAA_CONFIDENCE_THRESHOLD` — Escalation threshold (default 0.7)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `caa-architecture-audit-topic` | Produce | Audit trail |
| `caa-architecture-events-topic` | Produce | Campaign events |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Redis: fail-open mock
- Kafka: not started in tests
- GCS: mocked via `unittest.mock.AsyncMock`
- Tavily: mocked (stub mode in tests)
