---
name: brand-naming-persister
version: "1.0"
description: Persist naming results to Redis registry, sync naming context to Django backend, and emit naming events for downstream consumers (maps to SKL-NTA-13)
target_agents:
  - naming_tagline
triggers:
  - "naming persistence"
  - "save naming"
  - "persist naming"
  - "naming registry"
  - "naming context sync"
priority: 7
max_tokens: 400
---

# Naming Persister

## Purpose
Persist the completed naming brief and selected candidates across two storage layers: Redis naming registry (live query) and Django brand context sync (cross-agent availability). This ensures naming decisions are queryable by other agents and available as brand context for downstream pipeline executions.

## Methodology

### 1. Input Validation
- Read SKL-NTA-12 `nta_naming_brief` for the complete naming brief document (required)
- Verify `confidence_score` is present (required for versioning)
- Read `tenant_context` for `tenant_id`
- Read `input_context` for `company_id` and optional `brand_context_id`

### 2. Redis Naming Registry
Update the live naming registry in Redis (DB allocated for NTA):

**Key: `nta:{tenant_id}:registry:naming`** (Hash, no TTL)
- `recommended_names_json`: Serialized top 3 recommended names with scores
- `selected_taglines_json`: Serialized best tagline pairings
- `domain_status_json`: Serialized domain availability summary
- `trademark_status_json`: Serialized trademark risk summary
- `confidence_score`: float
- `updated_at`: ISO timestamp
- `job_id`: str
- `version`: int (auto-increment)

**Key: `nta:{tenant_id}:registry:naming_version:{version}`** (JSON, 365d TTL)
- Full snapshot of the naming brief at this version
- Enables historical comparison and naming evolution tracking

**Key: `nta:{tenant_id}:registry:taglines`** (Hash, no TTL)
- `best_pairings_json`: Serialized name-tagline pairings
- `all_taglines_json`: Serialized complete tagline set
- `updated_at`: ISO timestamp

**Registry update protocol**:
1. GET current version from `nta:{tenant_id}:registry:naming` field `version`
2. Increment version
3. MULTI/EXEC:
   - SET version snapshot at `nta:{tenant_id}:registry:naming_version:{new_version}`
   - HSET all fields on `nta:{tenant_id}:registry:naming`
   - HSET all fields on `nta:{tenant_id}:registry:taglines`

### 3. Django Brand Context Sync
Sync the naming results to Django's brand context system:
- POST to `{NTA_BACKEND_URL}/api/v1/analytics/naming-context/`
- Payload: compact naming summary (recommended names, taglines, availability status, confidence)
- This makes naming decisions available to future WF2/WF3 agent executions via the Brand Context Selector
- Error handling: log warning on failure, do not block pipeline

### 4. Kafka Event Emission
Emit naming event to `nta-naming-events-topic`:
```json
{
  "event_type": "naming_brief_created",
  "tenant_id": "...",
  "job_id": "...",
  "top_recommendation": "...",
  "candidates_evaluated": 15,
  "confidence_score": 0.82,
  "version": 2,
  "timestamp": "ISO8601"
}
```

## Output Schema
Write to `node_outputs.nta_persistence` with keys:
- `registry_version`: int
- `registry_updated`: bool
- `taglines_updated`: bool
- `django_synced`: bool
- `kafka_emitted`: bool
- `persistence_summary`: str (one-line summary of what was persisted)

## Integration Notes
- The naming registry keys are consumed by the Brand Context Selector and downstream WF2/WF3 agents
- Version snapshots enable naming evolution tracking across NTA re-executions
- All persistence operations are fail-open — pipeline completes even if storage fails
- Django sync enables other agents to load naming context via the brand context API
