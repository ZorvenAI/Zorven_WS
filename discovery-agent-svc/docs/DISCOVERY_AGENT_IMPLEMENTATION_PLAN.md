# Implementation Plan: `discovery-agent-svc`

> **Note**: Upon approval, this plan will be saved to `docs/DISCOVERY_AGENT_IMPLEMENTATION_PLAN.md`.

## Context

The `pipeline-orchestrator-svc` (port 8010) is fully implemented and calls external agent services via HTTP POST through its `ExternalWrapper` node. Three of four seed manifests reference `http://discovery-agent-svc/v1/search` as an external node for web research. The **discovery-agent-svc** is the missing "Researcher" microservice that performs web searches, scrapes URLs, cleans content to Markdown, and returns structured findings back to the orchestrator.

**Location**: `Prevision_WS/discovery-agent-svc/` (separate top-level directory, per workspace convention)

---

## Critical Contracts

### Input (from ExternalWrapper → Discovery)

```
POST /v1/execute  (or /v1/search alias)
Headers: X-Tenant-ID: {tenant_id}, Content-Type: application/json
Timeout: 60 seconds
```

```json
{
  "input_prompt": "Analyze brand positioning for Acme Corp",
  "input_context": {"company_id": 42},
  "tenant_context": {
    "tenant_id": "1",
    "gcs_raw_bucket": "brand-automator/1/",
    "gcs_processed_bucket": "brand-automator-curated/1/",
    "rag_data_store_id": "ds-123"
  },
  "config": {"focus": "market_trends,competitors"},
  "previous_outputs": {}
}
```

### Output (Discovery → ExternalWrapper)

```json
{
  "query": "brand positioning Acme Corp market trends competitors",
  "sources": [
    {"type": "web", "title": "Article Title", "url": "https://..."},
    {"type": "document", "title": "PDF Report", "url": "gs://..."}
  ],
  "findings": ["Market trend: ...", "Competitor insight: ..."],
  "recommendations": ["Focus on differentiation in..."],
  "raw_context": "Full cleaned text from all scraped pages..."
}
```

- `findings` and `recommendations` are aggregated by the orchestrator's `ManagerNode`
- `sources` are rendered by the frontend's `BrandEquityDashboard` as clickable citations
- `raw_context` provides grounding data for downstream intelligence nodes

### Data Ingestion Handoff (for downloadable files)

When discovery encounters a PDF/Excel file, it uploads to GCS `_landing/` and emits an `IngestionEvent` to `raw-ingestion-topic`:

```json
{
  "event_id": "uuid",
  "trace_id": "uuid",
  "timestamp": "ISO8601",
  "source": "api-integration",
  "tenant_id": "1",
  "file_path": "gs://onboarding-bucket1/_landing/report.pdf",
  "file_type": "application/pdf",
  "file_size_bytes": 102400,
  "metadata": {"source_url": "https://example.com/report.pdf", "job_id": "..."},
  "raw_bucket": "brand-automator/1/"
}
```

---

## Directory Structure

```
discovery-agent-svc/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI + lifespan (Redis, Kafka startup/shutdown)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py               # POST /v1/execute, /v1/search (alias), GET /health
│   │   └── schemas.py              # Pydantic v2 request/response models
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Pydantic BaseSettings (DISCOVERY_ prefix)
│   │   └── logging_config.py       # Structured logging
│   ├── messaging/
│   │   ├── __init__.py
│   │   ├── kafka_producer.py       # TraceProducer (agent-trace-topic) + AuditProducer
│   │   └── schemas.py              # Kafka event Pydantic models
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── factory.py              # Strategy selector (search vs scrape)
│   │   ├── search_engine.py        # Tavily API + Redis cache wrapper
│   │   ├── browser_engine.py       # Playwright headless / httpx fallback
│   │   └── data_cleaner.py         # HTML-to-Markdown (markdownify)
│   ├── cache/
│   │   ├── __init__.py
│   │   └── redis_manager.py        # Query cache, page cache, rate limiting
│   └── services/
│       ├── __init__.py
│       └── discovery_executor.py   # Core orchestration: search → scrape → clean → return
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Fixtures, mock Redis, mock httpx
│   ├── test_api_routes.py
│   ├── test_discovery_executor.py
│   ├── test_search_engine.py
│   ├── test_browser_engine.py
│   ├── test_data_cleaner.py
│   ├── test_redis_manager.py
│   ├── test_kafka_producer.py
│   └── test_schemas.py
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## Phase 1: FastAPI Skeleton + API Contract

**Goal**: Runnable FastAPI service on port 8020 that accepts the orchestrator's ExternalWrapper payload and returns a stub response. Health endpoint. No scraping yet.

### Files to create

- **`pyproject.toml`** — Black (88 chars), pytest asyncio_mode=auto, Python 3.12 target
- **`requirements.txt`** — `fastapi>=0.115.0, uvicorn[standard], pydantic>=2.9, pydantic-settings, httpx>=0.27.0, redis>=5.0, aiokafka>=0.11.0, markdownify>=0.14, tavily-python>=0.5`
- **`requirements-dev.txt`** — `pytest, pytest-asyncio, pytest-httpx, fakeredis, black, mypy`
- **`Dockerfile`** — `python:3.12-slim`, install deps, run uvicorn on port 8020
- **`app/core/config.py`** — `Settings(BaseSettings)` with `DISCOVERY_` prefix:
  - `SERVICE_TOKEN`, `REDIS_URL` (redis://localhost:6379/2), `KAFKA_BOOTSTRAP_SERVERS`
  - `TAVILY_API_KEY` (default empty = stub mode), `HOST` (0.0.0.0), `PORT` (8020)
  - `CORS_ORIGINS`, `LOG_LEVEL`, `MAX_SCRAPE_URLS` (10), `SCRAPE_TIMEOUT` (30)
  - `RATE_LIMIT_PER_MINUTE` (10), `GCS_PROJECT_ID`, `GCS_BUCKET_NAME`, `GCS_CREDENTIALS_PATH`
- **`app/core/logging_config.py`** — Structured JSON logging (copy pattern from orchestrator)
- **`app/api/schemas.py`** — Pydantic v2 models:
  - `ExecuteRequest`: `{input_prompt, input_context, tenant_context, config, previous_outputs}` (matches ExternalWrapper payload)
  - `TenantContext`: `{tenant_id, gcs_raw_bucket, gcs_processed_bucket, rag_data_store_id}`
  - `SourceItem`: `{type, title, url}`
  - `ExecuteResponse`: `{query, sources, findings, recommendations, raw_context}`
  - `HealthResponse`: `{status, version}`
- **`app/api/routes.py`** — Three endpoints:
  - `GET /health` → `{"status": "ok", "version": "0.1.0"}`
  - `POST /v1/execute` → accepts `ExecuteRequest`, returns `ExecuteResponse` (stub for now)
  - `POST /v1/search` → alias that delegates to the same handler as `/v1/execute`
  - Rate-limit dependency via `X-Tenant-ID` header
- **`app/main.py`** — FastAPI app with lifespan placeholder, CORS

### Tests: `test_api_routes.py`
- Health returns 200
- Execute returns 200 with correct response shape
- Search alias returns same result as execute
- Missing X-Tenant-ID header returns 422 or proceeds with default
- Malformed body returns 422

---

## Phase 2: Redis Caching + Rate Limiting

**Goal**: RedisManager with query cache, page cache, and per-tenant rate limiting.

### Files to create

- **`app/cache/redis_manager.py`** — `RedisManager` class:
  - `__init__(redis_url)` — lazy async Redis connection
  - `get_cached_search(query: str) -> dict | None` — key: `discovery:cache:{md5(query)}`, TTL 4h
  - `set_cached_search(query: str, result: dict)` — store with 4h TTL
  - `get_cached_page(url: str) -> str | None` — key: `discovery:page:{md5(url)}`, TTL 24h
  - `set_cached_page(url: str, markdown: str)` — store with 24h TTL
  - `check_rate_limit(tenant_id: str, limit: int) -> bool` — key: `discovery:rate:{tenant_id}`, 1 min window, returns True if under limit
  - `close()` — close Redis connection
  - All operations gracefully degrade on Redis failure (log warning, continue without cache)

### Tests: `test_redis_manager.py`
- Cache hit returns stored data
- Cache miss returns None
- Rate limiter allows up to limit, blocks after
- Redis failure doesn't crash (returns None / allows)

---

## Phase 3: Scraping Engine (Search + Scrape + Clean)

**Goal**: SearchEngine (Tavily with stub fallback), BrowserEngine (httpx-based with Playwright option), DataCleaner (HTML→Markdown), and Factory to wire them.

### Files to create

- **`app/scrapers/search_engine.py`** — `SearchEngine` class:
  - `__init__(tavily_api_key, redis_manager)` — if no API key, use stub mode
  - `search(query: str, max_results: int = 5) -> list[dict]` — returns `[{title, url, snippet}]`
  - Stub mode: returns realistic mock URLs based on query keywords
  - Real mode: calls `tavily-python` SDK, caches result in Redis
- **`app/scrapers/browser_engine.py`** — `BrowserEngine` class:
  - `__init__(timeout, redis_manager)` — uses httpx by default
  - `scrape(url: str, tenant_id: str) -> str` — returns raw HTML
  - Checks Redis page cache first
  - Uses `httpx.AsyncClient` with reasonable timeout and User-Agent
  - Stub fallback on HTTP error
  - Future: Playwright `new_context()` per request for tenant isolation
- **`app/scrapers/data_cleaner.py`** — `DataCleaner` class:
  - `clean(html: str) -> str` — converts HTML to Markdown using `markdownify`
  - Strips scripts, styles, nav elements before conversion
  - Truncates to max length (configurable, default 50000 chars)
  - `is_downloadable(url: str, content_type: str) -> bool` — checks if URL points to PDF/Excel/etc.
- **`app/scrapers/factory.py`** — `ScraperFactory`:
  - `create(config, redis_manager) -> tuple[SearchEngine, BrowserEngine, DataCleaner]`
  - Wires dependencies based on config (API keys, mode selection)

### Tests: `test_search_engine.py`, `test_browser_engine.py`, `test_data_cleaner.py`
- SearchEngine stub returns mock results
- SearchEngine with cache returns cached result on second call
- BrowserEngine scrapes and returns HTML (mock httpx)
- BrowserEngine page cache avoids re-scraping
- DataCleaner converts HTML to Markdown
- DataCleaner strips scripts/styles
- is_downloadable detects PDF/Excel MIME types

---

## Phase 4: Discovery Executor (Core Orchestration)

**Goal**: Wire search → scrape → clean → return into a single executor that handles the full POST /v1/execute flow.

### Files to create

- **`app/services/discovery_executor.py`** — `DiscoveryExecutor` class:
  - `__init__(search_engine, browser_engine, data_cleaner, redis_manager, trace_producer)`
  - `execute(request: ExecuteRequest, tenant_id: str) -> ExecuteResponse`:
    1. Build search query from `input_prompt` + `config.focus`
    2. Check rate limit for tenant_id
    3. Search via SearchEngine (with cache)
    4. For each URL (up to `MAX_SCRAPE_URLS`):
       - Emit trace event: "Scraping {url}..."
       - Check if downloadable → skip (handle in Phase 5)
       - Scrape via BrowserEngine (with cache)
       - Clean via DataCleaner
    5. Aggregate results into `ExecuteResponse`
    6. Emit trace event: "Discovery complete"
    7. Return response
  - `close()` — cleanup
- **Update `app/api/routes.py`** — Wire `DiscoveryExecutor` into the execute endpoint
- **Update `app/main.py`** — Initialize executor in lifespan, inject into routes

### Tests: `test_discovery_executor.py`
- Full execute flow with mocked search/scrape returns correct response shape
- Rate limit exceeded returns 429
- Search cache hit skips API call
- Page cache hit skips scraping
- HTTP error on scrape falls back gracefully

---

## Phase 5: Kafka Integration (Trace + Audit)

**Goal**: Emit fine-grained trace events for ThoughtTrace UI and audit events for compliance.

### Files to create

- **`app/messaging/schemas.py`** — Pydantic models for Kafka events:
  - `TraceEvent`: `{job_id, node_id, status, message, metadata, timestamp}`
  - `AuditEvent`: `{job_id, tenant_id, url, raw_html, cleaned_markdown, timestamp}`
- **`app/messaging/kafka_producer.py`** — Two producers:
  - `TraceProducer`: sends to `agent-trace-topic`
    - `send_step(job_id, node_id, message, metadata)` — e.g. "Searching...", "Scraping URL..."
    - Graceful on Kafka unavailability (same pattern as orchestrator)
  - `AuditProducer`: sends to `discovery-audit-topic`
    - `send_audit(job_id, tenant_id, url, raw_html, cleaned_markdown)`
- **Update `app/main.py`** — Start/stop Kafka producers in lifespan
- **Update `app/services/discovery_executor.py`** — Emit trace events at each step:
  - "Initializing search for: {query}"
  - "Scraping {url} ({n}/{total})"
  - "Content cleaned: {url}"
  - "Discovery complete — {n} sources processed"

### Tests: `test_kafka_producer.py`
- TraceProducer sends correctly shaped events
- AuditProducer sends raw+cleaned pair
- Kafka unavailable doesn't crash producer

---

## Phase 6: GCS + Data Ingestion Handoff

**Goal**: When a URL resolves to a downloadable file (PDF/Excel), upload to GCS `_landing/` and emit an `IngestionEvent` to `raw-ingestion-topic` for the data-ingestion pipeline to process.

### Files to create/modify

- **`app/services/file_handler.py`** — `FileHandler` class:
  - `__init__(gcs_project_id, gcs_bucket, gcs_credentials_path, kafka_producer)`
  - `handle_downloadable(url, content_type, content_bytes, tenant_id, job_id) -> SourceItem`:
    1. Download file content (already have from scraping attempt)
    2. Upload to `gs://{bucket}/_landing/{uuid}_{filename}`
    3. Emit `IngestionEvent` to `raw-ingestion-topic` (matching data_ingestion domain model schema)
    4. Return `SourceItem(type="document", title=filename, url=gcs_uri)`
  - Stub mode: if no GCS credentials, log warning and return source reference without upload
- **Update `app/services/discovery_executor.py`** — In the scrape loop, check `data_cleaner.is_downloadable()` and route to `FileHandler` instead of scraping
- **Update `app/scrapers/browser_engine.py`** — Return content-type header along with content so executor can detect downloadable files

### Tests: `test_file_handler.py`
- Downloadable file triggers GCS upload (mocked)
- IngestionEvent emitted to Kafka (mocked)
- No GCS credentials → stub mode works without crashing

---

## Phase 7: Docker Compose Integration

**Goal**: Standalone docker-compose for dev, and integration with the main workspace docker-compose.

### Files to create

- **`discovery-agent-svc/docker-compose.yml`** — Standalone dev compose:
  - discovery-agent-svc (port 8020)
  - Redis (port 6381, DB 2)
  - Healthcheck on /health
- **Update `ai-brand-automator/docker-compose.yml`** — Add `discovery-agent` service:
  - Build from `../discovery-agent-svc`
  - Port: 8020
  - Environment: `DISCOVERY_REDIS_URL=redis://redis:6379/2`, `DISCOVERY_KAFKA_BOOTSTRAP_SERVERS=brand-kafka:9092`, `DISCOVERY_TAVILY_API_KEY=${TAVILY_API_KEY:-}`
  - Depends on: redis (healthy)
  - Network: `app-network`
  - Healthcheck: `curl -f http://localhost:8020/health`

---

## Phase 8: Unit Testing

**Goal**: Comprehensive unit test suite for all components. All external dependencies (Redis, Kafka, Tavily, httpx, GCS) are mocked. Tests run without any infrastructure.

### Files to create

- **`tests/__init__.py`**
- **`tests/conftest.py`** — Shared unit test fixtures:
  - `client` fixture: `httpx.AsyncClient` with `ASGITransport` wrapping the FastAPI app
  - `valid_execute_payload` fixture: returns a dict matching the ExternalWrapper payload shape
  - `tenant_headers` fixture: returns `{"X-Tenant-ID": "test-tenant"}`
  - `mock_redis_manager` fixture: `AsyncMock` of `RedisManager` (cache always misses, rate limit always allows)
  - `mock_search_engine` fixture: `AsyncMock` of `SearchEngine` returning controlled results
  - `mock_browser_engine` fixture: `AsyncMock` of `BrowserEngine` returning controlled HTML
  - `mock_trace_producer` fixture: `AsyncMock` of `TraceProducer` capturing sent events

- **`tests/test_schemas.py`** — Pydantic schema validation:
  - `ExecuteRequest` accepts valid ExternalWrapper payload
  - `ExecuteRequest` accepts payload with all optional fields omitted
  - `ExecuteRequest` rejects missing `input_prompt` (required field)
  - `TenantContext` parses all fields correctly
  - `SourceItem` validates `type` field (web, document, financial)
  - `ExecuteResponse` serializes with all fields present
  - `ExecuteResponse` serializes with empty `sources` and `findings` lists
  - Kafka `TraceEvent` schema includes all required fields (job_id, node_id, status, message, timestamp)
  - Kafka `AuditEvent` schema includes url, raw_html, cleaned_markdown

- **`tests/test_api_routes.py`** — Endpoint contract tests (mocked dependencies):
  - `GET /health` returns 200 with `{"status": "ok", "version": "0.1.0"}`
  - `POST /v1/execute` with valid payload returns 200 with `ExecuteResponse` shape
  - `POST /v1/search` with valid payload returns 200 (alias parity)
  - `POST /v1/execute` with empty body returns 422
  - `POST /v1/execute` with missing `input_prompt` returns 422
  - `POST /v1/execute` with invalid JSON returns 422
  - `POST /v1/execute` when rate limited returns 429 with error message
  - `POST /v1/execute` propagates `X-Tenant-ID` header to executor
  - `POST /v1/execute` with no `X-Tenant-ID` uses default tenant or returns 422

- **`tests/test_redis_manager.py`** — Cache and rate limit logic (mocked `redis.asyncio`):
  - `get_cached_search` returns parsed JSON when key exists
  - `get_cached_search` returns None when key doesn't exist
  - `set_cached_search` calls `redis.set` with correct key pattern `discovery:cache:{hash}` and TTL 14400s (4h)
  - `get_cached_page` returns Markdown string when key exists
  - `get_cached_page` returns None when key doesn't exist
  - `set_cached_page` calls `redis.set` with correct key pattern `discovery:page:{hash}` and TTL 86400s (24h)
  - `check_rate_limit` returns True when count <= limit
  - `check_rate_limit` returns False when count > limit
  - `check_rate_limit` sets EXPIRE on first increment (count == 1)
  - `check_rate_limit` does NOT reset EXPIRE on subsequent increments
  - Redis connection error in `get_cached_search` → returns None (doesn't raise)
  - Redis connection error in `check_rate_limit` → returns True (allows request, doesn't block)
  - `close()` closes the Redis connection

- **`tests/test_search_engine.py`** — Search engine with Tavily + caching:
  - Stub mode (no API key): returns realistic mock results with titles and URLs
  - Stub mode: results include URLs relevant to query keywords
  - Real mode: calls Tavily SDK `search()` method with correct parameters
  - Real mode: caches Tavily result via `redis_manager.set_cached_search()`
  - Cache hit: returns cached result, does NOT call Tavily SDK
  - Cache miss: calls Tavily SDK, returns fresh results
  - Tavily API error: returns empty results list, does not raise
  - `search()` respects `max_results` parameter
  - Results have correct shape: `[{title: str, url: str, snippet: str}]`

- **`tests/test_browser_engine.py`** — URL scraping:
  - Successful scrape: returns raw HTML string
  - Scrape checks Redis page cache first via `redis_manager.get_cached_page()`
  - Cache hit: returns cached Markdown, does NOT make HTTP request
  - Cache miss: makes httpx GET request with appropriate User-Agent header
  - Scrape caches cleaned result via `redis_manager.set_cached_page()`
  - HTTP 404 error: returns empty string, does not raise
  - HTTP timeout: returns empty string, does not raise
  - Connection error: returns empty string, does not raise
  - Response includes content-type header for downloadable detection
  - Timeout parameter is respected in httpx client

- **`tests/test_data_cleaner.py`** — HTML to Markdown conversion:
  - Simple HTML converts to correct Markdown
  - `<script>` tags are stripped before conversion
  - `<style>` tags are stripped before conversion
  - `<nav>` elements are stripped before conversion
  - `<header>` and `<footer>` elements are stripped
  - Empty HTML returns empty string
  - HTML with only scripts/styles returns empty string
  - Very long content is truncated to `max_length` (default 50000 chars)
  - `is_downloadable("file.pdf", "application/pdf")` returns True
  - `is_downloadable("file.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")` returns True
  - `is_downloadable("file.csv", "text/csv")` returns True
  - `is_downloadable("page.html", "text/html")` returns False
  - `is_downloadable("image.png", "image/png")` returns False

- **`tests/test_discovery_executor.py`** — Core orchestration logic (all deps mocked):
  - `execute()` builds search query from `input_prompt` + `config.focus`
  - `execute()` calls `redis_manager.check_rate_limit()` with correct tenant_id
  - Rate limit exceeded: raises HTTPException 429
  - `execute()` calls `search_engine.search()` with constructed query
  - `execute()` calls `browser_engine.scrape()` for each search result URL
  - `execute()` calls `data_cleaner.clean()` on each scraped HTML
  - `execute()` skips downloadable URLs (routes to file handler)
  - `execute()` respects `MAX_SCRAPE_URLS` limit
  - `execute()` returns `ExecuteResponse` with correct fields
  - Response `sources` list matches scraped URLs
  - Response `findings` extracts key content from cleaned Markdown
  - Response `raw_context` concatenates all cleaned Markdown
  - Response `query` matches the constructed search query
  - `execute()` emits trace events via `trace_producer` at each step
  - Trace events emitted in correct order: init → scrape per URL → complete
  - Search engine returns empty results → response has empty sources/findings (not error)
  - All scrapes fail → response still valid with empty raw_context
  - `close()` cleans up all resources

- **`tests/test_kafka_producer.py`** — Kafka event emission:
  - `TraceProducer.start()` creates aiokafka producer
  - `TraceProducer.send_step()` produces to `agent-trace-topic`
  - `TraceProducer.send_step()` serializes event as JSON with correct schema
  - `TraceProducer.send_step()` includes timestamp in ISO 8601 format
  - `TraceProducer` graceful on connection error (logs warning, doesn't raise)
  - `TraceProducer.stop()` closes producer
  - `TraceProducer.is_connected` returns False when not started
  - `AuditProducer.send_audit()` produces to `discovery-audit-topic`
  - `AuditProducer.send_audit()` includes both raw_html and cleaned_markdown
  - `AuditProducer` graceful on connection error

- **`tests/test_file_handler.py`** — GCS upload + ingestion event:
  - `handle_downloadable()` uploads content to GCS with `_landing/` prefix
  - GCS destination path includes UUID prefix: `_landing/{uuid}_{filename}`
  - `handle_downloadable()` emits `IngestionEvent` to `raw-ingestion-topic`
  - `IngestionEvent` matches data_ingestion domain schema (event_id, trace_id, tenant_id, file_path, file_type)
  - `IngestionEvent.source` is `"api-integration"`
  - `IngestionEvent.metadata` includes `source_url` and `job_id`
  - `handle_downloadable()` returns `SourceItem` with type="document"
  - Stub mode (no GCS creds): logs warning, returns SourceItem with original URL
  - GCS upload error: logs error, returns SourceItem with original URL (doesn't crash)
  - Kafka unavailable: GCS upload still succeeds, ingestion event skipped

### Test configuration in `pyproject.toml`

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: integration tests requiring Redis (deselect with '-m not integration')",
]

[tool.black]
line-length = 88
target-version = ["py312"]
```

### Running tests

```bash
# All unit tests (no infrastructure needed)
pytest tests/ -m "not integration" -v

# Specific test file
pytest tests/test_discovery_executor.py -v

# Specific test
pytest tests/test_data_cleaner.py::TestDataCleaner::test_strips_script_tags -v

# With coverage
pytest tests/ -m "not integration" --cov=app --cov-report=term-missing
```

---

## Design Decisions

1. **Dual endpoints**: `/v1/execute` (per DDD) + `/v1/search` (per existing seed manifests) — both route to the same handler. No seed manifest changes needed.
2. **Port 8020**: Follows the 80xx pattern (orchestrator 8010, discovery 8020, intelligence will be 8030).
3. **Redis DB 2**: Separate from Celery (DB 0), orchestrator checkpointing (DB 1).
4. **httpx-first scraping**: Start with `httpx.AsyncClient` for URL fetching. Playwright is heavy and can be added as an optional mode later without changing the interface.
5. **Tavily stub mode**: When `DISCOVERY_TAVILY_API_KEY` is empty, SearchEngine returns realistic mock data. Enables development without API credits.
6. **GCS stub mode**: When `DISCOVERY_GCS_CREDENTIALS_PATH` is empty, FileHandler logs and skips upload. Returns source reference pointing to the original URL.
7. **Kafka optional**: Same graceful degradation pattern as orchestrator. Service runs in HTTP-only mode when broker unavailable.
8. **Rate limiting via Redis**: `INCR` + `EXPIRE` pattern per DDD. Returns HTTP 429 when tenant exceeds limit. Degrades to no-limit on Redis failure.
9. **No hexagonal architecture**: The DDD specifies a flat structure. This service is simpler than data-ingestion (no complex domain events), so flat app/ layout is appropriate.

---

## Critical File References

| File | Why It Matters |
|------|---------------|
| `pipeline-orchestrator-svc/app/nodes/external_wrapper.py` | Exact HTTP payload sent to discovery (POST with input_prompt, config, tenant_context) |
| `ai-brand-automator/orchestration/management/commands/seed_manifests.py` | 3 manifests reference `/v1/search` with config.focus values |
| `pipeline-orchestrator-svc/app/nodes/internal/manager_node.py` | Aggregates `findings` and `recommendations` from node outputs |
| `ai-brand-automator/data_ingestion/domain/models.py` | IngestionEvent schema for GCS handoff |
| `ai-brand-automator-frontend/src/components/pipelines/BrandEquityDashboard.tsx` | Renders `sources` array with `{type, title, url}` |
| `ai-brand-automator-frontend/src/components/pipelines/ResultDashboard.tsx` | Renders `findings`, `recommendations`, `summary`, `score` |
| `pipeline-orchestrator-svc/app/core/config.py` | Pattern for pydantic-settings with env prefix |
| `pipeline-orchestrator-svc/app/messaging/kafka_producer.py` | Pattern for optional Kafka with graceful degradation |

---

## Phase 9: Integration Testing

**Goal**: Automated integration tests that verify the full flow from orchestrator → discovery → response, Redis caching behavior, Kafka event emission, and rate limiting — all within pytest using real (or containerized) Redis and mocked external APIs.

### Files to create

- **`tests/integration/__init__.py`**
- **`tests/integration/conftest.py`** — Shared integration fixtures:
  - `redis_client` fixture: connects to a real Redis instance (localhost:6379/2 or `DISCOVERY_TEST_REDIS_URL` env var), flushes DB before each test, tears down after
  - `app_with_redis` fixture: FastAPI `TestClient` with real Redis wired into the app (not mocked)
  - `mock_tavily` fixture: patches Tavily SDK to return controlled search results
  - `mock_httpx_scrape` fixture: patches httpx to return controlled HTML for specific URLs
  - `kafka_capture` fixture: captures Kafka events in a list instead of sending to broker
- **`tests/integration/test_full_execute_flow.py`** — End-to-end execute endpoint:
  - Send ExternalWrapper-shaped payload to `POST /v1/execute`
  - Verify response contains `query`, `sources`, `findings`, `recommendations`, `raw_context`
  - Verify each source has `type`, `title`, `url`
  - Verify `findings` is a non-empty list of strings
  - Verify response completes within 60s timeout (matching orchestrator's ExternalWrapper timeout)
- **`tests/integration/test_search_alias.py`** — Verify `/v1/search` returns identical results to `/v1/execute` for same payload
- **`tests/integration/test_redis_caching.py`** — Cache behavior with real Redis:
  - First call with query → Tavily SDK called once, result cached
  - Second call with same query → Tavily SDK NOT called, result returned from cache
  - Verify cache key `discovery:cache:{hash}` exists in Redis with correct TTL (~4h)
  - First scrape of URL → httpx called, page cached
  - Second scrape of same URL → httpx NOT called, cached Markdown returned
  - Verify cache key `discovery:page:{hash}` exists with correct TTL (~24h)
- **`tests/integration/test_rate_limiting.py`** — Rate limit with real Redis:
  - Send `RATE_LIMIT_PER_MINUTE` requests → all return 200
  - Send one more request within same minute → returns 429 with clear error message
  - Wait for rate window to expire (or manually flush key) → next request returns 200
  - Verify `discovery:rate:{tenant_id}` key has 60s TTL
  - Different tenant_ids have independent rate limits
- **`tests/integration/test_kafka_events.py`** — Kafka trace + audit event emission:
  - Execute a request, capture Kafka events via `kafka_capture` fixture
  - Verify trace events emitted in order: "Initializing search...", "Scraping {url}...", "Discovery complete"
  - Each trace event has `job_id`, `node_id`, `status`, `message`, `timestamp`
  - Verify audit events contain `url`, `raw_html`, `cleaned_markdown` pairs
  - Verify events are NOT emitted when Kafka is disabled (empty bootstrap servers)
- **`tests/integration/test_orchestrator_contract.py`** — Contract compatibility:
  - Construct exact payload that `ExternalWrapper` sends (from `external_wrapper.py:35-41`)
  - Send to `/v1/execute` and `/v1/search`
  - Verify response can be stored in `node_outputs[node_id]` (is a valid JSON dict)
  - Verify `findings` and `recommendations` arrays exist (required by `ManagerNode` aggregation)
  - Verify all three config.focus variations from seed manifests work:
    - `{"focus": "royalty_rates,market_trends,brand_rankings"}` (iso-brand-equity)
    - `{"focus": "market_trends,competitors"}` (brand-analysis)
    - `{"focus": "competitors,market_share"}` (competitor-audit)
- **`tests/integration/test_file_handoff.py`** — GCS + ingestion handoff:
  - Mock a URL that returns `Content-Type: application/pdf`
  - Verify discovery does NOT try to clean it as HTML
  - Verify GCS upload is triggered (mocked) with correct `_landing/` path
  - Verify `IngestionEvent` emitted to `raw-ingestion-topic` matches the data_ingestion domain schema
  - Verify the source appears in response with `type: "document"`
  - Stub mode (no GCS creds): verify no upload attempted, source still returned with original URL
- **`tests/integration/test_tenant_isolation.py`** — Multi-tenant safety:
  - Send requests with different `X-Tenant-ID` headers
  - Verify rate limits are independent per tenant
  - Verify cache keys include tenant context where appropriate
  - Verify `X-Tenant-ID` is propagated in audit events
- **`tests/integration/test_error_resilience.py`** — Graceful degradation:
  - Redis unavailable → service still returns results (no cache, no rate limit)
  - Tavily API error → stub results returned, no 500
  - Scraping a URL that returns 404 → skipped gracefully, other URLs still processed
  - All URLs fail to scrape → response still valid with empty findings
  - Request with empty `input_prompt` → handled gracefully

### Test configuration

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "integration: integration tests requiring Redis (deselect with '-m not integration')",
]
```

Integration tests are marked with `@pytest.mark.integration` so they can be excluded in CI environments without Redis:
```bash
# Run unit tests only
pytest tests/ -m "not integration"

# Run integration tests only (requires Redis on localhost:6379)
pytest tests/integration/ -v

# Run everything
pytest tests/ -v
```

---

## Verification Plan

### Unit Tests (per phase)
- `pytest tests/ -m "not integration" -v` — runs after each phase

### Integration Tests (Phase 8)
- `pytest tests/integration/ -v` — requires Redis running locally
- CI: spin up Redis via `docker run -d -p 6379:6379 redis:7-alpine` before test step

### Manual Smoke Test
- Start service: `uvicorn app.main:app --port 8020`
- Send ExternalWrapper payload via curl, verify response shape

### End-to-End with Orchestrator
- Start both services (orchestrator on 8010, discovery on 8020)
- Create a `brand-analysis` job from Django
- Verify orchestrator calls discovery at `/v1/search`
- Verify ManagerNode aggregates findings into result_data
- Verify frontend ThoughtTrace shows discovery node progress
- Verify BrandEquityDashboard renders sources as clickable citations

### Cache Verification
- Send same query twice, verify second call faster (Redis cache hit in logs)

### Rate Limit Verification
- Send 11 requests in 1 minute for same tenant, verify 429 on 11th
