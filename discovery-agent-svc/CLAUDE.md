# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

`discovery-agent-svc` is a stateless FastAPI microservice (port 8020) that performs web research for the pipeline orchestrator. It searches via Tavily API, scrapes URLs with httpx, cleans HTML to Markdown, caches in Redis, and returns structured findings. Downloadable files (PDF/Excel) are uploaded to GCS and handed off to the data-ingestion pipeline via Kafka.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8020

# Run all tests (unit + integration, requires Redis on localhost:6379)
pytest tests/ -v

# Run unit tests only (no Redis needed)
pytest tests/ -m "not integration" -v

# Run integration tests only (requires Redis)
pytest tests/integration/ -v

# Run a single test file
pytest tests/test_discovery_executor.py -v

# Run a single test
pytest tests/test_data_cleaner.py::TestDataCleaner::test_strips_script_tags -v

# Format code
black app/ tests/

# Docker Compose (standalone dev)
docker compose up --build
```

## Architecture

Flat `app/` layout (not hexagonal — simpler than data-ingestion):

- **`app/api/`** — FastAPI routes and Pydantic v2 schemas. Dual endpoints: `POST /v1/execute` (primary) and `POST /v1/search` (alias for seed manifests). Module-level `executor` variable is set by lifespan.
- **`app/core/`** — Config (`Settings` with `DISCOVERY_` env prefix) and structured logging.
- **`app/cache/`** — `RedisManager` with query cache (4h TTL), page cache (24h TTL), and per-tenant rate limiting (INCR+EXPIRE, 60s window). All ops fail open on Redis error.
- **`app/scrapers/`** — `SearchEngine` (Tavily + stub fallback), `BrowserEngine` (httpx + Redis page cache), `DataCleaner` (BeautifulSoup + markdownify), `ScraperFactory` (DI wiring).
- **`app/services/`** — `DiscoveryExecutor` (search → scrape → clean → return), `FileHandler` (GCS upload + Kafka ingestion event).
- **`app/messaging/`** — `TraceProducer` (agent-trace-topic) and `AuditProducer` (discovery-audit-topic). Both graceful when Kafka unavailable.

## Key Contracts

**Input** (from orchestrator's ExternalWrapper):
```
POST /v1/execute (or /v1/search)
Headers: X-Tenant-ID, Content-Type: application/json
Body: {input_prompt, input_context, tenant_context, config, previous_outputs}
```

**Output** (consumed by ManagerNode + BrandEquityDashboard):
```json
{
  "query": "...",
  "sources": [{"type": "web|document", "title": "...", "url": "..."}],
  "findings": ["..."],
  "recommendations": ["..."],
  "raw_context": "..."
}
```

## Environment Variables

All prefixed with `DISCOVERY_`. Key ones:
- `DISCOVERY_TAVILY_API_KEY` — empty = stub mode (mock search results)
- `DISCOVERY_REDIS_URL` — default `redis://localhost:6379/2` (DB 2)
- `DISCOVERY_KAFKA_BOOTSTRAP_SERVERS` — empty = no Kafka events
- `DISCOVERY_GCS_PROJECT_ID` / `DISCOVERY_GCS_BUCKET_NAME` — empty = GCS stub mode
- `DISCOVERY_RATE_LIMIT_PER_MINUTE` — default 10
- `DISCOVERY_MAX_SCRAPE_URLS` — default 10

## Testing Conventions

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorators needed
- Integration tests require Redis and are marked `@pytest.mark.integration`
- All external dependencies (Redis, Kafka, Tavily, httpx, GCS) are mocked in unit tests
- Test classes use `TestClassName` pattern, no `setUp`/`tearDown` — use fixtures

## Redis Key Patterns

- `discovery:cache:{md5(query)}` — search results, 4h TTL
- `discovery:page:{md5(url)}` — cleaned Markdown, 24h TTL
- `discovery:rate:{tenant_id}` — rate limit counter, 60s TTL
