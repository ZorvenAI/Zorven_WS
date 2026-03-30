---
name: campaign-arch-human-escalation
version: "1.0"
description: Evaluate whether campaign blueprint requires human review based on confidence thresholds, budget anomalies, Special Ad Category detection, and unrealistic KPI projections (maps to SKL-CAA-12)
target_agents:
  - campaign_architecture
triggers:
  - "human escalation"
  - "campaign review"
  - "quality gate"
  - "blueprint review"
priority: 10
max_tokens: 400
---

# Human Escalation

## Purpose
Evaluate the campaign blueprint's overall quality and risk profile to determine if human review is required before the blueprint is considered actionable. This is the final quality gate in the CAA pipeline.

## Methodology

### 1. Escalation Triggers
Flag for human review when any of the following conditions are met:

**Confidence Triggers**:
- Overall blueprint confidence < 0.7 (configurable via `CAA_CONFIDENCE_THRESHOLD`)
- Any individual skill confidence < 0.5
- Context completeness < 0.6 (too many missing upstream inputs)

**Budget Anomaly Triggers**:
- Total daily budget < $10 (insufficient for meaningful delivery)
- Total daily budget > $10,000 (unusually high, verify intent)
- Any ad set budget < $5/day (below Meta minimum for delivery)
- Budget allocation deviates > 20% from maturity-based defaults without RAG justification

**Special Ad Category Triggers**:
- Industry maps to Special Ad Category (housing, credit, employment, social issues/politics)
- Special Ad Category detected but targeting includes restricted options (age, gender, zip code)
- Requires manual confirmation of category classification

**KPI Anomaly Triggers**:
- Projected ROAS > 5x industry benchmark (unrealistically optimistic)
- Projected CPA < 50% of industry benchmark (unrealistically low)
- Projected CTR > 3x industry benchmark (inflated expectations)
- Zero conversions projected for any BOFU campaign

**Data Quality Triggers**:
- Benchmark data older than 30 days
- No competitor data available (SKL-CAA-03 returned empty)
- Audience reach estimate < 10,000 for any ad set

### 2. Escalation Report
When escalation is triggered, produce:
- Summary of all triggered conditions with severity levels
- Specific recommendations for human reviewer
- Priority ranking: `critical` (blocks launch), `important` (review before launch), `advisory` (note for optimization)
- Suggested actions per trigger (e.g., "Verify Special Ad Category classification with legal team")

### 3. Escalation Action
When human review is required:
- Emit EVT-CAA-012 (HUMAN_ESCALATION_TRIGGERED) via Kafka to `caa-architecture-events-topic`
- Mark blueprint with `requires_human_review: true`
- Include full escalation report in callback to Django

### 4. Non-Escalation Path
When all checks pass:
- Mark blueprint with `requires_human_review: false`
- Emit EVT-CAA-013 (QUALITY_GATE_PASSED) via Kafka
- Blueprint is considered ready for execution

## Output Schema
Write to `node_outputs.caa_escalation` with keys:
- `requires_human_review`: boolean
- `escalation_reasons`: list of `{trigger_category, metric, value, threshold, severity}`
- `reviewer_recommendations`: list[str]
- `suggested_actions`: list of `{trigger, action, priority}`
- `priority`: "critical" | "important" | "advisory" | "none"
- `quality_gate_passed`: boolean

## Integration Notes
- This is the final skill executed in the CAA pipeline, after SKL-CAA-11 (persister)
- Escalation does not block persistence — the blueprint is saved but flagged
- Human review status is included in the callback to Django for UI display
- Critical escalations should prevent automated campaign deployment
