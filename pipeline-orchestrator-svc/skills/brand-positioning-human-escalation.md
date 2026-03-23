---
name: brand-positioning-human-escalation
version: "1.0"
description: Escalation triggers — insufficient WF1 data, low differentiation score, no clear winner, cultural sensitivity flags (maps to SKL-BPA-12)
target_agents:
  - brand_positioning
triggers:
  - "human escalation"
  - "human review"
  - "escalation"
  - "insufficient data"
  - "low confidence"
  - "sensitivity flag"
priority: 10
max_tokens: 450
---

# Human Escalation Protocol

## Purpose
Define the conditions under which the Brand Positioning Agent must pause automated processing and flag the strategy for human review. Escalation prevents the delivery of low-quality, risky, or culturally insensitive positioning recommendations.

## Methodology

### 1. Escalation Triggers
The following conditions trigger escalation. Any single trigger is sufficient:

| Trigger ID | Condition | Source Skill | Threshold |
|------------|-----------|-------------|-----------|
| ESC-01 | Insufficient upstream data | SKL-BPA-04 | `identity_confidence` < 0.3 |
| ESC-02 | Low differentiation score | SKL-BPA-09 | `differentiation_score` < 40 |
| ESC-03 | No clear positioning winner | SKL-BPA-06 | Top two candidates within 0.5 composite score |
| ESC-04 | Cultural sensitivity flag | SKL-BPA-03 | Any trend with `sensitivity: high` in ride-trends |
| ESC-05 | Low strategy confidence | SKL-BPA-10 | `strategy_confidence` < 50 |
| ESC-06 | Low value proposition fit | SKL-BPA-07 | `overall_fit` < 0.50 |
| ESC-07 | Critical POP gaps | SKL-BPA-09 | Any POP with `delivery_status: "Does Not Meet"` |
| ESC-08 | Large repositioning magnitude | SKL-BPA-08 | Migration vector magnitude > 60 on any map |
| ESC-09 | Contradictory brand guidelines | SKL-BPA-05 | RAG-sourced guidelines conflict with generated positioning |
| ESC-10 | Missing required upstream inputs | SKL-BPA-10 | Any required input absent from `data_completeness` |

### 2. Escalation Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **Advisory** | Informational; strategy can proceed but human review recommended | Include in report, no blocking |
| **Warning** | Quality concern; strategy delivered with prominent warning banner | Flag in `result_data`, highlight in executive summary |
| **Blocking** | Critical issue; strategy should NOT be delivered without human approval | Set `human_review_required: true`, include hold notice in callback |

**Trigger-to-Level Mapping**:
- Advisory: ESC-03, ESC-08
- Warning: ESC-01, ESC-05, ESC-06, ESC-07, ESC-09
- Blocking: ESC-02 (if < 20), ESC-04, ESC-10

### 3. Escalation Report
For each triggered escalation, produce a structured report entry:
- Trigger ID and human-readable description
- Severity level
- The specific metric value that triggered escalation
- Recommended human action (e.g., "Review cultural sensitivity of trend X before approving positioning")
- Suggested remediation path (e.g., "Upload brand guidelines to improve identity confidence")

### 4. Notification Mechanism
- Escalation data is included in the callback `result_data` under `escalation_report`
- Django backend routes escalation to the appropriate user based on tenant role permissions
- Blocking escalations set `status: "pending_review"` instead of `status: "completed"` in the callback

### 5. Auto-Resolution Rules
Certain escalations can auto-resolve if conditions change during the pipeline run:
- ESC-01 auto-resolves if Discovery agent provides sufficient enrichment data
- ESC-10 auto-resolves if optional-but-missing inputs become available from parallel execution
- Auto-resolved escalations are logged but not surfaced to the user

## Output Schema
Write to `node_outputs.bpa_escalation` and include in `result_data.escalation_report`:
- `triggered`: bool (true if any escalation fired)
- `human_review_required`: bool (true if any blocking escalation)
- `escalations`: list of `{trigger_id, description, severity, metric_value, threshold, recommended_action, remediation_path}`
- `auto_resolved`: list of `{trigger_id, resolution_reason}`
- `highest_severity`: "advisory" | "warning" | "blocking" | "none"

## Integration Notes
- This skill is evaluated after all other BPA skills have produced their outputs
- SKL-BPA-10 (strategy synthesis) includes the escalation report in its risk assessment section
- The callback client sends `status: "pending_review"` for blocking escalations instead of `status: "completed"`
