---
name: campaign-arch-blueprint-persister
version: "1.0"
description: Persist campaign blueprint to Redis hot cache and GCS cold storage with structured key patterns for cross-service access and audit retrieval (maps to SKL-CAA-11)
target_agents:
  - campaign_architecture
triggers:
  - "persist blueprint"
  - "save campaign"
  - "store blueprint"
  - "campaign storage"
priority: 10
max_tokens: 400
---

# Blueprint Persister

## Purpose
Write the complete campaign blueprint to two storage tiers: Redis (fast cache for cross-service access and real-time retrieval) and GCS (durable storage for audit trail and historical analysis).

## Methodology

### 1. Redis Cache
Write to Redis with structured key patterns:
- `caa:{tenant_id}:registry:campaign:{campaign_id}` — full blueprint JSON
- `caa:{tenant_id}:registry:campaign:{campaign_id}:confidence` — confidence score (float)
- `caa:{tenant_id}:registry:campaign:latest` — pointer to most recent campaign_id
- `caa:{tenant_id}:registry:campaign:{campaign_id}:metadata` — lightweight metadata (brand, maturity, budget, created_at)
- TTL: 7 days (configurable via `CAA_CACHE_TTL_SECONDS`)

### 2. GCS Upload
Upload to GCS bucket with structured paths:
- Blueprint: `gs://{bucket}/caa/{tenant_id}/{job_id}/blueprint.json`
- Metadata: `gs://{bucket}/caa/{tenant_id}/{job_id}/metadata.json`
- Content: Complete campaign blueprint from SKL-CAA-10

GCS object metadata:
- `tenant_id`: string
- `job_id`: string
- `campaign_id`: string
- `confidence_score`: string (float as string)
- `brand_maturity`: string
- `total_budget`: string
- `created_at`: ISO 8601 timestamp

### 3. Registry Update
Update the analytics registry so other services can discover CAA results:
- Write registry entry to Redis: `caa:{tenant_id}:registry:latest_job_id`
- Include summary metrics for quick access without loading full blueprint

### 4. Versioning
If a prior blueprint exists for this tenant:
- Increment version counter: `caa:{tenant_id}:registry:campaign:version`
- Previous versions remain accessible in GCS by job_id
- Redis only holds the latest version (prior versions evicted)

## Output Schema
Write to `node_outputs.caa_persistence` with keys:
- `campaign_id`: string (UUID)
- `gcs_uri`: string (GCS path of uploaded blueprint)
- `cache_keys`: list of Redis keys written
- `version`: int (blueprint version for this tenant)
- `persisted_at`: ISO 8601 timestamp
- `storage_status`: dict with `redis` and `gcs` status ("success" | "failed")

## Integration Notes
- Redis data is consumed by downstream services needing campaign context
- GCS data is consumed by RAG pipelines and audit systems
- If GCS is unavailable, Redis-only persistence succeeds (fail-open)
- If Redis is unavailable, GCS-only persistence succeeds (fail-open)
- At least one storage tier must succeed for the skill to report success
