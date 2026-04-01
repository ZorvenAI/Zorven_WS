---
name: creative-gen-context-loader
version: "1.0"
description: Consolidate CAA blueprint + WF1+WF2+Company data into unified CampaignCreativeContext for downstream creative generation (maps to SKL-CGA-01)
target_agents:
  - creative_generation
triggers:
  - "creative context"
  - "campaign context"
  - "load creative inputs"
  - "creative generation setup"
priority: 10
max_tokens: 800
---

# Context Loader

## Purpose
Consolidate the Campaign Architecture Agent (CAA) blueprint output with Workflow 1 (discovery, market research, competitor intel, audience personas, trends, VoC) and Workflow 2 (brand positioning, architecture, personality, naming, story) outputs plus company profile data into a single CampaignCreativeContext object. This unified context drives all downstream creative generation skills.

## Methodology

### 1. Extract CAA Blueprint
Read `node_outputs.campaign_architecture` from the pipeline state. Extract:
- Campaign hierarchy (campaigns, ad sets, ad briefs)
- Funnel stage mapping (TOFU, MOFU, BOFU)
- Audience targeting specifications per ad set
- Budget allocations and objective mapping
- Placement strategy

### 2. Extract WF1 Intelligence
Pull upstream WF1 node outputs:
- `node_outputs.discovery` -- brand research findings, industry context
- `node_outputs.market_research` -- TAM/SAM/SOM, market sizing
- `node_outputs.competitor_intel` -- competitor creative patterns, SWOT
- `node_outputs.audience_persona` -- persona profiles, demographics, psychographics
- `node_outputs.trend_cultural` -- cultural trends, seasonal context
- `node_outputs.voice_of_customer` -- sentiment themes, customer language patterns

### 3. Extract WF2 Brand Identity
Pull upstream WF2 node outputs:
- `node_outputs.brand_positioning` -- differentiation, perceptual map position
- `node_outputs.brand_architecture` -- brand hierarchy, sub-brand relationships
- `node_outputs.brand_personality` -- Aaker 5D scores, archetypes, voice matrix
- `node_outputs.brand_naming` -- approved name, tagline
- `node_outputs.brand_story` -- origin narrative, mission/vision, elevator pitch

### 4. Extract Company Profile
From `input_context`:
- Company name, industry, website URL
- Logo and brand asset references (GCS paths)
- Brand color palette, typography preferences
- Existing brand guidelines (if available)

### 5. Assemble CampaignCreativeContext
Merge all sources into a normalized context object with validation:
- Flag missing required fields (CAA blueprint is mandatory)
- Mark optional enrichments as present/absent
- Compute context completeness score (0-1)

## Output Schema
Write to `node_outputs.cga_context` with keys:
- `context_id`: string (UUID)
- `brand_name`: string
- `brand_identity`: dict (personality, voice, colors, typography, tagline)
- `audience_profiles`: list of audience dicts from CAA + persona enrichment
- `funnel_stages`: list of funnel stage configs with objectives
- `campaign_hierarchy`: dict (campaigns, ad sets, briefs from CAA)
- `competitor_creative_patterns`: list (from competitor intel)
- `customer_language`: dict (sentiment themes, phrases from VoC)
- `cultural_context`: dict (trends, seasonal factors)
- `company_profile`: dict (name, industry, assets)
- `completeness_score`: float (0-1)
- `missing_inputs`: list[str]

## Integration Notes
- This is the first skill in the CGA pipeline; all other CGA skills depend on it
- CAA blueprint is required; WF1/WF2 outputs gracefully degrade if absent
- Completeness score propagates to final package confidence scoring in SKL-CGA-12
- Brand color palette feeds directly into SKL-CGA-04 image prompt construction
