---
name: brand-architecture-human-escalation
version: "1.0"
description: Evaluate architecture confidence and risk signals to determine if human review is needed, generate escalation reports with specific review requests (maps to SKL-BAA-12)
target_agents:
  - brand_architecture
triggers:
  - "human escalation"
  - "review needed"
  - "low confidence"
  - "architecture review"
  - "escalation check"
priority: 7
max_tokens: 400
---

# Human Escalation Handler

## Purpose
Evaluate the completed architecture strategy for confidence and risk signals that warrant human review before the strategy is considered actionable. Architecture decisions have high organizational impact — this skill ensures that uncertain or high-risk recommendations are flagged for expert validation rather than being silently accepted.

## Methodology

### 1. Escalation Triggers
Evaluate all upstream outputs against escalation thresholds:

| Trigger | Source | Threshold | Severity |
|---|---|---|---|
| Low overall confidence | SKL-BAA-10 `confidence_score` | < 0.7 | Warning |
| Very low confidence | SKL-BAA-10 `confidence_score` | < 0.5 | Critical |
| Close model scores | SKL-BAA-06 `score_gap` | < 5 | Advisory |
| High transition magnitude | SKL-BAA-06 `transition_magnitude` | > 70 | Warning |
| Conditional recommendation | SKL-BAA-06 `recommendation_confidence` | == "conditional" | Advisory |
| Low naming consistency | SKL-BAA-08 `consistency_score` | < 40 | Advisory |
| High portfolio risk | SKL-BAA-09 `portfolio_risk_score` | > 70 | Warning |
| Incomplete required data | SKL-BAA-10 `data_completeness.required_present < required_total` | Any missing | Warning |
| Positioning misalignment | SKL-BAA-04 `positioning_alignment` for recommended model | < 15 (out of 25) | Warning |
| No BPA context available | Context loader | BPA context missing | Critical |

### 2. Severity Classification
- **Critical**: Architecture strategy should NOT be auto-accepted. Requires human approval before implementation.
- **Warning**: Strategy is usable but has significant uncertainty. Human review strongly recommended.
- **Advisory**: Minor concerns that should be noted but do not block acceptance.

### 3. Escalation Report Generation
For each triggered escalation, generate:
- `trigger_name`: Identifier matching the trigger table above
- `severity`: "critical" | "warning" | "advisory"
- `current_value`: The actual value that triggered escalation
- `threshold`: The threshold that was breached
- `description`: Human-readable explanation of the concern
- `review_request`: Specific question for the human reviewer
- `recommended_action`: Suggested resolution

### 4. Overall Escalation Decision
Compute the escalation decision:
- If any **critical** trigger fires: `escalation_required: true`, `escalation_level: "critical"`
- If any **warning** trigger fires: `escalation_required: true`, `escalation_level: "warning"`
- If only **advisory** triggers fire: `escalation_required: false`, `escalation_level: "advisory"`
- If no triggers fire: `escalation_required: false`, `escalation_level: "none"`

### 5. Escalation Actions
When `escalation_required` is true:
1. Add escalation metadata to the strategy response
2. Set `result_data.escalation_required = true`
3. Include the escalation report in `result_data.escalation_report`
4. Emit EVT-BAA-011 (HUMAN_REVIEW_REQUESTED) event
5. The Django frontend can render escalation status in the workspace UI

When `escalation_required` is false:
1. Add `escalation_required: false` to result_data
2. Include any advisory notes for informational purposes
3. Emit EVT-BAA-012 (EXECUTION_COMPLETED) event

### 6. Confidence Adjustment
If escalation is triggered, adjust the reported confidence:
- Critical escalation: Cap confidence at 0.5
- Warning escalation: Cap confidence at 0.7
- Advisory only: No adjustment

## Output Schema
Write to `node_outputs.baa_escalation` with keys:
- `escalation_required`: bool
- `escalation_level`: "critical" | "warning" | "advisory" | "none"
- `triggers_fired`: list of `{trigger_name, severity, current_value, threshold, description, review_request, recommended_action}`
- `trigger_count`: `{critical: int, warning: int, advisory: int}`
- `adjusted_confidence`: float (may be capped based on escalation)
- `escalation_summary`: str (one-paragraph summary for the human reviewer)
- `auto_accept_safe`: bool (true only if escalation_level is "none" or "advisory")

## Integration Notes
- This is the final analytical skill — runs after SKL-BAA-10 (strategy synthesis)
- Escalation metadata is included in the callback result_data sent to Django
- The Django workspace UI should render escalation badges when `escalation_required: true`
- Future enhancement: Kafka event triggers a notification to brand managers
- Escalation decisions are logged in the audit trail (baa-architecture-audit-topic)
