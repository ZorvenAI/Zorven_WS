# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**brand-story-agent-svc** is a FastAPI microservice that synthesizes all prior WF2 agent outputs into emotionally resonant brand narratives. It is **WF2 Agent 2.5** — the fifth and **final** (capstone) agent in Workflow 2: Brand Strategy & Positioning.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes outputs from 5 WF1 agents + BPA positioning + BPV personality + NTA naming + BAA architecture (recommended) + Company model
- Produces: Origin story (3 lengths), Mission/Vision statements, Elevator pitches (15s/30s/60s), Channel narratives, Story style guide, Sub-brand story variations, WF2 Strategy Complete Summary
- Powered by Anthropic Claude Sonnet 4 (two LLM calls: narrative generation + narrative synthesis)
- Persists results to Redis + GCS

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8035)
uvicorn app.main:app --host 0.0.0.0 --port 8035 --reload

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
    routes.py                # /health, /v1/execute, /v1/story
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with BSA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 20)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus (EVT-BSA-001..020)
  services/
    bsa_executor.py          # Executor (cache -> context load -> analyze -> GCS -> cache -> audit)
    bsa_analyzer.py          # 5-phase PAOR engine
    context_loader.py        # HTTP client for WF1 + BPA + BPV + NTA + Company context
    anthropic_client.py      # Claude Sonnet 4 wrapper
    gcs_client.py            # GCS narrative persistence (3-tier auth)
  logic/
    wf2_strategy_context_loader.py    # SKL-BSA-01
    audience_emotional_synthesizer.py # SKL-BSA-02
    cultural_narrative_scanner.py     # SKL-BSA-03
    existing_narrative_analyzer.py    # SKL-BSA-04
    competitor_narrative_mapper.py    # SKL-BSA-05
    origin_story_crafter.py           # SKL-BSA-06
    mission_vision_refiner.py         # SKL-BSA-07
    elevator_pitch_generator.py       # SKL-BSA-08
    channel_narrative_adapter.py      # SKL-BSA-09
    story_style_guide_builder.py      # SKL-BSA-10
    subbrand_story_variation.py       # SKL-BSA-11
    brand_narrative_synthesizer.py    # SKL-BSA-12
    story_persister.py                # SKL-BSA-13
    human_escalation.py               # SKL-BSA-14
  skills/
    registry.py              # SkillRegistry with 14 skills
```

### Key Components

**BSAExecutor**: Thin wrapper — cache check -> load WF1+BPA+BPV+NTA+Company context (parallel) -> prerequisite check (WF1+BPA+BPV+NTA required, BAA recommended) -> delegate to BSAAnalyzer -> GCS persist -> cache result -> update registry -> emit audit/trace events.

**BSAAnalyzer**: 5-phase PAOR engine:
1. Research (parallel): WF2 strategy context, audience emotional synthesis, cultural narrative scanning, existing narrative analysis, competitor narrative mapping
2. Narrative Generation (Claude call 1): origin story (3 versions: 500/800/1500 words), mission/vision, elevator pitches (15s/30s/60s)
3. Narrative Synthesis (Claude call 2): channel narratives, story style guide, sub-brand stories (if BAA), narrative package assembly
4. Validation: archetype alignment check, length compliance, voice consistency
5. Persist + Escalation: Redis + GCS, human escalation if confidence < 0.7

**BSAContextLoader**: HTTP client that calls 5 Django endpoints in parallel:
- `GET /api/v1/analytics/wf1-context/` — WF1 Brand Discovery
- `GET /api/v1/analytics/bpa-context/` — BPA Brand Positioning
- `GET /api/v1/analytics/bpv-context/` — BPV Brand Personality
- `GET /api/v1/analytics/nta-context/` — NTA Brand Naming
- `GET /api/v1/analytics/company-context/` — Company model + products

**GCSClient**: Uploads narrative JSON to GCS with 3-tier auth (inline JSON → file path → ADC). Path: `gs://{bucket}/{tenant_id}/brand-story/{job_id}/narrative_{timestamp}.json`

### 14 Skills

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-BSA-01..05 | WF2 context, audience emotional, cultural narrative, existing narrative, competitor narrative |
| Generation | SKL-BSA-06..08 | Origin story crafter, mission/vision refiner, elevator pitch generator |
| Synthesis | SKL-BSA-09..12 | Channel adapter, style guide, sub-brand variation, narrative synthesizer |
| Persist | SKL-BSA-13..14 | Story persistence (Redis + GCS), human escalation |

## Environment Variables

All use `BSA_` prefix. Key settings:
- `BSA_REDIS_URL` — Redis DB 20
- `BSA_ANTHROPIC_API_KEY` — Claude Sonnet 4
- `BSA_SERVICE_TOKEN` — X-Service-Token auth
- `BSA_BACKEND_URL` — Django backend for context loading
- `BSA_BACKEND_SERVICE_TOKEN` — Token for context API calls
- `BSA_GCS_PROJECT_ID` — GCP project ID
- `BSA_GCS_BUCKET_NAME` — GCS bucket for narrative storage
- `BSA_GCS_CREDENTIALS_PATH` — Path to service account JSON
- `BSA_GCS_CREDENTIALS_JSON` — Inline service account JSON (Railway)
- `BSA_CONFIDENCE_THRESHOLD` — Escalation threshold (default 0.7)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `bsa-story-audit-topic` | Produce | Audit trail |
| `bsa-story-events-topic` | Produce | Story events |

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
