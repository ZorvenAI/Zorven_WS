---
name: ad-publishing-campaign-creator
version: "1.0"
description: Create Meta Ads campaign in PAUSED status with objective mapping, Special Ad Category, and rollback tracking (maps to SKL-APA33-03)
target_agents:
  - ad_publishing
triggers:
  - "create meta campaign"
  - "campaign creation"
  - "meta ads campaign setup"
  - "publish campaign structure"
priority: 8
max_tokens: 800
---

# Campaign Creator

## Purpose
Create the top-level Meta Ads campaign entity in PAUSED status based on the CAA blueprint. This skill maps the CAA campaign objective to the corresponding Meta Marketing API objective enum, applies Special Ad Category settings when required, and registers the created entity for rollback tracking in case of downstream failures.

## Methodology

### 1. Map CAA Objective to Meta Campaign Objective
Translate the CAA blueprint objective to Meta's objective enum:
- `awareness` -> `OUTCOME_AWARENESS`
- `traffic` -> `OUTCOME_TRAFFIC`
- `engagement` -> `OUTCOME_ENGAGEMENT`
- `leads` -> `OUTCOME_LEADS`
- `sales` -> `OUTCOME_SALES`
- Reject unknown objectives with a descriptive error

### 2. Construct Campaign Creation Payload
Build the `POST /{ad_account_id}/campaigns` payload:
- `name`: `{brand_name} - {objective} - {date_stamp}` (human-readable, searchable)
- `objective`: mapped Meta objective enum value
- `status`: `PAUSED` (NEVER create in ACTIVE status)
- `special_ad_categories`: `["HOUSING"]`, `["CREDIT"]`, `["EMPLOYMENT_OPPORTUNITY"]`, or `[]`
- `buying_type`: `AUCTION` (default) or `RESERVED` if specified in CAA config
- `bid_strategy`: from CAA blueprint (LOWEST_COST_WITHOUT_CAP, LOWEST_COST_WITH_BID_CAP, COST_CAP)
- `daily_budget` or `lifetime_budget`: from CAA budget allocation (in cents, Meta API requirement)
- `spend_cap`: optional campaign-level spend cap from CAA

### 3. Execute Campaign Creation API Call
Call `POST /act_{ad_account_id}/campaigns` with the constructed payload:
- On 200 response: extract `campaign_id` from response
- On 400 (validation error): parse Meta error code and sub-code, return actionable error message
- On 403 (permission denied): halt and escalate to SKL-APA33-12
- On 429 (rate limit): apply exponential backoff (1s, 2s, 4s) with max 3 retries
- On 5xx (Meta server error): retry up to 3 times, then fail

### 4. Register Entity for Rollback Tracking
Add the created campaign to the rollback registry:
- Store `{entity_type: "campaign", entity_id: campaign_id, ad_account_id, created_at}` in pipeline state
- This registry is consumed by the rollback handler if any downstream step fails
- Rollback action: `DELETE /{campaign_id}` or update status to `DELETED`

### 5. Verify Campaign Creation
Call `GET /{campaign_id}?fields=id,name,objective,status,special_ad_categories`:
- Confirm the campaign exists with expected objective and PAUSED status
- Verify Special Ad Category is correctly applied
- Log the campaign ID for audit trail

## Output Schema
Write to `node_outputs.apa_campaign` with keys:
- `campaign_id`: string (Meta campaign ID)
- `campaign_name`: string
- `objective`: string (Meta objective enum)
- `status`: string (PAUSED)
- `special_ad_categories`: list[str]
- `buying_type`: string
- `budget`: dict (type, amount_cents, currency)
- `bid_strategy`: string
- `rollback_registry`: list[dict] (entities created so far)
- `api_calls_made`: int
- `created_at`: string (ISO 8601)

## Integration Notes
- Campaign is ALWAYS created in PAUSED status; activation only occurs in SKL-APA33-09 after human approval
- Budget values must be converted to cents (integer) for the Meta API -- e.g., $50.00 becomes 5000
- The rollback registry is append-only and passed through every subsequent entity creation skill (SKL-APA33-04, SKL-APA33-07)
