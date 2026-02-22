# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

`intelligence-agent-svc` is a FastAPI microservice (port 8030) that performs ISO 10668 brand valuation and analytical intelligence for the pipeline orchestrator. It calculates brand value using the Royalty Relief NPV methodology, scores brands via a multi-pillar Brand Strength Index (BSI), performs competitive gap analysis from discovery findings, and extracts themes with sentiment scoring. It supports both AI-powered analysis (Gemini) and rule-based calculations (NumPy).

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8030

# Run all unit tests (no Redis needed)
pytest tests/ -v -m "not integration"

# Run integration tests (requires Redis on localhost:6379)
pytest tests/integration/ -v -m integration

# Run a single test file
pytest tests/test_royalty_relief.py -v

# Run a single test
pytest tests/test_proxy_engine.py::TestProxyEngine::test_redistribute_missing_financial -v

# Format code
black app/ tests/

# Docker Compose (standalone dev)
docker compose up --build
```

## Architecture

Flat `app/` layout matching discovery-agent-svc patterns:

- **`app/api/`** — FastAPI routes and Pydantic v2 schemas. Three POST endpoints: `/v1/execute` (primary router), `/v1/iso-calc` (ISO valuation alias), `/v1/analyze` (gap analysis alias). Module-level `executor` variable set by lifespan.
- **`app/core/`** — Config (`Settings` with `INTELLIGENCE_` env prefix) and structured logging.
- **`app/cache/`** — `RedisManager` with benchmark cache (30d TTL), WACC cache (30d TTL), result cache (4h TTL), and per-tenant rate limiting (INCR+EXPIRE, 60s window). All ops fail open.
- **`app/logic/iso_engine/`** — `RoyaltyReliefEngine` (NumPy NPV calculation), `BSICalculator` (0-100 multi-pillar scoring), `ProxyEngine` (dynamic weight redistribution for missing data).
- **`app/logic/analysis/`** — `CompetitiveGapAnalyzer` (AI or rule-based gap extraction), `ThemeAnalyzer` (keyword-based theme + sentiment scoring).
- **`app/services/`** — `IntelligenceExecutor` (routes to ISO/gap/general flows), `StorageService` (GCS financial data), `RAGAdapter` (Vertex AI historical context).
- **`app/messaging/`** — `TraceProducer` (agent-trace-topic) and `AuditProducer` (valuation-audit-logs). Both graceful when Kafka unavailable.

## Key Contracts

**Input** (from orchestrator's ExternalWrapper):
```
POST /v1/execute (or /v1/iso-calc, /v1/analyze)
Headers: X-Tenant-ID, Content-Type: application/json
Body: {input_prompt, input_context, tenant_context, config, previous_outputs}
```

**Output** (consumed by ManagerNode):
```json
{
  "findings": ["Brand value estimated at $X...", "BSI: 72/100"],
  "recommendations": ["Improve brand awareness..."],
  "valuation": {"brand_value_npv": 142154.52, "royalty_rate": 0.04, ...},
  "bsi": {"score": 72, "pillars": [...], "data_completeness": 1.0},
  "methodology": "royalty_relief",
  "rationale": "Step-by-step derivation...",
  "analysis_type": "iso_valuation"
}
```

**Routing Logic**: `config.method == "royalty_relief"` → ISO valuation; `config.analysis_type == "competitive_gap"` → gap analysis; otherwise → general analysis.

## ISO 10668 Royalty Relief Formula

```
NPV = Σ (Revenue_t × RoyaltyRate × (1 - TaxRate)) / (1 + DiscountRate)^t
```

BSI Pillars: Financial (40%), Behavioral (35%), Legal (25%). When a pillar is missing, `ProxyEngine` redistributes weights proportionally (e.g., Financial missing → Behavioral 58.3%, Legal 41.7%).

## Environment Variables

All prefixed with `INTELLIGENCE_`. Key ones:
- `INTELLIGENCE_GEMINI_API_KEY` — empty = rule-based only mode
- `INTELLIGENCE_REDIS_URL` — default `redis://localhost:6379/3` (DB 3)
- `INTELLIGENCE_KAFKA_BOOTSTRAP_SERVERS` — empty = no Kafka events
- `INTELLIGENCE_GCS_PROJECT_ID` / `INTELLIGENCE_GCS_BUCKET_NAME` — empty = GCS stub mode
- `INTELLIGENCE_RAG_PROJECT_ID` — empty = RAG stub mode
- `INTELLIGENCE_RATE_LIMIT_PER_MINUTE` — default 10
- `INTELLIGENCE_DEFAULT_HORIZON_YEARS` — default 5
- `INTELLIGENCE_DEFAULT_TAX_RATE` — default 0.25
- `INTELLIGENCE_DEFAULT_DISCOUNT_RATE` — default 0.10

## Testing Conventions

- `asyncio_mode = "auto"` in pyproject.toml — no `@pytest.mark.asyncio` decorators needed
- Integration tests require Redis and are marked `@pytest.mark.integration`
- All external dependencies (Redis, Kafka, GCS, Gemini) are mocked in unit tests
- Test classes use `TestClassName` pattern with `setup_method` for common initialization

## Redis Key Patterns

- `intel:benchmarks:{sector}` — industry royalty rates, 30d TTL
- `intel:wacc:{region}` — discount rates by region, 30d TTL
- `intel:rate:{tenant_id}` — rate limit counter, 60s TTL
- `intel:result:{md5(key)}` — cached analysis results, 4h TTL
