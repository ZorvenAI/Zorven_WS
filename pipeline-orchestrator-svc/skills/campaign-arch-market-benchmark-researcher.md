---
name: campaign-arch-market-benchmark-researcher
version: "1.0"
description: Research industry-specific Meta Ads benchmarks via Tavily for CPM, CTR, CPC, CPA, and ROAS reference data by vertical; results cached 24h in Redis (maps to SKL-CAA-02)
target_agents:
  - campaign_architecture
triggers:
  - "market benchmarks"
  - "ad benchmarks"
  - "industry benchmarks"
  - "meta ads benchmarks"
priority: 10
max_tokens: 500
---

# Market Benchmark Researcher

## Purpose
Gather current industry-specific advertising benchmarks for Meta Ads (Facebook/Instagram) to inform realistic KPI targets, budget recommendations, and performance projections in the campaign blueprint.

## Methodology

### 1. Cache Check
Before researching, check Redis for cached benchmarks:
- Key: `caa:{tenant_id}:benchmarks:{industry_slug}`
- TTL: 24 hours
- If cached data exists and is within TTL, return immediately

### 2. Tavily Research Queries
Execute 2-3 targeted Tavily searches:
- `"{industry} Meta Facebook Ads benchmarks {current_year} CPM CTR CPC"`
- `"{industry} Instagram advertising benchmarks ROAS CPA {current_year}"`
- `"{industry} social media advertising cost per acquisition benchmarks"`

Extract structured metrics from search results using LLM parsing.

### 3. Benchmark Metrics
Gather the following per industry vertical:
- **CPM** (Cost Per Mille): Average cost per 1,000 impressions
- **CTR** (Click-Through Rate): Average click-through percentage
- **CPC** (Cost Per Click): Average cost per link click
- **CPA** (Cost Per Acquisition): Average cost per conversion
- **ROAS** (Return On Ad Spend): Average return ratio
- **Engagement Rate**: Average engagement percentage
- **Video View Rate**: Average for video ad formats

### 4. Benchmark Contextualization
Adjust raw benchmarks based on:
- Company size (startup vs. enterprise — startups typically see 20-40% higher CPA)
- Geographic market (US, EU, APAC — CPM varies 2-5x across regions)
- Campaign objective (awareness campaigns have lower CPC but higher CPA)
- Seasonal factors (Q4 holiday CPMs typically 30-50% higher)

### 5. Cache Write
Store researched benchmarks in Redis:
- Key: `caa:{tenant_id}:benchmarks:{industry_slug}`
- TTL: 86400 seconds (24 hours)

## Output Schema
Write to `node_outputs.caa_market_benchmarks` with keys:
- `industry`: string (industry vertical)
- `benchmarks`: dict with keys `cpm`, `ctr`, `cpc`, `cpa`, `roas`, `engagement_rate`, `video_view_rate` — each containing `low`, `median`, `high` values
- `adjustments`: dict (size_factor, geo_factor, seasonal_factor)
- `data_freshness`: ISO 8601 timestamp of research
- `sources`: list[str] (URLs of benchmark sources)
- `confidence`: float (0-1, based on source consistency)

## Integration Notes
- Consumed by SKL-CAA-06 (funnel objective mapper) for KPI target setting
- Consumed by SKL-CAA-08 (placement budget builder) for budget recommendations
- Consumed by SKL-CAA-10 (blueprint synthesizer) for performance projections
- If Tavily is unavailable, falls back to hardcoded industry averages (lower confidence)
