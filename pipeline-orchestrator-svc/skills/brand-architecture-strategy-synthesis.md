---
name: brand-architecture-strategy-synthesis
version: "1.0"
description: Synthesize all BAA skill outputs into a unified architecture strategy document with executive summary, implementation roadmap, and confidence scoring (maps to SKL-BAA-10)
target_agents:
  - brand_architecture
triggers:
  - "strategy synthesis"
  - "architecture strategy"
  - "strategy document"
  - "architecture summary"
  - "final strategy"
priority: 8
max_tokens: 800
---

# Architecture Strategy Synthesizer

## Purpose
Produce the capstone architecture strategy document by synthesizing outputs from all preceding skills (SKL-BAA-01 through SKL-BAA-09). This document is the primary deliverable of the Brand Architecture Agent — it provides an actionable, board-ready strategy for structuring the brand portfolio.

## Methodology

### 1. Input Aggregation
Collect and validate all upstream skill outputs:

| Source | Key | Required? |
|---|---|---|
| SKL-BAA-01 | `baa_competitor_architecture` | Enriching |
| SKL-BAA-02 | `baa_audience_alignment` | Enriching |
| SKL-BAA-03 | `baa_portfolio` | Required |
| SKL-BAA-04 | `baa_positioning_context` | Required |
| SKL-BAA-05 | `baa_rag_context` | Enriching |
| SKL-BAA-06 | `baa_model_recommendation` | Required |
| SKL-BAA-07 | `baa_hierarchy` | Required |
| SKL-BAA-08 | `baa_naming` | Required |
| SKL-BAA-09 | `baa_growth_plan` | Required |

Log completeness metrics: `{required_present, required_total, enriching_present, enriching_total}`.

### 2. Executive Summary (200-300 words)
Synthesize a concise executive summary covering:
- Current brand architecture state (from SKL-BAA-03)
- Recommended architecture model and confidence (from SKL-BAA-06)
- Key structural changes proposed (from SKL-BAA-07)
- Naming strategy highlights (from SKL-BAA-08)
- Growth trajectory summary (from SKL-BAA-09)
- Top 3 risks and mitigations (from SKL-BAA-09)

### 3. Architecture Recommendation Section
From SKL-BAA-06:
- Recommended model with scoring matrix visualization data
- Why-not-others analysis for non-recommended models
- Sensitivity analysis results
- Transition magnitude and migration requirements

### 4. Brand Hierarchy Section
From SKL-BAA-07:
- Full hierarchy tree (JSON for React Flow rendering)
- Node descriptions and relationship types
- Positioning scores per node (from SKL-BAA-04 alignment)
- Visual identity guidelines per node

### 5. Naming & Identity Section
From SKL-BAA-08:
- Naming convention rules
- Per-node naming recommendations
- Consistency score and breakdown
- Naming guidelines (mandatory/recommended/prohibited)

### 6. Growth Roadmap Section
From SKL-BAA-09:
- Phased growth plan with timeline
- Risk assessment summary
- KPIs per phase
- Resource requirements overview

### 7. Competitive Context Section
From SKL-BAA-01 (when available):
- Competitor architecture comparison
- Structural differentiation opportunities
- White-space analysis

### 8. Implementation Priorities
Synthesize a prioritized action list:
1. Immediate (0-3 months): Critical structural changes, naming updates
2. Short-term (3-6 months): Phase 1 growth actions, identity rollout
3. Medium-term (6-12 months): Phase 2-3 growth actions
4. Long-term (12+ months): Full portfolio vision realization

### 9. Confidence Scoring
Compute an overall architecture confidence score (0.0-1.0):
- `model_confidence` (0.3 weight): From SKL-BAA-06 recommendation robustness
- `data_completeness` (0.2 weight): % of required + enriching inputs present
- `hierarchy_coherence` (0.2 weight): Hierarchy passes structural validation
- `naming_consistency` (0.15 weight): Naming consistency score / 100
- `growth_feasibility` (0.15 weight): Inverse of portfolio risk score / 100

```
confidence = (model_confidence * 0.3) + (data_completeness * 0.2)
           + (hierarchy_coherence * 0.2) + (naming_consistency * 0.15)
           + (growth_feasibility * 0.15)
```

### 10. Citations
Compile all data sources referenced:
- WF1 agents used (VoCA, CIA, APA, TCIA, MRA)
- BPA positioning strategy reference
- RAG documents retrieved
- External research sources (Tavily)
- Company/portfolio data source

## Output Schema
Write to `node_outputs.baa_strategy` with keys:
- `executive_summary`: str (200-300 words)
- `recommendation`: `{recommended_model, model_scores: [], why_not_others: [], confidence_score, transition_magnitude, sensitivity: []}`
- `hierarchy`: `{root: HierarchyNode, total_depth, total_nodes}`
- `naming_hierarchy`: `{naming_pattern, naming_rules: [], consistency_score, naming_guidelines: []}`
- `growth_path`: `{phases: [], portfolio_risk_assessment: [], total_timeline_months, recommended_pace}`
- `competitive_context`: `{competitor_architectures: [], differentiation_opportunities: [], white_space: []}` (empty if SKL-BAA-01 unavailable)
- `implementation_priorities`: list of `{timeframe, actions: [], dependencies: []}`
- `confidence_score`: float (0.0-1.0)
- `confidence_breakdown`: `{model_confidence, data_completeness, hierarchy_coherence, naming_consistency, growth_feasibility}`
- `data_completeness`: `{required_present, required_total, enriching_present, enriching_total}`
- `citations`: list of `{source_type, source_id, description}`
- `findings`: list of str (key findings for result_data)
- `recommendations`: list of str (key recommendations for result_data)

## Integration Notes
- This is the terminal analytical skill; its output becomes the primary `result_data` returned to Django
- SKL-BAA-11 (persister) archives this full strategy document
- SKL-BAA-12 (escalation) uses `confidence_score` to determine if human review is needed
- The Django `BrandArchitectureExtractor` reads from this output to extract analytics metrics
- `confidence_score` < 0.7 (settings.CONFIDENCE_THRESHOLD) triggers escalation
