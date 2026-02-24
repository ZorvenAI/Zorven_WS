# Default Agent Node (RAG Specialist) Implementation Plan

## Context

The pipeline orchestrator currently routes all auto-detect queries to specialized pipelines (brand-equity, competitor-audit, content-strategy, brand-analysis). There is **no path for general/conversational queries** that need to retrieve answers from the tenant's uploaded knowledge base (PDFs, videos, text indexed in Vertex AI Search).

The **Default Agent Node** fills this gap. It is a new internal node in `pipeline-orchestrator-svc` that:
1. Queries the tenant's **Vertex AI Search** data store for relevant document chunks
2. Synthesizes a grounded, source-cited answer using **Gemini**
3. Emits real-time **Kafka trace events** ("AI is thinking..." display)
4. Caches query results in **Redis** for performance

This bridges the existing Data Ingestion / RAG indexing pipeline to the chat interface.

### Existing Configuration (already available in workspace)
- **GCP Project:** `brandsol-project`
- **Service Account:** `brandsol-service-account-87@brandsol-project.iam.gserviceaccount.com`
- **Credentials file:** `ai-brand-automator/credentials/gcs-credentials.json`
- **Vertex AI Data Store:** `prevision-docs-dev` (location: `global`)
- **Gemini API Key:** Available in `ai-brand-automator/.env` as `GOOGLE_API_KEY`
- **Data store path pattern:** `projects/brandsol-project/locations/global/collections/default_collection/dataStores/prevision-docs-dev-{tenant_id}`

---

## Phase 1: Settings & Dependencies

**Files:**
- `pipeline-orchestrator-svc/requirements.txt`
- `pipeline-orchestrator-svc/app/core/config.py`
- `deployment/docker-compose.yml` (orchestrator service section)

**Changes:**

1. Add to `requirements.txt`:
```
google-cloud-discoveryengine>=0.13.0
google-generativeai>=0.8.0
```

2. Add to `config.py` Settings class (after existing fields):
```python
# Vertex AI Search (RAG queries)
VERTEX_AI_PROJECT_ID: str = "brandsol-project"
VERTEX_AI_LOCATION: str = "global"
VERTEX_AI_DATA_STORE_ID: str = "prevision-docs-dev"

# Gemini (answer synthesis)
GOOGLE_API_KEY: str = ""
GEMINI_MODEL: str = "gemini-2.0-flash"
GEMINI_TEMPERATURE: float = 0.3

# RAG query cache
RAG_QUERY_CACHE_TTL: int = 3600       # 1 hour
RAG_SESSION_FILES_TTL: int = 86400    # 24 hours
```

3. Add to `deployment/docker-compose.yml` orchestrator service environment (after existing env vars):
```yaml
- ORCHESTRATOR_VERTEX_AI_PROJECT_ID=${VERTEX_AI_PROJECT_ID:-brandsol-project}
- ORCHESTRATOR_VERTEX_AI_LOCATION=${VERTEX_AI_LOCATION:-global}
- ORCHESTRATOR_VERTEX_AI_DATA_STORE_ID=${VERTEX_AI_DATA_STORE_ID:-prevision-docs-dev}
- ORCHESTRATOR_GOOGLE_API_KEY=${GOOGLE_API_KEY:-}
- GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcs-credentials.json
```

4. Mount the credentials volume in the orchestrator service:
```yaml
volumes:
  - ../ai-brand-automator/credentials:/app/credentials:ro
```

**Verification:** `docker exec ai-brand-automator-orchestrator python -c "from app.core.config import settings; print(settings.VERTEX_AI_PROJECT_ID, settings.VERTEX_AI_DATA_STORE_ID)"`

---

## Phase 2: Vertex Search Tool

Create the search tool that queries Vertex AI Discovery Engine using real GCP connections.

**New file:** `pipeline-orchestrator-svc/app/nodes/tools/__init__.py` (empty)
**New file:** `pipeline-orchestrator-svc/app/nodes/tools/vertex_search_tool.py`

**Class:** `VertexSearchTool` — a plain async Python class (NOT a LangChain tool, consistent with existing BaseNode pattern).

**Key methods:**
- `async search(query, tenant_id, data_store_id=None) -> list[SearchChunk]`
- `_get_data_store_path(tenant_id) -> str` — same pattern as `rag_index/adapters/vertex_ai_adapter.py:get_data_store_path()` (line 320-334)
- `_get_cache_key(tenant_id, query) -> str` — builds `rag:query:cache:{tenant_id}:{sha256_hash}`

**Pattern reuse from `rag_index/adapters/vertex_ai_adapter.py`:**
- Data store path: `projects/{project_id}/locations/{location}/collections/default_collection/dataStores/{data_store_id}-{tenant_id}`
- Lazy client initialization via `_get_client()` method
- Settings loaded from `app.core.config.settings`

**Search implementation:**
- Uses `discoveryengine_v1.SearchServiceClient` with `SearchRequest`
- Serving config: `{data_store_path}/servingConfigs/default_search`
- Extracts `snippets` and `document.name` / metadata from results
- Returns `list[SearchChunk]` — dataclass with `text`, `source_uri`, `source_name`, `relevance_score`

**Redis caching:**
- Cache key: `rag:query:cache:{tenant_id}:{sha256(query)}`
- TTL: `settings.RAG_QUERY_CACHE_TTL` (default 1 hour)
- Uses `app.core.redis_client.get_redis()` (existing async Redis pool)
- Cache miss → query Vertex AI → cache result as JSON
- Non-fatal if Redis unavailable (search still works, just not cached)

**Error handling:**
- `google.api_core.exceptions.NotFound` → return empty results (data store doesn't exist for tenant)
- `google.api_core.exceptions.PermissionDenied` → log error, return empty results
- Network errors → log warning, return empty results (non-fatal)

---

## Phase 3: Default Agent Node

Create the core RAG agent node.

**New file:** `pipeline-orchestrator-svc/app/nodes/internal/default_agent_node.py`

**Class:** `DefaultAgentNode(BaseNode)` — follows the existing internal node pattern.

**`async __call__(state: AgentState) -> dict` flow:**

1. **Extract context** from state:
   - `input_prompt` — user's question
   - `input_context.get("chat_history", [])` — conversation history
   - `tenant_context.get("tenant_id")` — for data store scoping
   - `tenant_context.get("rag_data_store_id")` — optional data store override

2. **Emit pre-search trace** (Kafka):
   ```python
   await trace_producer.send_trace(job_id, "default_agent", "started",
       {"last_thought": "Interpreting your question in the context of our chat..."})
   ```

3. **Search Vertex AI** via `VertexSearchTool`:
   ```python
   await trace_producer.send_trace(job_id, "default_agent", "started",
       {"last_thought": "Searching through your onboarded documents for answers..."})
   chunks = await search_tool.search(query, tenant_id)
   ```

4. **Emit post-search trace** (with source file names):
   ```python
   source_names = [c.source_name for c in chunks[:3]]
   await trace_producer.send_trace(job_id, "default_agent", "started",
       {"last_thought": f"Extracting relevant information from {', '.join(source_names)}..."})
   ```

5. **Synthesize answer** with Gemini:
   - Configure `google.generativeai` with `settings.GOOGLE_API_KEY`
   - Build prompt with system instruction, retrieved chunks, chat_history, and user question
   - Call `GenerativeModel(settings.GEMINI_MODEL).generate_content_async()`
   - If chunks found → grounded answer with source citations in Markdown
   - If no chunks found → transparent response: "I couldn't find that in your uploaded documents, but based on my general knowledge..."
   - Format response as Markdown with `**Sources:** [filename1], [filename2]` footer

6. **Emit synthesis trace**:
   ```python
   await trace_producer.send_trace(job_id, "default_agent", "completed",
       {"last_thought": "Drafting a summary based on retrieved findings..."})
   ```

7. **Return state updates** — writes to both `result_data` (terminal) and `node_outputs`:
   ```python
   result = {
       "summary": synthesized_answer,
       "sources": [{"name": c.source_name, "uri": c.source_uri} for c in chunks],
       "findings": [synthesized_answer],
       "recommendations": [],
       "grounded": bool(chunks),
   }
   node_outputs = dict(state.get("node_outputs", {}))
   node_outputs["default_agent"] = result
   return {"result_data": result, "node_outputs": node_outputs}
   ```

**System prompt:**
> "You are the Prevision AI Assistant. You have access to the user's uploaded documents and files. When answering questions, prioritize information from the provided search results over your own training data. Always cite your sources by referencing the file names. If the search results don't contain relevant information, be transparent and say so, then provide your best general knowledge answer. Maintain a professional, helpful tone."

**Gemini integration:**
- Uses `google.generativeai` (lightweight SDK, no LangChain needed)
- Model: `settings.GEMINI_MODEL` (default `gemini-2.0-flash`)
- Temperature: `settings.GEMINI_TEMPERATURE` (default 0.3 for factual responses)
- API key from `settings.GOOGLE_API_KEY` (same key used by ai-brand-automator)
- Graceful fallback if Gemini unavailable (returns search chunks as-is without synthesis)

**Trace producer access:**
- Import from `app.main import trace_producer` (existing module-level singleton)
- Non-fatal if Kafka unavailable (TraceProducer returns silently)

---

## Phase 4: Node Registration & Router Update

**Modified files:**
- `pipeline-orchestrator-svc/app/factory/node_registry.py`
- `pipeline-orchestrator-svc/app/nodes/internal/router_node.py`
- `pipeline-orchestrator-svc/app/services/job_executor.py`

### 4a. Node Registry

Add `DefaultAgentNode` as the 8th internal handler:
```python
from app.nodes.internal.default_agent_node import DefaultAgentNode

INTERNAL_HANDLERS = {
    # ... existing 7 handlers ...
    "DefaultAgentNode": DefaultAgentNode,
}
```

### 4b. Router Node Update

Add `general-chat` to `KEYWORD_MAP` and update fallback logic:

```python
KEYWORD_MAP = {
    # ... existing 4 entries ...
    "general-chat": [
        "document", "file", "upload", "pdf", "summary",
        "summarize", "what does", "explain", "tell me about",
        "find", "search", "look up",
    ],
}
```

Update routing logic: when `best_score` is 0 (no keyword matches any pipeline), default to `general-chat` instead of `brand-analysis`. This means:
- Specific pipeline keywords (brand equity, competitor, etc.) → route to that pipeline
- Document/RAG keywords → route to `general-chat`
- No keywords match anything → route to `general-chat` (was `brand-analysis`)

### 4c. Job Executor: Inline Manifest Fallback

Add an inline manifest for `general-chat` in `job_executor.py` so it works even before a Django-side manifest is seeded. In `_find_resolved_manifest()`, after existing logic returns None:

```python
if resolved_id == "general-chat" and manifest_data is None:
    manifest_data = {
        "nodes": [
            {"id": "default_agent", "type": "internal", "handler": "DefaultAgentNode"}
        ],
        "edges": [],
        "global_config": {},
    }
```

This is a single-node pipeline (DefaultAgentNode acts as both processor and terminal node).

---

## Phase 5: Pipeline Manifest & Intent Classification (Django)

**Modified files:**
- `ai-brand-automator/orchestration/management/commands/seed_manifests.py` (or data migration)
- `ai-brand-automator/ai_services/services.py`

### 5a. Seed General-Chat Manifest

Add a `general-chat` PipelineManifest to the database so it appears in `available_manifests`:

```python
PipelineManifest.objects.update_or_create(
    pipeline_id="general-chat",
    defaults={
        "name": "General Chat (RAG)",
        "description": "Conversational AI assistant with knowledge base retrieval",
        "is_active": True,
        "manifest_data": {
            "nodes": [
                {"id": "default_agent", "type": "internal", "handler": "DefaultAgentNode"}
            ],
            "edges": [],
            "global_config": {},
        },
    },
)
```

### 5b. Intent Classification Update

In `ai_services/services.py`, add RAG-oriented keywords to `classify_intent()` so document-related queries trigger the pipeline path (currently they'd be handled as "conversation"):

```python
# Add to pipeline_keywords list:
"document", "file", "uploaded", "summarize", "what does the file say",
"search my data", "find in my files", "knowledge base",
```

This ensures queries like "Summarize the PDF I uploaded" or "What does my document say about revenue?" are dispatched to the orchestrator (where RouterNode routes them to `general-chat` → DefaultAgentNode).

---

## Phase 6: Tests

### New test files:

**`pipeline-orchestrator-svc/tests/test_vertex_search_tool.py`** (~6 tests):
- `test_search_returns_chunks` — mocked SearchServiceClient returns structured chunks
- `test_search_with_redis_cache_hit` — cached result returned without Vertex API call
- `test_search_with_redis_cache_miss` — result fetched from Vertex and cached in Redis
- `test_data_store_path_format` — correct path: `projects/brandsol-project/locations/global/collections/default_collection/dataStores/prevision-docs-dev-{tenant_id}`
- `test_empty_query_returns_empty` — graceful handling of empty input
- `test_vertex_api_error_returns_empty` — non-fatal error handling (NotFound, PermissionDenied)

**`pipeline-orchestrator-svc/tests/test_default_agent_node.py`** (~7 tests):
- `test_returns_result_data_with_sources` — full flow with mocked VertexSearchTool + Gemini
- `test_empty_search_results_general_knowledge` — fallback "not in your documents" response
- `test_reads_chat_history` — chat_history passed to Gemini prompt
- `test_reads_tenant_context` — tenant_id used for search scoping
- `test_writes_to_node_outputs` — output stored in `node_outputs["default_agent"]`
- `test_trace_events_emitted` — verify Kafka trace producer called with correct thought messages
- `test_gemini_failure_returns_search_only` — graceful degradation (raw chunks without synthesis)

**Testing approach:** Tests mock `SearchServiceClient` and `google.generativeai` at the module level using `unittest.mock.patch` / `AsyncMock` — consistent with existing test patterns (e.g., `test_external_wrapper.py` mocks httpx). This tests the integration logic without requiring GCP credentials in CI.

### Modified test files:

**`pipeline-orchestrator-svc/tests/test_internal_nodes.py`**:
- Update `TestRouterNode.test_default_resolves_brand_analysis` → change expected default to `general-chat`
- Add `test_keyword_general_chat_document` — document-related keywords route to general-chat
- Add `test_keyword_general_chat_fallback` — no-keyword queries default to general-chat

**`pipeline-orchestrator-svc/tests/test_node_registry.py`**:
- Update handler count assertion from 7 to 8

**`pipeline-orchestrator-svc/tests/test_job_executor.py`**:
- Add `test_general_chat_inline_manifest` — verifies inline fallback manifest for `general-chat` when no Django manifest is available

---

## Files Summary

| File | Action | Phase |
|------|--------|-------|
| `pipeline-orchestrator-svc/requirements.txt` | Modify — add discoveryengine + generativeai | 1 |
| `pipeline-orchestrator-svc/app/core/config.py` | Modify — add Vertex AI, Gemini, cache settings | 1 |
| `deployment/docker-compose.yml` | Modify — add orchestrator env vars + credentials volume | 1 |
| `pipeline-orchestrator-svc/app/nodes/tools/__init__.py` | **New** — empty package init | 2 |
| `pipeline-orchestrator-svc/app/nodes/tools/vertex_search_tool.py` | **New** — Vertex AI Search client with Redis caching | 2 |
| `pipeline-orchestrator-svc/app/nodes/internal/default_agent_node.py` | **New** — RAG specialist node with Gemini synthesis | 3 |
| `pipeline-orchestrator-svc/app/factory/node_registry.py` | Modify — register DefaultAgentNode (8th handler) | 4 |
| `pipeline-orchestrator-svc/app/nodes/internal/router_node.py` | Modify — add general-chat routing, change default | 4 |
| `pipeline-orchestrator-svc/app/services/job_executor.py` | Modify — inline manifest fallback for general-chat | 4 |
| `ai-brand-automator/orchestration/management/commands/seed_manifests.py` | Modify or **New** — seed general-chat manifest | 5 |
| `ai-brand-automator/ai_services/services.py` | Modify — add RAG keywords to intent classifier | 5 |
| `pipeline-orchestrator-svc/tests/test_vertex_search_tool.py` | **New** — 6 tests | 6 |
| `pipeline-orchestrator-svc/tests/test_default_agent_node.py` | **New** — 7 tests | 6 |
| `pipeline-orchestrator-svc/tests/test_internal_nodes.py` | Modify — router default + new keyword tests | 6 |
| `pipeline-orchestrator-svc/tests/test_node_registry.py` | Modify — count 7→8 | 6 |
| `pipeline-orchestrator-svc/tests/test_job_executor.py` | Modify — inline manifest test | 6 |

---

## Key Design Decisions

1. **BaseNode pattern, not LangChain agent**: The orchestrator has no LangChain dependency and all 7 existing nodes follow the BaseNode pattern. Adding LangChain for one node would be over-engineering. The DefaultAgentNode directly calls VertexSearchTool and Gemini.

2. **VertexSearchTool as plain class**: Not a LangChain `Tool` — it's an async Python class with a `search()` method, consistent with how `ExternalWrapper` calls remote services.

3. **Gemini via `google-generativeai`**: Lightweight SDK, avoids the heavy LangChain + langchain-google-genai dependency chain. Direct API call for answer synthesis.

4. **Real GCP connections**: No mock mode. The orchestrator connects to the actual Vertex AI Search data store (`prevision-docs-dev`) and uses the real Gemini API key. GCS credentials are mounted as a read-only volume from `ai-brand-automator/credentials/`.

5. **DefaultAgentNode is terminal**: It writes to `result_data` directly (like ManagerNode) because the general-chat pipeline is a single-node pipeline. Also writes to `node_outputs["default_agent"]` for compatibility if used in multi-node pipelines.

6. **Router fallback change**: No-keyword queries default to `general-chat` instead of `brand-analysis`. Ambiguous queries should get RAG-grounded conversational responses, not brand analysis stubs.

7. **Inline manifest fallback**: `job_executor.py` has a hardcoded single-node manifest for `general-chat` so it works immediately without seeding the Django database. The seeded manifest serves as the "official" entry in the catalog.

---

## Verification (End-to-End)

```bash
# 1. Rebuild orchestrator with new dependencies
cd deployment
docker compose up -d --build orchestrator

# 2. Verify Vertex AI connection
docker exec ai-brand-automator-orchestrator python -c "
from google.cloud import discoveryengine_v1 as de
client = de.SearchServiceClient()
print('SearchServiceClient connected successfully')
"

# 3. Run orchestrator tests
cd pipeline-orchestrator-svc
pytest tests/ -v

# 4. Run Django tests
cd ai-brand-automator
docker exec ai-brand-automator-backend python -m pytest orchestration/tests/ ai_services/tests/ -v

# 5. Seed the general-chat manifest
docker exec ai-brand-automator-backend python manage.py seed_manifests

# 6. E2E test: Upload a file -> Wait for indexing -> Ask a question
# In the frontend chat:
#   a. Upload a PDF or text file (triggers data ingestion -> curation -> RAG indexing)
#   b. Wait for indexing to complete
#   c. Type: "Summarize the document I just uploaded"
# Expected flow:
#   - Intent classifier routes to pipeline (document keywords)
#   - RouterNode resolves to general-chat
#   - DefaultAgentNode queries Vertex AI Search for tenant's data
#   - Gemini synthesizes a grounded answer with source citations
#   - Kafka traces appear: "Searching...", "Extracting...", "Drafting..."
#   - Result displayed in chat with source citations

# 7. E2E test: General question (no documents)
# Type: "What is brand equity?"
# Expected: DefaultAgentNode searches, finds nothing, provides general knowledge answer
```
