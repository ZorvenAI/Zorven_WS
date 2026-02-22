# Integration Testing Plan: AI Pipeline Platform (ITP v1.0)

## Context

The AI Brand Automator platform has 4 microservices (Django backend, pipeline orchestrator, discovery agent, intelligence agent) with comprehensive unit tests (~200+ across all services) and orchestrator E2E tests (8 test files using httpx_mock). However, there are no **cross-service integration tests** that validate the actual contracts between services running in Docker containers. Recent bugs (missing `manifest_data` in auto-detect payloads, hardcoded BSI scores, celery-worker using stale images) prove that unit tests alone miss integration-level failures.

This plan implements 4 phases of integration testing per the ITP v1.0 design document.

---

## Service Architecture Under Test

```
Django Backend (core-api-service)
    |
    |  POST /v1/jobs/dispatch
    |  X-Service-Token auth
    v
Pipeline Orchestrator (:8010)
    |                          |
    |  POST /v1/execute        |  POST /v1/iso-calc
    |  POST /v1/search         |  POST /v1/analyze
    |  X-Tenant-ID header      |  X-Tenant-ID header
    v                          v
Discovery Agent (:8020)    Intelligence Agent (:8030)
    |                          |
    v                          v
  Redis (:6379/2)            Redis (:6379/3)

    Orchestrator --> PATCH callback_url --> Django Backend
                     X-Callback-Token auth
```

---

## Directory Structure

```
tests/integration/                       # New top-level directory in workspace root
├── conftest.py                          # Shared fixtures: Docker service URLs, auth tokens, helpers
├── docker-compose.test.yml              # Slim stack: orchestrator + discovery + intelligence + redis
├── pytest.ini                           # asyncio_mode=auto, markers, timeout defaults
├── requirements.txt                     # httpx, pytest-asyncio, pytest-timeout, numpy
│
├── phase1_contracts/                    # Phase 1: Service contract validation
│   ├── conftest.py                      # Contract-specific fixtures (payloads, manifests)
│   ├── test_dispatch_contract.py        # Django -> Orchestrator dispatch contract
│   ├── test_callback_contract.py        # Orchestrator -> Django callback contract
│   ├── test_discovery_contract.py       # Orchestrator -> Discovery agent contract
│   ├── test_intelligence_contract.py    # Orchestrator -> Intelligence agent contract
│   └── test_cancel_contract.py          # Django -> Orchestrator cancel flow
│
├── phase2_domain/                       # Phase 2: Domain logic validation
│   ├── conftest.py                      # Domain test fixtures (financial data, golden inputs)
│   ├── test_npv_benchmarks.py           # ISO 10668 Royalty Relief NPV accuracy
│   ├── test_bsi_scoring.py              # BSI multi-pillar scoring + ProxyEngine
│   ├── test_golden_path.py              # Full pipeline golden path (dispatch -> result)
│   ├── test_data_asymmetry.py           # Missing/partial data handling across pipeline
│   └── test_intent_routing.py           # Auto-detect manifest resolution accuracy
│
├── phase3_stress/                       # Phase 3: Stress and resilience
│   ├── conftest.py                      # Stress test fixtures (concurrent helpers)
│   ├── test_concurrent_pipelines.py     # N simultaneous pipeline executions
│   ├── test_rate_limiting.py            # Per-tenant rate limit enforcement
│   ├── test_redis_resilience.py         # Redis failure/recovery during execution
│   ├── test_agent_timeout.py            # Agent service timeout handling
│   └── test_cancel_under_load.py        # Cancel during active execution
│
└── phase4_frontend/                     # Phase 4: Frontend E2E (Playwright)
    ├── conftest.py                      # Playwright fixtures, page objects
    ├── test_pipeline_execution_ui.py    # Trigger pipeline, observe ThoughtTrace
    └── test_brand_equity_dashboard.py   # Verify BSI score renders correctly
```

---

## Test Infrastructure

### `docker-compose.test.yml`

Slim stack without frontend, Kong, or Celery -- tests call services directly via HTTP.

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  orchestrator:
    build:
      context: ../../pipeline-orchestrator-svc
      dockerfile: Dockerfile
    environment:
      - ORCHESTRATOR_REDIS_URL=redis://redis:6379/1
      - ORCHESTRATOR_SERVICE_TOKEN=test-service-token
      - ORCHESTRATOR_CALLBACK_TOKEN=test-callback-token
      - ORCHESTRATOR_KAFKA_BOOTSTRAP_SERVERS=
    ports: ["8010:8010"]
    depends_on:
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      interval: 5s
      timeout: 3s
      retries: 5

  discovery-agent-svc:
    build:
      context: ../../discovery-agent-svc
      dockerfile: Dockerfile
    environment:
      - DISCOVERY_REDIS_URL=redis://redis:6379/2
      - DISCOVERY_TAVILY_API_KEY=
      - DISCOVERY_KAFKA_BOOTSTRAP_SERVERS=
    ports: ["8020:8020"]
    depends_on:
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8020/health"]
      interval: 5s
      timeout: 3s
      retries: 5

  intelligence-agent-svc:
    build:
      context: ../../intelligence-agent-svc
      dockerfile: Dockerfile
    environment:
      - INTELLIGENCE_REDIS_URL=redis://redis:6379/3
      - INTELLIGENCE_GEMINI_API_KEY=
      - INTELLIGENCE_KAFKA_BOOTSTRAP_SERVERS=
    ports: ["8030:8030"]
    depends_on:
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8030/health"]
      interval: 5s
      timeout: 3s
      retries: 5
```

### Shared `conftest.py`

```python
"""Shared integration test fixtures."""
import asyncio
import pytest
import httpx

ORCHESTRATOR_URL = "http://localhost:8010"
DISCOVERY_URL = "http://localhost:8020"
INTELLIGENCE_URL = "http://localhost:8030"
SERVICE_TOKEN = "test-service-token"
CALLBACK_TOKEN = "test-callback-token"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def http_client():
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client

@pytest.fixture
def service_headers():
    return {"X-Service-Token": SERVICE_TOKEN, "Content-Type": "application/json"}

@pytest.fixture
def tenant_headers():
    return {"X-Tenant-ID": "integration-test-tenant", "Content-Type": "application/json"}
```

### `pytest.ini`

```ini
[pytest]
asyncio_mode = auto
markers =
    integration: marks tests as integration tests (require Docker stack)
    stress: marks tests as stress tests (longer timeout)
timeout = 60
```

### `requirements.txt`

```
httpx>=0.25.0
pytest>=7.4.0
pytest-asyncio>=0.23.0
pytest-timeout>=2.2.0
aiohttp>=3.9.0
redis>=5.0.0
numpy>=1.26.0
```

---

## Phase 1: Contract Tests

**Goal**: Validate request/response schemas between services match expectations.

### `test_dispatch_contract.py` (6 tests)

| Test | Description | Expected |
|------|-------------|----------|
| `test_dispatch_returns_202_accepted` | POST valid payload to `/v1/jobs/dispatch` | 202 `{"status": "accepted"}` |
| `test_dispatch_rejects_missing_job_id` | Missing `job_id` field | 422 validation error |
| `test_dispatch_rejects_bad_auth` | Wrong/missing `X-Service-Token` | 401 unauthorized |
| `test_dispatch_accepts_null_manifest` | `manifest: null` (auto-detect mode) | 202 accepted |
| `test_dispatch_accepts_manifest_with_nodes` | Full manifest with nodes/edges | 202 accepted |
| `test_dispatch_schema_matches_django_payload` | Payload mirrors `OrchestratorDispatcher._build_payload()` | 202 accepted |

**Dispatch Payload Schema** (mirrors `ai-brand-automator/orchestration/services.py:163-185`):

```json
{
  "job_id": "uuid-string",
  "manifest": {
    "nodes": [
      {"id": "node_id", "type": "internal|external", "handler": "NodeClass", "url": "...", "config": {}}
    ],
    "edges": [["source_id", "target_id"]],
    "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7}
  },
  "input_prompt": "Analyze brand positioning for Acme Corp",
  "input_context": {"company_id": 42},
  "tenant_context": {
    "tenant_id": "1",
    "gcs_raw_bucket": "brand-automator/1/",
    "gcs_processed_bucket": "brand-automator-curated/1/",
    "rag_data_store_id": "ds-123"
  },
  "callback_url": "http://host.docker.internal:9999/callback",
  "available_manifests": [
    {"pipeline_id": "brand-analysis", "name": "Brand Analysis", "description": "...", "manifest_data": {...}}
  ]
}
```

### `test_callback_contract.py` (5 tests)

These tests dispatch a job to the orchestrator with `callback_url` pointing to a local aiohttp server running in the test process to capture callbacks.

| Test | Description | Expected Callback Shape |
|------|-------------|------------------------|
| `test_callback_running_schema` | Dispatched job sends "running" callback | `{"status": "running", "progress": {"node_id": {"status": "pending"}}}` |
| `test_callback_progress_schema` | Per-node progress updates | `{"progress": {"node_id": {"status": "running", "started_at": "ISO8601"}}}` |
| `test_callback_completed_schema` | Pipeline completion | `{"status": "completed", "result_data": {...}, "progress": {...}}` |
| `test_callback_failed_schema` | Pipeline failure | `{"status": "failed", "error_message": "...", "progress": {...}}` |
| `test_callback_resolved_manifest_schema` | Auto-detect resolves manifest | `{"resolved_manifest_id": "brand-analysis", "progress": {...}}` |

### `test_discovery_contract.py` (5 tests)

Direct HTTP calls to discovery-agent-svc.

| Test | Description | Expected |
|------|-------------|----------|
| `test_execute_returns_expected_schema` | POST `/v1/execute` | Response has `query`, `sources`, `findings`, `recommendations`, `raw_context` |
| `test_search_alias_accepted` | POST `/v1/search` (seed manifest URL) | Same schema as `/v1/execute` |
| `test_tenant_id_header_propagated` | `X-Tenant-ID` header accepted | 200 OK |
| `test_empty_config_uses_defaults` | Missing `config.focus` | Still returns valid response |
| `test_response_findings_are_strings` | Each finding in the list | Is a string (not HTML, not nested dict) |

**Discovery Request Payload** (from `ExternalWrapper`):

```json
{
  "input_prompt": "Analyze brand positioning for Acme Corp",
  "input_context": {"company_id": 42},
  "tenant_context": {"tenant_id": "1", "gcs_raw_bucket": "...", "gcs_processed_bucket": "...", "rag_data_store_id": "..."},
  "config": {"focus": "market_trends,competitors"},
  "previous_outputs": {}
}
```

### `test_intelligence_contract.py` (6 tests)

Direct HTTP calls to intelligence-agent-svc.

| Test | Description | Expected |
|------|-------------|----------|
| `test_iso_calc_returns_valuation_and_bsi` | POST `/v1/iso-calc` | Response has `valuation`, `bsi`, `findings` |
| `test_analyze_returns_gap_analysis` | POST `/v1/analyze` | Response has `findings`, `recommendations` |
| `test_execute_routes_by_config_method` | `config.method="royalty_relief"` | ISO valuation path triggered |
| `test_execute_routes_by_analysis_type` | `config.analysis_type="competitive_gap"` | Gap analysis path triggered |
| `test_bsi_schema_has_pillars` | BSI object structure | `bsi.pillars` is list of `{name, weight, score, rationale}` |
| `test_valuation_schema_has_npv` | Valuation object structure | `valuation.brand_value_npv` is float > 0 |

### `test_cancel_contract.py` (3 tests)

| Test | Description | Expected |
|------|-------------|----------|
| `test_cancel_returns_200` | POST `/v1/jobs/{id}/cancel` | 200 `{"status": "ok"}` |
| `test_cancel_sets_redis_flag` | Check Redis after cancel | Key `cancel:{job_id}` exists |
| `test_cancel_rejects_bad_auth` | Wrong `X-Service-Token` | 401 |

---

## Phase 2: Domain Logic Validation

**Goal**: Verify ISO 10668 calculations, BSI scoring, and golden-path pipeline execution produce correct results.

### `test_npv_benchmarks.py` (5 tests)

Test the intelligence agent's NPV calculation against hand-calculated benchmarks.

| Test | Inputs | Expected NPV |
|------|--------|-------------|
| `test_npv_known_inputs` | Revenue $10M x 5yr, rate=4%, discount=10%, tax=25% | ~$1,137,236 (within +/-$1) |
| `test_npv_zero_revenues` | Empty revenue list | NPV = 0.0 |
| `test_npv_single_year` | $10M x 1yr, rate=4%, discount=10%, tax=25% | $272,727.27 |
| `test_npv_with_growth` | $10M base, 5% annual growth, 5yr | Compounded projection |
| `test_sector_royalty_rates` | Query sector rates | technology=4%, luxury=5%, retail=3% |

**NPV Formula** (ISO 10668 Royalty Relief):

```
NPV = Sum[ (Revenue_t x RoyaltyRate x (1 - TaxRate)) / (1 + DiscountRate)^t ]
```

**Manual calculation for `test_npv_known_inputs`**:

```
Year 1: $10,000,000 x 0.04 x 0.75 / 1.10^1 = $272,727.27
Year 2: $10,000,000 x 0.04 x 0.75 / 1.10^2 = $247,933.88
Year 3: $10,000,000 x 0.04 x 0.75 / 1.10^3 = $225,394.44
Year 4: $10,000,000 x 0.04 x 0.75 / 1.10^4 = $204,904.03
Year 5: $10,000,000 x 0.04 x 0.75 / 1.10^5 = $186,276.39
                                          Total: $1,137,236.01
```

### `test_bsi_scoring.py` (6 tests)

BSI Pillars: Financial (40%), Behavioral (35%), Legal (25%). ProxyEngine redistributes weights when pillars are missing.

| Test | Pillars Provided | Expected |
|------|-----------------|----------|
| `test_full_data_bsi` | All 3 | Uses 40/35/25 weights, completeness=1.0 |
| `test_missing_financial_pillar` | Behavioral + Legal | Weights: 58.3%/41.7%, completeness=0.67 |
| `test_missing_behavioral_pillar` | Financial + Legal | Weights: 61.5%/38.5%, completeness=0.67 |
| `test_no_data_uses_stubs` | None | Stub scores (65/60/70), completeness=0.0 |
| `test_bsi_score_clamped_0_100` | Extreme values | Score never outside 0-100 |
| `test_data_completeness_fraction` | 1, 2, 3 pillars | 0.33, 0.67, 1.0 |

### `test_golden_path.py` (3 tests)

Full pipeline execution via orchestrator dispatch, with callback capture.

| Test | Manifest | Validates |
|------|----------|-----------|
| `test_brand_analysis_golden_path` | brand-analysis (4 nodes, 1 external) | Callbacks: running -> progress -> completed. Findings from discovery present. |
| `test_iso_brand_equity_golden_path` | iso-brand-equity (4 nodes, 2 external) | `result_data.score` > 0, `result_data.valuation.brand_value_npv` > 0 |
| `test_content_strategy_golden_path` | content-strategy (4 nodes, all internal) | Completes without any external HTTP calls |

**Callback Capture Strategy**: Spin up a lightweight `aiohttp` server in the test process on `host.docker.internal:9999`. The orchestrator's `callback_url` points there, and the test collects all PATCH payloads to verify the lifecycle sequence.

### `test_data_asymmetry.py` (4 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_empty_input_context` | No company data provided | Pipeline completes with stub/default data |
| `test_discovery_returns_no_findings` | Discovery has no web results | Intelligence still produces valid BSI using stub behavioral data |
| `test_partial_financial_data` | Only `revenue_growth` provided | Financial pillar scored, others use stubs |
| `test_revenue_extracted_from_discovery_text` | Discovery findings contain "$51.2 billion" | Intelligence extracts and uses as base revenue |

### `test_intent_routing.py` (5 tests)

| Test | Input Prompt | Expected Resolution |
|------|-------------|-------------------|
| `test_brand_keywords_resolve_brand_analysis` | "brand positioning market analysis" | `brand-analysis` |
| `test_competitor_keywords_resolve_competitor_audit` | "competitor audit gap analysis" | `competitor-audit` |
| `test_content_keywords_resolve_content_strategy` | "content strategy editorial calendar" | `content-strategy` |
| `test_ambiguous_prompt_defaults_brand_analysis` | "do something interesting" | `brand-analysis` (default fallback) |
| `test_routing_plus_execution` | Any prompt + available_manifests | Routes, then executes full pipeline to completion |

---

## Phase 3: Stress & Resilience Tests

**Goal**: Verify the system handles concurrent load, rate limits, and infrastructure failures gracefully.

### `test_concurrent_pipelines.py` (3 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_5_concurrent_dispatches` | 5 simultaneous dispatches | All return 202 and eventually complete |
| `test_concurrent_different_manifests` | brand-analysis + competitor-audit + content-strategy | All 3 complete independently |
| `test_concurrent_same_tenant` | Multiple jobs for tenant "1" | No interference between jobs |

### `test_rate_limiting.py` (3 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_discovery_rate_limit` | >10 req/min to discovery from same tenant | 429 Too Many Requests |
| `test_intelligence_rate_limit` | >10 req/min to intelligence from same tenant | 429 Too Many Requests |
| `test_rate_limit_per_tenant` | Tenant A at limit, Tenant B requests | Tenant B unaffected (200 OK) |

### `test_redis_resilience.py` (2 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_pipeline_completes_without_redis` | Stop Redis mid-execution | Pipeline still completes (Redis is non-fatal) |
| `test_cancel_check_fails_open` | Redis down during cancel check | Returns false (doesn't crash executor) |

### `test_agent_timeout.py` (2 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_slow_agent_gets_stubbed` | Agent response >30s | ExternalWrapper returns stub data |
| `test_timeout_doesnt_crash_pipeline` | Timeout on one node | Pipeline continues with stub, marks node as done |

### `test_cancel_under_load.py` (2 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_cancel_during_execution` | Dispatch + immediate cancel | Job marked failed/cancelled |
| `test_cancel_after_first_node` | Wait for 1st node, then cancel | Partial progress preserved in callback |

---

## Phase 4: Frontend E2E (Playwright)

**Goal**: Verify the UI correctly displays pipeline progress and results.

> Phase 4 requires the full stack (Django + frontend + Kong + all agents) and Playwright. This phase is lower priority and should be implemented after Phases 1-3 are stable.

### `test_pipeline_execution_ui.py` (2 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_thought_trace_shows_progress` | Trigger analysis from UI | ThoughtTrace component shows node status transitions: pending -> running -> done |
| `test_completed_shows_results` | Pipeline completes | Results page shows summary, findings, recommendations |

### `test_brand_equity_dashboard.py` (2 tests)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_bsi_score_displayed_correctly` | ISO pipeline completes | BrandEquityDashboard shows score > 0 (not the old 8/100 bug) |
| `test_pillar_scores_displayed` | ISO pipeline completes | Dashboard shows Financial, Behavioral, Legal pillar scores |

---

## Seed Manifests (Test Data)

The following 4 pipeline manifests are used as test data. They mirror the seed manifests defined in `ai-brand-automator/orchestration/management/commands/seed_manifests.py`.

### brand-analysis

```json
{
  "nodes": [
    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
    {"id": "market_research", "type": "external", "url": "http://discovery-agent-svc:8020/v1/search", "config": {"focus": "market_trends,competitors"}},
    {"id": "brand_strategist", "type": "internal", "handler": "StrategyNode"},
    {"id": "report_generator", "type": "internal", "handler": "ReportNode"}
  ],
  "edges": [["intent_router", "market_research"], ["market_research", "brand_strategist"], ["brand_strategist", "report_generator"]],
  "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7}
}
```

### iso-brand-equity

```json
{
  "nodes": [
    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
    {"id": "web_research", "type": "external", "url": "http://discovery-agent-svc:8020/v1/search", "config": {"focus": "royalty_rates,market_trends,brand_rankings"}},
    {"id": "valuation_logic", "type": "external", "url": "http://intelligence-agent-svc:8030/v1/execute", "config": {"focus": "brand_valuation,royalty_rates"}},
    {"id": "manager", "type": "internal", "handler": "ManagerNode"}
  ],
  "edges": [["intent_router", "web_research"], ["web_research", "valuation_logic"], ["valuation_logic", "manager"]],
  "global_config": {"model": "gemini-2.0-flash", "temperature": 0.3}
}
```

### competitor-audit

```json
{
  "nodes": [
    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
    {"id": "competitor_research", "type": "external", "url": "http://discovery-agent-svc:8020/v1/search", "config": {"focus": "competitors,market_share"}},
    {"id": "gap_analyzer", "type": "external", "url": "http://intelligence-agent-svc:8030/v1/execute", "config": {"focus": "competitive_gaps"}},
    {"id": "report_generator", "type": "internal", "handler": "ReportNode"}
  ],
  "edges": [["intent_router", "competitor_research"], ["competitor_research", "gap_analyzer"], ["gap_analyzer", "report_generator"]],
  "global_config": {"model": "gemini-2.0-flash", "temperature": 0.5}
}
```

### content-strategy (all internal)

```json
{
  "nodes": [
    {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
    {"id": "audience_analyzer", "type": "internal", "handler": "AudienceNode"},
    {"id": "content_planner", "type": "internal", "handler": "PlannerNode"},
    {"id": "calendar_builder", "type": "internal", "handler": "CalendarNode"}
  ],
  "edges": [["intent_router", "audience_analyzer"], ["audience_analyzer", "content_planner"], ["content_planner", "calendar_builder"]],
  "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7}
}
```

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `tests/integration/conftest.py` | Create | Shared fixtures, service URLs, auth helpers |
| `tests/integration/docker-compose.test.yml` | Create | Slim test stack (redis + 3 agents) |
| `tests/integration/pytest.ini` | Create | Test configuration |
| `tests/integration/requirements.txt` | Create | Test dependencies |
| `tests/integration/phase1_contracts/conftest.py` | Create | Contract test fixtures |
| `tests/integration/phase1_contracts/test_dispatch_contract.py` | Create | 6 tests |
| `tests/integration/phase1_contracts/test_callback_contract.py` | Create | 5 tests |
| `tests/integration/phase1_contracts/test_discovery_contract.py` | Create | 5 tests |
| `tests/integration/phase1_contracts/test_intelligence_contract.py` | Create | 6 tests |
| `tests/integration/phase1_contracts/test_cancel_contract.py` | Create | 3 tests |
| `tests/integration/phase2_domain/conftest.py` | Create | Domain test fixtures |
| `tests/integration/phase2_domain/test_npv_benchmarks.py` | Create | 5 tests |
| `tests/integration/phase2_domain/test_bsi_scoring.py` | Create | 6 tests |
| `tests/integration/phase2_domain/test_golden_path.py` | Create | 3 tests |
| `tests/integration/phase2_domain/test_data_asymmetry.py` | Create | 4 tests |
| `tests/integration/phase2_domain/test_intent_routing.py` | Create | 5 tests |
| `tests/integration/phase3_stress/conftest.py` | Create | Stress test fixtures |
| `tests/integration/phase3_stress/test_concurrent_pipelines.py` | Create | 3 tests |
| `tests/integration/phase3_stress/test_rate_limiting.py` | Create | 3 tests |
| `tests/integration/phase3_stress/test_redis_resilience.py` | Create | 2 tests |
| `tests/integration/phase3_stress/test_agent_timeout.py` | Create | 2 tests |
| `tests/integration/phase3_stress/test_cancel_under_load.py` | Create | 2 tests |
| `.github/workflows/ci-cd.yml` | Modify | Add integration-tests job (Phase 1-3) |

**Total**: 22 new files, 1 modified file, ~75 test cases

---

## Implementation Order

1. **Infrastructure first**: `docker-compose.test.yml`, `conftest.py`, `pytest.ini`, `requirements.txt`
2. **Phase 1 contract tests**: Direct HTTP calls to each service -- fastest to implement and highest ROI
3. **Phase 2 domain tests**: NPV benchmarks and BSI scoring first (pure calculation validation), then golden path tests
4. **Phase 3 stress tests**: Concurrent pipelines and rate limiting
5. **Phase 4 frontend**: Deferred -- implement after backend integration tests are stable

---

## Key Design Decisions

1. **Tests run against Docker containers** (not in-process) -- validates real networking, serialization, and startup
2. **No Django/Celery in test stack** -- tests call the orchestrator directly via HTTP, same as Celery would. This avoids needing PostgreSQL and Django migrations in the test stack
3. **Callback capture**: For golden-path tests, spin up a lightweight `aiohttp` server in the test process to receive callbacks from the orchestrator
4. **Stub mode for external APIs**: Tavily, Gemini, GCS all run in stub mode (empty API keys) so tests don't require real credentials
5. **Redis is required**: Rate limiting, cancel flags, and caching are core behaviors being tested
6. **Each phase is independently runnable**: `pytest tests/integration/phase1_contracts/ -v`

---

## Existing Code to Reuse

| Component | Location | Reuse |
|-----------|----------|-------|
| Manifest definitions | `ai-brand-automator/orchestration/management/commands/seed_manifests.py` | Copy manifest_data dicts for test payloads |
| Dispatch payload builder | `ai-brand-automator/orchestration/services.py:163-185` | Mirror `_build_payload()` for contract tests |
| Discovery mock handler | `pipeline-orchestrator-svc/tests/e2e/conftest.py:52-119` | Reference for expected discovery response shape |
| ExternalWrapper contract | `pipeline-orchestrator-svc/app/nodes/external_wrapper.py` | Request/response schema for agent calls |
| Callback shapes | `pipeline-orchestrator-svc/app/services/callback_client.py` | Expected PATCH payloads for each lifecycle stage |
| BSI/NPV formulas | `intelligence-agent-svc/app/logic/iso_engine/` | Hand-calculate expected values for benchmark tests |

---

## CI/CD Integration

Add to `.github/workflows/ci-cd.yml` after existing test jobs:

```yaml
  integration-tests:
    runs-on: ubuntu-latest
    needs: [orchestrator-tests, discovery-agent-tests, intelligence-agent-tests]
    steps:
      - uses: actions/checkout@v3
      - name: Build test stack
        run: |
          cd tests/integration
          docker compose -f docker-compose.test.yml up -d --build --wait
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install test dependencies
        run: pip install -r tests/integration/requirements.txt
      - name: Run Phase 1 - Contract Tests
        run: pytest tests/integration/phase1_contracts/ -v --timeout=60
      - name: Run Phase 2 - Domain Tests
        run: pytest tests/integration/phase2_domain/ -v --timeout=120
      - name: Run Phase 3 - Stress Tests
        run: pytest tests/integration/phase3_stress/ -v --timeout=300
      - name: Teardown
        if: always()
        run: |
          cd tests/integration
          docker compose -f docker-compose.test.yml down -v
```

---

## Run Commands

```bash
# Start test stack
cd tests/integration && docker compose -f docker-compose.test.yml up -d --build --wait

# Run all integration tests
pytest tests/integration/ -v

# Run by phase
pytest tests/integration/phase1_contracts/ -v
pytest tests/integration/phase2_domain/ -v
pytest tests/integration/phase3_stress/ -v

# Run a single test
pytest tests/integration/phase2_domain/test_npv_benchmarks.py::test_npv_known_inputs -v

# Teardown
cd tests/integration && docker compose -f docker-compose.test.yml down -v
```

---

## Verification Checklist

After implementation:

- [ ] `docker compose -f docker-compose.test.yml up -d --build --wait` -- all 4 services healthy
- [ ] `pytest tests/integration/phase1_contracts/ -v` -- all 25 contract tests pass
- [ ] `pytest tests/integration/phase2_domain/ -v` -- all 23 domain tests pass (NPV within +/-$1 tolerance)
- [ ] `pytest tests/integration/phase3_stress/ -v` -- all 12 stress tests pass
- [ ] CI workflow YAML validates: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci-cd.yml'))"`

---

## Test Count Summary

| Phase | Test Files | Test Count | Estimated Runtime |
|-------|-----------|------------|-------------------|
| Phase 1: Contracts | 5 | 25 | ~30s |
| Phase 2: Domain | 5 | 23 | ~60s |
| Phase 3: Stress | 5 | 12 | ~120s |
| Phase 4: Frontend | 2 | 4 | ~60s (deferred) |
| **Total** | **17** | **64 (+4 deferred)** | **~3.5 min** |
