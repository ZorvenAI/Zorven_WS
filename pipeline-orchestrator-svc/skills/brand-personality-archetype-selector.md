---
name: brand-personality-archetype-selector
version: "1.0"
description: Select and validate a Jungian archetype from the 12 canonical archetypes based on Aaker profile alignment, audience resonance, and competitive differentiation (maps to SKL-BPV-06)
target_agents:
  - brand_personality
triggers:
  - "archetype selector"
  - "jungian archetype"
  - "brand archetype"
  - "archetype selection"
  - "personality archetype"
priority: 9
max_tokens: 500
---

# Jungian Archetype Selector

## Purpose
Map the Aaker 5D personality profile to one of the 12 Jungian brand archetypes. The archetype provides a narrative framework that makes the personality profile actionable — it guides storytelling, visual identity, and customer relationship dynamics.

## Methodology

### 1. Input Collection
- Read SKL-BPV-05 `bpv_aaker_profile` for the validated Aaker dimension scores (required)
- Read SKL-BPV-01 `bpv_audience_psychology` for audience emotional targets (enriching)
- Read SKL-BPV-02 `bpv_brand_perception` for competitive differentiation context (enriching)
- If Aaker profile is absent, trigger SKL-BPV-12 and abort archetype selection

### 2. The 12 Jungian Archetypes

| Archetype | Core Desire | Aaker Alignment |
|---|---|---|
| **Innocent** | Safety, happiness | Sincerity (high), Competence (low) |
| **Sage** | Knowledge, truth | Competence (high), Sincerity (moderate) |
| **Explorer** | Freedom, discovery | Excitement (high), Ruggedness (moderate) |
| **Outlaw** | Liberation, revolution | Excitement (high), Ruggedness (high) |
| **Magician** | Transformation, vision | Excitement (high), Sophistication (moderate) |
| **Hero** | Mastery, courage | Competence (high), Ruggedness (moderate) |
| **Lover** | Intimacy, passion | Sophistication (high), Sincerity (moderate) |
| **Jester** | Joy, spontaneity | Excitement (high), Sincerity (moderate) |
| **Everyman** | Belonging, connection | Sincerity (high), Ruggedness (low) |
| **Caregiver** | Service, protection | Sincerity (high), Competence (moderate) |
| **Ruler** | Control, authority | Competence (high), Sophistication (high) |
| **Creator** | Innovation, expression | Excitement (moderate), Sophistication (moderate) |

### 3. Archetype Scoring
For each archetype, compute a fit score (0-100) across three dimensions:

**Aaker Alignment (0-40)**:
- Compare the archetype's expected Aaker profile against the actual profile
- Use cosine similarity between archetype template vector and actual dimension vector
- Scale to 0-40

**Audience Resonance (0-30)**:
- Match archetype's core desire against audience emotional targets (SKL-BPV-01)
- Score higher if the archetype's narrative aligns with audience motivations
- If audience data unavailable, use neutral score of 15

**Differentiation Potential (0-30)**:
- Assess how distinctive this archetype is in the competitive landscape
- Archetypes overused in the category score lower
- If competitive data unavailable, use neutral score of 15

### 4. Selection Logic
- Rank archetypes by composite fit score
- Select the top-scoring archetype as the primary recommendation
- If top two archetypes are within 5 points, flag as a close call for human consideration
- Include the runner-up archetype for comparison

### 5. Archetype Narrative
For the selected archetype, generate:
- **Brand motto**: A concise phrase capturing the archetype's essence for this brand
- **Relationship dynamic**: How this archetype relates to customers (e.g., mentor, companion, challenger)
- **Story arc**: The narrative structure this archetype implies (e.g., quest, transformation, belonging)
- **Shadow traits**: Negative expressions of the archetype to avoid

## Output Schema
Write to `node_outputs.bpv_archetype` with keys:
- `selected_archetype`: str (one of the 12 archetypes)
- `runner_up_archetype`: str
- `archetype_scores`: list of `{archetype, aaker_alignment, audience_resonance, differentiation_potential, total_score}`
- `score_gap`: float (difference between top two archetypes)
- `narrative`: `{brand_motto, relationship_dynamic, story_arc, shadow_traits: []}`
- `selection_confidence`: "strong" | "close_call"
- `rationale`: str (100-200 word explanation)

## Integration Notes
- Downstream consumers: SKL-BPV-10 (character brief uses archetype narrative), SKL-BPV-09 (voice matrix uses archetype relationship dynamic)
- `score_gap` < 5 triggers an advisory in SKL-BPV-12
- The archetype is a narrative tool, not a constraint — it should inform but not override the Aaker profile
