# Implementation Plan: `intelligence-agent-svc`

## Context

The AI Brand Automator platform needs its analytical "Brain" service — `intelligence-agent-svc`. Two seed manifests already reference it:

1. **iso-brand-equity**: `valuation_logic` node calls `http://intelligence-agent-svc/v1/iso-calc` with `config: {"method": "royalty_relief", "horizon_years": 5}`
2. **competitor-audit**: `gap_analyzer` node calls `http://intelligence-agent-svc/v1/analyze` with `config: {"analysis_type": "competitive_gap"}`

The service currently does not exist. The orchestrator's ExternalWrapper falls back to stub data when it's unreachable. We need to implement the full service following the DDD spec (ISO 10668 Royalty Relief, BSI Calculator, Proxy Engine) and matching the discovery-agent-svc architectural patterns.

## Orchestrator Contract (MUST match)

**Request** (POST from ExternalWrapper, 60s timeout):
```json
{
  "input_prompt": "string",
  "input_context": {},
  "tenant_context": {"tenant_id": "", "gcs_raw_bucket": "", "gcs_processed_bucket": "", "rag_data_store_id": ""},
  "config": {"method": "royalty_relief", "horizon_years": 5, "model": "gemini-2.0-flash", "temperature": 0.3},
  "previous_outputs": {"web_research": {"findings": [...], "sources": [...], ...}}
}
```
**Header**: `X-Tenant-ID: <tenant_id>`

**Response** (MUST include `findings` and `recommendations` for ManagerNode aggregation):
```json
{
  "findings": ["Brand value estimated at $X using Royalty Relief method", ...],
  "recommendations": ["Consider improving brand awareness score", ...],
  "valuation": {"brand_value_npv": 1250000.0, "royalty_rate": 0.045, "discount_rate": 0.10, ...},
  "bsi": {"score": 72, "pillars": {...}},
  "methodology": "royalty_relief",
  "rationale": "Step-by-step derivation..."
}
```

## Service Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Port | 8030 | Follows 8010 (orchestrator), 8020 (discovery) |
| Redis DB | 3 | Follows DB 1 (orchestrator), DB 2 (discovery) |
| External Redis Port | 6382 | Follows 6380, 6381 |
| Env Prefix | `INTELLIGENCE_` | Follows `ORCHESTRATOR_`, `DISCOVERY_` |
| Python | 3.12 | Same as all services |

---

## Directory Structure

```
intelligence-agent-svc/
├── app/
│   ├── __init__.py
│   ├── main.py                         # FastAPI + lifespan (initialize executor, Redis, Kafka)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                   # /health, /v1/execute, /v1/iso-calc, /v1/analyze
│   │   └── schemas.py                  # ExecuteRequest, ExecuteResponse, ValuationResult, BSIResult
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                   # Settings with INTELLIGENCE_ prefix
│   │   └── logging_config.py           # Structured logging (copy discovery pattern)
│   ├── cache/
│   │   ├── __init__.py
│   │   └── redis_manager.py            # Benchmark cache, WACC cache, rate limiting
│   ├── logic/
│   │   ├── __init__.py
│   │   ├── iso_engine/
│   │   │   ├── __init__.py
│   │   │   ├── royalty_relief.py       # NPV calculation using NumPy
│   │   │   ├── bsi_calculator.py       # Brand Strength Index (0-100)
│   │   │   └── proxy_engine.py         # Dynamic weight redistribution for missing data
│   │   └── analysis/
│   │       ├── __init__.py
│   │       ├── competitive_gap.py      # Gap analysis from discovery findings
│   │       └── theme_analyzer.py       # NLP theme extraction + sentiment
│   ├── services/
│   │   ├── __init__.py
│   │   ├── intelligence_executor.py    # Core orchestration: route → analyze → return
│   │   ├── storage_service.py          # Fetch tenant financial docs from GCS
│   │   └── rag_adapter.py              # Query Vertex AI RAG for historical context
│   └── messaging/
│       ├── __init__.py
│       ├── kafka_producer.py           # TraceProducer + AuditProducer
│       └── schemas.py                  # TraceEvent, AuditEvent
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Shared fixtures (async client, payloads, headers)
│   ├── test_routes.py                  # Endpoint contract tests
│   ├── test_intelligence_executor.py   # Executor orchestration tests
│   ├── test_royalty_relief.py          # NPV math validation
│   ├── test_bsi_calculator.py          # BSI scoring tests
│   ├── test_proxy_engine.py            # Weight redistribution tests
│   ├── test_competitive_gap.py         # Gap analysis tests
│   ├── test_redis_manager.py           # Cache tests
│   └── integration/
│       ├── __init__.py
│       ├── conftest.py                 # Real Redis fixtures
│       └── test_full_execute_flow.py   # End-to-end with real Redis
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
└── CLAUDE.md
```

---

## Files to Create (Implementation Order)

### Phase 1: Project Scaffolding

#### 1.1 `pyproject.toml`
Replicate from discovery-agent-svc. Changes: name=`intelligence-agent-svc`, description=`ISO 10668 brand valuation and analytical intelligence agent`.

#### 1.2 `requirements.txt`
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.9.0
pydantic-settings>=2.5.0
httpx>=0.27.0
redis>=5.0.0
aiokafka>=0.11.0
numpy>=1.26.0
pandas>=2.2.0
google-cloud-storage>=2.18.0
google-cloud-aiplatform>=1.38.0
google-generativeai>=0.8.0
```

#### 1.3 `requirements-dev.txt`
```
-r requirements.txt
pytest>=8.0.0
pytest-asyncio>=0.24.0
pytest-httpx>=0.30.0
black>=24.0.0
mypy>=1.11.0
```

#### 1.4 `Dockerfile`
Copy from discovery-agent-svc. Change: `EXPOSE 8030`, CMD port to 8030.

#### 1.5 `docker-compose.yml`
Copy from discovery-agent-svc. Changes:
- Service name: `intelligence-agent`
- Port: `8030:8030`
- Redis port: `6382:6379`
- Env prefix: `INTELLIGENCE_`
- Redis URL: `redis://redis:6379/3`

---

### Phase 2: Core Layer

#### 2.1 `app/core/config.py`
**Reuse pattern from**: `discovery-agent-svc/app/core/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INTELLIGENCE_", case_sensitive=False)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/3"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = ""

    # Gemini AI
    GEMINI_API_KEY: str = ""                  # empty = stub mode (rule-based only)
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # GCS
    GCS_PROJECT_ID: str = ""                  # empty = stub mode
    GCS_BUCKET_NAME: str = ""
    GCS_CREDENTIALS_PATH: str = ""

    # Vertex AI RAG
    RAG_PROJECT_ID: str = ""
    RAG_LOCATION: str = "us-central1"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8030
    LOG_LEVEL: str = "INFO"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 10

    # ISO defaults
    DEFAULT_HORIZON_YEARS: int = 5
    DEFAULT_TAX_RATE: float = 0.25
    DEFAULT_DISCOUNT_RATE: float = 0.10

settings = Settings()
```

#### 2.2 `app/core/logging_config.py`
Direct copy from `discovery-agent-svc/app/core/logging_config.py`. Same formatter, same noisy library suppression.

---

### Phase 3: API Layer

#### 3.1 `app/api/schemas.py`
**Reuse**: `ExecuteRequest` is identical to discovery-agent-svc. New response models for valuation output.

```python
# --- Request (same as discovery) ---
class TenantContext(BaseModel):
    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""

class ExecuteRequest(BaseModel):
    input_prompt: str
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: TenantContext | dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)

# --- Response models ---
class PillarScore(BaseModel):
    name: str                               # "financial", "behavioral", "legal"
    weight: float                           # 0.0-1.0
    score: float                            # 0-100
    rationale: str

class BSIResult(BaseModel):
    score: int                              # 0-100
    pillars: list[PillarScore]
    data_completeness: float                # 0.0-1.0

class ValuationResult(BaseModel):
    brand_value_npv: float
    royalty_rate: float
    discount_rate: float
    tax_rate: float
    horizon_years: int
    annual_royalties: list[float]           # per-year royalty amounts
    methodology: str                        # "royalty_relief" or "price_premium"

class ExecuteResponse(BaseModel):
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    valuation: ValuationResult | None = None
    bsi: BSIResult | None = None
    methodology: str = ""
    rationale: str = ""
    analysis_type: str = ""                 # "iso_valuation" | "competitive_gap"
    gap_analysis: dict[str, Any] | None = None

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
```

#### 3.2 `app/api/routes.py`
**Reuse pattern from**: `discovery-agent-svc/app/api/routes.py`

Three endpoints (matching seed manifest URLs):
- `POST /v1/execute` — primary endpoint (generic analysis dispatch)
- `POST /v1/iso-calc` — alias for ISO valuation (`config.method` defaults to `royalty_relief`)
- `POST /v1/analyze` — alias for competitive gap analysis (`config.analysis_type` defaults to `competitive_gap`)
- `GET /health`

Module-level `executor: Optional[IntelligenceExecutor] = None` set by lifespan.

The `_execute_intelligence()` helper determines the analysis type from `config`:
- If `config.method == "royalty_relief"` → ISO valuation flow
- If `config.analysis_type == "competitive_gap"` → Gap analysis flow
- Otherwise → general AI analysis

---

### Phase 4: Cache Layer

#### 4.1 `app/cache/redis_manager.py`
**Reuse pattern from**: `discovery-agent-svc/app/cache/redis_manager.py`

Key patterns (from DDD spec):
```
intel:benchmarks:{sector}   → JSON   → 30 days TTL  (industry royalty rates)
intel:wacc:{region}         → Float  → 30 days TTL  (discount rates by region)
intel:rate:{tenant_id}      → Int    → 60s TTL      (rate limiting)
intel:result:{md5(key)}     → JSON   → 4h TTL       (cached analysis results)
```

Same fail-open pattern as discovery. Same lazy connection, close(), _hash() methods.

---

### Phase 5: ISO Engine (Rule-Based Calculations)

#### 5.1 `app/logic/iso_engine/royalty_relief.py`
Core NPV calculation using NumPy. No external dependencies.

```python
class RoyaltyReliefEngine:
    """ISO 10668 compliant Royalty Relief brand valuation."""

    def calculate_npv(
        self,
        projected_revenues: list[float],
        royalty_rate: float,
        discount_rate: float,
        tax_rate: float = 0.25,
    ) -> ValuationResult:
        """
        NPV = Sum (Revenue_t x RoyaltyRate x (1 - TaxRate)) / (1 + DiscountRate)^t

        Args:
            projected_revenues: Revenue forecast for each year
            royalty_rate: Comparable royalty rate (e.g., 0.045 for 4.5%)
            discount_rate: WACC or risk-adjusted discount rate
            tax_rate: Corporate tax rate (default 25%)

        Returns:
            ValuationResult with NPV and per-year breakdown
        """
        years = np.arange(1, len(projected_revenues) + 1)
        revenues = np.array(projected_revenues)
        royalties = revenues * royalty_rate * (1 - tax_rate)
        discount_factors = (1 + discount_rate) ** years
        present_values = royalties / discount_factors
        npv = float(np.sum(present_values))

        return ValuationResult(
            brand_value_npv=round(npv, 2),
            royalty_rate=royalty_rate,
            discount_rate=discount_rate,
            tax_rate=tax_rate,
            horizon_years=len(projected_revenues),
            annual_royalties=[round(float(r), 2) for r in royalties],
            methodology="royalty_relief",
        )

    def estimate_revenues_from_context(
        self, previous_outputs: dict, input_context: dict
    ) -> list[float]:
        """Extract or estimate 5-year revenue forecast from previous outputs and context."""
        ...

    @staticmethod
    def select_royalty_rate(sector: str, benchmarks: dict | None) -> float:
        """Select appropriate royalty rate from sector benchmarks."""
        SECTOR_DEFAULTS = {
            "technology": 0.04,
            "consumer_goods": 0.035,
            "financial_services": 0.025,
            "healthcare": 0.045,
            "default": 0.04,
        }
        if benchmarks and sector in benchmarks:
            return benchmarks[sector]
        return SECTOR_DEFAULTS.get(sector, SECTOR_DEFAULTS["default"])
```

#### 5.2 `app/logic/iso_engine/bsi_calculator.py`
Brand Strength Index scoring (0-100).

```python
class BSICalculator:
    """Brand Strength Index — ISO 10668 multi-pillar scoring."""

    DEFAULT_WEIGHTS = {
        "financial": 0.40,
        "behavioral": 0.35,
        "legal": 0.25,
    }

    def derive_index(
        self,
        financial_data: dict | None,
        behavioral_data: dict | None,
        legal_data: dict | None,
        weights: dict | None = None,
    ) -> BSIResult:
        """Calculate BSI from available pillar data."""
        ...
```

#### 5.3 `app/logic/iso_engine/proxy_engine.py`
Handles missing data gracefully per the DDD spec.

```python
class ProxyEngine:
    """Dynamic weight redistribution when data is incomplete."""

    def get_calculation_strategy(self, data_manifest: dict) -> str:
        if not data_manifest.get("financial_data"):
            return "PRICE_PREMIUM_MODE"
        return "STANDARD_ROYALTY_RELIEF"

    def redistribute_weights(
        self, available_pillars: list[str], default_weights: dict
    ) -> dict:
        available_weights = {k: v for k, v in default_weights.items() if k in available_pillars}
        total = sum(available_weights.values())
        if total == 0:
            return {p: 1.0 / len(available_pillars) for p in available_pillars}
        return {k: v / total for k, v in available_weights.items()}
```

---

### Phase 6: Analysis Layer (AI-Powered)

#### 6.1 `app/logic/analysis/competitive_gap.py`
Analyzes discovery findings to identify competitive gaps. Uses Gemini when available, falls back to rule-based extraction.

#### 6.2 `app/logic/analysis/theme_analyzer.py`
NLP theme extraction and sentiment analysis. Keyword-based fallback when Gemini unavailable.

---

### Phase 7: Services Layer

#### 7.1 `app/services/intelligence_executor.py`
Central orchestration service with constructor DI. Routes to ISO valuation, gap analysis, or general analysis based on config.

#### 7.2 `app/services/storage_service.py`
Fetch tenant-scoped financial documents from GCS. Stub mode when GCS not configured.

#### 7.3 `app/services/rag_adapter.py`
Query Vertex AI RAG for historical brand context. Stub mode when RAG not configured.

---

### Phase 8: Messaging Layer

#### 8.1 `app/messaging/kafka_producer.py`
TraceProducer (agent-trace-topic) + AuditProducer (valuation-audit-logs). Same graceful degradation as discovery.

#### 8.2 `app/messaging/schemas.py`
TraceEvent (reuse from discovery) + ValuationAuditEvent (new).

---

### Phase 9: App Entry Point

#### 9.1 `app/main.py`
FastAPI app with lifespan. Initializes Redis, GCS, RAG, Gemini, logic engines, and executor with DI.

---

### Phase 10: Testing

#### 10.1 `tests/conftest.py`
Shared fixtures: async client, ISO calc payload, gap analysis payload, tenant headers.

#### 10.2 `tests/test_royalty_relief.py`
Math validation: NPV against hand-calculated values, edge cases.

#### 10.3 `tests/test_bsi_calculator.py`
BSI scoring with various pillar combinations and missing data.

#### 10.4 `tests/test_proxy_engine.py`
Weight redistribution when pillars are missing.

#### 10.5 `tests/test_competitive_gap.py`
Gap analysis with realistic discovery findings as input.

#### 10.6 `tests/test_intelligence_executor.py`
Routing tests (ISO calc vs gap analysis vs general), mocked dependencies.

#### 10.7 `tests/test_routes.py`
Endpoint contract tests for all three endpoints.

#### 10.8 `tests/test_redis_manager.py`
Benchmark cache, WACC cache, rate limiting.

#### 10.9 `tests/integration/`
Integration tests with real Redis (marked `@pytest.mark.integration`).

---

### Phase 11: Documentation

#### 11.1 `CLAUDE.md`
Service-specific AI guidelines following the discovery-agent-svc pattern.

---

## Critical File References (Existing Code to Reuse)

| Source File | Reuse For |
|---|---|
| `discovery-agent-svc/app/main.py` | Lifespan pattern, CORS, app setup |
| `discovery-agent-svc/app/api/routes.py` | Module-level executor, dual endpoints, _execute helper |
| `discovery-agent-svc/app/api/schemas.py` | ExecuteRequest model (identical), response structure |
| `discovery-agent-svc/app/core/config.py` | Settings class with env prefix |
| `discovery-agent-svc/app/core/logging_config.py` | Direct copy |
| `discovery-agent-svc/app/cache/redis_manager.py` | Redis pattern (key structure, fail-open) |
| `discovery-agent-svc/app/messaging/kafka_producer.py` | TraceProducer + AuditProducer |
| `discovery-agent-svc/app/messaging/schemas.py` | TraceEvent model |
| `discovery-agent-svc/tests/conftest.py` | Test fixtures pattern |
| `discovery-agent-svc/pyproject.toml` | Project config template |
| `discovery-agent-svc/Dockerfile` | Dockerfile template |
| `discovery-agent-svc/docker-compose.yml` | Docker compose template |
| `pipeline-orchestrator-svc/app/nodes/external_wrapper.py` | Contract reference (payload format) |
| `ai-brand-automator/orchestration/management/commands/seed_manifests.py` | Seed manifest URLs and configs |

## Implementation Priority

1. **Project scaffolding** — pyproject.toml, requirements, Dockerfile, docker-compose, config, logging
2. **API layer** — schemas, routes, health endpoint
3. **ISO math engine** — royalty_relief.py, bsi_calculator.py, proxy_engine.py (+ tests)
4. **Analysis layer** — competitive_gap.py, theme_analyzer.py (+ tests)
5. **Executor** — intelligence_executor.py routing and orchestration (+ tests)
6. **Services** — storage_service.py (GCS), rag_adapter.py (Vertex AI) — stub mode
7. **Cache** — redis_manager.py with benchmark/WACC caching
8. **Messaging** — kafka_producer.py trace + audit
9. **Entry point** — main.py with lifespan wiring
10. **Route tests + integration tests**
11. **CLAUDE.md**

## Verification

```bash
# Create the service directory
cd /Users/naveenhanuman/Development/Prevision_WS/
mkdir -p intelligence-agent-svc

# After implementation, run tests
cd intelligence-agent-svc
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v

# Verify the service starts
uvicorn app.main:app --host 0.0.0.0 --port 8030

# Test health endpoint
curl http://localhost:8030/health

# Test ISO calc endpoint
curl -X POST http://localhost:8030/v1/iso-calc \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -d '{"input_prompt": "Calculate brand value", "config": {"method": "royalty_relief"}}'

# Test analyze endpoint
curl -X POST http://localhost:8030/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -d '{"input_prompt": "Analyze gaps", "config": {"analysis_type": "competitive_gap"}}'

# Run all workspace tests to ensure no regressions
cd ../pipeline-orchestrator-svc && .venv/bin/pytest tests/ -v
cd ../discovery-agent-svc && .venv/bin/pytest tests/ -v
```

### What Success Looks Like
- Service starts on port 8030 and responds to `/health`
- `/v1/iso-calc` returns `ValuationResult` with NPV, royalty rate, BSI score
- `/v1/analyze` returns competitive gap findings and recommendations
- `/v1/execute` auto-routes based on config
- All responses include `findings` and `recommendations` (ManagerNode compatibility)
- Math tests validate NPV against hand-calculated values
- Proxy Engine correctly redistributes weights when data is missing
- Service operates in stub mode when Gemini/GCS/RAG are unavailable
- Redis caching works for benchmarks and rate limiting
- Existing orchestrator E2E tests continue to pass
