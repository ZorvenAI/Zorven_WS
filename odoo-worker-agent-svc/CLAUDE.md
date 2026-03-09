# Odoo Worker Agent Service

## What This Service Does

Multi-persona AI worker agent for Odoo ERP operations (port 8100). Sits between the pipeline orchestrator and `odoo-mcp-server-svc`, providing intelligent persona-based reasoning via a PAOR (Plan → Act → Observe → Reflect) loop. Receives business prompts, resolves the appropriate persona (sales_manager, accountant, etc.), selects relevant skills, and executes multi-step MCP tool calls using Gemini 2.0 Flash.

## Build & Run Commands

```bash
cd odoo-worker-agent-svc

# Install
pip install -r requirements.txt
pip install -r requirements-dev.txt   # dev/test deps

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload

# Tests
pytest tests/ -v                      # All tests
pytest tests/ -m "not integration" -v # Unit only (no Redis)
pytest tests/test_health.py -v        # Single file

# Format
black app/ tests/

# Docker
docker compose up --build
```

## Architecture

```
app/
├── api/          # FastAPI routes + Pydantic request/response schemas
├── core/         # Config (ODOO_WORKER_ prefix), structured logging
├── cache/        # RedisManager (DB 10, rate limit + result cache)
├── personas/     # PersonaDefinition model, YAML loader, 2-tier resolver
├── skills/       # SkillMeta model, loader, registry, router (YAML+MD format)
├── services/     # WorkerExecutor, MCPClient, CircuitBreaker
├── agent/        # PAOR engine, Gemini LLM wrapper, reasoning models
├── rbac/         # RBAC pre-flight validation
├── rag/          # RAG context retrieval client
├── messaging/    # Kafka trace + audit producers
└── main.py       # FastAPI app with lifespan management
config/personas/  # 14 persona YAML definitions
skills/           # 22+ skill Markdown files with YAML frontmatter
```

## Key Contracts

```
POST /v1/execute
  Headers: X-Tenant-ID
  Body: { input_prompt, input_context, tenant_context, config, previous_outputs }
  Response: { status, findings, recommendations, data, result_data, error,
              persona_used, tools_called, reasoning_steps }

GET /health
  Response: { status: "healthy", service: "odoo-worker-agent-svc" }
```

## Environment Variables

All prefixed with `ODOO_WORKER_`:

| Variable | Default | Description |
|----------|---------|-------------|
| HOST | 0.0.0.0 | Server bind host |
| PORT | 8100 | Server port |
| MCP_SERVER_URL | http://odoo-mcp-server:8095 | Odoo MCP server URL |
| MCP_TIMEOUT | 60.0 | MCP call timeout (seconds) |
| GOOGLE_API_KEY | "" | Gemini API key (empty = stub mode) |
| GEMINI_MODEL | gemini-2.0-flash | Gemini model name |
| REDIS_URL | redis://localhost:6379/10 | Redis URL (DB 10) |
| KAFKA_BOOTSTRAP_SERVERS | "" | Kafka servers (empty = disabled) |
| SERVICE_TOKEN | dev-service-token | Service auth token |
| MAX_REASONING_STEPS | 10 | Max PAOR loop iterations |
| MAX_TOOL_CALLS_PER_STEP | 5 | Max MCP calls per step |
| LOG_LEVEL | INFO | Logging level |
| RBAC_PRE_FLIGHT | true | Enable RBAC pre-validation |
| RAG_ENABLED | false | Enable RAG context enrichment |
| RAG_SERVICE_URL | http://localhost:8070 | RAG service URL |
| PERSONAS_DIR | config/personas | Persona YAML directory |
| RATE_LIMIT_PER_MINUTE | 10 | Per-tenant rate limit |
| CORS_ORIGINS | localhost:3000,localhost:8000 | CORS allowed origins |

## Testing Conventions

- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
- Integration tests marked with `@pytest.mark.integration`
- Gemini: mocked in tests, falls back to stub when no API key
- Redis: mocked for unit tests, real for integration tests
- MCP server: mocked via `httpx` respx or manual mock

## Redis Key Patterns

| Key | TTL | Purpose |
|-----|-----|---------|
| `odoo_worker:result:{md5}` | 4h | Cached execution results |
| `odoo_worker:rate:{tenant_id}` | 60s | Rate limit counter |
| `odoo_worker:persona:{md5}` | 1h | Cached persona resolutions |
