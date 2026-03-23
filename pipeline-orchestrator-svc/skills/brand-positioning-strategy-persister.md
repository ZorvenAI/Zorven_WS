---
name: brand-positioning-strategy-persister
version: "1.0"
description: Persist positioning strategy to GCS, RAG indexing, and Redis/PG registry update (maps to SKL-BPA-11)
target_agents:
  - brand_positioning
triggers:
  - "persist strategy"
  - "save positioning"
  - "archive strategy"
  - "rag index"
  - "strategy storage"
priority: 7
max_tokens: 400
---

# Strategy Persistence

## Purpose
Archive the completed positioning strategy document to durable storage (GCS), index it in the tenant's RAG data store for future retrieval, and update the Redis/PostgreSQL positioning registry so the strategy is discoverable by other agents and pipeline runs.

## Methodology

### 1. GCS Archival
- Target bucket: `tenant_context.gcs_processed_bucket`
- Object path: `positioning/{brand_name}/{timestamp}_positioning_strategy.json`
- Content: Full `bpa_strategy_synthesis` output serialized as JSON
- Set metadata headers:
  - `x-goog-meta-brand`: brand name
  - `x-goog-meta-pipeline-job-id`: job_id
  - `x-goog-meta-strategy-confidence`: confidence score
  - `x-goog-meta-framework`: recommended positioning framework
  - `x-goog-meta-created-at`: ISO 8601 timestamp
- If GCS upload fails, log error but do NOT fail the pipeline; mark `gcs_persisted: false`

### 2. RAG Indexing
- Target data store: `tenant_context.rag_data_store_id`
- Prepare a RAG-optimized document with:
  - Title: `"{brand_name} Brand Positioning Strategy — {date}"`
  - Body: Executive summary + recommended positioning + key differentiators
  - Metadata tags: brand name, industry, framework, confidence score
- Submit via the RAG uploader agent endpoint (if available) or direct Vertex AI API
- If RAG indexing fails, log warning and set `rag_indexed: false`

### 3. Redis Registry Update
- Key pattern: `bpa:strategy:{tenant_id}:{brand_name}`
- Value: JSON object with:
  - `job_id`: current job ID
  - `statement`: recommended positioning statement
  - `framework`: framework used
  - `confidence`: strategy confidence score
  - `created_at`: ISO 8601 timestamp
  - `gcs_path`: GCS object path
- TTL: 90 days (refreshed on each new strategy run)
- This allows other agents to quickly check if a positioning strategy exists

### 4. PostgreSQL Registry (via Callback)
- Include registry metadata in the callback `result_data` so Django can persist to the `AnalysisJob` and any positioning-specific models
- Fields: `positioning_statement`, `framework`, `confidence`, `gcs_path`, `rag_indexed`

### 5. Verification
- After all persistence steps, compile a persistence report:
  - GCS: uploaded / failed
  - RAG: indexed / failed / skipped
  - Redis: set / failed
  - PG: delegated to callback

## Output Schema
Write to `node_outputs.bpa_persistence` with keys:
- `gcs_persisted`: bool
- `gcs_path`: str or null
- `rag_indexed`: bool
- `rag_document_id`: str or null
- `redis_key_set`: bool
- `redis_key`: str or null
- `persistence_report`: `{gcs: str, rag: str, redis: str, pg: str}`
- `errors`: list of `{step, error_message}`

## Integration Notes
- This skill runs after SKL-BPA-10 (strategy synthesis) and before the final callback
- Persistence failures are non-fatal; the strategy is still returned via callback
- Future pipeline runs use SKL-BPA-05 (RAG retrieval) to find this archived strategy
