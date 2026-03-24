---
name: brand-architecture-growth-planner
version: "1.0"
description: Design phased portfolio growth roadmap with risk assessment, milestone triggers, and resource allocation per growth phase (maps to SKL-BAA-09)
target_agents:
  - brand_architecture
triggers:
  - "growth planning"
  - "portfolio growth"
  - "brand expansion"
  - "growth roadmap"
  - "portfolio strategy"
priority: 9
max_tokens: 600
---

# Portfolio Growth Planner

## Purpose
Design a phased portfolio growth roadmap that maps the evolution of the brand architecture over time. Each phase represents a strategic milestone — adding sub-brands, entering new categories, restructuring existing brands, or expanding geographically — with explicit triggers, resource requirements, and risk assessments.

## Methodology

### 1. Input Collection
- Read SKL-BAA-06 `baa_model_recommendation` for the recommended architecture model and transition magnitude
- Read SKL-BAA-07 `baa_hierarchy` for the current/proposed brand hierarchy tree
- Read SKL-BAA-03 `baa_portfolio` for existing portfolio baseline and product catalog
- Read SKL-BAA-04 `baa_positioning_context` for positioning-driven expansion opportunities
- Read SKL-BAA-01 `baa_competitor_architecture` for competitive whitespace opportunities
- Read SKL-BAA-02 `baa_audience_alignment` for underserved audience segments

### 2. Growth Phase Design
Design 3-5 growth phases, each with:

**Phase Structure**:
- `phase_number`: Sequential (1-5)
- `phase_name`: Descriptive title (e.g., "Foundation Alignment", "Category Extension", "Market Expansion")
- `duration_months`: Estimated timeframe (3-18 months per phase)
- `objective`: One-sentence strategic objective
- `actions`: List of specific brand portfolio changes
  - New sub-brand launches
  - Brand consolidations or retirements
  - Endorsement restructuring
  - Category entries
  - Geographic expansions
- `trigger_criteria`: Conditions that signal readiness to begin this phase
  - Revenue thresholds
  - Market share milestones
  - Brand awareness targets
  - Operational readiness metrics
- `resource_requirements`: Estimated investment areas
  - Marketing budget range
  - Headcount needs
  - Technology/platform changes
  - Legal/trademark work

**Phase Sequencing Rules**:
- Phase 1 is always "Foundation" — stabilize current architecture per recommended model
- If `transition_magnitude` > 50 from SKL-BAA-06, Phase 1 focuses on migration
- Each subsequent phase builds on the prior phase's completion
- No phase should add more than 3 new brands (complexity management)
- Geographic expansion phases should follow domestic stabilization

### 3. Risk Assessment
For each phase, evaluate:

| Risk Category | Assessment |
|---|---|
| **Brand Dilution** | Risk of weakening parent brand equity through expansion |
| **Cannibalization** | Risk of new brands stealing share from existing ones |
| **Operational Complexity** | Risk of management overhead exceeding capacity |
| **Market Timing** | Risk of entering markets too early or too late |
| **Resource Strain** | Risk of insufficient budget/talent for execution |

Each risk scored: `severity` (1-5), `likelihood` (1-5), `risk_score` = severity x likelihood.

**Mitigation strategies**: For each risk with `risk_score` >= 12, provide a specific mitigation action.

### 4. Portfolio Risk Score
Compute an aggregate portfolio risk score (0-100):
- Sum of all phase risk scores, normalized to 0-100
- < 30: Low risk portfolio (aggressive growth viable)
- 30-60: Moderate risk (phased approach recommended)
- > 60: High risk (conservative growth, additional validation needed)

### 5. Growth Metrics
Define KPIs for each phase:
- Brand awareness targets per new brand
- Revenue contribution expectations
- Market share goals
- Customer acquisition cost benchmarks
- Brand architecture health score targets

## Output Schema
Write to `node_outputs.baa_growth_plan` with keys:
- `phases`: list of `{phase_number, phase_name, duration_months, objective, actions: [], trigger_criteria: [], resource_requirements: {}, risks: [{category, severity, likelihood, risk_score, mitigation}], kpis: []}`
- `total_timeline_months`: int (sum of all phase durations)
- `portfolio_risk_score`: int (0-100)
- `portfolio_risk_assessment`: list of `{risk_category, aggregate_severity, aggregate_likelihood, aggregate_score, top_mitigation}`
- `growth_summary`: str (100-200 word narrative)
- `recommended_pace`: "aggressive" | "moderate" | "conservative"
- `phase_dependencies`: list of `{phase, depends_on: [phase_numbers]}`

## Integration Notes
- Downstream consumers: SKL-BAA-10 (strategy synthesis includes growth roadmap in implementation section)
- `portfolio_risk_score` > 70 triggers an advisory escalation in SKL-BAA-12
- SKL-BAA-11 (persister) archives the growth plan for future phase tracking
- Growth phases inform future BAA re-executions — the next run should check which phases have been completed
