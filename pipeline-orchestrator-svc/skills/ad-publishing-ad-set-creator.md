---
name: ad-publishing-ad-set-creator
version: "1.0"
description: Create ad sets in PAUSED status under the campaign with targeting specs, budget allocation, bid strategy, scheduling, and placements (maps to SKL-APA33-04)
target_agents:
  - ad_publishing
triggers:
  - "create ad sets"
  - "ad set creation"
  - "meta ad set setup"
  - "audience ad set mapping"
priority: 7
max_tokens: 800
---

# Ad Set Creator

## Purpose
Create one or more Meta Ads ad sets under the campaign created in SKL-APA33-03. Each ad set maps to a CAA audience segment with translated targeting specifications, budget allocation, bid strategy, scheduling windows, and placement configuration. All ad sets are created in PAUSED status and tracked for rollback.

## Methodology

### 1. Map CAA Audience Segments to Ad Sets
For each audience segment in the CAA blueprint:
- Read the segment name, funnel stage (TOFU/MOFU/BOFU), and budget percentage
- Retrieve the translated targeting spec from SKL-APA33-05 (`node_outputs.apa_targeting`)
- Calculate the ad set budget as a proportion of the campaign total budget
- Determine the optimization goal based on funnel stage:
  - TOFU: `REACH`, `IMPRESSIONS`, or `LINK_CLICKS`
  - MOFU: `LINK_CLICKS`, `LANDING_PAGE_VIEWS`, or `POST_ENGAGEMENT`
  - BOFU: `CONVERSIONS`, `LEAD_GENERATION`, or `VALUE`

### 2. Construct Ad Set Creation Payload
For each ad set, build `POST /{ad_account_id}/adsets`:
- `name`: `{brand_name} - {segment_name} - {funnel_stage}`
- `campaign_id`: from `node_outputs.apa_campaign.campaign_id`
- `status`: `PAUSED`
- `targeting`: translated Meta targeting spec JSON from SKL-APA33-05
- `optimization_goal`: mapped from funnel stage
- `billing_event`: `IMPRESSIONS` (standard) or `LINK_CLICKS` (for traffic objectives)
- `bid_amount`: from CAA bid strategy (in cents), or omit for automatic bidding
- `daily_budget` or `lifetime_budget`: calculated from campaign allocation (in cents)
- `start_time` / `end_time`: ISO 8601 timestamps from CAA scheduling
- `promoted_object`: Page ID or pixel ID depending on objective
- `publisher_platforms`: `["facebook", "instagram"]` unless CAA specifies otherwise
- `facebook_positions`: `["feed", "stories", "reels", "marketplace"]` per CAA placement config
- `instagram_positions`: `["stream", "story", "reels", "explore"]` per CAA placement config

### 3. Apply Special Ad Category Restrictions
If Special Ad Category is set:
- Remove `age_min`, `age_max`, `genders` from targeting spec (Meta requirement)
- Restrict `geo_locations` to country + state level only (no ZIP/radius targeting)
- Remove `interests` and `behaviors` that are restricted categories
- Set `special_ad_category_country`: list of target countries

### 4. Execute Ad Set Creation API Calls
For each ad set:
- Call `POST /act_{ad_account_id}/adsets` with constructed payload
- On success: extract `adset_id` from response
- On 400: parse Meta error (common: invalid targeting spec, budget below minimum $1/day)
- Apply same retry/backoff strategy as campaign creation (3 retries, exponential backoff)
- If one ad set fails, continue creating remaining ad sets (partial success allowed)

### 5. Register Entities for Rollback
Append each created ad set to the rollback registry:
- `{entity_type: "adset", entity_id: adset_id, parent_campaign_id, segment_name, created_at}`
- Track creation order for ordered rollback (delete ad sets before campaign)

## Output Schema
Write to `node_outputs.apa_ad_sets` with keys:
- `ad_sets`: list[dict] each containing:
  - `adset_id`: string (Meta ad set ID)
  - `adset_name`: string
  - `segment_name`: string
  - `funnel_stage`: string (TOFU/MOFU/BOFU)
  - `optimization_goal`: string
  - `targeting_spec_applied`: dict (the targeting JSON sent to Meta)
  - `budget`: dict (type, amount_cents, currency)
  - `placements`: dict (platforms and positions)
  - `status`: string (PAUSED)
- `total_ad_sets_created`: int
- `failed_ad_sets`: list[dict] (segment_name, error_message)
- `rollback_registry`: list[dict] (updated with ad set entities)
- `created_at`: string (ISO 8601)

## Integration Notes
- Ad sets inherit the campaign objective; the optimization_goal must be compatible with the campaign objective or Meta API returns error 100
- Minimum daily budget per ad set is $1.00 (100 cents); the budget allocator must enforce this floor
- The rollback registry from SKL-APA33-03 is extended here and passed forward to SKL-APA33-07 for ad entity tracking
