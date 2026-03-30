---
name: campaign-arch-strategy-context-loader
version: "1.0"
description: Load and consolidate WF1 analytics, WF2 brand strategy, and Company model into unified campaign strategy context; assess brand maturity for funnel allocation (maps to SKL-CAA-01)
target_agents:
  - campaign_architecture
triggers:
  - "campaign context"
  - "strategy context"
  - "load brand strategy"
  - "campaign strategy loader"
priority: 10
max_tokens: 600
---

# Strategy Context Loader

## Purpose
Consolidate all upstream WF1 and WF2 agent outputs into a unified campaign strategy context that downstream CAA skills reference. This is the foundation for campaign architecture — every subsequent skill depends on this context.

## Methodology

### 1. Parallel Context Retrieval
Load context sources via HTTP in parallel:
- **WF1 Discovery** (`GET /api/v1/analytics/wf1-context/`): Market research, competitor intel, audience personas, trend insights, VoC analysis
- **BPA Positioning** (`GET /api/v1/analytics/bpa-context/`): Recommended positioning, candidates, canvas, perceptual maps, differentiation
- **BAA Architecture** (`GET /api/v1/analytics/baa-context/`): Hierarchy model, sub-brands, portfolio structure
- **BPV Personality** (`GET /api/v1/analytics/bpv-context/`): Aaker 5D profile, archetypes, values hierarchy, voice matrix, emotional map
- **NTA Naming** (`GET /api/v1/analytics/nta-context/`): Shortlisted names, taglines, naming brief, availability results
- **BSA Story** (`GET /api/v1/analytics/bsa-context/`): Origin story, mission/vision, pitches, channel narratives, style guide
- **Company Model** (`GET /api/v1/analytics/company-context/`): Company seeds (name, industry, description, mission, vision, founding story)

### 2. Prerequisite Validation
- REQUIRED: WF1 (audience personas, competitor intel), BPA (positioning), BPV (personality/voice), Company — if any missing, emit EVT-CAA-001 (PREREQUISITE_MISSING)
- RECOMMENDED: BAA, NTA, BSA — if missing, proceed with reduced campaign personalization capability

### 3. Brand Maturity Assessment
Classify brand maturity for funnel budget allocation:
- **New** (0-6 months, no market presence): 60% TOFU / 25% MOFU / 10% BOFU / 5% Retention
- **Emerging** (6-24 months, growing awareness): 40% TOFU / 30% MOFU / 20% BOFU / 10% Retention
- **Established** (24+ months, strong recognition): 20% TOFU / 25% MOFU / 35% BOFU / 20% Retention

Maturity signals: company founding date, existing customer base, brand recognition scores from WF1, prior campaign history from RAG.

### 4. Context Assembly
Build unified `campaign_strategy_context` dict combining all upstream data with maturity classification.

## Output Schema
Write to `node_outputs.caa_strategy_context` with keys:
- `positioning`: dict (statement, differentiators, canvas_summary)
- `architecture`: dict | null (model, sub_brands, hierarchy)
- `personality`: dict (archetype, voice_matrix, emotional_map, values)
- `naming`: dict (recommended_name, tagline)
- `story`: dict | null (origin_story_short, mission, vision, pitches)
- `discovery`: dict (audience_personas, competitors, trends, voc)
- `company`: dict (name, industry, description, mission, vision)
- `brand_maturity`: "new" | "emerging" | "established"
- `funnel_allocation`: dict (tofu, mofu, bofu, retention — percentages)
- `context_completeness`: float (0-1, fraction of available contexts)
- `missing_contexts`: list[str]

## Integration Notes
- This is the first skill executed in the CAA pipeline
- All subsequent skills (SKL-CAA-02 through SKL-CAA-12) depend on this context
- Context loading is fail-open: missing optional data reduces output quality but does not block execution
