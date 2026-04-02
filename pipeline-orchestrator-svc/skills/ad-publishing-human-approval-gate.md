---
name: ad-publishing-human-approval-gate
version: "1.0"
description: MANDATORY human approval gate before campaign activation -- HARDCODED, cannot be bypassed. RBAC-enforced with ADMIN-only approval and double-confirm for production (maps to SKL-APA33-08)
target_agents:
  - ad_publishing
triggers:
  - "human approval"
  - "approval gate"
  - "review before publish"
  - "approve ad campaign"
priority: 10
max_tokens: 1000
---

# Human Approval Gate

## Purpose
Enforce a MANDATORY human-in-the-loop approval step before any Meta Ads campaign is activated with real ad spend. This gate is HARDCODED into the pipeline and cannot be bypassed, disabled, or skipped by any configuration, API parameter, or environment variable. It presents campaign previews, budget commitments, and targeting summaries to an authorized user for explicit approval. RBAC enforcement ensures only ADMIN users can approve production campaigns.

## Methodology

### 1. Assemble Approval Request Payload
Compile a comprehensive review package from upstream outputs:
- **Campaign summary**: name, objective, total budget (display currency), duration
- **Ad set summaries**: segment names, targeting descriptions (human-readable), per-set budgets
- **Ad previews**: preview URLs from SKL-APA33-07 for each ad (desktop feed, mobile feed, Instagram)
- **Creative details**: headlines, primary text, CTAs, image thumbnails
- **Targeting overview**: age ranges, locations, interests, behaviors (human-readable summary)
- **Special Ad Category**: whether housing/credit/employment restrictions apply
- **Sandbox/Production flag**: prominently displayed, color-coded in approval UI
- **Estimated reach**: from targeting validation (daily/monthly estimates)
- **Total budget commitment**: sum of all ad set budgets with currency

### 2. Store Approval Request in Redis
Create an approval record with 24-hour TTL:
- Key: `apa:approval:{job_id}`
- Value: JSON containing full approval payload, created_at, expires_at, status
- Status lifecycle: `pending` -> `approved` | `rejected` | `expired`
- Include `approval_token` (UUID) for secure approval endpoint validation
- Set TTL to 86400 seconds (24 hours); expired approvals auto-reject

### 3. Return Awaiting Approval Status
Send callback to Django with:
- `status`: `awaiting_approval`
- `approval_request`: the compiled review package
- `approval_url`: endpoint for the frontend approval UI
- `expires_at`: ISO 8601 timestamp (24h from now)
- Pipeline execution PAUSES here; the executor yields control

### 4. RBAC Enforcement
When approval action is received:
- **VIEWER role**: DENIED -- return 403 with message "Viewers cannot approve ad campaigns"
- **EDITOR role**: ESCALATED -- create escalation to ADMIN, notify via SKL-APA33-12, return 202 with message "Approval escalated to admin"
- **ADMIN role**: ALLOWED -- proceed to approval validation
- Role is verified from the JWT claims in the approval request, cross-checked with tenant role assignment

### 5. Production Double-Confirm
When `sandbox_mode == false` (PRODUCTION):
- First approval: records `first_confirm_at`, returns prompt for second confirmation
- Second confirmation required within 5 minutes of first
- Display explicit warning: "This will spend real money on Meta Ads. Campaign budget: ${amount} {currency}. Confirm?"
- Log both confirmation timestamps in audit trail
- Sandbox mode: single confirmation sufficient

### 6. Process Approval Decision
On APPROVED:
- Update Redis record status to `approved`
- Record `approved_by` (user ID), `approved_at` (timestamp), `approval_notes` (optional)
- Resume pipeline execution, proceeding to SKL-APA33-09 (meta-publisher)

On REJECTED:
- Update Redis record status to `rejected`
- Record `rejected_by`, `rejected_at`, `rejection_reason`
- Execute full rollback of all created entities (campaign, ad sets, creatives, ads)
- Send callback with `status: "rejected"` and rejection details

On EXPIRED:
- Automatic rejection after 24h TTL
- Execute full rollback
- Send callback with `status: "expired"` and recommendation to re-run pipeline

## Output Schema
Write to `node_outputs.apa_approval` with keys:
- `approval_id`: string (UUID)
- `status`: string (pending | approved | rejected | expired)
- `sandbox_mode`: boolean
- `approved_by`: string | null (user ID)
- `approved_at`: string | null (ISO 8601)
- `rejection_reason`: string | null
- `double_confirmed`: boolean (true for production approvals)
- `budget_committed`: dict (amount, currency, display_string)
- `entities_pending_activation`: dict (campaign_count, adset_count, ad_count)
- `approval_duration_seconds`: float | null (time from request to decision)
- `rbac_action`: string (approved | denied | escalated)

## Integration Notes
- This gate is the ONLY path to campaign activation; there is no programmatic override, no admin flag, no environment variable that can skip it
- The approval UI renders in the frontend workspace view with preview iframes, budget summary, and approve/reject buttons
- Approval events are published to `apa-approval-audit-topic` Kafka topic for compliance audit trail, including the full approval payload and decision metadata
