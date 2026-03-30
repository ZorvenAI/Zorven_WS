---
name: campaign-arch-placement-budget-builder
version: "1.0"
description: Design placement strategy and budget allocation per ad set; CBO vs ABO decision and Meta placement distribution across Feed, Stories, Reels, and more (maps to SKL-CAA-08)
target_agents:
  - campaign_architecture
triggers:
  - "placement strategy"
  - "budget allocation"
  - "ad placements"
  - "cbo abo"
priority: 10
max_tokens: 500
---

# Placement & Budget Builder

## Purpose
Define the placement strategy (where ads appear) and budget allocation (how spend is distributed) for each ad set in the campaign hierarchy. Includes the CBO vs ABO decision and placement-level optimization guidance.

## Methodology

### 1. CBO vs ABO Decision
Campaign Budget Optimization (CBO) vs Ad Set Budget Optimization (ABO):

**Use CBO when** (recommended):
- Total daily budget >= $100/day
- 3+ ad sets in a campaign
- Testing phase is complete (known winning audiences)
- Meta's algorithm has sufficient data to optimize

**Use ABO when**:
- Total daily budget < $100/day
- Strict per-audience budget control needed
- Initial testing phase (need equal spend across test cells)
- Special Ad Category campaigns (CBO performance is less predictable)

### 2. Meta Placement Options
Available placements by platform:

**Facebook**:
- Feed: Highest reach, moderate CPM
- Stories: High engagement, lower CPM
- In-Stream Video: Video-only, high completion rates
- Right Column: Desktop only, lowest CPM, lowest CTR
- Search Results: Intent-based, moderate performance
- Marketplace: E-commerce focused

**Instagram**:
- Feed: High engagement, moderate CPM
- Stories: Best for vertical video, high swipe-up rates
- Reels: Highest engagement growth, competitive CPM
- Explore: Discovery-focused, broad reach

**Audience Network**:
- Banner/Interstitial: Extended reach, lower quality
- Rewarded Video: High completion, gaming audiences

**Messenger**:
- Inbox: Direct engagement, conversational
- Stories: Similar to Instagram Stories performance

### 3. Placement Strategy by Funnel Stage
Recommend placements per funnel stage:
- **TOFU**: All placements (maximize reach) — emphasis on Feed + Reels
- **MOFU**: Feed + Stories + Reels (engagement-focused) — exclude Audience Network
- **BOFU**: Feed + Stories (conversion-focused) — exclude low-intent placements
- **Retention**: Feed + Messenger (personalized re-engagement)

### 4. Budget Distribution
Allocate daily budget from SKL-CAA-06 across ad sets:
- Primary split by funnel stage (from funnel allocation percentages)
- Secondary split by audience within each stage (equal or performance-weighted)
- Minimum $5/day per ad set (Meta requirement for delivery)
- Reserve 10-20% for testing ad sets (SKL-CAA-09)

### 5. Bid Strategy Recommendations
Per campaign objective:
- AWARENESS: Lowest cost (maximize impressions)
- TRAFFIC: Cost cap or lowest cost (control CPC)
- ENGAGEMENT: Lowest cost (maximize interactions)
- LEADS: Cost cap (control CPA)
- SALES: ROAS target or cost cap (optimize for value)

## Output Schema
Write to `node_outputs.caa_placement_budget` with keys:
- `budget_optimization`: "CBO" | "ABO" with rationale
- `ad_sets`: list of `{name, funnel_stage, audience_ref, daily_budget, placements, bid_strategy}`
- `placements_per_stage`: dict mapping funnel stage to list of placement strings
- `total_daily_budget`: float
- `total_monthly_budget`: float
- `minimum_viable_budget`: float (lowest budget that allows all ad sets to deliver)
- `budget_warnings`: list[str] (e.g., "Ad set X below $5/day minimum")

## Integration Notes
- Consumed by SKL-CAA-10 (blueprint synthesizer) for ad set specifications
- Audience references link to SKL-CAA-07 audience targeting specs
- Budget allocation must respect funnel percentages from SKL-CAA-06
- If total budget is below minimum viable, recommend reducing ad set count
