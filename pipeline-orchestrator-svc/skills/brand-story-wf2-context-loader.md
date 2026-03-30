---
name: brand-story-wf2-context-loader
version: "1.0"
description: Load full WF2 strategy context from all prior agents (BPA positioning, BAA architecture, BPV personality, NTA naming) plus Company seeds and WF1 discovery data (maps to SKL-BSA-01)
target_agents:
  - brand_story
triggers:
  - "wf2 context"
  - "strategy context"
  - "load prior agents"
  - "brand strategy context"
priority: 10
max_tokens: 600
---

# WF2 Strategy Context Loader

## Purpose
Consolidate all upstream WF2 agent outputs into a unified strategy context object that downstream BSA skills can reference. This is the foundation for narrative generation — every subsequent skill depends on this context.

## Methodology

### 1. Parallel Context Retrieval
Load 5 context sources via HTTP in parallel:
- **WF1 Discovery** (`GET /api/v1/analytics/wf1-context/`): Market research, competitor intel, audience personas, trend insights, VoC analysis
- **BPA Positioning** (`GET /api/v1/analytics/bpa-context/`): Recommended positioning, candidates, canvas, perceptual maps, differentiation
- **BPV Personality** (`GET /api/v1/analytics/bpv-context/`): Aaker 5D profile, archetypes, values hierarchy, voice matrix, emotional map
- **NTA Naming** (`GET /api/v1/analytics/nta-context/`): Shortlisted names, taglines, naming brief, availability results
- **Company Model** (`GET /api/v1/analytics/company-context/`): Company seeds (name, industry, description, mission, vision, founding story)

Optional: BAA Architecture via `brand-context-options/` endpoint.

### 2. Prerequisite Validation
- REQUIRED: WF1, BPA, BPV, NTA, Company — if any missing, emit EVT-BSA-014 (PREREQUISITE_MISSING)
- RECOMMENDED: BAA — if missing, proceed with reduced sub-brand capability

### 3. Context Assembly
Build unified `wf2_strategy_context` dict:
- `positioning`: BPA recommended positioning statement + key differentiators
- `architecture`: BAA hierarchy model + sub-brands (if available)
- `personality`: BPV primary archetype + voice matrix + emotional map
- `naming`: NTA recommended name + tagline + naming brief
- `discovery`: WF1 key insights (audience emotional drivers, competitor narratives, cultural trends)
- `company`: Company seeds (founding year, industry, existing mission/vision)

## Output Schema
Write to `node_outputs.bsa_wf2_context` with keys:
- `positioning`: dict (statement, differentiators, canvas_summary)
- `architecture`: dict | null (model, sub_brands, hierarchy)
- `personality`: dict (archetype, voice_matrix, emotional_map, values)
- `naming`: dict (recommended_name, tagline, naming_brief)
- `discovery`: dict (audience, competitors, trends, voc)
- `company`: dict (name, industry, description, mission, vision, founding_story)
- `context_completeness`: float (0-1, fraction of available contexts)
- `missing_contexts`: list[str]

## Integration Notes
- This is the first skill executed in the BSA pipeline
- All subsequent skills (SKL-BSA-02 through SKL-BSA-14) depend on this context
- Context loading is fail-open: missing optional data reduces output quality but does not block execution
