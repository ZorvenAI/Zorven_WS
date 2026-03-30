---
name: campaign-arch-funnel-objective-mapper
version: "1.0"
description: Map funnel stages (TOFU/MOFU/BOFU/Retention) to Meta campaign objectives with budget allocation per stage based on brand maturity (maps to SKL-CAA-06)
target_agents:
  - campaign_architecture
triggers:
  - "funnel mapping"
  - "campaign objectives"
  - "funnel stages"
  - "objective mapping"
priority: 10
max_tokens: 500
---

# Funnel Objective Mapper

## Purpose
Map each funnel stage to the optimal Meta Ads campaign objective and allocate budget percentages based on brand maturity, industry benchmarks, and prior campaign learnings.

## Methodology

### 1. Funnel Stage Definitions
Define four funnel stages with corresponding Meta objectives:

**TOFU (Top of Funnel) — Awareness**:
- Valid objectives: `AWARENESS`, `TRAFFIC`
- Goal: Maximize reach and brand recall
- KPIs: CPM, Reach, Frequency, Brand Lift
- Recommended: `AWARENESS` for new brands, `TRAFFIC` for content-driven strategies

**MOFU (Middle of Funnel) — Consideration**:
- Valid objectives: `TRAFFIC`, `ENGAGEMENT`
- Goal: Drive interest and interaction
- KPIs: CTR, CPC, Engagement Rate, Landing Page Views
- Recommended: `ENGAGEMENT` for social-first brands, `TRAFFIC` for website-centric

**BOFU (Bottom of Funnel) — Conversion**:
- Valid objectives: `LEADS`, `APP_PROMOTION`, `SALES`
- Goal: Drive measurable conversions
- KPIs: CPA, Conversion Rate, ROAS, Cost Per Lead
- Recommended: `SALES` for e-commerce, `LEADS` for B2B/service businesses

**Retention — Loyalty**:
- Valid objectives: `ENGAGEMENT`, `SALES`
- Goal: Re-engage existing customers, drive repeat purchases
- KPIs: Repeat Purchase Rate, Customer LTV, Engagement Rate
- Recommended: `SALES` with custom audience targeting

### 2. Budget Allocation
Base allocation from brand maturity (SKL-CAA-01):
- **New**: 60% TOFU / 25% MOFU / 10% BOFU / 5% Retention
- **Emerging**: 40% TOFU / 30% MOFU / 20% BOFU / 10% Retention
- **Established**: 20% TOFU / 25% MOFU / 35% BOFU / 20% Retention

Adjust allocation based on:
- RAG learnings (SKL-CAA-05): If prior campaigns show strong BOFU performance, shift 5-10% from TOFU
- Industry benchmarks (SKL-CAA-02): If industry ROAS is high, increase BOFU allocation
- Business type: E-commerce skews BOFU; brand-building skews TOFU

### 3. KPI Target Setting
For each funnel stage, set target KPIs:
- Use industry benchmarks (SKL-CAA-02) as baseline
- Apply brand maturity multiplier (new brands expect 20-30% worse performance initially)
- Set optimistic / realistic / conservative scenarios

### 4. Objective Validation
Ensure selected objectives are compatible with:
- Available conversion events (pixel setup required for SALES/LEADS)
- Budget minimums (SALES objective requires minimum $10/day per ad set)
- Special Ad Category restrictions (housing, credit, employment limit objectives)

## Output Schema
Write to `node_outputs.caa_funnel_mapping` with keys:
- `funnel_stages`: list of `{stage, objective, budget_pct, daily_budget, kpi_targets}`
- `kpi_targets`: dict per stage with `{optimistic, realistic, conservative}` for each metric
- `total_daily_budget`: float
- `total_monthly_budget`: float
- `allocation_rationale`: string (explanation of allocation decisions)
- `objective_warnings`: list[str] (e.g., "SALES requires pixel; verify setup")

## Integration Notes
- Consumed by SKL-CAA-08 (placement budget builder) for per-stage budget distribution
- Consumed by SKL-CAA-10 (blueprint synthesizer) for campaign-level structure
- The six valid Meta objectives are: AWARENESS, TRAFFIC, ENGAGEMENT, LEADS, APP_PROMOTION, SALES
- Budget allocation percentages must sum to 100%
