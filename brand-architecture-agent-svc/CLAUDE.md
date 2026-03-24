# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**brand-architecture-agent-svc** is a FastAPI microservice that designs brand architecture structures using WF1 Brand Discovery + WF2 Brand Positioning intelligence. It is **WF2 Agent 2.2** — the second agent in Workflow 2: Brand Strategy.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes outputs from 5 WF1 agents (MRA, CIA, APA, TCIA, VoCA) + BPA positioning strategy + Company model
- Produces: architecture model recommendation, brand hierarchy tree, naming conventions, portfolio growth path
- Powered by Anthropic Claude Sonnet 4 for LLM analysis

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8032)
uvicorn app.main:app --host 0.0.0.0 --port 8032 --reload

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
    routes.py                # /health, /v1/execute, /v1/architecture
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with BAA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 17)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus
  services/
    baa_executor.py          # Executor (cache -> context load -> analyze -> cache -> audit)
    baa_analyzer.py          # PAOR engine (3-phase analysis)
    context_loader.py        # HTTP client for WF1 + BPA + Company context
    anthropic_client.py      # Claude Sonnet 4 wrapper
  logic/
    competitor_arch_analyzer.py  # SKL-BAA-01
    audience_alignment.py        # SKL-BAA-02
    portfolio_loader.py          # SKL-BAA-03
    positioning_loader.py        # SKL-BAA-04
    rag_retriever.py             # SKL-BAA-05
    model_recommender.py         # SKL-BAA-06
    hierarchy_builder.py         # SKL-BAA-07
    naming_designer.py           # SKL-BAA-08
    growth_planner.py            # SKL-BAA-09
    strategy_synthesizer.py      # SKL-BAA-10
    strategy_persister.py        # SKL-BAA-11
    human_escalation.py          # SKL-BAA-12
  skills/
    registry.py              # SkillRegistry with 12 skills
```

### Key Components

**BAAExecutor**: Thin wrapper — cache check -> load WF1+BPA+Company context (parallel) -> prerequisite check -> delegate to BAAAnalyzer -> cache result -> update registry -> emit audit/trace events.

**BAAAnalyzer**: PAOR engine with 3 phases: Research (parallel), Architecture Design (sequential via Claude), Persist + Escalation.

**BAAContextLoader**: HTTP client that calls 3 Django endpoints in parallel:
- `GET /api/v1/analytics/wf1-context/` — WF1 Brand Discovery
- `GET /api/v1/analytics/bpa-context/` — BPA Brand Positioning
- `GET /api/v1/analytics/company-context/` — Company model + products

### 12 Skills

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-BAA-01..05 | Competitor arch analysis, audience alignment, portfolio loading, positioning loading, RAG retrieval |
| Design | SKL-BAA-06..10 | Model recommendation, hierarchy building, naming design, growth planning, strategy synthesis |
| Persist | SKL-BAA-11..12 | Strategy persistence, human escalation evaluation |

## Environment Variables

All use `BAA_` prefix. Key settings:
- `BAA_REDIS_URL` — Redis DB 17
- `BAA_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `BAA_SERVICE_TOKEN` — X-Service-Token auth
- `BAA_BACKEND_URL` — Django backend for context loading
- `BAA_BACKEND_SERVICE_TOKEN` — Token for context API calls
- `BAA_CONFIDENCE_THRESHOLD` — Architecture decision threshold (default 0.7)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `baa-architecture-audit-topic` | Produce | Audit trail |
| `baa-architecture-events-topic` | Produce | Architecture events |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Redis: fail-open mock
- Kafka: not started in tests
