# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**brand-naming-agent-svc** is a FastAPI microservice that generates brand name candidates with multi-dimensional scoring, performs availability checking (domain/social/trademark), synthesizes taglines, and produces naming briefs. It is **WF2 Agent 2.4** — the fourth agent in Workflow 2: Brand Strategy.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes outputs from 5 WF1 agents + BPA positioning + BPV personality + BAA architecture (recommended) + Company model
- Produces: name candidates (7-15) with scores, availability results, taglines, naming brief
- Powered by Anthropic Claude Sonnet 4 (two LLM calls: name generation + tagline synthesis)

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8034)
uvicorn app.main:app --host 0.0.0.0 --port 8034 --reload

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
    routes.py                # /health, /v1/execute, /v1/naming
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with NTA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 19)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus
  services/
    nta_executor.py          # Executor (cache -> context load -> analyze -> cache -> audit)
    nta_analyzer.py          # 5-phase PAOR engine
    context_loader.py        # HTTP client for WF1 + BPA + BPV + Company context
    anthropic_client.py      # Claude Sonnet 4 wrapper
  logic/
    brand_context_loader.py        # SKL-NTA-01
    audience_psychology_analyzer.py # SKL-NTA-02
    competitive_naming_analyzer.py  # SKL-NTA-03
    identity_seed_loader.py         # SKL-NTA-04
    rag_retriever.py                # SKL-NTA-05
    domain_checker.py               # SKL-NTA-06
    social_handle_checker.py        # SKL-NTA-07
    trademark_searcher.py           # SKL-NTA-08
    name_generator.py               # SKL-NTA-09
    name_scorer.py                  # SKL-NTA-10
    tagline_synthesizer.py          # SKL-NTA-11
    naming_brief_builder.py         # SKL-NTA-12
    naming_persister.py             # SKL-NTA-13
    human_escalation.py             # SKL-NTA-14
  skills/
    registry.py              # SkillRegistry with 14 skills
```

### Key Components

**NTAExecutor**: Thin wrapper — cache check -> load WF1+BPA+BPV+Company context (parallel) -> prerequisite check -> delegate to NTAAnalyzer -> cache result -> update registry -> emit audit/trace events.

**NTAAnalyzer**: 5-phase PAOR engine:
1. Research (parallel): brand context, audience psychology, competitive naming, identity seed, RAG
2. Name Generation (Claude call 1): generates 7-15 candidates with linguistic/memorability/strategy scores
3. Availability Checking: domain DNS, social handle HTTP HEAD, trademark Tavily search
4. Tagline Synthesis (Claude call 2): taglines for shortlisted names + naming brief
5. Persist + Escalation: Redis, GCS upload, RAG emit, human escalation

**NTAContextLoader**: HTTP client that calls 4 Django endpoints in parallel:
- `GET /api/v1/analytics/wf1-context/` — WF1 Brand Discovery
- `GET /api/v1/analytics/bpa-context/` — BPA Brand Positioning
- `GET /api/v1/analytics/bpv-context/` — BPV Brand Personality
- `GET /api/v1/analytics/company-context/` — Company model + products

### 14 Skills

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-NTA-01..05 | Brand context, audience psychology, competitive naming, identity seed, RAG |
| Availability | SKL-NTA-06..08 | Domain checker, social handle checker, trademark searcher |
| Generation | SKL-NTA-09..10 | Name generator, name scorer |
| Synthesis | SKL-NTA-11..12 | Tagline synthesizer, naming brief builder |
| Persist | SKL-NTA-13..14 | Naming persistence, human escalation |

## Environment Variables

All use `NTA_` prefix. Key settings:
- `NTA_REDIS_URL` — Redis DB 19
- `NTA_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `NTA_SERVICE_TOKEN` — X-Service-Token auth
- `NTA_BACKEND_URL` — Django backend for context loading
- `NTA_BACKEND_SERVICE_TOKEN` — Token for context API calls
- `NTA_TAVILY_API_KEY` — Tavily for trademark search
- `NTA_CONFIDENCE_THRESHOLD` — Naming decision threshold (default 0.7)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `nta-naming-audit-topic` | Produce | Audit trail |
| `nta-naming-events-topic` | Produce | Naming events |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Redis: fail-open mock
- Kafka: not started in tests
