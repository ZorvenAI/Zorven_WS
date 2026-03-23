---
name: brand-positioning-trend-alignment
version: "1.0"
description: Analyze TCIA trend data and produce trend-positioning affinity matrix (maps to SKL-BPA-03)
target_agents:
  - brand_positioning
triggers:
  - "trend alignment"
  - "cultural trend"
  - "trend affinity"
  - "trend positioning"
  - "macro trend"
priority: 8
max_tokens: 450
---

# Trend-Positioning Alignment

## Purpose
Evaluate Trend & Cultural Intelligence Agent (TCIA) outputs to determine which macro and micro trends the brand positioning should ride, resist, or monitor. Produces a trend-positioning affinity matrix used by the statement generator and strategy synthesizer.

## Methodology

### 1. Trend Data Ingestion
- Read `previous_outputs.trend_cultural` for trend objects (trend name, category, velocity, relevance score, cultural context, opportunity alerts)
- Filter trends to those with relevance score >= 0.4 for the focal brand's industry
- If TCIA output is absent, skip this skill and emit `trend_alignment_skipped: true`

### 2. Trend Classification
Categorize each qualifying trend along two dimensions:

**Lifecycle Stage**:
- Emerging (< 12 months visible, high velocity)
- Accelerating (12-36 months, mainstream adoption growing)
- Mature (> 36 months, table-stakes territory)
- Declining (velocity negative)

**Positioning Relevance**:
- Ride: High affinity with brand identity + customer needs; lean into this trend
- Resist: Counter-positioning opportunity; differentiate by going against the trend
- Monitor: Relevant but premature or risky to commit

### 3. Affinity Scoring
For each trend, compute affinity with the brand across four factors (0-10 each):
- **Identity Fit**: Alignment with brand mission, values, and personality from Company model
- **Audience Resonance**: Overlap with APA persona interests and VoCA sentiment themes
- **Competitive Whitespace**: Whether competitors have already claimed this trend (from CIA data)
- **Longevity Risk**: Probability the trend endures beyond 18 months

**Composite Affinity** = weighted average (Identity 0.3, Audience 0.3, Whitespace 0.2, Longevity 0.2)

### 4. Trend-Positioning Affinity Matrix
Produce a matrix with rows = trends, columns = scoring factors + composite + recommendation (Ride/Resist/Monitor).

### 5. Cultural Sensitivity Flags
- Flag trends tied to social, political, or religious movements as "sensitivity: high"
- Recommend human review before incorporating sensitive trends into positioning
- These flags feed into SKL-BPA-12 (human escalation) triggers

## Output Schema
Write to `node_outputs.bpa_trend_alignment` with keys:
- `affinity_matrix`: list of `{trend_name, category, lifecycle, identity_fit, audience_resonance, competitive_whitespace, longevity_risk, composite, recommendation}`
- `ride_trends`: top trends recommended for positioning alignment
- `resist_trends`: counter-positioning trend opportunities
- `monitor_trends`: watch-list trends
- `sensitivity_flags`: list of `{trend_name, reason, recommended_action}`
- `trend_alignment_skipped`: bool (true if TCIA data absent)

## Integration Notes
- Downstream consumers: SKL-BPA-06 (statement generator uses ride/resist trends as positioning pillars), SKL-BPA-10 (strategy synthesis includes trend risk assessment)
