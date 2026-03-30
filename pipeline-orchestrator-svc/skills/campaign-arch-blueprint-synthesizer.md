---
name: campaign-arch-blueprint-synthesizer
version: "1.0"
description: Capstone synthesis of full CampaignBlueprint JSON assembling campaign, ad set, and ad hierarchy in Meta Marketing API-compatible format with performance projections and risk assessment (maps to SKL-CAA-10)
target_agents:
  - campaign_architecture
triggers:
  - "campaign blueprint"
  - "blueprint synthesis"
  - "campaign plan"
  - "full campaign"
priority: 10
max_tokens: 800
---

# Blueprint Synthesizer

## Purpose
Assemble all upstream skill outputs into a comprehensive CampaignBlueprint JSON document. This is the capstone skill that produces the final, actionable campaign architecture in a format compatible with the Meta Marketing API hierarchy.

## Methodology

### 1. Input Assembly
Collect outputs from all prior skills:
- SKL-CAA-01: Strategy context and brand maturity
- SKL-CAA-02: Industry benchmarks
- SKL-CAA-03: Competitor advertising patterns
- SKL-CAA-04: Odoo customer data (optional)
- SKL-CAA-05: RAG prior campaign learnings (optional)
- SKL-CAA-06: Funnel-to-objective mapping and budget allocation
- SKL-CAA-07: Audience targeting specifications
- SKL-CAA-08: Placement and budget distribution
- SKL-CAA-09: A/B test plan

### 2. Campaign Hierarchy Construction
Build the Meta Ads hierarchy:

**Campaign Level** (1 per funnel stage):
- Campaign name: `{brand_name} - {funnel_stage} - {objective}`
- Objective: From SKL-CAA-06 mapping
- Budget optimization: CBO or ABO from SKL-CAA-08
- Special Ad Category: Auto-detect from industry (housing, credit, employment, politics)
- Daily budget: From SKL-CAA-06 allocation

**Ad Set Level** (1-3 per campaign):
- Ad set name: `{funnel_stage} - {audience_name}`
- Targeting: From SKL-CAA-07 audience specs
- Placements: From SKL-CAA-08 placement strategy
- Budget: From SKL-CAA-08 distribution
- Schedule: Start date, end date (or ongoing)
- Bid strategy: From SKL-CAA-08 recommendations

**Ad Level** (2-3 per ad set — creative briefs, not final assets):
- Ad name: `{audience} - {creative_concept} - {format}`
- Format recommendation: Image, Video, Carousel
- Messaging angle: Derived from brand positioning (SKL-CAA-01)
- CTA: Mapped from funnel stage
- Creative brief: Brand voice guidelines from BPV personality

### 3. Performance Projections
For each campaign, project 30-day performance:
- Impressions: Daily budget / CPM * 1000
- Clicks: Impressions * CTR
- Conversions: Clicks * Conversion Rate
- Cost: Daily budget * 30
- ROAS: (Conversions * Avg Order Value) / Cost

Use three scenarios (optimistic / realistic / conservative) with benchmarks from SKL-CAA-02.

### 4. Risk Assessment
Evaluate and flag risks:
- Budget sufficiency: Can all ad sets deliver at minimum $5/day?
- Audience saturation: Will frequency exceed 3x in 30 days?
- Objective compatibility: Are conversion events configured?
- Special Ad Category: Does industry trigger restricted targeting?
- Seasonal impact: Is launch timing near high-CPM periods (Q4, holidays)?

### 5. Confidence Scoring
Calculate overall blueprint confidence (0-1):
- Context completeness weight: 0.3 (from SKL-CAA-01)
- Benchmark availability weight: 0.2 (from SKL-CAA-02)
- Prior campaign data weight: 0.2 (from SKL-CAA-05)
- Budget viability weight: 0.15 (from SKL-CAA-08)
- Audience quality weight: 0.15 (from SKL-CAA-07)

## Output Schema
Write to `node_outputs.caa_blueprint` with keys:
- `blueprint_id`: string (UUID)
- `brand_name`: string
- `brand_maturity`: string
- `campaigns`: list of campaign objects, each containing:
  - `campaign_name`: string
  - `objective`: string
  - `funnel_stage`: string
  - `daily_budget`: float
  - `budget_optimization`: "CBO" | "ABO"
  - `special_ad_category`: string | null
  - `ad_sets`: list of ad set objects, each containing:
    - `ad_set_name`: string
    - `targeting`: dict (demographics, interests, behaviors, custom_audiences, exclusions)
    - `placements`: list[str]
    - `daily_budget`: float
    - `bid_strategy`: string
    - `ads`: list of ad brief objects
- `ab_tests`: list (from SKL-CAA-09)
- `performance_projections`: dict with `optimistic`, `realistic`, `conservative` scenarios
- `risk_assessment`: list of `{risk, severity, mitigation}`
- `confidence_score`: float (0-1)
- `total_daily_budget`: float
- `total_monthly_budget`: float
- `recommended_duration_days`: int

## Integration Notes
- This is the primary output of the CAA agent pipeline
- Output format is designed for downstream Meta Marketing API integration
- Creative briefs (not final assets) are included — actual creative production is a separate workflow
- Consumed by SKL-CAA-11 (persister) and SKL-CAA-12 (human escalation)
