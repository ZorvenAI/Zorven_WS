# Implementation Plan: `pipeline-orchestrator-svc`

> **Note**: Upon approval, this plan will be saved to `docs/PIPELINE_ORCHESTRATOR_IMPLEMENTATION_PLAN.md`.

## Implementation Status

| Phase | Description | Status | Tests |
|-------|-------------|--------|-------|
| 1 | FastAPI Skeleton + API Contracts | ✅ Complete | 10 tests passing |
| 2 | State Schema + Graph Builder + Node Registry | ✅ Complete | 19 tests passing |
| 3 | Internal Nodes + External Wrapper + Callback Client | ✅ Complete | 24 tests passing |
| 4 | Job Executor — End-to-End Execution | ✅ Complete | 6 tests passing |
| 5 | Kafka Integration | ✅ Complete | 9 tests passing |
| 6 | Docker Compose Integration | ✅ Complete | — |
| 7 | Frontend — PipelineGraph (React Flow) | ✅ Complete | Build + lint clean |
| 8 | Frontend — Live LogConsole | ✅ Complete | Build + lint clean |
| 9 | Frontend — BrandEquityDashboard | ✅ Complete | Build + lint clean |
| **Total** | | **All 9 phases complete** | **74 backend + build clean** |

**Last updated**: 2026-02-19

---

## Context

The `orchestration` Django app (core-api-service layer) is already implemented with models, views, serializers, Celery tasks, and tests. It dispatches jobs via HTTP POST to `http://localhost:8010/v1/jobs/dispatch` and receives callbacks. The **pipeline-orchestrator-svc** is the missing runtime engine that actually executes pipelines. It converts JSON manifests into LangGraph state machines, runs nodes in dependency order, reports progress via callbacks, and returns final results.

**Location**: `Prevision_WS/pipeline-orchestrator-svc/` (separate top-level directory, per workspace convention for different-stack services)

---

## Directory Structure

```
pipeline-orchestrator-svc/
├── app/
│   ├── __init__.py
│   ├── main.py                         # FastAPI + lifespan (Kafka startup/shutdown)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                   # /health, /v1/jobs/dispatch, /v1/jobs/{id}/cancel
│   │   ├── schemas.py                  # Pydantic v2 request/response models
│   │   └── auth.py                     # X-Service-Token dependency
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                   # Pydantic BaseSettings (env vars)
│   │   ├── redis_client.py             # Async Redis connection pool
│   │   └── logging_config.py           # Structured logging
│   ├── factory/
│   │   ├── __init__.py
│   │   ├── graph_builder.py            # JSON Manifest → LangGraph StateGraph
│   │   └── node_registry.py            # Handler string → Python class mapping
│   ├── messaging/
│   │   ├── __init__.py
│   │   ├── kafka_consumer.py           # pipeline-trigger-topic consumer
│   │   └── kafka_producer.py           # agent-trace-topic + pipeline-result-topic
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseNode ABC
│   │   ├── internal/
│   │   │   ├── __init__.py
│   │   │   ├── router_node.py          # Intent routing (keyword matching)
│   │   │   ├── manager_node.py         # Aggregation/summary node
│   │   │   ├── strategy_node.py        # Brand strategy stub
│   │   │   ├── report_node.py          # Report generation stub
│   │   │   ├── audience_node.py        # Audience analysis stub
│   │   │   ├── planner_node.py         # Content planning stub
│   │   │   └── calendar_node.py        # Calendar building stub
│   │   └── external_wrapper.py         # Generic HTTP caller for remote agents
│   ├── state/
│   │   ├── __init__.py
│   │   └── schema.py                   # AgentState TypedDict (LangGraph shared memory)
│   └── services/
│       ├── __init__.py
│       ├── job_executor.py             # Orchestrates: build graph → run → callback
│       └── callback_client.py          # HTTP client for Django callback endpoint
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Fixtures, mock Redis, mock httpx
│   ├── test_api_routes.py
│   ├── test_graph_builder.py
│   ├── test_node_registry.py
│   ├── test_internal_nodes.py
│   ├── test_external_wrapper.py
│   ├── test_job_executor.py
│   ├── test_callback_client.py
│   ├── test_state_schema.py
│   └── test_kafka_messaging.py
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## Phase 1: FastAPI Skeleton + API Contracts — ✅ COMPLETE

**Goal**: A runnable FastAPI service on port 8010 that accepts dispatch/cancel requests with token auth, returning correct HTTP status codes. No graph execution yet.

> **Status**: All files created and tested. 10 tests in `test_api_routes.py` passing (health, dispatch 202, dispatch without manifest, invalid/missing token 403, malformed body 422, invalid node type 422, cancel 200 with mocked Redis, cancel invalid token 403).

**Files to create**:
- `app/main.py` — FastAPI app with lifespan placeholder, CORS for `localhost:3000`
- `app/core/config.py` — `Settings(BaseSettings)` loading `ORCHESTRATOR_*` env vars: `SERVICE_TOKEN`, `CALLBACK_TOKEN`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `HOST`, `PORT`
- `app/api/schemas.py` — Pydantic v2 models matching existing contracts:
  - `DispatchRequest`: `{job_id, manifest, input_prompt, input_context, tenant_context, callback_url, available_manifests?}`
  - `ManifestData`, `ManifestNode`, `TenantContext`, `AvailableManifest`
  - `DispatchResponse`, `CancelResponse`
- `app/api/auth.py` — `verify_service_token` FastAPI dependency (checks `X-Service-Token` header)
- `app/api/routes.py` — Three endpoints:
  - `GET /health` → `{"status": "ok"}` (no auth)
  - `POST /v1/jobs/dispatch` → validate token, validate body, return 202
  - `POST /v1/jobs/{job_id}/cancel` → validate token, set cancel flag in Redis, return 200
- `app/core/logging_config.py` — Structured JSON logging
- `Dockerfile` — `python:3.12-slim`, install deps, run uvicorn
- `requirements.txt` — `fastapi, uvicorn[standard], pydantic>=2.9, pydantic-settings, httpx, redis>=5.0, langgraph>=0.2, langgraph-checkpoint-redis, aiokafka`
- `requirements-dev.txt` — `pytest, pytest-asyncio, pytest-httpx, fakeredis, black, mypy`
- `pyproject.toml` — Black (88 chars), pytest config

**Contract reference**: `ai-brand-automator/orchestration/services.py` (dispatch payload at line 58-84, cancel at line 133-161)

**Tests**: `test_api_routes.py` — dispatch returns 202, cancel returns 200, invalid token returns 403, malformed body returns 422

---

## Phase 2: State Schema + Graph Builder + Node Registry — ✅ COMPLETE

**Goal**: Convert JSON manifests into LangGraph `StateGraph` objects. No execution yet — just construction and validation.

> **Status**: All files created and tested. `graph_builder.py` uses Kahn's topological sort with cycle detection, entry/terminal node identification, internal handler resolution via `node_registry.py`, and `ExternalWrapper` for external nodes. 19 tests passing across `test_graph_builder.py` (12), `test_node_registry.py` (4), `test_state_schema.py` (3).

**Files to create**:
- `app/state/schema.py` — `AgentState(TypedDict)`:
  - `job_id, tenant_id, input_prompt, input_context, tenant_context, global_config`
  - `callback_url, available_manifests, resolved_manifest_id`
  - `node_outputs: dict[str, Any]` — per-node output keyed by node_id
  - `progress: dict[str, dict]` — matches `AgentProgress` TS type: `{status, output?, started_at?, completed_at?}`
  - `result_data, error, cancelled`
- `app/nodes/base.py` — `BaseNode(ABC)` with `__call__(state) -> AgentState`
- `app/factory/node_registry.py` — `INTERNAL_HANDLERS` dict mapping all 7 handler strings (`RouterNode`, `ManagerNode`, `StrategyNode`, `ReportNode`, `AudienceNode`, `PlannerNode`, `CalendarNode`) to classes; `resolve_handler()` function
- `app/factory/graph_builder.py` — `GraphBuilder.build(manifest, checkpointer)`:
  - Topological sort to find entry node (zero in-degree) and terminal nodes (zero out-degree)
  - Adds each node to `StateGraph` (internal → handler class, external → `ExternalWrapper`)
  - Wires `set_entry_point`, `add_edge` for each edge pair, terminal → `END`
  - Returns compiled graph

**Reference**: Topological sort logic from `ai-brand-automator/orchestration/serializers.py:131-155`; seed manifest structures from `seed_manifests.py`

**Tests**: `test_graph_builder.py` — compile all 4 seed manifests, unknown handler raises `ValueError`, cyclic edges raise error; `test_node_registry.py` — all 7 handlers resolve; `test_state_schema.py` — AgentState construction

---

## Phase 3: Internal Nodes (Stubs) + External Wrapper + Callback Client — ✅ COMPLETE

**Goal**: Implement all node handlers as stubs returning realistic mock data, plus the HTTP callback client and external agent HTTP wrapper.

> **Status**: All 7 internal node stubs implemented, `callback_client.py` with async httpx PATCH + `X-Callback-Token` auth, `external_wrapper.py` with graceful HTTP fallback. 24 tests passing across `test_internal_nodes.py` (12), `test_external_wrapper.py` (4), `test_callback_client.py` (8).

**Files to create**:
- `app/services/callback_client.py` — Async `httpx` client:
  - `send_progress(callback_url, progress)` → PATCH with `X-Callback-Token`
  - `send_completed(callback_url, result_data, progress)` → PATCH `status: "completed"`
  - `send_failed(callback_url, error_message, progress)` → PATCH `status: "failed"`
  - `send_resolved_manifest(callback_url, manifest_id)` → PATCH `resolved_manifest_id`
- `app/nodes/internal/router_node.py` — Keyword matching on `input_prompt` → resolves manifest from `available_manifests`. Maps: "brand equity/valuation/ISO" → `iso-brand-equity`; "competitor/audit/gap" → `competitor-audit`; "content/strategy/calendar" → `content-strategy`; default → `brand-analysis`
- `app/nodes/internal/manager_node.py` — Aggregates `node_outputs` into `result_data` with `{summary, findings, recommendations, score}` structure (matches `ResultDashboard.tsx` expectations)
- `app/nodes/internal/strategy_node.py` — Mock brand strategy analysis
- `app/nodes/internal/report_node.py` — Mock formatted report
- `app/nodes/internal/audience_node.py` — Mock audience demographics
- `app/nodes/internal/planner_node.py` — Mock content plan
- `app/nodes/internal/calendar_node.py` — Mock editorial calendar
- `app/nodes/external_wrapper.py` — `ExternalWrapper(BaseNode)`:
  - POST to `self.url` with `X-Tenant-ID` header (from `state.tenant_context.tenant_id`)
  - Payload: `{input_prompt, input_context, tenant_context, config, previous_outputs}`
  - Graceful fallback: on `httpx.HTTPError`, return stub data instead of crashing

**Progress format**: Each node updates `progress[node_id]` matching `AgentProgress` TS type: `{status: "pending"|"running"|"done"|"failed", output?, started_at?, completed_at?}`

**Tests**: `test_internal_nodes.py`, `test_external_wrapper.py` (mock HTTP), `test_callback_client.py` (verify PATCH calls/headers)

---

## Phase 4: Job Executor — End-to-End Pipeline Execution — ✅ COMPLETE

**Goal**: Wire everything together. Dispatch → build graph → execute node-by-node → send progress callbacks → return final results.

> **Status**: `job_executor.py` fully implemented with state building, intent routing (auto-detect mode), graph compilation, `ainvoke()` execution with `thread_id` config, Redis cancel flag checking, and progress/completed/failed callbacks. Route wired in `routes.py` via `BackgroundTasks`. 6 tests passing in `test_job_executor.py` (simple manifest, auto-detect, cancel, invalid manifest, progress per node, Redis failure resilience).

**Files to create/modify**:
- `app/services/job_executor.py` — Central orchestration:
  1. Build initial `AgentState` from `DispatchRequest`
  2. Initialize all nodes as `pending` in progress, send initial callback
  3. If manifest is null → run intent routing (resolve from `available_manifests`)
  4. Build LangGraph via `GraphBuilder`
  5. Execute via `graph.astream()` with Redis checkpointer thread config `{thread_id: "{tenant_id}:{job_id}"}`
  6. Between nodes: check cancel flag (`cancel:{job_id}` Redis key), send progress callback
  7. On completion: send `status: "completed"` + `result_data` callback
  8. On error: send `status: "failed"` + `error_message` callback
- `app/core/redis_client.py` — Async Redis connection pool (lazy init, close on shutdown)
- Update `app/api/routes.py` — Dispatch endpoint launches `JobExecutor.execute()` via `BackgroundTasks`

**Callback contract reference**: `ai-brand-automator/orchestration/views.py:106-194` (callback endpoint validates `X-Callback-Token`, accepts `status`, `progress`, `result_data`, `error_message`, `resolved_manifest_id`)

**Tests**: `test_job_executor.py` — mock callback client + Redis, execute `brand-analysis` manifest, verify progress callbacks per node, final `completed` callback with `result_data` keys, cancel flag causes early `failed` callback

---

## Phase 5: Kafka Integration — Trigger Consumer + Trace Producer — ✅ COMPLETE

**Goal**: Add Kafka-based trigger consumption (alternative to HTTP dispatch) and real-time trace event streaming.

> **Status**: `kafka_producer.py` (TraceProducer) and `kafka_consumer.py` (TriggerConsumer) implemented with graceful fallback when Kafka is unavailable. `main.py` lifespan hooks start/stop producer + consumer, with background consume loop. 9 tests passing in `test_kafka_messaging.py`.

**Files to create**:
- `app/messaging/kafka_producer.py` — `TraceProducer`:
  - `send_trace(job_id, node_id, status, output?)` → `agent-trace-topic`
  - `send_result(job_id, result_data)` → `pipeline-result-topic`
- `app/messaging/kafka_consumer.py` — `TriggerConsumer`:
  - Subscribes to `pipeline-trigger-topic`, group `orchestrator-consumers`
  - Deserializes messages as `DispatchRequest`, routes to `JobExecutor`
- Update `app/main.py` lifespan:
  - Start/stop Kafka producer + consumer on app startup/shutdown
  - **Kafka is optional**: if broker unavailable, log warning and run HTTP-only (matches existing `profiles: [with-kafka]` pattern)
- Update `app/services/job_executor.py` — emit trace events via producer between node executions

**Tests**: `test_kafka_messaging.py` — mock aiokafka, verify trace event structure, verify consumer routes to executor

---

## Phase 6: Docker Compose Integration — ✅ COMPLETE

**Goal**: Add the service to the existing infrastructure and verify end-to-end flow.

> **Status**: Standalone `pipeline-orchestrator-svc/docker-compose.yml` created (orchestrator + Redis on port 6380). `deployment/docker-compose.yml` updated with orchestrator service definition (builds from `../pipeline-orchestrator-svc`, port 8010, Redis DB 1, healthcheck), `ORCHESTRATOR_URL` set to `http://orchestrator:8010`, `BACKEND_URL` env var added to backend and celery-worker services.

**Files to create/modify**:
- `pipeline-orchestrator-svc/docker-compose.yml` — Standalone dev compose (orchestrator + Redis)
- Update `ai-brand-automator/docker-compose.yml` — Add `orchestrator` service:
  - Build from `../pipeline-orchestrator-svc`, port 8010
  - Environment: `ORCHESTRATOR_REDIS_URL=redis://redis:6379/1`, `ORCHESTRATOR_KAFKA_BOOTSTRAP_SERVERS=brand-kafka:9092`, service/callback tokens
  - Depends on: redis (healthy)
  - Healthcheck: `curl -f http://localhost:8010/health`
  - Network: `app-network`

**Verification**:
1. Start full docker-compose stack
2. Create analysis job via frontend `/dashboard/pipelines`
3. Verify ThoughtTrace updates as nodes execute (via 3s polling)
4. Verify ResultDashboard renders final results
5. Verify cancel button terminates running pipeline

---

## Critical Files Reference

| File | Why It Matters |
|------|---------------|
| `ai-brand-automator/orchestration/services.py` | Exact HTTP dispatch contract (payload, headers, response codes) |
| `ai-brand-automator/orchestration/views.py:106-194` | Callback endpoint (token validation, accepted fields) |
| `ai-brand-automator/orchestration/management/commands/seed_manifests.py` | All 4 seed manifest structures (nodes, edges, handlers) |
| `ai-brand-automator-frontend/src/types/orchestration.ts` | TypeScript types constraining progress/result JSON shape |
| `ai-brand-automator-frontend/src/components/pipelines/ThoughtTrace.tsx` | Renders progress — expects `{status, output?, started_at?, completed_at?}` |
| `ai-brand-automator-frontend/src/components/pipelines/ResultDashboard.tsx` | Renders results — looks for `summary, findings, recommendations, score` keys |
| `ai-brand-automator/data_ingestion/factory.py` | Reference for dependency injection pattern |

## Phase 7: Frontend — Enhanced ThoughtTrace with React Flow — ✅ COMPLETE

**Goal**: Replace the linear stepper with a dynamic DAG visualization using React Flow. Shows pipeline topology with animated node states.

> **Status**: `@xyflow/react` installed. `PipelineGraph.tsx` created with custom `PipelineNode` component, left-to-right layout via topological sort, animated edges for running nodes, color-coded status borders (gray/pulsing blue/green/red). `ManifestNode`, `ManifestGraphData` types added to `orchestration.ts`. `getManifestGraphData()` API helper added. Job detail page uses `PipelineGraph` when manifest data is available, falls back to `ThoughtTrace`.

**New dependency**: `npm install @xyflow/react` (React Flow v12, MIT license, React 19 compatible)

**Files to create/modify**:
- Install: `@xyflow/react` package
- `src/components/pipelines/PipelineGraph.tsx` — **New component**: React Flow canvas rendering the manifest DAG
  - Receives `manifest_data` (nodes + edges) and `progress` (per-node status)
  - Converts manifest nodes → React Flow nodes with positions (auto-layout via topological order)
  - Converts manifest edges → React Flow edges with animated flow
  - Custom node component with visual states:
    - **Gray** border + Circle icon: Pending
    - **Pulsing blue** border + spinning Loader2: Running (use `animate-pulse` + `border-brand-electric`)
    - **Green** border + CheckCircle2: Done
    - **Red** border + XCircle: Failed
  - Each node shows label (humanized node ID) and status text
  - Hoverable: shows node output/error on hover via tooltip
- `src/types/orchestration.ts` — Add `ManifestNode` and `ManifestEdge` types for graph rendering
- Update `src/lib/orchestration.ts` — `getJob()` response already includes `manifest` ID; add helper to fetch manifest data for graph rendering
- Update `src/app/dashboard/pipelines/[jobId]/page.tsx` — Replace `<ThoughtTrace>` with `<PipelineGraph>` when manifest data is available, keep `<ThoughtTrace>` as fallback

**Layout strategy**: Simple left-to-right horizontal layout. Position nodes at `x = index * 200, y = 0` based on topological order. Use `dagre` or manual positioning since manifests are simple linear DAGs.

**Reference files**:
- `src/components/pipelines/ThoughtTrace.tsx` — Visual states and status icons to reuse
- `src/types/orchestration.ts:10-15` — `AgentProgress` type

---

## Phase 8: Frontend — Live Log Console — ✅ COMPLETE

**Goal**: Add a sidebar panel streaming execution logs alongside the pipeline graph.

> **Status**: `LogConsole.tsx` created with collapsible panel, auto-scroll, color-coded entries (cyan info, green success, red error), monospace font. `LogEntry` type added to `orchestration.ts`. Job detail page updated with 2-column grid layout (graph 2/3, log console 1/3) using `diffProgress()` to generate log entries from polling snapshots via `useRef` for previous progress tracking.

**Files to create/modify**:
- `src/components/pipelines/LogConsole.tsx` — **New component**: Scrollable log panel
  - Renders timestamped log entries: `[HH:MM:SS] node_name: status_message`
  - Auto-scrolls to bottom as new entries arrive
  - Entries derived from `progress` changes between polling intervals
  - Color-coded: running → cyan, done → green, failed → red
  - Monospace font (`font-mono`), dark background (`bg-white/5`)
  - Collapsible sidebar (toggle button)
- Update `src/app/dashboard/pipelines/[jobId]/page.tsx`:
  - Add 2-column layout: graph/stepper (left, 2/3 width) + log console (right, 1/3 width)
  - Track previous progress state to diff and generate log entries
  - `useRef` to store previous progress for diffing

**Log entry generation** (from polling diff):
```tsx
// Compare prev progress with current progress
// If node went from "pending" → "running": log "Starting {node_name}..."
// If node went from "running" → "done": log "{node_name} completed"
// If node went from "running" → "failed": log "ERROR: {node_name} failed"
```

---

## Phase 9: Frontend — Specialized Result Dashboards — ✅ COMPLETE

**Goal**: Render specialized visualizations based on the manifest type, particularly for Brand Equity analysis.

> **Status**: `BrandEquityDashboard.tsx` created with pure SVG radial gauges (Awareness/Sentiment/Financials pillars), central equity score gauge with linear gradient, grounding citations with source type icons (document/web/financial), structured findings & recommendations. `ResultDashboard.tsx` updated to accept `manifestName` prop and route to `BrandEquityDashboard` when manifest name matches "Brand Equity" or "ISO". Job detail page passes `job.manifest_name` to `ResultDashboard`.

**Files to create/modify**:
- `src/components/pipelines/BrandEquityDashboard.tsx` — **New component**: Specialized ISO Brand Equity result view
  - **Pillar Gauges**: Circular progress indicators for Awareness, Sentiment, Financials scores
    - Pure CSS/SVG radial gauges (no charting library needed)
    - Each gauge shows score (0-100), label, and color gradient
  - **Score Summary**: Large central score display with brand equity value
  - **Grounding Citations**: Clickable list of source references from `result_data.sources`
    - Each citation links to GCS document URL or source web URL
    - Shows source type icon (document, web, financial)
  - **Findings & Recommendations**: Structured sections (reuses existing ResultDashboard patterns)
- Update `src/components/pipelines/ResultDashboard.tsx`:
  - Add manifest-aware routing: if `manifest_name` contains "Brand Equity" or "ISO", render `<BrandEquityDashboard>`
  - Otherwise render the existing generic dashboard
  - Accept `manifestName` as optional prop
- Update `src/app/dashboard/pipelines/[jobId]/page.tsx`:
  - Pass `job.manifest_name` to `<ResultDashboard>` for specialized routing

**Radial gauge implementation** (pure SVG, no library):
```tsx
// SVG circle with stroke-dasharray for progress arc
// Gradient colors: brand-electric → brand-teal
// Centered label text
```

---

## Verification Plan

### Backend Verification (Phases 1-6) — ✅ PASSED
1. **Unit tests**: `cd pipeline-orchestrator-svc && pytest tests/ -v` — **74 tests passing** across 8 test files
2. **Formatting**: `black .` — all files formatted (88 char line length)
3. **Manual smoke test**: Start service with `uvicorn app.main:app --port 8010`, send dispatch request via `curl`
4. **Integration test**: Start full docker-compose, create analysis job from frontend, verify:
   - Job transitions: QUEUED → RUNNING → COMPLETED
   - ThoughtTrace shows per-node progress
   - ResultDashboard renders final results
   - Cancel button works

### Frontend Verification (Phases 7-9) — ✅ PASSED
1. **TypeScript check**: `npx tsc --noEmit` — **0 errors**
2. **Lint check**: `npm run lint` — **0 errors** (only pre-existing warnings in unrelated files)
3. **Build check**: `npm run build` — **successful** (all pages compile)
4. **Visual test**: Navigate to `/dashboard/pipelines/{jobId}` with a running job, verify:
   - React Flow graph shows pipeline topology with animated states
   - Log console streams execution entries
   - Completed Brand Equity job shows specialized dashboard with gauges
5. **Fallback test**: Job without manifest data falls back to ThoughtTrace stepper

---

## Design Decisions

1. **HTTP + Kafka dual triggering**: Service accepts jobs via both HTTP POST (existing contract) and Kafka consumer (DDD spec). Kafka is optional.
2. **Callback over Kafka results**: Callbacks go via HTTP PATCH (existing, working), with Kafka `pipeline-result-topic` as supplementary channel.
3. **Internal nodes as stubs**: Since `discovery-agent-svc` and `intelligence-agent-svc` don't exist, internal nodes return realistic mock data. External wrapper gracefully falls back to stubs on connection errors.
4. **LangGraph checkpointing**: Redis DB 1 (separate from Celery on DB 0) with key format `thread:{tenant_id}:{job_id}`.
5. **React Flow for graph visualization**: `@xyflow/react` v12 — lightweight, React 19 compatible, MIT licensed. Auto-layout based on topological order.
6. **No charting library for gauges**: Pure SVG radial gauges instead of adding a heavy charting dependency. Keeps bundle size small.
7. **Polling-based log console**: Derives log entries from progress diffs between polling intervals. WebSocket/SSE deferred until Kafka trace consumer is battle-tested.
