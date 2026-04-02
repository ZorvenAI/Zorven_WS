---
name: ad-publishing-human-escalation
version: "1.0"
description: Escalation handler for circuit breaker trips, rollback events, verification failures, and EDITOR approval attempts with admin notification and recommended actions (maps to SKL-APA33-12)
target_agents:
  - ad_publishing
triggers:
  - "escalate to admin"
  - "circuit breaker escalation"
  - "rollback notification"
  - "publishing failure alert"
priority: 1
max_tokens: 600
---

# Human Escalation Handler

## Purpose
Handle all escalation scenarios in the ad publishing pipeline that require human administrator intervention. This includes circuit breaker trips during image upload or campaign activation, rollback events, post-publish verification failures, and EDITOR-role approval attempts that need ADMIN authorization. Constructs actionable notification payloads with full context on what happened, what was affected, and recommended next steps.

## Methodology

### 1. Classify Escalation Type
Determine the escalation trigger from the pipeline state:
- **CIRCUIT_BREAKER_UPLOAD**: Image upload circuit breaker tripped (5 failures/60s in SKL-APA33-06)
- **CIRCUIT_BREAKER_ACTIVATION**: Campaign activation circuit breaker tripped (2 failures/30s in SKL-APA33-09)
- **ROLLBACK_EXECUTED**: Full entity rollback was triggered during activation
- **VERIFICATION_RED**: Post-publish verification found critical discrepancies (SKL-APA33-10)
- **EDITOR_APPROVAL**: EDITOR-role user attempted to approve a campaign (SKL-APA33-08)
- **APPROVAL_EXPIRED**: 24-hour approval window expired without decision
- Assign severity: CRITICAL (activation/rollback), HIGH (verification), MEDIUM (upload/approval)

### 2. Collect Escalation Context
Gather all relevant context for the administrator:
- **Affected entities**: campaign ID, ad set IDs, ad IDs, creative IDs
- **Entity states**: current status of each entity in Meta (ACTIVE, PAUSED, DELETED, unknown)
- **Error details**: Meta API error codes, error messages, HTTP status codes
- **Rollback status**: which entities were successfully rolled back, which failed
- **Timeline**: timestamps of each action leading to the escalation
- **Budget exposure**: whether any budget was spent before the issue was detected
- **Sandbox/Production**: prominently flag the environment

### 3. Generate Recommended Actions
Based on escalation type, provide specific actionable recommendations:
- **CIRCUIT_BREAKER_UPLOAD**: "Retry pipeline after Meta API recovers. {N} of {M} images uploaded successfully. Consider reducing batch size."
- **CIRCUIT_BREAKER_ACTIVATION**: "URGENT: Verify all entities are PAUSED in Meta Ads Manager. Rollback status: {success/partial/failed}. Manual verification required."
- **ROLLBACK_EXECUTED**: "All entities rolled back to PAUSED. Review Meta Ads Manager to confirm. Re-run pipeline when ready."
- **VERIFICATION_RED**: "Campaign is ACTIVE but has issues: {discrepancy_list}. Consider pausing campaign in Meta Ads Manager while investigating."
- **EDITOR_APPROVAL**: "Campaign {id} awaiting ADMIN approval. Budget: ${amount}. Editor {user_id} initiated review."
- **APPROVAL_EXPIRED**: "Campaign entities rolled back. Re-run pipeline to generate new approval request."

### 4. Send Escalation Callback
Send escalation notification to Django backend via callback:
- `status`: `escalated` (new status, distinct from failed/completed)
- `escalation`: dict with type, severity, context, recommended_actions
- Django backend routes to admin notification system (email, Slack webhook, or in-app alert)

### 5. Store Escalation in Redis
Record escalation for tracking and resolution:
- Key: `apa:escalation:{job_id}:{escalation_type}`
- Value: full escalation payload with timestamps
- TTL: 7 days (escalations should be resolved within this window)
- Track escalation resolution: `resolved_by`, `resolved_at`, `resolution_action`

### 6. Publish Kafka Audit Event
Emit to `apa-escalation-audit-topic`:
- Event type: `escalation_raised`
- Full escalation context for compliance and incident tracking
- Severity level for alerting infrastructure integration

## Output Schema
Write to `node_outputs.apa_escalation` with keys:
- `escalation_id`: string (UUID)
- `escalation_type`: string (CIRCUIT_BREAKER_UPLOAD | CIRCUIT_BREAKER_ACTIVATION | ROLLBACK_EXECUTED | VERIFICATION_RED | EDITOR_APPROVAL | APPROVAL_EXPIRED)
- `severity`: string (CRITICAL | HIGH | MEDIUM)
- `affected_entities`: dict (campaign_ids, adset_ids, ad_ids, creative_ids)
- `rollback_status`: dict | null (total_entities, rolled_back, failed)
- `budget_exposure`: dict (spent_before_issue, currency) | null
- `recommended_actions`: list[str]
- `escalated_at`: string (ISO 8601)
- `sandbox_mode`: boolean
- `resolution_status`: string (pending | resolved)

## Integration Notes
- Escalations with CRITICAL severity should trigger immediate admin notification; the Django backend can integrate with PagerDuty, Slack, or email via the existing notification infrastructure
- The `CIRCUIT_BREAKER_ACTIVATION` escalation is the highest-priority event in the APA pipeline -- it means entities may be in an inconsistent state between the pipeline's view and Meta's actual state
- Resolution tracking allows the admin to mark escalations as resolved through the Django admin UI, creating a complete incident lifecycle record
