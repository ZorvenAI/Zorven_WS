---
name: economic-indicators-lookup
version: "1.0"
description: Economic indicator lookup via World Bank API (maps to SKL-MRA-04)
target_agents:
  - market_research
triggers:
  - "economic"
  - "GDP"
  - "inflation"
  - "unemployment"
  - "population"
  - "macro"
  - "indicator"
  - "country data"
priority: 5
max_tokens: 350
---

# Economic Indicators Lookup

## Skill: SKL-MRA-04 (Economic Indicator Lookup)

## Available Indicators
- **GDP** (NY.GDP.MKTP.CD): Gross Domestic Product in current USD
- **GDP Growth** (NY.GDP.MKTP.KD.ZG): Annual GDP growth rate (%)
- **Inflation** (FP.CPI.TOTL.ZG): Consumer price inflation (%)
- **Unemployment** (SL.UEM.TOTL.ZS): Unemployment rate (% of labor force)
- **Population** (SP.POP.TOTL): Total population
- **GNI per Capita** (NY.GNI.PCAP.CD): Gross National Income per person
- **Trade % GDP** (NE.TRD.GNFS.ZS): Trade as percentage of GDP
- **FDI Net Inflows** (BX.KLT.DINV.WD.GD.ZS): Foreign direct investment

## Data Source
World Bank Open Data API (no API key required). Data available for 200+ countries, typically 1-2 year lag for most indicators.

## Usage Guidelines
- Use ISO alpha-2 country codes (e.g., "US", "GB", "IN") or "WLD" for world aggregate
- Default date range: 2019-2024
- For local/city-level queries, skip economic indicators (country-level data not useful)
- Cross-reference economic data with industry-specific data for market sizing context
