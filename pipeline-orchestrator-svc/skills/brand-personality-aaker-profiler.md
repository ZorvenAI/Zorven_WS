---
name: brand-personality-aaker-profiler
version: "1.0"
description: Validate and normalize Aaker 5-dimension personality scores, identify primary and secondary dimensions, and compute profile confidence (maps to SKL-BPV-05)
target_agents:
  - brand_personality
triggers:
  - "aaker profiler"
  - "personality dimensions"
  - "aaker scores"
  - "five dimensions"
  - "personality profile"
priority: 10
max_tokens: 600
---

# Aaker 5D Personality Profiler

## Purpose
Produce the definitive Aaker 5-dimension personality profile by synthesizing founder intent (seed weights), audience psychology (trait affinity), and brand perception (perception gaps). This is the central analytical skill of the Brand Personality Agent — all downstream personality artifacts derive from this profile.

## Methodology

### 1. Input Collection
Collect and validate upstream skill outputs:
- SKL-BPV-03 `bpv_identity_seed`: Seed weights from brand voice/values (required)
- SKL-BPV-01 `bpv_audience_psychology`: Audience trait affinities (enriching)
- SKL-BPV-02 `bpv_brand_perception`: Perception gaps and cultural opportunities (enriching)
- SKL-BPV-04 `bpv_rag_context`: Prior personality profile for continuity (enriching)

If seed weights are absent, trigger SKL-BPV-12 and use uniform weights (0.2 each).

### 2. Weighted Score Computation
Compute each Aaker dimension score (0-100) using a weighted blend:

| Input Source | Weight | Rationale |
|---|---|---|
| Seed weights (SKL-BPV-03) | 30% | Founder intent anchor |
| Audience trait affinity (SKL-BPV-01) | 30% | Audience resonance |
| Perception gap adjustment (SKL-BPV-02) | 25% | Market reality correction |
| Prior personality (SKL-BPV-04) | 15% | Historical continuity |

If enriching inputs are absent, redistribute their weight proportionally to available sources.

### 3. Dimension Scoring
For each of the 5 dimensions (Sincerity, Excitement, Competence, Sophistication, Ruggedness):
- Scale the blended weight to 0-100
- Apply perception gap adjustment: boost underperceived intended traits, dampen unintended perceived traits
- Apply cultural opportunity bonus: +5 to dimensions with high cultural relevance (from SKL-BPV-02)
- Clamp final scores to 0-100 range

### 4. Profile Normalization
- Ensure scores reflect a differentiated profile (not all dimensions equal)
- If standard deviation across dimensions < 10, amplify the top 2 dimensions by 15% and suppress the bottom 2 by 10%
- Re-clamp to 0-100 after amplification

### 5. Primary/Secondary Identification
- **Primary Dimension**: Highest-scoring dimension (the dominant personality trait)
- **Secondary Dimension**: Second-highest dimension (the supporting personality trait)
- **Dormant Dimensions**: Dimensions scoring below 30 (intentionally deprioritized)
- Compute `profile_differentiation`: standard deviation of the 5 scores (higher = more distinctive)

### 6. Sub-Trait Decomposition
For the primary and secondary dimensions, decompose into Aaker sub-traits:
- Sincerity: down-to-earth, honest, wholesome, cheerful
- Excitement: daring, spirited, imaginative, up-to-date
- Competence: reliable, intelligent, successful
- Sophistication: upper-class, charming
- Ruggedness: outdoorsy, tough

### 7. Profile Confidence
Compute confidence (0.0-1.0):
- `data_breadth` (0.3): How many input sources contributed
- `score_clarity` (0.3): Profile differentiation (std dev / 30, capped at 1.0)
- `intent_alignment` (0.2): Correlation between seed weights and final scores
- `perception_grounding` (0.2): Whether perception data was available to validate

## Output Schema
Write to `node_outputs.bpv_aaker_profile` with keys:
- `dimensions`: `{sincerity: int, excitement: int, competence: int, sophistication: int, ruggedness: int}`
- `primary_dimension`: str
- `secondary_dimension`: str
- `dormant_dimensions`: list of str
- `sub_traits`: `{primary: {dimension, traits: [{name, score}]}, secondary: {dimension, traits: [{name, score}]}}`
- `profile_differentiation`: float
- `confidence`: float (0.0-1.0)
- `confidence_breakdown`: `{data_breadth, score_clarity, intent_alignment, perception_grounding}`
- `weight_contributions`: `{seed_weight, audience_weight, perception_weight, rag_weight}`
- `data_completeness`: `{required_present: int, required_total: int, enriching_present: int, enriching_total: int}`

## Integration Notes
- This is the central decision skill; its output drives SKL-BPV-06 (archetype selector), SKL-BPV-07 (values hierarchy), SKL-BPV-08 (emotional mapper), SKL-BPV-09 (voice matrix)
- `confidence` < 0.5 triggers a warning escalation in SKL-BPV-12
- PG-07 sub-brand constraint (applied post-Claude in BPVAnalyzer) may clamp sub-brand dimension deviations to +/-20 from parent
