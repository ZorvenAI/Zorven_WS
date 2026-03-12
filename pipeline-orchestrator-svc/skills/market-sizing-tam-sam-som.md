---
name: market-sizing-tam-sam-som
version: "1.0"
description: Focused TAM/SAM/SOM market sizing methodology (maps to SKL-MRA-03 sizing)
target_agents:
  - market_research
triggers:
  - "TAM"
  - "SAM"
  - "SOM"
  - "total addressable"
  - "serviceable"
  - "obtainable"
  - "market size"
  - "market sizing"
  - "how big"
  - "revenue potential"
priority: 9
max_tokens: 450
---

# Market Sizing: TAM/SAM/SOM

## Skills: SKL-MRA-01 (Web Search), SKL-MRA-04 (Economic Data), SKL-MRA-03 (Synthesis)

## Top-Down Approach
1. Start with total industry revenue from analyst reports (Gartner, IDC, Statista)
2. Apply geographic filters based on target market
3. Apply vertical/segment filters based on product focus
4. Result: TAM estimate with source citations

## Bottom-Up Approach
1. Define unit economics (price per customer/transaction)
2. Count total potential customers in target segment
3. Multiply: TAM = Price x Total Potential Customers
4. Validate against top-down estimate

## TAM -> SAM -> SOM Funnel
- **TAM**: Total market demand (global or national)
- **SAM**: TAM x Geographic reach x Product fit x Channel reach
- **SOM**: SAM x Realistic market share (typically 1-10% for new entrants)

## Validation Rules
- TAM > SAM > SOM (always)
- SOM should be achievable within 3-5 year horizon
- Multiple data sources required for High confidence
- Express values in USD with clear units (B = billions, M = millions)

## Geographic Scoping
- **Global**: Use world aggregate data, industry reports
- **National**: Use country GDP + industry % of GDP
- **Regional/Local**: Use metro population + per-capita spending in category
