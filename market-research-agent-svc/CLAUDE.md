# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

`market-research-agent-svc` is a stateless FastAPI microservice (port 8021) that provides structured market research capabilities for the pipeline orchestrator. It performs market sizing (TAM/SAM/SOM), competitive landscape analysis, industry trend tracking, and economic indicator lookups using web search (Tavily), World Bank Open Data API, and GNews. Claude Sonnet 4 is used as the LLM for research planning and synthesis.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8021

# Run all tests
pytest tests/ -v

# Run unit tests only (no Redis needed)
pytest tests/ -m "not integration" -v

# Run a single test file
pytest tests/test_mra_executor.py -v

# Format code
black app/ tests/

# Docker Compose (standalone dev)
docker compose up --build
```

## Architecture

Flat `app/` layout following the standard microservice convention:

- **`app/api/`** — FastAPI routes and Pydantic v2 schemas. Dual endpoints: `POST /v1/execute` (primary) and `POST /v1/research` (alias for seed manifests). Module-level `executor` set by lifespan.
- **`app/core/`** — Config (`Settings` with `MRA_` env prefix) and structured logging.
- **`app/cache/`** — `RedisManager` with result cache (4h), economic data cache (24h), news cache (1h), and per-tenant rate limiting.
- **`app/services/`** — `MRAExecutor` (guardrail → cache → research → audit), `api_clients.py` (Tavily, WorldBank, GNews clients).
- **`app/logic/`** — `MarketResearcher` (PAOR reasoning loop), `guardrails.py` (input/output validation).
- **`app/messaging/`** — `TraceProducer` (agent-trace-topic) and `AuditProducer` (market-research-audit-topic). Both graceful when Kafka unavailable.

## Key Contracts

**Input** (from orchestrator's ExternalWrapper):
```
POST /v1/execute (or /v1/research)
Headers: X-Tenant-ID, Content-Type: application/json
Body: {input_prompt, input_context, tenant_context, config, previous_outputs}
```

**Output** (consumed by ManagerNode):
```json
{
  "query": "...",
  "market_overview": "...",
  "market_sizing": {"tam": "...", "sam": "...", "som": "..."},
  "competitive_landscape": [{"name": "...", "description": "...", "market_position": "..."}],
  "industry_trends": ["..."],
  "economic_indicators": {"gdp_WLD": {"latest_value": ..., "latest_date": "..."}},
  "sources": [{"type": "web|economic_data|news", "title": "...", "url": "..."}],
  "findings": ["..."],
  "recommendations": ["..."],
  "raw_context": "...",
  "confidence_score": 0.85,
  "methodology_notes": ["..."]
}
```

## Environment Variables

All prefixed with `MRA_`. Key ones:
- `MRA_ANTHROPIC_API_KEY` — empty = stub mode (no LLM synthesis)
- `MRA_TAVILY_API_KEY` — empty = no web search
- `MRA_GNEWS_API_KEY` — empty = no news data
- `MRA_REDIS_URL` — default `redis://localhost:6379/11` (DB 11)
- `MRA_KAFKA_BOOTSTRAP_SERVERS` — empty = no Kafka events
- `MRA_LLM_MODEL` — default `claude-sonnet-4-5-20250929`
- `MRA_RATE_LIMIT_PER_MINUTE` — default 10

## Testing Conventions

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorators needed
- Integration tests require Redis and are marked `@pytest.mark.integration`
- All external dependencies (Redis, Kafka, Tavily, Anthropic, httpx) are mocked in unit tests

## Redis Key Patterns

- `mra:result:{md5(prompt+config)}` — research results, 4h TTL
- `mra:economic:{indicator}:{country}:{year}` — World Bank data, 24h TTL
- `mra:news:{md5(query)}` — news results, 1h TTL
- `mra:rate:{tenant_id}` — rate limit counter, 60s TTL
