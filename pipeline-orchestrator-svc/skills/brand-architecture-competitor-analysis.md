---
name: brand-architecture-competitor-analysis
version: "1.0"
description: Analyze competitor brand architecture patterns from CIA data — portfolio structures, naming conventions, architecture models in use (maps to SKL-BAA-01)
target_agents:
  - brand_architecture
triggers:
  - "competitor architecture"
  - "competitor portfolio"
  - "architecture patterns"
  - "competitor brand structure"
  - "competitive architecture"
priority: 9
max_tokens: 500
---

# Competitor Architecture Analysis

## Purpose
Consume the Competitor Intelligence Agent (CIA) output to map how competitors organize their brand portfolios. This reveals dominant architecture models in the category, identifies structural white-space, and informs the architecture model recommendation.

## Methodology

### 1. CIA Matrix Ingestion
- Read `previous_outputs.competitor_intelligence` for the full competitor profile set
- Extract per-competitor data: parent brand, sub-brands, product lines, endorsed brands, and independent brands
- If CIA output is absent, log warning and proceed with minimal competitive context from `input_context`

### 2. Architecture Pattern Classification
For each competitor, classify its observed architecture model:

| Model | Signal |
|-------|--------|
| **Branded House** | Single master brand on all products (e.g., Virgin, FedEx) |
| **House of Brands** | Independent brands with no visible parent (e.g., P&G portfolio) |
| **Endorsed** | Sub-brands with visible parent endorsement (e.g., Courtyard by Marriott) |
| **Hybrid** | Mix of endorsed and independent brands under one parent |
| **Sub-Brand** | Extensions that combine parent name with modifier (e.g., iPhone Pro) |

- Assign a confidence score (0-1) to each classification based on evidence strength
- Flag competitors where classification is ambiguous (confidence < 0.5)

### 3. Portfolio Complexity Scoring
For each competitor, compute portfolio complexity metrics:
- `brand_count`: Total distinct brand names in portfolio
- `tier_depth`: Number of hierarchy levels (1 = flat, 4+ = deep)
- `naming_consistency`: Degree of naming pattern adherence (0-100)
- `architecture_clarity`: How easily a customer can understand the portfolio structure (0-100)

### 4. Category Architecture Landscape
- Aggregate competitor classifications into a category-level distribution (e.g., "60% Branded House, 20% Endorsed, 20% Hybrid")
- Identify the dominant architecture model in the category
- Detect structural white-space: architecture models underrepresented in the category
- Assess whether the focal brand's current structure aligns with or diverges from category norms

### 5. Competitive Differentiation Opportunities
- Score each architecture model for differentiation potential in this category:
  - **Conformity Risk** (0-10): How many competitors use this model (higher = more crowded)
  - **Distinction Potential** (0-10): How much structural differentiation this model offers
  - **Customer Clarity** (0-10): How well customers in this category respond to this structure
- Rank models by composite differentiation score

## Output Schema
Write to `node_outputs.baa_competitor_architecture` with keys:
- `competitor_profiles`: list of `{name, architecture_model, confidence, brand_count, tier_depth, naming_consistency, architecture_clarity}`
- `category_distribution`: `{branded_house_pct, house_of_brands_pct, endorsed_pct, hybrid_pct, sub_brand_pct}`
- `dominant_model`: str
- `structural_white_space`: list of `{model, representation_pct, differentiation_score}`
- `differentiation_ranking`: list of `{model, conformity_risk, distinction_potential, customer_clarity, composite_score}`
- `data_quality`: `{cia_available: bool, competitors_profiled: int, avg_confidence: float}`

## Integration Notes
- Requires CIA output in `previous_outputs`; if absent, emit warning and use stub competitive set from `input_context`
- Downstream consumers: SKL-BAA-06 (model recommender uses differentiation ranking), SKL-BAA-10 (strategy synthesis references competitive landscape)
