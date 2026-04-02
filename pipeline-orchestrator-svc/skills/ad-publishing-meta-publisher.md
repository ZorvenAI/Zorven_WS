---
name: ad-publishing-meta-publisher
version: "1.0"
description: After human approval, activate campaign and ad sets by updating status to ACTIVE with partial approval support and aggressive circuit breaker for rollback (maps to SKL-APA33-09)
target_agents:
  - ad_publishing
triggers:
  - "activate campaign"
  - "publish to meta"
  - "go live meta ads"
  - "campaign activation"
priority: 4
max_tokens: 800
---

# Meta Publisher

## Purpose
After receiving human approval from SKL-APA33-08, activate the Meta Ads campaign by updating entity statuses from PAUSED to ACTIVE. Supports partial approval where only a subset of ad sets are approved for activation. Implements an aggressive circuit breaker (2 failures in 30 seconds) that triggers immediate full rollback and admin escalation to prevent partially-activated campaigns from spending budget uncontrolled.

## Methodology

### 1. Verify Approval Status
Before any activation:
- Read `node_outputs.apa_approval` and confirm `status == "approved"`
- Verify `approved_at` is within the last 24 hours (approval freshness check)
- Confirm `approved_by` is a valid ADMIN user
- If production: verify `double_confirmed == true`
- HALT if any verification fails -- do not activate without valid approval

### 2. Determine Activation Scope
Check for partial approval:
- If `approval.approved_ad_sets` is specified: only activate listed ad set IDs
- If not specified: activate all ad sets in `node_outputs.apa_ad_sets.ad_sets`
- Build activation manifest: list of `{entity_type, entity_id, target_status: "ACTIVE"}`
- Order: activate ad sets first, then campaign (Meta requires active ad sets under a campaign)

### 3. Activate Ad Sets
For each approved ad set, call `POST /{adset_id}`:
- Body: `{"status": "ACTIVE"}`
- On 200: record `{adset_id, activated_at, status: "ACTIVE"}`
- On 400 (policy violation): record error, skip this ad set, continue
- On 403/5xx: increment circuit breaker failure counter

### 4. Activate Campaign
After at least one ad set is successfully activated:
- Call `POST /{campaign_id}` with body `{"status": "ACTIVE"}`
- On 200: campaign is now live and will begin spending budget
- On failure: immediately trigger rollback of all activated ad sets

### 5. Circuit Breaker: 2 Failures / 30 Seconds
Aggressive circuit breaker for activation (more sensitive than upload circuit breaker):
- Threshold: 2 failures within 30-second sliding window
- On trip: IMMEDIATELY execute full rollback:
  1. Pause all ad sets that were just activated: `POST /{adset_id}` with `{"status": "PAUSED"}`
  2. Pause the campaign: `POST /{campaign_id}` with `{"status": "PAUSED"}`
  3. If pause calls also fail: escalate to SKL-APA33-12 with CRITICAL severity
- Store rollback status in Redis: `apa:rollback:{job_id}`
- Send escalation callback to Django with affected entity IDs

### 6. Record Activation Results
Log the final activation state for each entity:
- Timestamp of activation
- Whether the entity was approved but failed to activate
- Any Meta API warnings (e.g., "low budget", "narrow audience")

## Output Schema
Write to `node_outputs.apa_published` with keys:
- `campaign_id`: string
- `campaign_status`: string (ACTIVE | PAUSED | ROLLBACK)
- `activated_ad_sets`: list[dict] (adset_id, status, activated_at)
- `skipped_ad_sets`: list[dict] (adset_id, reason -- not approved or failed)
- `total_activated`: int
- `total_skipped`: int
- `circuit_breaker_tripped`: boolean
- `rollback_executed`: boolean
- `rollback_results`: list[dict] | null (entity_id, rollback_status)
- `activation_duration_seconds`: float
- `budget_now_live`: dict (total_daily_budget, currency) | null

## Integration Notes
- This is the point of no return for ad spend; once ACTIVE, Meta may begin delivering impressions within minutes
- The aggressive circuit breaker (2/30s vs 5/60s for uploads) reflects the higher stakes of activation -- partial activation can result in uncontrolled spend
- After successful activation, SKL-APA33-10 (verifier) runs immediately to confirm delivery status and targeting correctness
