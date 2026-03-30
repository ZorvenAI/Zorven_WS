---
name: brand-story-persister
version: "1.0"
description: Persist final narrative package to Redis cache and GCS for long-term storage and cross-service access (maps to SKL-BSA-13)
target_agents:
  - brand_story
triggers:
  - "persist story"
  - "save narrative"
  - "store brand story"
  - "narrative storage"
priority: 10
max_tokens: 400
---

# Story Persister

## Purpose
Write the complete narrative package to two storage tiers: Redis (fast cache for cross-service access) and GCS (durable storage for audit/retrieval).

## Methodology

### 1. Redis Cache
Write to Redis DB 20 with keys:
- `bsa:{tenant_id}:parent` — full narrative package (JSON)
- `bsa:{tenant_id}:confidence` — confidence score (float)
- TTL: 7 days (configurable)

### 2. GCS Upload
Upload to GCS bucket:
- Path: `gs://{bucket}/{tenant_id}/brand-story/{job_id}/narrative_{timestamp}.json`
- Content: Complete narrative package (origin story, mission/vision, pitches, channels, style guide, sub-brands, WF2 summary)
- Metadata: tenant_id, job_id, confidence_score, timestamp

### 3. Registry Update
Update the analytics registry so other services can discover the latest BSA results.

## Output Schema
- `gcs_uri`: string (GCS path of uploaded narrative)
- `cache_keys`: list of Redis keys written
- `persisted_at`: ISO 8601 timestamp

## Integration Notes
- Redis data is consumed by the NTA context endpoint and downstream services
- GCS data is consumed by RAG pipelines and audit systems
- If GCS is unavailable, Redis-only persistence succeeds (fail-open)
