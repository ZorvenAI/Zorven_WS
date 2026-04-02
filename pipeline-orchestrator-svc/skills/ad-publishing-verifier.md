---
name: ad-publishing-verifier
version: "1.0"
description: Post-publish verification of all Meta entities -- delivery status, targeting correctness, budget validation, and discrepancy reporting (maps to SKL-APA33-10)
target_agents:
  - ad_publishing
triggers:
  - "verify published ads"
  - "post-publish check"
  - "meta ads verification"
  - "delivery status check"
priority: 3
max_tokens: 700
---

# Post-Publish Verifier

## Purpose
Perform a comprehensive post-publish verification pass across all Meta Ads entities created and activated by the pipeline. Confirms that all entities exist in Meta's system, checks initial delivery status, validates that targeting specifications were applied correctly, and verifies budget configurations match the intended values. Any discrepancies are flagged for human review.

## Methodology

### 1. Verify Campaign Entity
Call `GET /{campaign_id}?fields=id,name,status,objective,special_ad_categories,daily_budget,lifetime_budget,bid_strategy`:
- Confirm `status == "ACTIVE"` (or PAUSED if partial activation)
- Verify `objective` matches the intended CAA objective
- Verify `special_ad_categories` matches the declared category
- Check for `effective_status` -- Meta may override status (e.g., CAMPAIGN_PAUSED, ADSET_PAUSED)
- Flag discrepancy if any field does not match expected values

### 2. Verify Ad Set Entities
For each activated ad set, call `GET /{adset_id}?fields=id,name,status,effective_status,targeting,daily_budget,optimization_goal,billing_event,start_time,end_time`:
- Confirm `status == "ACTIVE"` and `effective_status == "ACTIVE"`
- Compare `targeting` JSON against the targeting spec sent in SKL-APA33-04
- Verify `daily_budget` or `lifetime_budget` matches intended allocation (in cents)
- Check `optimization_goal` matches the funnel stage mapping
- Common `effective_status` issues: `PENDING_REVIEW` (Meta policy review), `DISAPPROVED` (policy violation)

### 3. Verify Ad Entities
For each ad, call `GET /{ad_id}?fields=id,name,status,effective_status,creative,adset_id`:
- Confirm `status == "ACTIVE"` and `effective_status == "ACTIVE"`
- Verify the creative ID matches the intended creative
- Check for `DISAPPROVED` status indicating Meta policy rejection
- If disapproved: extract `ad_review_feedback` for the rejection reason

### 4. Check Initial Delivery Signals
Call `GET /{campaign_id}/insights?fields=impressions,reach,spend&date_preset=today` (may be empty if just activated):
- Record whether delivery has started (impressions > 0)
- If 30+ minutes post-activation and zero impressions: flag as potential delivery issue
- Common causes: low budget, narrow audience, Learning phase, Meta review pending

### 5. Budget Reconciliation
Compare intended vs actual budget:
- Sum all ad set budgets and compare against campaign-level budget
- Verify currency consistency across all entities
- Check that no ad set budget is below Meta's minimum ($1.00/day)
- Calculate total daily spend commitment and compare against CAA blueprint allocation

### 6. Generate Discrepancy Report
Compile all verification results:
- GREEN: all checks passed, delivery confirmed
- YELLOW: minor discrepancies (e.g., rounding differences in budget, pending review)
- RED: critical issues (disapproved ads, missing entities, budget mismatch > 5%)
- Escalate RED issues to SKL-APA33-12 for admin notification

## Output Schema
Write to `node_outputs.apa_verification` with keys:
- `verification_status`: string (GREEN | YELLOW | RED)
- `campaign_verified`: dict (entity_id, status_match, objective_match, budget_match)
- `ad_sets_verified`: list[dict] (entity_id, status_match, targeting_match, budget_match, effective_status)
- `ads_verified`: list[dict] (entity_id, status_match, creative_match, effective_status, review_status)
- `delivery_started`: boolean
- `initial_impressions`: int
- `budget_reconciliation`: dict (intended_total, actual_total, variance_cents, variance_percent)
- `discrepancies`: list[dict] (entity_id, entity_type, field, expected, actual, severity)
- `disapproved_ads`: list[dict] (ad_id, rejection_reason, recommended_action)
- `verified_at`: string (ISO 8601)

## Integration Notes
- Verification runs immediately after activation; some checks (delivery signals) may require a follow-up verification pass 30-60 minutes later
- Disapproved ads are common during first publication; the rejection reasons from `ad_review_feedback` should be surfaced in the Django UI for user remediation
- The verification report feeds into SKL-APA33-11 (registry-writer) as part of the permanent publication record
