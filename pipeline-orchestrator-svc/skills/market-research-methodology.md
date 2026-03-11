---
name: market-research-methodology
version: "1.0"
description: Market sizing and TAM/SAM/SOM analysis framework
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
priority: 10
max_tokens: 500
---

# Market Research Methodology

## TAM/SAM/SOM Framework
- **TAM (Total Addressable Market)**: The total market demand for a product or service globally. Calculate using top-down (industry reports, government data) and bottom-up (unit economics × total potential customers) approaches.
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
