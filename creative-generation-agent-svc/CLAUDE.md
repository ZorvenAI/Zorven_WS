# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**creative-generation-agent-svc** is a FastAPI microservice that generates complete ad creative packages for Meta Ads campaigns. It is **WF3 Agent 3.2** — the second agent in Workflow 3: Meta Ads Campaign Management.

This service is part of the AI Brand Automator platform (`Prevision_WS`):
- Consumes: CAA campaign blueprint (creative briefs per audience x funnel) + WF2 analytics (BPV voice, BPA positioning, NTA name/tagline, BSA story arcs) + WF1 analytics (APA personas) + Company model
- Produces: AI-generated images (Nano Banana 2), ad copy (hooks, primary text, CTAs), compliance results, visual-copy assemblies, complete creative packages
- Powered by Anthropic Claude Sonnet 4 (3 LLM calls) + Nano Banana 2 / Gemini image generation
- Persists images + packages to GCS, metadata to Redis

## Build, Run, and Test

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service (port 8042)
uvicorn app.main:app --host 0.0.0.0 --port 8042 --reload

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
    routes.py                # /health, /v1/execute, /v1/creative
    schemas.py               # Pydantic v2 request/response models
    auth.py                  # X-Service-Token verification
  core/
    config.py                # Settings with CGA_ env prefix
    logging_config.py
  cache/
    redis_manager.py         # Async Redis (fail-open, DB 22)
  messaging/
    kafka_producer.py        # Trace, Audit, Event producers
    event_emitter.py         # Internal event bus (EVT-CGA-001..025)
  services/
    cga_executor.py          # Executor (cache -> context load -> analyze -> GCS -> cache -> audit)
    cga_analyzer.py          # 5-phase engine (3 Claude calls + Nano Banana 2 image gen)
    context_loader.py        # HTTP client for CAA + WF1 + WF2 + Company context
    anthropic_client.py      # Claude Sonnet 4 wrapper
    image_gen_client.py      # Nano Banana 2 adapter (google-genai SDK)
    gcs_client.py            # GCS image + package persistence (3-tier auth)
  logic/
    creative_context_loader.py       # SKL-CGA-01
    audience_creative_profiler.py    # SKL-CGA-02
    creative_learnings_loader.py     # SKL-CGA-03
    image_prompt_builder.py          # SKL-CGA-04
    image_generator.py               # SKL-CGA-05
    hook_generator.py                # SKL-CGA-07
    primary_copy_generator.py        # SKL-CGA-08
    cta_generator.py                 # SKL-CGA-09
    copy_compliance_checker.py       # SKL-CGA-10
    visual_copy_assembler.py         # SKL-CGA-11
    creative_package_synthesizer.py  # SKL-CGA-12
    creative_persister.py            # SKL-CGA-13
    guardrails.py                    # Input/Plan/Output guardrails
    human_escalation.py              # SKL-CGA-14
  skills/                    # Reserved for runtime skill wiring
```

### Key Components

**CGAExecutor**: Thin wrapper — cache check -> load CAA+WF1+WF2+Company context (parallel) -> prerequisite check (CAA blueprint + WF1 APA + WF2 BPV+BPA+NTA + Company required) -> delegate to CGAAnalyzer -> GCS persist -> cache result -> emit audit/trace events.

**CGAAnalyzer**: 5-phase engine:
1. Research + Image Gen: Creative context, learnings + Claude call 1 (creative profiling + image prompts) + Nano Banana 2 image generation
2. Copy Generation (Claude call 2): Hooks + primary copy + CTAs per audience x funnel
3. Assembly + Compliance (Claude call 3): Meta compliance check + visual-copy pairing + package synthesis
4. Validation: Copy lengths, CTA enums, A/B variant counts, minimum package check
5. Persist + Escalation: Redis + GCS, human escalation if confidence < 0.7

**CGAContextLoader**: HTTP client that calls 7 Django endpoints in parallel:
- WF1 context (APA personas)
- BPA context (positioning)
- BPV context (personality/voice)
- NTA context (name/tagline)
- BSA context (story arcs, optional)
- Company model (colors, logo, industry)
- CAA blueprint (from previous_outputs or analytics context)

**ImageGenClient**: Adapter pattern with NanoBanana2Adapter (google-genai SDK) and StubAdapter. Generates images in 3 aspect ratios (1:1, 9:16, 16:9). Retry with exponential backoff, circuit breaker.

### 12 Skills (SKL-CGA-06 deferred)

| Phase | Skills | Description |
|-------|--------|-------------|
| Research | SKL-CGA-01..03 | Creative context, audience profiling, creative learnings |
| Image Gen | SKL-CGA-04..05 | Image prompt builder, Nano Banana 2 generator |
| Copy Gen | SKL-CGA-07..10 | Hooks, primary copy, CTAs, compliance checker |
| Assembly | SKL-CGA-11..12 | Visual-copy assembler, package synthesizer |
| Persist | SKL-CGA-13..14 | Creative persistence (Redis + GCS), human escalation |

## Environment Variables

All use `CGA_` prefix. Key settings:
- `CGA_REDIS_URL` — Redis DB 22
- `CGA_ANTHROPIC_API_KEY` — Claude Sonnet 4 (copy gen)
- `CGA_GOOGLE_API_KEY` — Nano Banana 2 image gen (empty = stub mode)
- `CGA_IMAGE_GEN_MODEL` — `gemini-2.0-flash-preview-image-generation`
- `CGA_SERVICE_TOKEN` — X-Service-Token auth
- `CGA_BACKEND_URL` — Django backend for context loading
- `CGA_BACKEND_SERVICE_TOKEN` — Token for context API calls
- `CGA_GCS_PROJECT_ID`, `CGA_GCS_BUCKET_NAME`, `CGA_GCS_CREDENTIALS_JSON` — GCS
- `CGA_DEFAULT_IMAGES_PER_ADSET` — Images per audience x funnel (default 3)
- `CGA_MAX_IMAGE_GEN_RETRIES` — Retry limit for image gen (default 3)
- `CGA_CONFIDENCE_THRESHOLD` — Escalation threshold (default 0.7)

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `agent-trace-topic` | Produce | Real-time node progress |
| `cga-creative-audit-topic` | Produce | Audit trail |
| `cga-creative-events-topic` | Produce | Creative events |

## Code Style

- **Formatter**: Black, 88-char lines, Python 3.12 target
- **Async**: All operations are async
- **Commit messages**: Conventional commits

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"`
- Anthropic client: `unittest.mock.AsyncMock`
- Nano Banana 2: mocked via `unittest.mock.AsyncMock` (stub mode in tests)
- Redis: fail-open mock
- Kafka: not started in tests
- GCS: mocked via `unittest.mock.AsyncMock`
