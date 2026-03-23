# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**brand-positioning-agent-svc** is a FastAPI microservice that generates strategic brand positioning using WF1 Brand Discovery intelligence. It is **WF2 Agent 2.1** — the first agent in Workflow 2: Brand Strategy.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes outputs from 5 WF1 agents: MRA, CIA, APA, TCIA, VoCA
- Produces: positioning statements, value proposition canvas, perceptual maps, differentiation framework
- Powered by Anthropic Claude Sonnet 4 for LLM analysis

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8031)
uvicorn app.main:app --host 0.0.0.0 --port 8031 --reload

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
    routes.py                # /health, /v1/execute, /v1/position
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with BPA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 16)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus
  services/
    bpa_executor.py          # Executor (cache → WF1 load → analyze → cache → audit)
    bpa_analyzer.py          # PAOR engine (3-phase analysis)
    wf1_loader.py            # HTTP client for WF1 context
    anthropic_client.py      # Claude Sonnet 4 wrapper
  logic/
    competitive_mapper.py    # SKL-BPA-01
    needs_synthesizer.py     # SKL-BPA-02
    trend_scanner.py         # SKL-BPA-03
    identity_loader.py       # SKL-BPA-04
    rag_retriever.py         # SKL-BPA-05
    positioning_generator.py # SKL-BPA-06
    canvas_builder.py        # SKL-BPA-07
    perceptual_mapper.py     # SKL-BPA-08
    differentiation_builder.py # SKL-BPA-09
    strategy_synthesizer.py  # SKL-BPA-10
    strategy_persister.py    # SKL-BPA-11
    human_escalation.py      # SKL-BPA-12
  skills/
    registry.py              # SkillRegistry with 12 skills
```

### Key Components

**BPAExecutor**: Thin wrapper — cache check → WF1 context load → delegate to BPAAnalyzer → cache result → emit audit/trace events.

**BPAAnalyzer**: PAOR engine with 3 phases: Research (parallel), Synthesis (sequential via Claude), Persist + Escalation.

**WF1ContextLoader**: HTTP client that calls Django `GET /api/v1/analytics/wf1-context/` to fetch the latest WF1 Brand Discovery results.

### 12 Skills

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-BPA-01..05 | Competitive mapping, needs synthesis, trend scanning, identity loading, RAG retrieval |
| Synthesis | SKL-BPA-06..10 | Positioning generation, canvas building, perceptual mapping, differentiation, strategy synthesis |
| Persist | SKL-BPA-11..12 | Strategy persistence, human escalation evaluation |

## Environment Variables

All use `BPA_` prefix. Key settings:
- `BPA_REDIS_URL` — Redis DB 16
- `BPA_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `BPA_SERVICE_TOKEN` — X-Service-Token auth
- `BPA_BACKEND_URL` — Django backend for WF1 context
- `BPA_BACKEND_SERVICE_TOKEN` — Token for WF1 context API

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `bpa-positioning-audit-topic` | Produce | Audit trail |
| `bpa-positioning-events-topic` | Produce | Positioning events |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Redis: fail-open mock
- Kafka: not started in tests
