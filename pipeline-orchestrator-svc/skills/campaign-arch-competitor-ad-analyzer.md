---
name: campaign-arch-competitor-ad-analyzer
version: "1.0"
description: Analyze competitor advertising patterns from Meta Ad Library via Tavily; identify ad spend patterns, creative approaches, and audience targeting using CIA competitor list from WF1 (maps to SKL-CAA-03)
target_agents:
  - campaign_architecture
triggers:
  - "competitor ads"
  - "competitor advertising"
  - "ad library analysis"
  - "competitive ad intelligence"
priority: 10
max_tokens: 500
---

# Competitor Ad Analyzer

## Purpose
Research competitor advertising strategies on Meta platforms using the WF1 Competitor Intelligence (CIA) competitor list. Identifies patterns in ad spend, creative formats, messaging, and targeting to inform differentiated campaign architecture.

## Methodology

### 1. Competitor List Extraction
From SKL-CAA-01 strategy context, extract top 3-5 competitors identified by the CIA agent in WF1:
- Company names and domains
- Market positioning relative to the brand
- Known product/service categories

### 2. Tavily Research Queries
For each competitor (top 3-5):
- `"{competitor_name} Meta Ad Library Facebook ads"`
- `"{competitor_name} Instagram advertising strategy {current_year}"`
- `"{competitor_name} {industry} social media ad campaigns"`

### 3. Competitive Pattern Analysis
Extract and structure insights:

**Ad Spend Patterns**:
- Estimated monthly ad spend range (low/medium/high)
- Spend trend direction (increasing, stable, decreasing)
- Seasonal spend peaks

**Creative Approaches**:
- Dominant ad formats (image, video, carousel, collection)
- Average video length and aspect ratios
- Primary creative themes and messaging angles
- CTA patterns (Shop Now, Learn More, Sign Up, etc.)

**Audience Targeting Signals**:
- Inferred target demographics from ad content
- Geographic focus areas
- Product/service emphasis (which offerings they promote most)

### 4. Competitive Gap Analysis
Identify opportunities:
- Underserved audience segments competitors are not targeting
- Ad formats competitors are not using
- Messaging angles absent from competitor ads
- Placement gaps (e.g., competitors absent from Reels or Stories)

## Output Schema
Write to `node_outputs.caa_competitor_ads` with keys:
- `competitors_analyzed`: list of `{name, domain, ad_count_estimate}`
- `spend_patterns`: list of `{competitor, estimated_monthly_spend, trend, peak_months}`
- `creative_patterns`: list of `{competitor, dominant_formats, themes, cta_patterns}`
- `targeting_signals`: list of `{competitor, inferred_demographics, geo_focus}`
- `competitive_gaps`: list of `{gap_type, description, opportunity_score}`
- `differentiation_recommendations`: list[str]
- `confidence`: float (0-1, based on data availability)

## Integration Notes
- Consumed by SKL-CAA-07 (audience targeting builder) for exclusion and differentiation
- Consumed by SKL-CAA-09 (A/B test planner) for creative test hypotheses
- Consumed by SKL-CAA-10 (blueprint synthesizer) for competitive positioning
- If no competitor data is available, proceeds with industry-level patterns only
