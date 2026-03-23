---
name: brand-positioning-audience-needs
version: "1.0"
description: Synthesize APA personas and VoCA themes into needs hierarchy — table-stakes, differentiators, delighters (maps to SKL-BPA-02)
target_agents:
  - brand_positioning
triggers:
  - "audience needs"
  - "needs hierarchy"
  - "table stakes"
  - "differentiators"
  - "delighters"
  - "persona needs"
priority: 9
max_tokens: 500
---

# Audience Needs Synthesis

## Purpose
Merge Audience Persona Agent (APA) persona profiles with Voice of Customer Agent (VoCA) sentiment themes to produce a Kano-model-inspired needs hierarchy that informs positioning statement generation.

## Methodology

### 1. Persona Ingestion
- Read `previous_outputs.audience_persona` for persona segments (demographics, psychographics, jobs-to-be-done, pain points, goals)
- Read `previous_outputs.voice_of_customer` for theme clusters, sentiment distributions, and pain point priority matrix
- If either upstream is absent, log a warning and proceed with available data only

### 2. Cross-Reference Mapping
- For each APA persona, match VoCA themes by keyword overlap and semantic similarity
- Tag each theme-persona pair with sentiment polarity and frequency weight
- Identify orphan themes (VoCA themes not mapped to any persona) and flag for review

### 3. Kano Classification
Classify every identified need into one of three tiers:

| Tier | Definition | Signal |
|------|-----------|--------|
| **Table-Stakes** | Must-have; absence causes dissatisfaction, presence does not delight | High frequency + negative sentiment when missing |
| **Differentiators** | Performance drivers; more is better, linearly correlated with satisfaction | Moderate frequency + positive correlation with NPS |
| **Delighters** | Unexpected value; absence is tolerated, presence creates outsized loyalty | Low frequency + high positive sentiment spike |

### 4. Priority Scoring
For each need, compute a composite priority score:
- `frequency_weight` (0-1): Proportion of VoCA mentions across total feedback
- `sentiment_impact` (0-1): Absolute sentiment swing when need is met vs. unmet
- `persona_breadth` (0-1): Fraction of personas affected
- `competitive_gap` (0-1): Degree to which competitors under-serve this need (from CIA data if available)
- **Composite** = 0.3 * frequency + 0.25 * sentiment + 0.25 * breadth + 0.2 * gap

### 5. Needs Hierarchy Output
- Group needs by tier, sorted by composite score descending within each tier
- Include top 3 representative VoCA quotes per need (anonymized, SHA-256 hashed identifiers)
- Map each need to the personas it most strongly affects

## Output Schema
Write to `node_outputs.bpa_audience_needs` with keys:
- `table_stakes`: list of `{need, composite_score, personas[], quotes[], competitive_gap}`
- `differentiators`: list of same structure
- `delighters`: list of same structure
- `orphan_themes`: list of `{theme, sentiment, frequency}` (unmapped VoCA themes)
- `data_quality`: `{apa_available: bool, voca_available: bool, coverage_pct: float}`

## Integration Notes
- Downstream consumers: SKL-BPA-06 (statement generator uses differentiators as positioning fuel), SKL-BPA-07 (value proposition canvas maps needs to pain relievers/gain creators)
