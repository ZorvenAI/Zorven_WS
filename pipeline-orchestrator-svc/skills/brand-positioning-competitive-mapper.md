---
name: brand-positioning-competitive-mapper
version: "1.0"
description: Analyze CIA competitor matrix, plot 2D perceptual space, identify white-space zones (maps to SKL-BPA-01)
target_agents:
  - brand_positioning
triggers:
  - "competitive map"
  - "perceptual space"
  - "white space"
  - "competitor positioning"
  - "positioning landscape"
priority: 9
max_tokens: 500
---

# Competitive Positioning Mapper

## Purpose
Consume the Competitor Intelligence Agent (CIA) output matrix and transform it into a structured competitive landscape that feeds downstream positioning generation.

## Methodology

### 1. CIA Matrix Ingestion
- Read `previous_outputs.competitor_intelligence` for the full competitor profile set
- Extract per-competitor scores across all profiled dimensions (product, pricing, distribution, brand perception, customer experience)
- Normalize scores to a 0-100 scale if raw values vary in range

### 2. Dimension Selection
- Identify the **two most discriminating dimensions** using variance analysis across competitors
- Prefer dimensions where the focal brand has a credible claim (cross-reference with `input_context.company`)
- Fall back to Price vs. Feature Richness if variance analysis is inconclusive

### 3. 2D Perceptual Space Plot
- Place each competitor on the selected X/Y axes with normalized coordinates
- Assign quadrant labels (e.g., Premium-Full Featured, Budget-Minimal, etc.)
- Include the focal brand's current estimated position (if data available) or mark as "TBD"

### 4. White-Space Identification
- Scan for quadrants or sub-regions with no or sparse competitor presence
- Score each white-space zone on three criteria (0-10 each):
  - **Demand Signal**: Evidence from MRA/VoCA data that customers want offerings in this zone
  - **Feasibility**: Alignment with the focal brand's capabilities and resources
  - **Defensibility**: Barriers to competitor entry once the zone is claimed
- Rank zones by composite score

### 5. Cluster Detection
- Identify competitor clusters (3+ competitors within 15% proximity on both axes)
- Flag clusters as "red ocean" zones with high competitive intensity
- Note isolated competitors as potential niche positioning references

## Output Schema
Write to `node_outputs.bpa_competitive_map` with keys:
- `selected_dimensions`: `{x_axis: str, y_axis: str, rationale: str}`
- `competitor_positions`: list of `{name, x, y, quadrant}`
- `focal_brand_position`: `{x, y, quadrant, confidence}` or `null`
- `white_space_zones`: list of `{quadrant, demand_signal, feasibility, defensibility, composite_score}`
- `clusters`: list of `{quadrant, members[], intensity_rating}`

## Integration Notes
- Requires CIA output in `previous_outputs`; if absent, emit warning and use stub competitive set from `input_context`
- Downstream consumers: SKL-BPA-06 (statement generator), SKL-BPA-08 (perceptual maps), SKL-BPA-09 (differentiation)
