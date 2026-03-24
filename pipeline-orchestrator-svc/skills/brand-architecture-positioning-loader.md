---
name: brand-architecture-positioning-loader
version: "1.0"
description: Load BPA positioning strategy as architecture input — positioning statement, differentiation, value proposition alignment (maps to SKL-BAA-04)
target_agents:
  - brand_architecture
triggers:
  - "positioning loader"
  - "positioning input"
  - "brand positioning context"
  - "positioning strategy input"
  - "positioning alignment"
priority: 10
max_tokens: 400
---

# Positioning Strategy Loader

## Purpose
Ingest the Brand Positioning Agent (BPA) output to anchor architecture decisions in the established positioning strategy. Architecture must reinforce, not contradict, the brand's positioning. This skill ensures structural decisions align with strategic intent.

## Methodology

### 1. BPA Output Ingestion
- Read `previous_outputs.brand_positioning` for the complete positioning strategy:
  - Recommended positioning statement
  - Framework used (e.g., Ries & Trout, Aaker, Kapferer)
  - Strategy confidence score
  - Value proposition canvas (jobs, pains, gains, fit scores)
  - Differentiation architecture (POPs, PODs, RTBs)
  - Perceptual maps (current and target positions)
- If BPA output is absent, log warning and proceed with reduced confidence

### 2. Positioning Constraint Extraction
Derive architecture constraints from the positioning strategy:

| Constraint | Source | Architecture Impact |
|-----------|--------|-------------------|
| **Brand Promise** | Positioning statement | All brands in portfolio must deliver on or complement this promise |
| **Differentiation Pillars** | PODs from BPA | Architecture must protect and amplify these differentiators |
| **Table-Stakes** | POPs from BPA | Every customer-facing brand must meet these minimums |
| **Target Position** | Perceptual maps | Architecture should enable migration toward target position |
| **Value Proposition** | Value canvas | Portfolio structure should not dilute the core value proposition |

### 3. Positioning-Architecture Alignment Scoring
Score each architecture model for alignment with the positioning strategy:
- **Branded House**: High if positioning centers on a single, strong brand promise; low if positioning requires distinct identities per segment
- **House of Brands**: High if positioning allows diverse value propositions; low if brand equity concentration matters
- **Endorsed**: High if positioning benefits from parent credibility with product flexibility
- **Hybrid**: High if positioning strategy has tiered elements
- **Sub-Brand**: High if positioning uses a strong master with targeted extensions
- Each score is 0-25, representing the positioning alignment dimension of the model recommender

### 4. Conflict Detection
- Identify potential conflicts between the positioning strategy and current portfolio structure
- Flag brands/products whose positioning contradicts the master brand positioning
- Compute a `positioning_misalignment_score` (0-100): higher values indicate greater conflict

## Output Schema
Write to `node_outputs.baa_positioning_context` with keys:
- `positioning_statement`: str or null
- `positioning_framework`: str or null
- `positioning_confidence`: float (0-100) or null
- `constraints`: list of `{type, description, source_field, impact}`
- `model_positioning_scores`: `{branded_house: int, house_of_brands: int, endorsed: int, hybrid: int, sub_brand: int}`
- `positioning_misalignment_score`: int (0-100)
- `conflicts`: list of `{brand_name, conflict_description, severity: "low"|"medium"|"high"}`
- `data_quality`: `{bpa_available: bool, positioning_complete: bool, fields_present: int, fields_total: int}`

## Integration Notes
- Downstream consumers: SKL-BAA-06 (model recommender uses `model_positioning_scores` as the positioning alignment dimension), SKL-BAA-10 (strategy synthesis references positioning constraints)
- If BPA output is absent, all `model_positioning_scores` default to 12 (neutral midpoint) and `data_quality.bpa_available` is false
- `positioning_misalignment_score` > 70 triggers SKL-BAA-12 (human escalation) for positioning misalignment
