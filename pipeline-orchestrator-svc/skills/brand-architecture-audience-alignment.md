---
name: brand-architecture-audience-alignment
version: "1.0"
description: Align APA + VoCA audience personas with brand architecture needs — segment-to-brand mapping, complexity tolerance, navigation expectations (maps to SKL-BAA-02)
target_agents:
  - brand_architecture
triggers:
  - "audience alignment"
  - "persona architecture"
  - "audience brand mapping"
  - "segment alignment"
  - "portfolio audience"
priority: 9
max_tokens: 500
---

# Audience Architecture Alignment

## Purpose
Synthesize Audience Persona Agent (APA) persona profiles and Voice of Customer Agent (VoCA) sentiment data to determine how the target audience segments map to brand architecture requirements. This informs whether the portfolio needs distinct brands per segment or a unified master brand.

## Methodology

### 1. Persona Ingestion
- Read `previous_outputs.audience_persona` for persona segments (demographics, psychographics, jobs-to-be-done, pain points, purchase drivers)
- Read `previous_outputs.voice_of_customer` for sentiment themes, brand perception clusters, and confusion signals
- If either upstream is absent, log a warning and proceed with available data only

### 2. Segment-to-Brand Affinity Mapping
For each persona segment, assess brand architecture preferences:

| Dimension | Question | Scoring |
|-----------|----------|---------|
| **Complexity Tolerance** | How many brands can this segment track? | 0-100 (100 = high tolerance for many brands) |
| **Parent Brand Reliance** | Does this segment value corporate endorsement? | 0-100 (100 = strong preference for parent brand visibility) |
| **Category Crossing** | Does this segment buy across multiple product categories? | 0-100 (100 = broad cross-category buyer) |
| **Brand Loyalty Depth** | Is loyalty tied to the master brand or individual product? | "master" or "product" or "mixed" |
| **Navigation Expectation** | Does this segment expect a single brand experience or distinct ones? | "unified" or "distinct" or "flexible" |

### 3. Segment Clustering for Architecture
- Group persona segments by their architecture preference profile using the dimensions above
- Identify whether segments naturally cluster into:
  - **Single-brand segments**: All segments prefer unified experience (favors Branded House)
  - **Multi-brand segments**: Segments have divergent preferences (favors House of Brands or Endorsed)
  - **Tiered segments**: Segments align by price/prestige tier (favors Sub-Brand or Endorsed)

### 4. VoCA Confusion Signals
- Extract VoCA themes related to brand confusion, portfolio navigation, or brand misattribution
- Score the current portfolio's **clarity deficit** (0-100): how much audience confusion exists
- Identify specific confusion hotspots (product pairs confused, brand attributions misplaced)

### 5. Architecture Model Affinity Scoring
Based on audience data, score each architecture model's fit with the audience:
- **Branded House**: High if segments prefer unified experience, low complexity tolerance variance
- **House of Brands**: High if segments are divergent, distinct category needs
- **Endorsed**: High if segments value parent credibility but want product distinctness
- **Hybrid**: High if segment clusters are mixed
- **Sub-Brand**: High if segments are tiered by value proposition within same category
- Each score is 0-25, representing the audience fit dimension of the model recommender

## Output Schema
Write to `node_outputs.baa_audience_alignment` with keys:
- `segment_profiles`: list of `{persona_name, complexity_tolerance, parent_brand_reliance, category_crossing, loyalty_depth, navigation_expectation}`
- `segment_clusters`: list of `{cluster_label, personas[], architecture_preference}`
- `clarity_deficit`: `{score: int, confusion_hotspots: [{product_pair, misattribution_type, frequency}]}`
- `model_audience_scores`: `{branded_house: int, house_of_brands: int, endorsed: int, hybrid: int, sub_brand: int}`
- `data_quality`: `{apa_available: bool, voca_available: bool, personas_analyzed: int, coverage_pct: float}`

## Integration Notes
- Downstream consumers: SKL-BAA-06 (model recommender uses `model_audience_scores` as the audience fit dimension), SKL-BAA-07 (hierarchy builder uses segment-to-brand mapping)
- If both APA and VoCA are absent, emit all scores as 50 (neutral) and flag `data_quality.coverage_pct: 0`
