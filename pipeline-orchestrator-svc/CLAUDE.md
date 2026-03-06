# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**pipeline-orchestrator-svc** is a FastAPI microservice that converts JSON pipeline manifests into stateful LangGraph DAGs and executes them as multi-agent pipelines. It is the runtime engine for the AI Brand Automator platform.

This service is part of a larger workspace (`Prevision_WS`):
- **ai-brand-automator** -- Django backend (core-api-service), dispatches jobs and receives callbacks
- **ai-brand-automator-frontend** -- Next.js frontend, displays pipeline progress via ThoughtTrace component
- **pipeline-orchestrator-svc** -- This service, executes pipeline-as-code manifests

## Build, Run, and Test

### Local Development

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # adds pytest, black, mypy

# Run the service (port 8010)
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### Docker

```bash
# Build and run with Redis
docker compose up --build

# Service available at http://localhost:8010
# Redis exposed on host port 6380
```

### Running Tests

```bash
# Run all tests (async mode auto-configured via pyproject.toml)
pytest

# Run a specific test file
pytest tests/test_api_routes.py

# Run with verbose output
pytest -v

# Run a single test class or method
pytest tests/test_internal_nodes.py::TestRouterNode
pytest tests/test_job_executor.py::TestJobExecutor::test_execute_simple_manifest
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`), so all `async def test_*` methods run automatically without `@pytest.mark.asyncio`. HTTP mocking uses `pytest-httpx` and Redis is mocked via `unittest.mock.AsyncMock`.

### Linting and Type Checking

```bash
black .                     # format (88 char lines, Python 3.12 target)
mypy app/ --strict          # type check with strict mode
```

## Architecture

### High-Level Flow

```
Django core-api-service                    pipeline-orchestrator-svc
        |                                           |
        |  POST /v1/jobs/dispatch                   |
        |  (X-Service-Token auth)                   |
        | ----------------------------------------> |
        |           202 Accepted                    |
        | <---------------------------------------- |
        |                                           |
        |                              Build LangGraph from manifest
        |                              Execute nodes sequentially
        |                                           |
        |  PATCH callback_url                       |
        |  (X-Callback-Token auth)                  |
        | <---------------------------------------- |
        |  {status: "running", progress: {...}}     |
        |                                           |
        |  PATCH callback_url                       |
        | <---------------------------------------- |
        |  {status: "completed",                    |
        |   result_data: {...},                     |
        |   progress: {...}}                        |
```

### Directory Structure

```
app/
  main.py                   # FastAPI app entry point, lifespan hooks
  api/
    routes.py               # HTTP endpoints: /health, /v1/jobs/dispatch, /v1/jobs/{id}/cancel
    schemas.py              # Pydantic v2 request/response models
    auth.py                 # X-Service-Token verification dependency
  core/
    config.py               # Pydantic Settings (ORCHESTRATOR_ prefix env vars)
    redis_client.py         # Async Redis connection pool (cancel flags)
    logging_config.py       # Structured logging setup
  factory/
    graph_builder.py        # Manifest -> LangGraph DAG compiler (topological sort, cycle detection)
    node_registry.py        # Handler name -> Python class mapping
  nodes/
    base.py                 # BaseNode ABC: __call__(state) -> dict
    external_wrapper.py     # HTTP POST wrapper for remote agent services
    internal/
      router_node.py        # Intent routing via keyword matching
      manager_node.py       # Terminal node: aggregates outputs into result_data
      strategy_node.py      # Brand strategy analysis (stub)
      report_node.py        # Report generation (stub)
      audience_node.py      # Audience demographics (stub)
      planner_node.py       # Content planning (stub)
      calendar_node.py      # Editorial calendar (stub)
  services/
    job_executor.py         # Central orchestration: state init -> graph exec -> callbacks
    callback_client.py      # HTTP PATCH client for progress/result callbacks
  messaging/
    kafka_producer.py       # Emits trace events to agent-trace-topic, results to pipeline-result-topic
    kafka_consumer.py       # Listens on pipeline-trigger-topic (alternative to HTTP dispatch)
  state/
    schema.py               # AgentState TypedDict (shared memory for LangGraph)
tests/
  conftest.py               # Shared fixtures: async client, dispatch payload, auth headers
  test_api_routes.py        # Endpoint contract tests
  test_job_executor.py      # End-to-end executor tests with mocked callbacks
  test_graph_builder.py     # Manifest compilation + error handling
  test_node_registry.py     # Handler resolution
  test_internal_nodes.py    # All 7 internal node stubs
  test_external_wrapper.py  # HTTP wrapper with stub fallback
  test_callback_client.py   # PATCH payload and header verification
  test_state_schema.py      # AgentState TypedDict construction
  test_kafka_messaging.py   # Producer/consumer lifecycle
```

### Key Components

**GraphBuilder** (`app/factory/graph_builder.py`): Takes a manifest dict with `nodes`, `edges`, and `global_config`. Performs topological sort (Kahn's algorithm) for execution order, detects cycles, resolves internal handlers from the node registry, wraps external nodes with `ExternalWrapper`, and compiles into a `langgraph.graph.StateGraph`.

**JobExecutor** (`app/services/job_executor.py`): The core runtime engine. Builds initial `AgentState` from the dispatch request, handles auto-detect mode (intent routing when no manifest), invokes the compiled graph, checks Redis cancel flags between stages, and sends progress/completion/failure callbacks to the Django backend.

**AgentState** (`app/state/schema.py`): A `TypedDict(total=False)` that flows through every node. Key fields: `job_id`, `tenant_id`, `input_prompt`, `input_context`, `tenant_context`, `node_outputs` (keyed by node_id), `progress` (matches frontend AgentProgress TS type), `result_data`, `cancelled`.

**CallbackClient** (`app/services/callback_client.py`): Sends HTTP PATCH requests to the Django backend's callback endpoint. Uses a reusable `httpx.AsyncClient`. Methods: `send_running`, `send_progress`, `send_completed`, `send_failed`, `send_resolved_manifest`.

**ExternalWrapper** (`app/nodes/external_wrapper.py`): Generic HTTP POST wrapper for calling remote agent microservices (e.g., discovery-agent-svc, intelligence-agent-svc). Propagates `X-Tenant-ID` header. Falls back to stub data when the external service is unreachable, allowing pipelines to run before all agent services are deployed.

## Contracts with Django Backend

### Dispatch (Django -> Orchestrator)

**Endpoint**: `POST /v1/jobs/dispatch`
**Auth**: `X-Service-Token` header (shared secret)
**Response**: `202 {"status": "accepted"}`

Request body (`DispatchRequest`):
```json
{
  "job_id": "uuid",
  "manifest": {                          // null for auto-detect mode
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
  "callback_url": "http://backend:8001/api/v1/orchestration/jobs/{job_id}/callback/",
  "available_manifests": [               // only for auto-detect mode
    {"pipeline_id": "brand-analysis", "name": "Brand Analysis", "description": "..."}
  ]
}
```

### Callback (Orchestrator -> Django)

**Method**: `PATCH {callback_url}`
**Auth**: `X-Callback-Token` header (shared secret)

Callback payloads by lifecycle stage:
```json
// Running (job started)
{"status": "running", "progress": {"node_id": {"status": "pending"}}}

// Progress (per-node updates)
{"progress": {"node_id": {"status": "running", "started_at": "ISO8601"}}}

// Resolved manifest (auto-detect mode)
{"resolved_manifest_id": "brand-analysis", "progress": {...}}

// Completed
{"status": "completed", "progress": {...}, "result_data": {"summary": "...", "findings": [...], "recommendations": [...]}}

// Failed
{"status": "failed", "progress": {...}, "error_message": "..."}
```

### Cancel (Django -> Orchestrator)

**Endpoint**: `POST /v1/jobs/{job_id}/cancel`
**Auth**: `X-Service-Token` header
**Mechanism**: Sets `cancel:{job_id}` key in Redis with 1-hour TTL. The executor checks this flag between node executions.

## How to Add a New Internal Node

1. **Create the node class** in `app/nodes/internal/`:

```python
# app/nodes/internal/my_node.py
"""MyNode -- description of what it does."""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class MyNode(BaseNode):
    """One-line description."""

    async def __call__(self, state: AgentState) -> dict:
        # Read from state
        prompt = state.get("input_prompt", "")
        config = self.config  # merged global_config + node-level config

        # Do work...
        result = {"analysis": "...", "findings": [...], "recommendations": [...]}

        # Write to node_outputs under a descriptive key
        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["my_node_key"] = result
        return {"node_outputs": node_outputs}
```

2. **Register in the node registry** (`app/factory/node_registry.py`):

```python
from app.nodes.internal.my_node import MyNode

INTERNAL_HANDLERS: dict[str, type[BaseNode]] = {
    # ... existing handlers ...
    "MyNode": MyNode,
}
```

3. **Add tests** in `tests/test_internal_nodes.py`:

```python
from app.nodes.internal.my_node import MyNode

class TestMyNode:
    async def test_returns_expected_data(self):
        node = MyNode()
        result = await node(_base_state())
        outputs = result.get("node_outputs", {})
        assert "my_node_key" in outputs
```

4. **Update the registry count test** in `tests/test_node_registry.py`:

```python
def test_registry_has_seven_handlers(self):  # update count
    assert len(INTERNAL_HANDLERS) == 8       # was 7
```

5. **Use in a manifest**: Reference by handler name in any pipeline manifest:

```json
{"id": "my_step", "type": "internal", "handler": "MyNode", "config": {"custom_key": "value"}}
```

### Node Contract

- Input: `AgentState` TypedDict (read any field)
- Output: `dict` of state keys to update (LangGraph merges into existing state)
- Nodes write to `node_outputs[some_key]` by convention
- The `config` dict is the merge of `global_config` and the node's own `config` from the manifest
- Terminal nodes (like `ManagerNode`) write to `result_data` instead

## Environment Variable Reference

All settings use the `ORCHESTRATOR_` prefix (configured via `pydantic-settings`).

| Variable | Default | Description |
|---|---|---|
| `ORCHESTRATOR_SERVICE_TOKEN` | `dev-service-token` | Shared secret for incoming dispatch/cancel requests (X-Service-Token header) |
| `ORCHESTRATOR_CALLBACK_TOKEN` | `dev-callback-token` | Shared secret for outgoing callbacks to Django (X-Callback-Token header) |
| `ORCHESTRATOR_CALLBACK_BASE_URL` | `""` | When set, overrides the callback URL from dispatch payload. Set to Django's private networking URL on Railway (e.g. `http://previsionws.railway.internal:8000`) |
| `ORCHESTRATOR_REDIS_URL` | `redis://localhost:6379/1` | Redis connection URL (used for cancel flags and LangGraph checkpointing) |
| `ORCHESTRATOR_KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address. Set to empty string to disable Kafka entirely |
| `ORCHESTRATOR_CORS_ORIGINS` | `http://localhost:3000,http://localhost:8000` | Comma-separated CORS allowed origins |
| `ORCHESTRATOR_HOST` | `0.0.0.0` | Server bind host |
| `ORCHESTRATOR_PORT` | `8010` | Server bind port |
| `ORCHESTRATOR_LOG_LEVEL` | `INFO` | Python logging level |

## Kafka Topics

Kafka is optional. The service operates in HTTP-only mode when the broker is unavailable.

| Topic | Direction | Purpose |
|---|---|---|
| `pipeline-trigger-topic` | Consume | Alternative to HTTP dispatch -- receives job trigger events |
| `agent-trace-topic` | Produce | Per-node status events (started, completed, failed) for real-time tracing |
| `pipeline-result-topic` | Produce | Final pipeline result data |

## Code Style

- **Formatter**: Black, 88-character line length, Python 3.12 target
- **Type checking**: mypy strict mode
- **Async**: All node execution, Redis, HTTP, and Kafka operations are async
- **Error handling**: Kafka and Redis failures are non-fatal (logged as warnings). External service failures fall back to stub data. Callback failures are logged but do not crash the executor.
- **Docstrings**: Google style
- **Commit messages**: Conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`)

## Testing Patterns

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` -- no decorator needed on async tests
- HTTP client fixture: `httpx.AsyncClient` with `ASGITransport` wrapping the FastAPI app
- HTTP mocking: `pytest-httpx` (`httpx_mock` fixture) for callback and external service tests
- Redis mocking: `unittest.mock.AsyncMock` patching `app.services.job_executor.get_redis`
- Kafka mocking: Not started in tests (constructor only, `is_connected` returns `False`)
- Auth in tests: Use `service_token_headers` fixture with `X-Service-Token: dev-service-token`
