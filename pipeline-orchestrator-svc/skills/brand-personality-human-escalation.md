---
name: brand-personality-human-escalation
version: "1.0"
description: Evaluate personality confidence and risk signals to determine if human review is needed, generate escalation reports with specific review requests (maps to SKL-BPV-12)
target_agents:
  - brand_personality
triggers:
  - "human escalation"
  - "review needed"
  - "low confidence"
  - "personality review"
  - "escalation check"
priority: 7
max_tokens: 400
---

# Human Escalation Handler

## Purpose
Evaluate the completed personality profile for confidence and risk signals that warrant human review before the profile is considered actionable. Personality decisions directly affect all brand communications — this skill ensures that uncertain or high-risk profiles are flagged for expert validation rather than being silently accepted.

## Methodology

### 1. Escalation Triggers
Evaluate all upstream outputs against escalation thresholds:

| Trigger | Source | Threshold | Severity |
|---|---|---|---|
| Low overall confidence | SKL-BPV-10 `confidence_score` | < 0.7 | Warning |
| Very low confidence | SKL-BPV-10 `confidence_score` | < 0.5 | Critical |
| Close archetype scores | SKL-BPV-06 `score_gap` | < 5 | Advisory |
| Low profile differentiation | SKL-BPV-05 `profile_differentiation` | < 10 | Warning |
| Low psychographic coherence | SKL-BPV-01 `psychographic_coherence` | < 30 | Advisory |
| Low values hierarchy coherence | SKL-BPV-07 `hierarchy_coherence` | < 50 | Advisory |
| Low emotional consistency | SKL-BPV-08 `emotional_consistency` | < 40 | Advisory |
| Low voice coherence | SKL-BPV-09 `voice_coherence` | < 50 | Advisory |
| Values tier violation | SKL-BPV-07 `validation.tier_compliance` | false | Warning |
| Positioning misalignment | SKL-BPV-10 `positioning_alignment` | < 40 | Warning |
| No audience data available | SKL-BPV-01 data_quality | Both APA and VoCA absent | Critical |
| Incomplete required data | SKL-BPV-10 `data_completeness` | required_present < required_total | Warning |

### 2. Severity Classification
- **Critical**: Personality profile should NOT be auto-accepted. Requires human approval before use in content generation.
- **Warning**: Profile is usable but has significant uncertainty. Human review strongly recommended.
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
1. Add escalation metadata to the personality response
2. Set `result_data.escalation_required = true`
3. Include the escalation report in `result_data.escalation_report`
4. Emit audit event to `bpv-personality-audit-topic`
5. The Django frontend can render escalation status in the workspace UI

## Output Schema
Write to `node_outputs.bpv_escalation` with keys:
- `escalation_required`: bool
- `escalation_level`: "critical" | "warning" | "advisory" | "none"
- `triggers_fired`: list of `{trigger_name, severity, current_value, threshold, description, review_request, recommended_action}`
- `trigger_count`: `{critical: int, warning: int, advisory: int}`
- `adjusted_confidence`: float (may be capped based on escalation)
- `escalation_summary`: str (one-paragraph summary for the human reviewer)
- `auto_accept_safe`: bool (true only if escalation_level is "none" or "advisory")

## Integration Notes
- This is the final analytical skill — runs after SKL-BPV-10 (character brief synthesis)
- Escalation metadata is included in the callback result_data sent to Django
- The Django workspace UI should render escalation badges when `escalation_required: true`
- Escalation decisions are logged in the audit trail (bpv-personality-audit-topic)
- Future enhancement: Kafka event triggers a notification to brand managers
