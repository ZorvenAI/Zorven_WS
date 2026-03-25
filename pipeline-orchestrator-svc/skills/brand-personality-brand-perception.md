---
name: brand-personality-brand-perception
version: "1.0"
description: Extract current brand perception signals from VoCA sentiment data and TCIA trend/cultural insights to identify perception gaps and personality opportunities (maps to SKL-BPV-02)
target_agents:
  - brand_personality
triggers:
  - "brand perception"
  - "perception analysis"
  - "brand sentiment"
  - "cultural perception"
  - "perception gap"
priority: 10
max_tokens: 500
---

# Brand Perception Analyzer

## Purpose
Synthesize VoCA sentiment analysis and TCIA trend/cultural insights to map how the brand is currently perceived in the market. This reveals the gap between current perception and desired personality, informing which traits to amplify, introduce, or suppress.

## Methodology

### 1. VoCA Perception Extraction
- Read `previous_outputs.voice_of_customer` for brand perception signals:
  - Brand attribute associations (what customers say the brand "is")
  - Sentiment polarity per attribute (positive/negative/neutral)
  - NPS drivers and detractors
  - Verbatim language patterns used to describe the brand
- Extract perceived personality traits from customer language (e.g., "reliable" maps to Competence, "fun" maps to Excitement)

### 2. TCIA Cultural Context
- Read `previous_outputs.trend_cultural` for cultural and trend signals:
  - Category cultural codes and conventions
  - Emerging cultural movements relevant to the brand's category
  - Cultural tension points the brand could address
  - Trend alignment opportunities
- If TCIA output is absent, log warning and proceed with VoCA-only perception

### 3. Perception-to-Personality Mapping
Map perceived brand attributes to Aaker's 5 dimensions:

| Perception Signal | Aaker Dimension | Direction |
|---|---|---|
| Reliable, dependable, efficient | Competence | Reinforce |
| Exciting, trendy, daring | Excitement | Reinforce |
| Honest, wholesome, cheerful | Sincerity | Reinforce |
| Glamorous, charming, smooth | Sophistication | Reinforce |
| Outdoorsy, tough, rugged | Ruggedness | Reinforce |
| Negative attribute associations | Any | Suppress or redirect |

### 4. Perception Gap Analysis
- Compare current perceived traits against the brand's stated identity (`input_context.company.brand_voice`)
- Compute a `perception_alignment` score (0-100): how closely current perception matches brand intent
- Identify perception gaps: traits the brand intends but customers do not perceive
- Identify perception surplus: traits customers perceive that the brand does not intend

### 5. Cultural Opportunity Scoring
For each Aaker dimension, score the cultural opportunity:
- **Cultural Relevance** (0-10): Is this trait aligned with current cultural movements?
- **Category Expectation** (0-10): Does the category reward this trait?
- **Differentiation Value** (0-10): Would this trait differentiate from competitors?

## Output Schema
Write to `node_outputs.bpv_brand_perception` with keys:
- `perceived_traits`: list of `{trait, aaker_dimension, sentiment, strength: float, source}`
- `perception_alignment`: int (0-100)
- `perception_gaps`: list of `{intended_trait, current_perception, gap_severity}`
- `perception_surplus`: list of `{perceived_trait, brand_intent, recommendation}`
- `cultural_opportunities`: list of `{aaker_dimension, cultural_relevance, category_expectation, differentiation_value, composite_score}`
- `cultural_tensions`: list of `{tension, opportunity, risk}`
- `data_quality`: `{voca_available: bool, tcia_available: bool, perception_signals_count: int}`

## Integration Notes
- Downstream consumers: SKL-BPV-05 (Aaker profiler uses perception gaps to adjust dimension scores), SKL-BPV-10 (character brief references perception alignment)
- If VoCA is absent, `perception_alignment` defaults to 50 (unknown) and perceived traits list is empty
- `perception_alignment` < 30 triggers an advisory in SKL-BPV-12 suggesting significant rebranding effort
