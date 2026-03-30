---
name: brand-naming-human-escalation
version: "1.0"
description: Evaluate naming confidence and risk signals to determine if human review is needed, generate escalation reports with specific review requests (maps to SKL-NTA-14)
target_agents:
  - naming_tagline
triggers:
  - "human escalation"
  - "review needed"
  - "low confidence"
  - "naming review"
  - "escalation check"
priority: 7
max_tokens: 400
---

# Human Escalation Handler

## Purpose
Evaluate the completed naming brief for confidence and risk signals that warrant human review before naming decisions are considered actionable. Brand names are high-stakes, long-lived decisions — this skill ensures that uncertain or high-risk recommendations are flagged for expert validation rather than being silently accepted.

## Methodology

### 1. Escalation Triggers
Evaluate all upstream outputs against escalation thresholds:

| Trigger | Source | Threshold | Severity |
|---|---|---|---|
| Low overall confidence | SKL-NTA-12 `confidence_score` | < 0.7 | Warning |
| Very low confidence | SKL-NTA-12 `confidence_score` | < 0.5 | Critical |
| Top candidate low score | SKL-NTA-10 top `composite_score` | < 50 | Warning |
| Close candidate scores | SKL-NTA-10 top 2 `score_gap` | < 5 | Advisory |
| Trademark high risk | SKL-NTA-08 any recommended name `risk_score` | > 60 | Critical |
| No viable domain | SKL-NTA-06 top name `viability_score` | = 0 | Warning |
| Poor social availability | SKL-NTA-07 top name `viability_score` | < 20 | Advisory |
| Low naming coherence | SKL-NTA-02 `naming_coherence` | < 30 | Advisory |
| Architecture non-compliance | SKL-NTA-10 `strategic.architecture_compliance` | = 0 for any recommended name | Critical |
| No audience data available | SKL-NTA-02 `data_quality` | Both APA and VoCA absent | Warning |
| Incomplete required data | SKL-NTA-12 `data_completeness` | skills_contributed < 8 | Advisory |
| Low tagline pairing scores | SKL-NTA-11 best `pairing_score` | < 40 | Advisory |

### 2. Severity Classification
- **Critical**: Naming recommendations should NOT be auto-accepted. Requires human approval before use in brand registration or public launch.
- **Warning**: Recommendations are usable but have significant uncertainty. Human review strongly recommended.
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

### 5. Confidence Adjustment
If escalation is triggered, adjust the reported confidence:
- Critical escalation: Cap confidence at 0.5
- Warning escalation: Cap confidence at 0.7
- Advisory only: No adjustment

### 6. Escalation Actions
When `escalation_required` is true:
1. Add escalation metadata to the naming response
2. Set `result_data.escalation_required = true`
3. Include the escalation report in `result_data.escalation_report`
4. Emit audit event to `nta-naming-audit-topic`
5. The Django frontend can render escalation status in the workspace UI

## Output Schema
Write to `node_outputs.nta_escalation` with keys:
- `escalation_required`: bool
- `escalation_level`: "critical" | "warning" | "advisory" | "none"
- `triggers_fired`: list of `{trigger_name, severity, current_value, threshold, description, review_request, recommended_action}`
- `trigger_count`: `{critical: int, warning: int, advisory: int}`
- `adjusted_confidence`: float (may be capped based on escalation)
- `escalation_summary`: str (one-paragraph summary for the human reviewer)
- `auto_accept_safe`: bool (true only if escalation_level is "none" or "advisory")

## Integration Notes
- This is the final analytical skill — runs after SKL-NTA-12 (naming brief compilation)
- Escalation metadata is included in the callback result_data sent to Django
- The Django workspace UI should render escalation badges when `escalation_required: true`
- Escalation decisions are logged in the audit trail (nta-naming-audit-topic)
- Trademark critical escalation should prominently warn against proceeding without legal counsel
