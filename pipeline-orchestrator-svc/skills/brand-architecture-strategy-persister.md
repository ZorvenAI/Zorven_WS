---
name: brand-architecture-strategy-persister
version: "1.0"
description: Persist architecture strategy to GCS, update Redis architecture registry, and index in Vertex AI RAG for future retrieval (maps to SKL-BAA-11)
target_agents:
  - brand_architecture
triggers:
  - "strategy persistence"
  - "save architecture"
  - "persist strategy"
  - "archive architecture"
priority: 7
max_tokens: 400
---

# Architecture Strategy Persister

## Purpose
Persist the completed architecture strategy across three storage layers: GCS (durable archive), Redis architecture registry (live query), and Vertex AI RAG (future retrieval). This ensures the architecture strategy is durably stored, queryable by other agents, and available for RAG-powered follow-up conversations.

## Methodology

### 1. Input Validation
- Read SKL-BAA-10 `baa_strategy` for the complete strategy document
- Verify `confidence_score` is present (required for versioning)
- Read `tenant_context` for `tenant_id`, `gcs_raw_bucket`, `rag_data_store_id`

### 2. GCS Persistence
Store the full strategy document in GCS:
- **Path**: `{gcs_raw_bucket}/architecture/strategy_{timestamp_iso}.json`
- **Content**: Full `baa_strategy` output as JSON
- **Metadata**: `{tenant_id, job_id, confidence_score, recommended_model, created_at}`
- **Retention**: Indefinite (architecture decisions are historical records)
- **Error handling**: Log warning on failure, do not block pipeline. Architecture strategy is still returned to Django via callback even if GCS persistence fails.

### 3. Redis Architecture Registry
Update the live architecture registry in Redis (DB 17):

**Key: `baa:{tenant_id}:registry:architecture`** (Hash, no TTL)
- `recommended_model`: str
- `confidence_score`: float
- `hierarchy_json`: Serialized hierarchy tree
- `naming_pattern`: str
- `consistency_score`: float
- `total_depth`: int
- `total_nodes`: int
- `updated_at`: ISO timestamp
- `job_id`: str
- `version`: int (auto-increment)

**Key: `baa:{tenant_id}:registry:architecture_version:{version}`** (JSON, 365d TTL)
- Full snapshot of the registry at this version
- Enables historical comparison and rollback

**Key: `baa:{tenant_id}:registry:portfolio`** (Hash, no TTL)
- `brands`: JSON list of all brands in the hierarchy
- `brand_count`: int
- `architecture_model`: str
- `updated_at`: ISO timestamp

**Registry update protocol**:
1. GET current version from `baa:{tenant_id}:registry:architecture` field `version`
2. Increment version
3. MULTI/EXEC:
   - SET version snapshot at `baa:{tenant_id}:registry:architecture_version:{new_version}`
   - HSET all fields on `baa:{tenant_id}:registry:architecture`
   - HSET all fields on `baa:{tenant_id}:registry:portfolio`

### 4. Vertex AI RAG Indexing
Index the strategy for future retrieval by SKL-BAA-05:
- **Document ID**: `architecture_strategy_{tenant_id}_{job_id}`
- **Content**: Executive summary + recommendation rationale + naming guidelines
- **Metadata**: `{tenant_id, document_type: "architecture_strategy", recommended_model, confidence_score, created_at}`
- **Error handling**: Log warning on failure, do not block pipeline

### 5. Kafka Event Emission
Emit architecture strategy event to `baa-architecture-events-topic`:
```json
{
  "event_type": "architecture_strategy_created",
  "tenant_id": "...",
  "job_id": "...",
  "recommended_model": "...",
  "confidence_score": 0.85,
  "version": 3,
  "timestamp": "ISO8601"
}
```

## Output Schema
Write to `node_outputs.baa_persistence` with keys:
- `gcs_path`: str or null (null if GCS failed)
- `registry_version`: int
- `registry_updated`: bool
- `rag_indexed`: bool
- `kafka_emitted`: bool
- `persistence_summary`: str (one-line summary of what was persisted)

## Integration Notes
- The architecture registry keys are consumed by the Brand Context Selector (deferred feature) and other WF2 agents
- Version snapshots enable architecture drift detection across BAA re-executions
- GCS path is stored in the Django `AnalysisJob.result_data` for audit trail
- All persistence operations are fail-open — pipeline completes even if storage fails
