---
name: brand-positioning-strategy-synthesis
version: "1.0"
description: Capstone strategy document — executive summary, recommended positioning, UVP, canvas, maps, differentiation, implementation guidelines, risk assessment (maps to SKL-BPA-10)
target_agents:
  - brand_positioning
triggers:
  - "strategy synthesis"
  - "positioning strategy"
  - "capstone"
  - "strategy document"
  - "executive summary"
priority: 10
max_tokens: 700
---

# Positioning Strategy Synthesis

## Purpose
Assemble all upstream BPA skill outputs into a comprehensive, executive-ready brand positioning strategy document. This is the capstone deliverable of the Brand Positioning Agent.

## Methodology

### 1. Input Validation
Verify all upstream skill outputs are present. Required inputs:
- SKL-BPA-01: `bpa_competitive_map` (competitive landscape)
- SKL-BPA-02: `bpa_audience_needs` (needs hierarchy)
- SKL-BPA-04: `bpa_identity_context` (brand anchor)
- SKL-BPA-06: `bpa_positioning_statements` (candidates + recommendation)
- SKL-BPA-09: `bpa_differentiation` (POP/POD/RTB)

Optional but enriching:
- SKL-BPA-03: `bpa_trend_alignment` (trend affinity matrix)
- SKL-BPA-05: `bpa_rag_context` (prior positioning)
- SKL-BPA-07: `bpa_value_proposition` (value canvas)
- SKL-BPA-08: `bpa_perceptual_maps` (visual maps)

Log warnings for missing optional inputs; trigger SKL-BPA-12 if any required input is absent.

### 2. Executive Summary
Produce a 150-250 word executive summary covering:
- Brand name and category context
- Core strategic challenge or opportunity identified
- Recommended positioning in one sentence
- Key differentiation theme
- Confidence level based on data completeness

### 3. Strategy Document Sections

**Section 1: Market Context**
- Industry landscape from MRA data (via competitive map)
- Key trends shaping the category (from trend alignment)
- Competitive dynamics summary (clusters, intensity, white-space)

**Section 2: Target Audience**
- Primary persona profiles with needs hierarchy
- Table-stakes that must be met
- Differentiators and delighters that fuel positioning

**Section 3: Recommended Positioning**
- The recommended positioning statement with framework used
- All candidate statements with scores for comparison
- Evolution narrative if prior positioning exists (from RAG context)

**Section 4: Value Proposition Canvas**
- Customer profile (jobs, pains, gains) and value map
- Fit scores with gap analysis

**Section 5: Perceptual Maps**
- 3-5 maps with current/target positions and migration vectors
- Strategic insights per map

**Section 6: Differentiation Architecture**
- POPs, PODs, RTBs in structured format
- Proof point matrix
- Competitive vulnerability assessment

**Section 7: Implementation Guidelines**
- Messaging hierarchy: tagline, elevator pitch, full positioning statement
- Channel adaptation notes (web, social, sales collateral, PR)
- Internal alignment recommendations (employee messaging, culture fit)

**Section 8: Risk Assessment**
- Positioning risks from competitive vulnerability analysis
- Trend-related risks from affinity matrix
- Data quality risks from coverage scores
- Recommended mitigations for each risk

### 4. Confidence Scoring
Compute an overall strategy confidence score (0-100):
- Data completeness: % of required + optional inputs present (weight 0.3)
- Differentiation strength: from SKL-BPA-09 score (weight 0.3)
- Value proposition fit: from SKL-BPA-07 overall fit (weight 0.2)
- Positioning statement quality: top candidate composite score (weight 0.2)

## Output Schema
Write to `node_outputs.bpa_strategy_synthesis` and `result_data`:
- `executive_summary`: str
- `sections`: list of `{title, content, data_references: []}`
- `recommended_positioning`: `{statement, framework, composite_score}`
- `strategy_confidence`: float (0-100)
- `data_completeness`: `{required_present: int, required_total: int, optional_present: int, optional_total: int}`
- `risk_register`: list of `{risk, category, severity, mitigation}`
- `implementation_guidelines`: `{tagline, elevator_pitch, channel_adaptations: {}}`

## Integration Notes
- This output is the primary `result_data` payload returned via callback to Django
- SKL-BPA-11 (persister) archives this output to GCS and RAG store
- `strategy_confidence` < 50 triggers SKL-BPA-12 (human escalation)
