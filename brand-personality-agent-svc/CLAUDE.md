# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**brand-personality-agent-svc** is a FastAPI microservice that designs brand personality profiles, values hierarchies, and voice matrices using WF1 Brand Discovery + WF2 Brand Positioning + Brand Architecture intelligence. It is **WF2 Agent 2.3** — the third agent in Workflow 2: Brand Strategy.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes outputs from 5 WF1 agents (MRA, CIA, APA, TCIA, VoCA) + BPA positioning + BAA architecture (recommended) + Company model (brand_voice + values)
- Produces: Aaker 5-dimension personality profile, Jungian archetype selection, values hierarchy, emotional attribute map, voice matrix, character brief
- Powered by Anthropic Claude Sonnet 4 for LLM analysis

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8033)
uvicorn app.main:app --host 0.0.0.0 --port 8033 --reload

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
    routes.py                # /health, /v1/execute, /v1/personality
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with BPV_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 18)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus
  services/
    bpv_executor.py          # Executor (cache -> context load -> analyze -> cache -> audit)
    bpv_analyzer.py          # PAOR engine (3-phase analysis)
    context_loader.py        # HTTP client for WF1 + BPA + Company context
    anthropic_client.py      # Claude Sonnet 4 wrapper
  logic/
    audience_psychology_analyzer.py  # SKL-BPV-01
    brand_perception_analyzer.py     # SKL-BPV-02
    identity_values_seed_loader.py   # SKL-BPV-03
    rag_retriever.py                 # SKL-BPV-04
    aaker_profiler.py                # SKL-BPV-05
    archetype_selector.py            # SKL-BPV-06
    values_hierarchy_builder.py      # SKL-BPV-07
    emotional_attribute_mapper.py    # SKL-BPV-08
    voice_matrix_designer.py         # SKL-BPV-09
    character_brief_synthesizer.py   # SKL-BPV-10
    personality_persister.py         # SKL-BPV-11
    human_escalation.py              # SKL-BPV-12
    sub_brand_constraint.py          # PG-07 sub-brand Aaker deviation validator
  skills/
    registry.py              # SkillRegistry with 12 skills
```

### Key Components

**BPVExecutor**: Thin wrapper — cache check -> load WF1+BPA+Company context (parallel) -> prerequisite check -> delegate to BPVAnalyzer -> cache result -> update registry -> sync personality context -> emit audit/trace events.

**BPVAnalyzer**: PAOR engine with 3 phases: Research (parallel), Personality Design (sequential via Claude), Persist + Escalation. Post-Claude: applies PG-07 sub-brand constraint if brand_context_id != "parent".

**BPVContextLoader**: HTTP client that calls 3 Django endpoints in parallel:
- `GET /api/v1/analytics/wf1-context/` — WF1 Brand Discovery
- `GET /api/v1/analytics/bpa-context/` — BPA Brand Positioning
- `GET /api/v1/analytics/company-context/` — Company model + products

### 12 Skills

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-BPV-01..04 | Audience psychology, brand perception, identity/values seed, RAG retrieval |
| Design | SKL-BPV-05..10 | Aaker profiler, archetype selector, values hierarchy, emotional mapper, voice matrix, character brief |
| Persist | SKL-BPV-11..12 | Personality persistence + brand context sync, human escalation |

## Environment Variables

All use `BPV_` prefix. Key settings:
- `BPV_REDIS_URL` — Redis DB 18
- `BPV_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `BPV_SERVICE_TOKEN` — X-Service-Token auth
- `BPV_BACKEND_URL` — Django backend for context loading
- `BPV_BACKEND_SERVICE_TOKEN` — Token for context API calls
- `BPV_CONFIDENCE_THRESHOLD` — Personality decision threshold (default 0.7)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `bpv-personality-audit-topic` | Produce | Audit trail |
| `bpv-personality-events-topic` | Produce | Personality events |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Redis: fail-open mock
- Kafka: not started in tests
