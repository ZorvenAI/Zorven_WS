# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

`content-agent-svc` is a stateless FastAPI microservice (port 8050) that authors SEO/AEO/GEO-compliant blog posts for the pipeline orchestrator. It receives research data from discovery-agent-svc, fetches brand persona from core-api, generates optimized Markdown blog posts via Gemini, uploads to GCS, and emits Kafka events for downstream agents.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8050

# Run all tests (unit + integration, requires Redis on localhost:6379)
pytest tests/ -v

# Run unit tests only (no Redis needed)
pytest tests/ -m "not integration" -v

# Run a single test file
pytest tests/test_content_executor.py -v

# Format code
black app/ tests/

# Docker Compose (standalone dev)
docker compose up --build
```

## Architecture

Flat `app/` layout (same as discovery-agent-svc):

- **`app/api/`** — FastAPI routes and Pydantic v2 schemas. `POST /v1/execute` (primary endpoint). Module-level `executor` variable is set by lifespan.
- **`app/core/`** — Config (`Settings` with `CONTENT_` env prefix) and structured logging.
- **`app/cache/`** — `RedisManager` with SEO keyword cache (4h TTL), result cache (4h TTL), and per-tenant rate limiting (INCR+EXPIRE, 60s window). All ops fail open on Redis error.
- **`app/logic/`** — `SEOOptimizer` (keywords, meta tags, slug), `AEOFormatter` (FAQ, JSON-LD), `GEOSynthesizer` (citation mapping), `BlogAuthor` (Gemini blog generation).
- **`app/services/`** — `ContentExecutor` (main orchestration), `CoreApiClient` (brand persona fetch), `GCSClient` (blog upload).
- **`app/messaging/`** — `TraceProducer` (agent-trace-topic) and `ContentPublishedProducer` (content-published-topic). Both graceful when Kafka unavailable.

## Key Contracts

**Input** (from orchestrator's ExternalWrapper):
```
POST /v1/execute
Headers: X-Tenant-ID, Content-Type: application/json
Body: {input_prompt, input_context, tenant_context, config, previous_outputs}
```

**Output** (consumed by ManagerNode):
```json
{
  "findings": ["..."],
  "recommendations": ["..."],
  "blog_content": "# Full Markdown blog...",
  "seo_meta": {"title": "...", "description": "...", "keywords": [...], "slug": "..."},
  "aeo_schema": {"faq_items": [...], "structured_data": {...}},
  "citations": [{"claim": "...", "source_title": "...", "source_url": "..."}],
  "gcs_uri": "gs://bucket/path/to/blog.md",
  "word_count": 950
}
```

## Environment Variables

All prefixed with `CONTENT_`. Key ones:
- `CONTENT_GOOGLE_API_KEY` — empty = stub mode (template blog posts)
- `CONTENT_REDIS_URL` — default `redis://localhost:6379/5` (DB 5)
- `CONTENT_KAFKA_BOOTSTRAP_SERVERS` — empty = no Kafka events
- `CONTENT_GCS_PROJECT_ID` / `CONTENT_GCS_BUCKET_NAME` — empty = GCS stub mode
- `CONTENT_CORE_API_URL` — default `http://localhost:8001`
- `CONTENT_CORE_API_TOKEN` — service-to-service auth token
- `CONTENT_RATE_LIMIT_PER_MINUTE` — default 10

## Testing Conventions

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorators needed
- Integration tests require Redis and are marked `@pytest.mark.integration`
- All external dependencies (Redis, Kafka, Gemini, httpx, GCS) are mocked in unit tests
- Test classes use `TestClassName` pattern, no `setUp`/`tearDown` — use fixtures

## Redis Key Patterns

- `content:seo:{tenant_id}:targets` — SEO keywords, 4h TTL
- `content:result:{md5(key)}` — blog results, 4h TTL
- `content:rate:{tenant_id}` — rate limit counter, 60s TTL
