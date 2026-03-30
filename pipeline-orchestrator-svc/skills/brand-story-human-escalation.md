---
name: brand-story-human-escalation
version: "1.0"
description: Evaluate narrative confidence and alignment scores to determine if human review is needed before finalizing the brand story (maps to SKL-BSA-14)
target_agents:
  - brand_story
triggers:
  - "human escalation"
  - "story review"
  - "narrative review"
  - "quality check"
priority: 10
max_tokens: 400
---

# Human Escalation

## Purpose
Evaluate the overall confidence score and specific quality metrics to determine if the generated brand story requires human review before being finalized.

## Methodology

### 1. Escalation Triggers
Flag for human review when:
- Overall confidence < 0.7 (configurable via BSA_CONFIDENCE_THRESHOLD)
- Any individual quality score < 0.5 (e.g., voice_consistency, archetype_alignment)
- Cross-artifact validation fails (inconsistent archetype expression)
- Mission/Vision positioning alignment < 0.6
- Channel consistency score < 0.5

### 2. Escalation Report
When escalation is triggered, produce:
- Summary of which metrics failed thresholds
- Specific recommendations for human reviewer
- Priority ranking (critical / important / advisory)
- Suggested focus areas for revision

### 3. Escalation Action
- Emit EVT-BSA-017 (HUMAN_ESCALATION_TRIGGERED) via Kafka
- Mark narrative package with `requires_human_review: true`
- Include escalation report in output

### 4. Non-Escalation Path
When all scores pass thresholds:
- Mark narrative package with `requires_human_review: false`
- Emit EVT-BSA-018 (QUALITY_GATE_PASSED)

## Output Schema
- `requires_human_review`: boolean
- `escalation_reasons`: list of `{metric, value, threshold, severity}`
- `reviewer_recommendations`: list[str]
- `priority`: "critical" | "important" | "advisory" | "none"

## Integration Notes
- This is the final quality gate before persistence (SKL-BSA-13)
- Escalation does not block persistence — the narrative is still saved but flagged
- Human review status is included in the callback to Django
