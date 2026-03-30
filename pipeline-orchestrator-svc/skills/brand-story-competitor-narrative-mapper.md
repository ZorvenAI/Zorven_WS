---
name: brand-story-competitor-narrative-mapper
version: "1.0"
description: Map competitor story archetypes and narrative strategies to identify narrative white space and differentiation opportunities (maps to SKL-BSA-05)
target_agents:
  - brand_story
triggers:
  - "competitor narratives"
  - "narrative white space"
  - "competitor stories"
  - "competitive narrative"
priority: 10
max_tokens: 500
---

# Competitor Narrative Mapper

## Purpose
Analyze competitor brand narratives (from CIA agent data) to map their story archetypes, identify saturated narrative territories, and reveal white space for differentiated brand storytelling.

## Methodology

### 1. Competitor Narrative Extraction
From WF1 context (CIA competitor intelligence):
- Extract competitor positioning statements and brand stories
- Identify competitor brand archetypes (hero, sage, rebel, etc.)
- Map competitor mission/vision themes

### 2. Archetype Saturation Analysis
- Count how many competitors use each archetype
- Identify "crowded" archetypes in the category
- Map the BPV-recommended archetype against competitor landscape

### 3. Narrative White Space Identification
- Find underused story angles in the category
- Identify emotional territories competitors haven't claimed
- Map differentiation opportunities for the brand story

## Output Schema
Write to `node_outputs.bsa_competitor_narratives` with keys:
- `competitor_archetypes`: list of `{competitor, archetype, narrative_theme, strength}`
- `archetype_saturation`: dict mapping archetype -> count in category
- `white_space`: list of `{narrative_angle, opportunity_score, rationale}`
- `differentiation_opportunities`: top 3 narrative differentiation strategies
- `avoid_zones`: narrative territories that are oversaturated

## Integration Notes
- Feeds into SKL-BSA-06 (Origin Story) for archetype differentiation
- Feeds into SKL-BSA-09 (Channel Narratives) for competitive positioning in messaging
- If CIA data is absent, produces minimal output focused on BPV archetype alone
