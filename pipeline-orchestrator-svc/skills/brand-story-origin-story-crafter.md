---
name: brand-story-origin-story-crafter
version: "1.0"
description: Build structured Claude prompt for origin story generation in 3 versions (500/800/1500 words) using archetype, emotional arc, and cultural context (maps to SKL-BSA-06)
target_agents:
  - brand_story
triggers:
  - "origin story"
  - "brand origin"
  - "founding story"
  - "brand story creation"
priority: 10
max_tokens: 600
---

# Origin Story Crafter

## Purpose
Construct the system and user prompts for Claude Call 1 (narrative generation) focusing on the origin story. Produces 3 versions at different lengths (short ~500 words, medium ~800 words, long ~1500 words) with consistent archetype expression and emotional arc.

## Methodology

### 1. Input Assembly
Collect from upstream skills:
- SKL-BSA-01: Brand positioning, personality archetype, naming brief, company seeds
- SKL-BSA-02: Emotional arc (tension → transformation → resolution)
- SKL-BSA-03: Cultural narrative anchors (rising themes to weave in)
- SKL-BSA-04: Existing narrative analysis (refine vs. create from scratch)
- SKL-BSA-05: Competitor narrative white space (differentiation angles)

### 2. Prompt Construction
Build Claude prompt sections:

**Archetype Framework**:
- Primary archetype and its narrative patterns (hero's journey, sage's revelation, etc.)
- Secondary archetype blend rationale
- Archetype-specific vocabulary and metaphor domains

**Emotional Arc Integration**:
- Tension phase: founding problem, market pain, personal motivation
- Transformation phase: eureka moment, brand promise realization
- Resolution phase: aspirational future, customer impact, values activation

**Cultural Anchoring**:
- Weave 1-2 rising cultural themes naturally into the narrative
- Avoid fading cultural references

**Version Requirements**:
- Short (500 words): Elevator-ready, punchy, focuses on transformation moment
- Medium (800 words): Website about page, full arc with emotional depth
- Long (1500 words): Press kit / investor deck, detailed with proof points

### 3. Quality Criteria
Each version must include:
- `archetype_arc_alignment` score (0-1): How well the story follows the archetype pattern
- `emotional_resonance_score` (0-1): Emotional impact assessment
- `voice_consistency_score` (0-1): Alignment with BPV voice matrix

## Output Schema
Contributes to Claude Call 1 prompt. Expected response structure:
- `origin_story.archetype_used`: string
- `origin_story.emotional_arc`: string
- `origin_story.versions`: list of `{version_label, word_count, content, archetype_arc_alignment, emotional_resonance_score, voice_consistency_score}`

## Integration Notes
- This is the largest creative output of the BSA agent
- Part of Claude Call 1 alongside SKL-BSA-07 and SKL-BSA-08
- Uses Claude Sonnet 4 via the BSA agent's configured LLM client
