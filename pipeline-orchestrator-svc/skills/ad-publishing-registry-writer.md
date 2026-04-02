---
name: ad-publishing-registry-writer
version: "1.0"
description: Write published campaign metadata to permanent Redis registry and Django callback with duplicate detection and full entity audit record (maps to SKL-APA33-11)
target_agents:
  - ad_publishing
triggers:
  - "register published campaign"
  - "save campaign metadata"
  - "publishing registry"
  - "campaign record"
priority: 2
max_tokens: 600
---

# Registry Writer

## Purpose
Persist the complete published campaign metadata to a permanent Redis registry and send a structured result callback to the Django backend. This creates the authoritative record of what was published, including all entity IDs, targeting configurations, budget commitments, and sandbox/production designation. Implements duplicate detection to prevent re-publishing the same campaign configuration.

## Methodology

### 1. Assemble Publication Record
Compile the complete publication record from all upstream outputs:
- Campaign: ID, name, objective, status, budget, bid strategy
- Ad sets: IDs, names, targeting specs, budgets, optimization goals, placements
- Ads: IDs, creative IDs, image hashes, headlines, CTAs
- Targeting: persona-to-targeting-spec mapping, estimated reach
- Budget: total committed, currency, per-ad-set allocation
- Approval: approved_by, approved_at, double_confirmed
- Verification: status, discrepancies, delivery started
- Metadata: job_id, tenant_id, brand_name, pipeline_run_id, sandbox_mode, timestamps

### 2. Duplicate Detection
Before writing, check for existing publication with the same fingerprint:
- Compute fingerprint: SHA-256 of `{ad_account_id + campaign_objective + targeting_specs_hash + creative_hashes}`
- Check Redis key `apa:published:fingerprint:{fingerprint_hash}`
- If exists: return warning with the existing publication record, do NOT create duplicate
- If new: proceed to write, store fingerprint with reference to this publication

### 3. Write to Redis Registry
Store the publication record in Redis with permanent retention:
- Primary key: `apa:published:{job_id}` -- full publication record (JSON)
- Index key: `apa:published:campaign:{campaign_id}` -- maps campaign ID to job ID
- Index key: `apa:published:account:{ad_account_id}` -- sorted set of campaign IDs by created_at
- Index key: `apa:published:tenant:{tenant_id}` -- sorted set of job IDs by created_at
- Fingerprint key: `apa:published:fingerprint:{hash}` -- duplicate detection reference
- All keys use no TTL (permanent) except fingerprint keys which expire after 30 days

### 4. Send Django Callback
Send the final result callback to the Django backend via `PATCH {callback_url}`:
- `status`: `completed`
- `result_data`: structured publication record with:
  - `campaign_id`: Meta campaign ID
  - `ad_set_ids`: list of Meta ad set IDs
  - `ad_ids`: list of Meta ad IDs
  - `creative_ids`: list of Meta creative IDs
  - `total_budget_committed`: dict (amount, currency)
  - `targeting_summary`: human-readable targeting description per ad set
  - `sandbox_mode`: boolean
  - `verification_status`: GREEN/YELLOW/RED
  - `approved_by`: user ID
  - `published_at`: ISO 8601 timestamp
- `progress`: final progress state with all nodes completed

### 5. Emit Kafka Audit Event
Publish to `apa33-publishing-audit-topic`:
- Event type: `campaign_published`
- Full publication record for compliance audit
- Include the approval chain (who approved, when, double-confirm status)

## Output Schema
Write to `node_outputs.apa_registry` with keys:
- `publication_id`: string (UUID)
- `job_id`: string
- `campaign_id`: string
- `ad_account_id`: string
- `entity_summary`: dict (campaign_count, adset_count, ad_count, creative_count)
- `budget_committed`: dict (total_amount, currency, per_adset_breakdown)
- `sandbox_mode`: boolean
- `fingerprint_hash`: string
- `duplicate_detected`: boolean
- `registry_keys_written`: list[str]
- `callback_sent`: boolean
- `kafka_event_published`: boolean
- `published_at`: string (ISO 8601)

## Integration Notes
- The Redis registry serves as the source of truth for campaign management operations (pause, resume, budget adjustments) in future pipeline runs
- Duplicate detection prevents accidental re-publication when a pipeline is retried after a transient failure in a non-publishing step
- The Django callback `result_data` structure must match the analytics extractor expectations for the `ad_publishing` node in the analytics pipeline
