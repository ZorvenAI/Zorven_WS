---
name: brand-positioning-value-proposition
version: "1.0"
description: Osterwalder Value Proposition Canvas — customer profile mapped to value map with fit analysis (maps to SKL-BPA-07)
target_agents:
  - brand_positioning
triggers:
  - "value proposition"
  - "value canvas"
  - "customer profile"
  - "pain relievers"
  - "gain creators"
priority: 9
max_tokens: 500
---

# Value Proposition Canvas

## Purpose
Construct an Osterwalder-style Value Proposition Canvas that maps the customer profile (jobs, pains, gains) to the brand's value map (products/services, pain relievers, gain creators). Quantifies fit between customer needs and brand offering.

## Methodology

### 1. Customer Profile Construction
Source data from upstream skills to populate the three customer profile segments:

**Customer Jobs** (functional, social, emotional):
- Functional jobs: From APA persona goals and JTBD data (SKL-BPA-02)
- Social jobs: From APA psychographic profiles and VoCA social sentiment
- Emotional jobs: From VoCA emotional themes and APA motivational drivers

**Customer Pains**:
- From VoCA pain point priority matrix (SKL-BPA-02 table-stakes gaps)
- From CIA competitor weaknesses that affect the customer (SKL-BPA-01)
- Rank pains by severity (1-5) and frequency (1-5)

**Customer Gains**:
- From SKL-BPA-02 differentiators and delighters
- From TCIA ride-trends that create new expectations (SKL-BPA-03)
- Classify as required, expected, desired, or unexpected

### 2. Value Map Construction
Map the brand's offering against the customer profile:

**Products & Services**:
- Core offerings from Company model (SKL-BPA-04)
- Capabilities implied by the recommended positioning statement (SKL-BPA-06)

**Pain Relievers**:
- For each top-10 customer pain, describe how the brand specifically alleviates it
- Rate relief strength: eliminates (3), reduces (2), mitigates (1), does not address (0)

**Gain Creators**:
- For each top-10 customer gain, describe how the brand creates or amplifies it
- Rate creation strength: exceeds expectations (3), meets (2), partially (1), none (0)

### 3. Fit Analysis
Calculate three types of fit:

| Fit Type | Metric | Threshold |
|----------|--------|-----------|
| **Problem-Solution Fit** | % of top pains addressed at relief >= 2 | Good >= 70% |
| **Product-Market Fit** | % of gains created at strength >= 2 | Good >= 60% |
| **Overall Fit Score** | Weighted average of both | Good >= 65% |

### 4. Gap Identification
- List customer pains with relief strength 0-1 as "unaddressed pain gaps"
- List customer gains with creation strength 0-1 as "missed gain opportunities"
- Prioritize gaps that overlap with competitive white-space zones (SKL-BPA-01)

## Output Schema
Write to `node_outputs.bpa_value_proposition` with keys:
- `customer_profile`: `{jobs: [{description, type, priority}], pains: [{description, severity, frequency}], gains: [{description, classification, importance}]}`
- `value_map`: `{products: [str], pain_relievers: [{pain, relief, strength}], gain_creators: [{gain, mechanism, strength}]}`
- `fit_scores`: `{problem_solution_fit: float, product_market_fit: float, overall_fit: float}`
- `unaddressed_gaps`: list of `{type: "pain"|"gain", description, priority, white_space_overlap: bool}`

## Integration Notes
- SKL-BPA-10 (strategy synthesis) embeds the canvas as a key deliverable section
- Low overall fit score (< 50%) triggers SKL-BPA-12 (human escalation)
