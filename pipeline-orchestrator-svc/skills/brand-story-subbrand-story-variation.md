---
name: brand-story-subbrand-story-variation
version: "1.0"
description: Generate sub-brand story variations based on BAA brand architecture hierarchy, maintaining parent narrative coherence while expressing sub-brand identity (maps to SKL-BSA-11)
target_agents:
  - brand_story
triggers:
  - "sub-brand story"
  - "sub brand narrative"
  - "brand hierarchy stories"
  - "portfolio narratives"
priority: 10
max_tokens: 500
---

# Sub-Brand Story Variation

## Purpose
Generate narrative variations for each sub-brand in the BAA architecture hierarchy. Each sub-brand story maintains coherence with the parent brand narrative while expressing its unique identity and audience.

## Methodology

### 1. Architecture Context
From BAA context (if available):
- Brand hierarchy (parent, sub-brands, endorsed brands)
- Architecture model (branded house, house of brands, endorsed, hybrid)
- Sub-brand positioning relative to parent
- Naming convention rules

### 2. Story Variation Strategy
Based on architecture model:
- **Branded House**: Sub-brand stories are chapters of the parent story (high coherence)
- **House of Brands**: Sub-brand stories are independent but share values (low coherence requirement)
- **Endorsed**: Sub-brand stories reference parent as credibility anchor (medium coherence)
- **Hybrid**: Mix of above based on sub-brand role

### 3. Per Sub-Brand Output
For each sub-brand:
- Relationship to parent narrative
- Narrative snippet (~100-200 words)
- Tone differentiation from parent
- Target audience specificity

## Output Schema
Contributes to Claude Call 2 prompt. Expected response structure:
- `subbrand_stories`: list of `{sub_brand, relationship_to_parent, narrative_snippet, tone_variation, target_audience}`

## Integration Notes
- Part of Claude Call 2 alongside SKL-BSA-09, SKL-BSA-10, SKL-BSA-12
- Only produces output when BAA architecture data is available
- If no BAA data, this skill is skipped and sub-brand stories are omitted
