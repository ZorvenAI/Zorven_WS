---
name: creative-gen-persister
version: "1.0"
description: Persist creative package metadata to Redis cache and upload full package JSON to GCS for long-term storage and retrieval (maps to SKL-CGA-13)
target_agents:
  - creative_generation
triggers:
  - "persist creative"
  - "save creative package"
  - "store creative output"
  - "creative storage"
priority: 10
max_tokens: 800
---

# Creative Package Persister

## Purpose
Persist the assembled CampaignCreativePackage to both Redis (for fast retrieval and caching) and GCS (for durable long-term storage). This final skill ensures creative outputs are available for downstream systems including the Django backend, frontend preview, and future campaign iterations.

## Methodology

### 1. Load Package
From `node_outputs.cga_package`:
- Read the full CampaignCreativePackage JSON
- Validate package_id and blueprint_id are present
- Verify at least one creative unit exists

### 2. Redis Cache Persistence
Store package metadata for fast access:

**Package index key**: `cga:package:{package_id}`
- Full package JSON (with GCS paths, not image data)
- TTL: 7 days (configurable via `CAA_REDIS_PACKAGE_TTL`)

**Brand lookup key**: `cga:brand:{brand_name}:latest`
- Reference to latest package_id for this brand
- TTL: 30 days

**Blueprint mapping key**: `cga:blueprint:{blueprint_id}:package`
- Maps CAA blueprint to its creative package
- TTL: 30 days

**Per-unit cache**: `cga:unit:{unit_id}`
- Individual creative unit for granular retrieval
- TTL: 7 days

### 3. GCS Upload
Upload full package and supporting artifacts:

**Package JSON**: `{gcs_processed_bucket}/creative-packages/{package_id}/package.json`
- Full CampaignCreativePackage as formatted JSON
- Content-Type: `application/json`

**Package manifest**: `{gcs_processed_bucket}/creative-packages/{package_id}/manifest.json`
- Lightweight index with image GCS paths, copy text, and metadata
- Used for quick listing without loading full package

**Compliance report**: `{gcs_processed_bucket}/creative-packages/{package_id}/compliance-report.json`
- Full compliance screening results for audit trail

### 4. Generate Access URLs
For each persisted artifact:
- Generate signed URLs with 7-day expiry
- Include signed URLs in the final output for immediate frontend preview

### 5. Verify Persistence
Confirm all writes succeeded:
- Redis: Read-back verification on package index key
- GCS: Verify upload response status for each artifact
- Log any persistence failures as warnings (non-fatal)

### 6. Emit Audit Event
If Kafka is available, publish to `caa-architecture-events-topic`:
- Event type: `creative_package_persisted`
- Package ID, blueprint ID, brand name
- Coverage percentage, confidence score
- Timestamp

## Output Schema
Write to `node_outputs.cga_persistence` with keys:
- `package_id`: string
- `redis_keys`: list of persisted Redis key names
- `gcs_artifacts`: list of `{path, signed_url, content_type, size_bytes}`
- `persistence_status`: "complete" | "partial" | "failed"
- `redis_success`: boolean
- `gcs_success`: boolean
- `verification_passed`: boolean
- `audit_event_published`: boolean

## Integration Notes
- This is the final skill in the CGA pipeline
- Redis TTLs should match the campaign duration from the CAA blueprint
- GCS paths follow tenant isolation: `{tenant_bucket}/creative-packages/...`
- The Django result handler receives package_id via callback and can retrieve from Redis
- Frontend uses signed URLs from this skill for creative preview rendering
- Failed persistence is non-fatal; package data is still in the callback result_data
