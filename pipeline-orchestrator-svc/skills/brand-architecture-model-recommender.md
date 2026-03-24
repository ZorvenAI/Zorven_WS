---
name: brand-architecture-model-recommender
version: "1.0"
description: Score 5 architecture models across 4 dimensions (positioning alignment, audience fit, competitive differentiation, operational efficiency) each 0-25 for total 0-100 (maps to SKL-BAA-06)
target_agents:
  - brand_architecture
triggers:
  - "model recommendation"
  - "architecture model"
  - "architecture scoring"
  - "brand structure recommendation"
  - "portfolio model"
priority: 10
max_tokens: 600
---

# Architecture Model Recommender

## Purpose
Evaluate five canonical brand architecture models against four strategic dimensions, producing a weighted scoring matrix that drives the architecture recommendation. This is the central analytical skill of the Brand Architecture Agent.

## Methodology

### 1. Input Validation
Verify upstream skill outputs are present. Required inputs:
- SKL-BAA-03: `baa_portfolio` (current portfolio baseline)
- SKL-BAA-04: `baa_positioning_context` (positioning alignment scores)

Enriching inputs (used when available):
- SKL-BAA-01: `baa_competitor_architecture` (competitive differentiation scores)
- SKL-BAA-02: `baa_audience_alignment` (audience fit scores)
- SKL-BAA-05: `baa_rag_context` (prior architecture for continuity scoring)

Log warnings for missing optional inputs. If required inputs are absent, trigger SKL-BAA-12.

### 2. Architecture Models Under Evaluation

| Model | Description | Best Suited For |
|-------|-------------|----------------|
| **Branded House** | Single master brand across all offerings | Strong parent brand, unified audience, operational simplicity |
| **House of Brands** | Independent brands with distinct identities | Diverse audiences, risk isolation, M&A portfolios |
| **Endorsed** | Sub-brands visibly backed by parent | Parent credibility + product flexibility, tiered markets |
| **Hybrid** | Mix of endorsed, sub-branded, and independent | Complex portfolios, multiple categories, transitional states |
| **Sub-Brand** | Master brand + descriptive modifier | Category extensions, tiered offerings, brand stretching |

### 3. Scoring Matrix (4 Dimensions x 0-25 Each)

**Dimension 1: Positioning Alignment (0-25)**
- Source: SKL-BAA-04 `model_positioning_scores` (scaled from 0-25)
- Evaluates how well each model reinforces the brand's positioning strategy
- If BPA unavailable, use neutral score of 12 for all models

**Dimension 2: Audience Fit (0-25)**
- Source: SKL-BAA-02 `model_audience_scores` (scaled from 0-25)
- Evaluates how well each model serves the audience segment structure
- If APA/VoCA unavailable, use neutral score of 12 for all models

**Dimension 3: Competitive Differentiation (0-25)**
- Source: SKL-BAA-01 `differentiation_ranking`
- Transform competitive differentiation composite score to 0-25 scale
- Models used by fewer competitors score higher (structural white-space premium)
- If CIA unavailable, use neutral score of 12 for all models

**Dimension 4: Operational Efficiency (0-25)**
- Computed from SKL-BAA-03 `baa_portfolio`:
  - **Migration Cost** (0-10): How much structural change is needed from current state
  - **Management Overhead** (0-10): Ongoing cost of maintaining this architecture
  - **Scalability** (0-5): How well the model accommodates future portfolio growth
- Scoring heuristics:
  - Branded House: Low migration if already unified, low overhead, moderate scalability
  - House of Brands: High migration cost from unified, high overhead, high scalability
  - Endorsed: Moderate migration, moderate overhead, good scalability
  - Hybrid: Variable migration, highest management overhead, highest scalability
  - Sub-Brand: Low-to-moderate migration, low overhead, moderate scalability

### 4. Composite Scoring
For each model:
```
total_score = positioning_alignment + audience_fit + competitive_differentiation + operational_efficiency
```
- Maximum possible: 100 (25 per dimension)
- Minimum meaningful: 0

### 5. Recommendation Logic
- Rank models by `total_score` descending
- Recommend the top-scoring model as the primary recommendation
- If the top two models are within 5 points, recommend both as viable and flag for human consideration
- If the recommended model differs from the current architecture (from SKL-BAA-03), compute a `transition_magnitude` score (0-100)
- Include a rationale narrative explaining why the recommended model scored highest

### 6. Sensitivity Analysis
- Re-run scoring with each dimension weight doubled (one at a time) to test robustness
- Flag if the recommendation changes under any sensitivity scenario
- Report the recommendation as "robust" if it holds across all scenarios, "conditional" otherwise

## Output Schema
Write to `node_outputs.baa_model_recommendation` with keys:
- `scoring_matrix`: list of `{model, positioning_alignment, audience_fit, competitive_differentiation, operational_efficiency, total_score}`
- `recommended_model`: str
- `runner_up_model`: str
- `recommendation_confidence`: "robust" | "conditional"
- `score_gap`: float (difference between top two models)
- `rationale`: str (150-250 word narrative)
- `transition_magnitude`: int (0-100, 0 if recommended model matches current)
- `current_model`: str or "undefined"
- `sensitivity_analysis`: list of `{scenario, recommended_model, score_change}`
- `data_completeness`: `{required_present: int, required_total: int, optional_present: int, optional_total: int}`

## Integration Notes
- This is the central decision skill; its output drives SKL-BAA-07 (hierarchy builder) and SKL-BAA-08 (naming designer)
- `score_gap` < 5 triggers an advisory escalation in SKL-BAA-12
- `transition_magnitude` > 70 triggers a warning escalation in SKL-BAA-12
- SKL-BAA-10 (strategy synthesis) uses the scoring matrix in its executive summary
