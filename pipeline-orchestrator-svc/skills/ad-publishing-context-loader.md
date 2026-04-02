---
name: ad-publishing-context-loader
version: "1.0"
description: Load CAA blueprint, CGA creative packages, APA personas, company model, and Meta credentials into unified AdPublishingContext (maps to SKL-APA33-01)
target_agents:
  - ad_publishing
triggers:
  - "ad publishing context"
  - "load publishing inputs"
  - "meta ads setup"
  - "publishing context loader"
priority: 10
max_tokens: 800
---

# Context Loader

## Purpose
Consolidate all upstream pipeline outputs required for Meta Ads publishing into a single AdPublishingContext object. This includes the Campaign Architecture Agent (CAA) blueprint, Creative Generation Agent (CGA) creative packages, APA audience personas, company profile data, and Meta Ads API credentials. The context loader validates that all mandatory prerequisites are present before any publishing operations begin.

## Methodology

### 1. Extract CAA Blueprint
Read `node_outputs.campaign_architecture` from pipeline state. Extract:
- Campaign hierarchy (campaigns, ad sets, ad unit briefs)
- Objective mapping per campaign (AWARENESS, TRAFFIC, ENGAGEMENT, LEADS, SALES)
- Budget allocations per ad set (daily/lifetime, currency)
- Funnel stage assignments (TOFU, MOFU, BOFU)
- Placement strategy (automatic vs manual, feed/stories/reels)
- Special Ad Category designation (HOUSING, CREDIT, EMPLOYMENT, or none)

### 2. Extract CGA Creative Packages
Read `node_outputs.creative_generation` from pipeline state. Extract:
- Generated ad images with GCS paths and aspect ratios (1:1, 9:16, 16:9)
- Ad copy variants per funnel stage (primary_text, headline, description, CTA)
- Creative-to-ad-set mapping from CGA assembly
- Compliance check results (Meta Ads policy pre-screening)

### 3. Extract APA Audience Personas
Read `node_outputs.audience_persona` from pipeline state. Extract:
- Persona profiles with demographics (age range, gender, location)
- Interest categories and behavioral signals
- Psychographic attributes for targeting enrichment
- Custom audience seed data (email lists, website visitors) if available

### 4. Extract Company Profile and Meta Credentials
From `input_context` and `tenant_context`:
- Company name, industry vertical, website URL
- Meta Ad Account ID (`act_XXXXXXX` format)
- Facebook Page ID for ad identity
- Business Manager ID (optional, for Business-level operations)
- Access token reference (encrypted, resolved at publish time)
- Sandbox vs production mode flag

### 5. Validate and Assemble AdPublishingContext
Perform prerequisite validation:
- FAIL if CAA blueprint is missing (hard dependency)
- FAIL if CGA creative packages are missing (nothing to publish)
- WARN if audience personas are absent (fall back to CAA targeting specs)
- FAIL if Meta Ad Account ID is not configured
- Compute context completeness score (0-1)

## Output Schema
Write to `node_outputs.apa_context` with keys:
- `context_id`: string (UUID)
- `brand_name`: string
- `caa_blueprint`: dict (full campaign hierarchy from CAA)
- `creative_packages`: list[dict] (image paths, copy variants, aspect ratios)
- `audience_personas`: list[dict] (persona profiles with targeting attributes)
- `meta_account`: dict (ad_account_id, page_id, business_id, sandbox_mode)
- `special_ad_category`: string | null (HOUSING, CREDIT, EMPLOYMENT)
- `budget_summary`: dict (total_budget, currency, allocation_strategy)
- `completeness_score`: float (0-1)
- `missing_inputs`: list[str]
- `validation_errors`: list[str]

## Integration Notes
- This is the first skill in the APA pipeline; all other APA skills depend on `apa_context`
- Meta credentials are validated by reference only here; actual API connectivity is checked in SKL-APA33-02 (account-validator)
- The `sandbox_mode` flag propagates through every downstream skill to prevent accidental production publishing during testing
