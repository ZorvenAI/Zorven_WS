---
name: market-research-methodology
version: "2.0"
description: Market sizing, TAM/SAM/SOM analysis, and synthesis framework (maps to SKL-MRA-03)
target_agents:
  - market_research
triggers:
  - "market"
  - "tam"
  - "sam"
  - "som"
  - "market size"
  - "sizing"
  - "addressable"
  - "analysis"
  - "synthesis"
  - "research report"
priority: 10
max_tokens: 500
---

# Market Research Methodology

## Skills: SKL-MRA-03 (Market Analysis Synthesis), SKL-MRA-06 (Research Report Generator)

## TAM/SAM/SOM Framework
- **TAM (Total Addressable Market)**: The total market demand for a product or service globally. Calculate using top-down (industry reports, government data) and bottom-up (unit economics x total potential customers) approaches.
- **SAM (Serviceable Addressable Market)**: The segment of TAM targeted by your products/services within geographical and operational reach. Apply geographic, demographic, and capability filters to TAM.
- **SOM (Serviceable Obtainable Market)**: The portion of SAM you can realistically capture. Consider market share, competitive positioning, go-to-market capacity.

## Data Triangulation
- Cross-reference at least 2-3 independent data sources for market size estimates
- Prefer recent data (within 2 years) from recognized research firms, government statistics, or industry associations
- Flag estimates with single-source backing as low confidence

## Confidence Scoring
- **High (0.8-1.0)**: Multiple concordant sources, recent data, well-defined market
- **Medium (0.5-0.79)**: Some data available but gaps exist, or sources show variance
- **Low (0.0-0.49)**: Limited data, emerging market, or significant extrapolation required

## Growth Rate Analysis
- Use CAGR (Compound Annual Growth Rate) for historical and projected growth
- Compare against GDP growth to assess relative market momentum
- Identify inflection points and growth drivers

## Analysis Types
- **landscape**: Competitive landscape analysis with Porter's Five Forces
- **sizing**: TAM/SAM/SOM quantification with data triangulation
- **segmentation**: Market segmentation by geography, demographics, behavior
- **trends**: Industry trend analysis with timeline classification
