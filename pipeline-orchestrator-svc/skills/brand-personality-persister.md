---
name: brand-personality-persister
version: "1.0"
description: Persist personality profile to Redis registry, sync brand context to Django backend, and emit personality events for downstream consumers (maps to SKL-BPV-11)
target_agents:
  - brand_personality
triggers:
  - "personality persistence"
  - "save personality"
  - "persist personality"
  - "brand context sync"
  - "personality registry"
priority: 7
max_tokens: 400
---

# Personality Persister

## Purpose
Persist the completed personality profile across two storage layers: Redis personality registry (live query) and Django brand context sync (cross-agent availability). This ensures the personality profile is queryable by other agents and available as brand context for downstream pipeline executions.

## Methodology

### 1. Input Validation
- Read SKL-BPV-10 `bpv_character_brief` for the complete personality document (required)
- Verify `confidence_score` is present (required for versioning)
- Read `tenant_context` for `tenant_id`
- Read `input_context` for `company_id` and optional `brand_context_id`

### 2. Redis Personality Registry
Update the live personality registry in Redis (DB 18):

**Key: `bpv:{tenant_id}:registry:personality`** (Hash, no TTL)
- `primary_dimension`: str
- `secondary_dimension`: str
- `archetype`: str
- `confidence_score`: float
- `aaker_scores_json`: Serialized Aaker dimension scores
- `core_values_json`: Serialized core values list
- `voice_dimensions_json`: Serialized voice matrix dimensions
- `updated_at`: ISO timestamp
- `job_id`: str
- `version`: int (auto-increment)

**Key: `bpv:{tenant_id}:registry:personality_version:{version}`** (JSON, 365d TTL)
- Full snapshot of the registry at this version
- Enables historical comparison and personality drift detection

**Key: `bpv:{tenant_id}:registry:voice_matrix`** (Hash, no TTL)
- `voice_dimensions_json`: Serialized full voice matrix
- `channel_matrix_json`: Serialized channel adaptations
- `do_list_json`: Serialized do guidelines
- `dont_list_json`: Serialized don't guidelines
- `updated_at`: ISO timestamp

**Registry update protocol**:
1. GET current version from `bpv:{tenant_id}:registry:personality` field `version`
2. Increment version
3. MULTI/EXEC:
   - SET version snapshot at `bpv:{tenant_id}:registry:personality_version:{new_version}`
   - HSET all fields on `bpv:{tenant_id}:registry:personality`
   - HSET all fields on `bpv:{tenant_id}:registry:voice_matrix`

### 3. Django Brand Context Sync
Sync the personality profile to Django's brand context system:
- POST to `{BPV_BACKEND_URL}/api/v1/analytics/personality-context/`
- Payload: compact personality summary (Aaker scores, archetype, core values, voice dimensions)
- This makes the personality available to future WF2/WF3 agent executions via the Brand Context Selector
- Error handling: log warning on failure, do not block pipeline

### 4. Kafka Event Emission
Emit personality event to `bpv-personality-events-topic`:
```json
{
  "event_type": "personality_profile_created",
  "tenant_id": "...",
  "job_id": "...",
  "primary_dimension": "...",
  "archetype": "...",
  "confidence_score": 0.85,
  "version": 3,
  "timestamp": "ISO8601"
}
```

## Output Schema
Write to `node_outputs.bpv_persistence` with keys:
- `registry_version`: int
- `registry_updated`: bool
- `voice_matrix_updated`: bool
- `django_synced`: bool
- `kafka_emitted`: bool
- `persistence_summary`: str (one-line summary of what was persisted)

## Integration Notes
- The personality registry keys are consumed by the Brand Context Selector and downstream WF2/WF3 agents
- Version snapshots enable personality drift detection across BPV re-executions
- All persistence operations are fail-open — pipeline completes even if storage fails
- Django sync enables other agents to load personality context via `GET /api/v1/analytics/personality-context/`
