# ERRATA-02 — Error Taxonomy Reconciliation

**Supersedes**: §18.4 in `Onboarding_Intelligence_Agent_Design_Document_v2_2.docx`
and error-code citations in `Onboarding_Intelligence_Agent_User_Story_Backlog_v2_1.docx`.

**Authoritative source**: `onboarding-intelligence-agent-svc/app/core/errors.py`
(`ErrorCode` enum + `ERROR_SPECS` dict). This errata records the reasoning;
the code is the single source of truth for codes, statuses, and operator
behaviour.

---

## 1. Extended taxonomy (ERR-17 … ERR-21)

Five conditions exist in the implementation that §18.4 has no row for.
Each was assigned a provisional code when it was first needed. This
errata promotes them to permanent.

| Code | Condition | HTTP | WS | Retryable | Operator behaviour | Added by |
|------|-----------|------|----|-----------|--------------------|----------|
| ERR-17 | Unknown skill id (PG-02 allowlist) | 404 | — | No | Caller or config bug, not a user error | A-06 |
| ERR-18 | Illegal session-state transition | 409 | — | No | State diagram violation; debug the caller | B-04 |
| ERR-19 | Django cannot reach the agent (reverse direction) | 503 | — | Yes | Chat shows "preparation temporarily unavailable", points at the manual path | C-01 |
| ERR-20 | Bad or missing X-Service-Token | 401 | — | No | Check caller's OIA_SERVICE_TOKEN matches SERVICE_TOKEN secret | C-01 |
| ERR-21 | SERVICE_TOKEN not configured on this service | 503 | — | No | Set the SERVICE_TOKEN secret and redeploy | C-01 |

## 2. Corrected card citations

Five acceptance criteria in the backlog cite a code that §18.4 assigns
to a different condition. The code column shows what the implementation
uses; the card column shows the incorrect citation that should be
updated in future backlog revisions.

| Card | Card cites | §18.4 meaning of that code | Correct code | Why |
|------|-----------|---------------------------|-------------|-----|
| A-06 AC-3 | ERR-03 (role denied) | Consent missing (IG-08), 403 | **ERR-04** | Both 403 but different operator remedies — consent modal vs. disabled action. Collapsing them makes a permissions bug look like a consent bug on call. |
| B-04 AC-2 | ERR-11 (illegal transition) | Grounding failure (OG-01), 200 | **ERR-18** | ERR-11 is a dropped value, not a state violation. Status also wrong (card says 409, ERR-11 is 200). |
| B-08 AC-1 | ERR-09 (consent missing) | Vision dependency degraded, 200 | **ERR-03** | ERR-09 is a degraded-mode banner, not a blocking consent error. Status also wrong (card says 403, ERR-09 is 200). |
| C-01 AC-3 | ERR-13 (agent unreachable) | Field conflict requiring a human, 202 | **ERR-19** | ERR-13 is an escalation card on the review page, not a network failure. Status also wrong (card says 503, ERR-13 is 202). |
| §5 PG-02 | ERR-06 (unknown skill id) | Live session already active, 409/4409 | **ERR-17** | ERR-06 would tell an operator a meeting is running when a skill id is simply wrong. |

## 3. Root cause

The cards were written before §18.4 was finalised, so a card naming a
code is not evidence the code is free. Four of the five miscitations
also pair the code with a status the taxonomy contradicts, which
confirms the codes were chosen for plausibility rather than looked up.

## 4. Complete taxonomy table

The authoritative table, combining the original §18.4 rows with the
extensions above. This replaces §18.4 for all future work.

| Code | Condition | HTTP | WS close | Retryable | Operator behaviour |
|------|-----------|------|----------|-----------|--------------------|
| ERR-01 | Invalid or expired JWT | 401 | 4401 | No | Re-authenticate |
| ERR-02 | Tenant mismatch (IG-05) | 403 | — | No | Blocked, security alert raised |
| ERR-03 | Consent missing or revoked (IG-08) | 403 | 4403 | No | Consent modal re-presented |
| ERR-04 | Role denied (PG-03) | 403 | — | No | Action hidden or disabled in UI |
| ERR-05 | Session not found or wrong state | 404 | 4404 | No | Session list refreshed |
| ERR-06 | Live session already active for company | 409 | 4409 | No | Offer to join or end the existing session |
| ERR-07 | STT dependency degraded | 200 | — | Yes | RECORD_ONLY banner |
| ERR-08 | LLM dependency degraded | 200 | — | Yes | Manual checkboxes banner |
| ERR-09 | Vision dependency degraded | 200 | — | Yes | Reduced-accuracy OCR badge |
| ERR-10 | Backend write failed, buffered | 202 | — | Yes | Saving delayed banner |
| ERR-11 | Grounding failure — value dropped (OG-01) | 200 | — | No | Counted in dropped_ungrounded, shown on review page |
| ERR-12 | Schema validation failure on model output (OG-04) | 502 | — | Yes | One retry with repair instruction, then escalate |
| ERR-13 | Field conflict requiring a human (SKL-OIA-14) | 202 | — | No | Escalation card on the review page |
| ERR-14 | Rate limited | 429 | 4429 | Yes | Retry-After honoured by the client |
| ERR-15 | Idempotency conflict — same key, different payload | 409 | — | No | Blocked; indicates a client bug, alerted |
| ERR-16 | GCS spool bound exceeded | 507 | — | No | Recording stopped gracefully with an explicit warning |
| ERR-17 | Unknown skill id (PG-02 allowlist) | 404 | — | No | Caller or configuration bug |
| ERR-18 | Illegal session-state transition | 409 | — | No | State diagram violation; debug the caller |
| ERR-19 | Django cannot reach the agent | 503 | — | Yes | Chat shows preparation temporarily unavailable |
| ERR-20 | Bad or missing X-Service-Token | 401 | — | No | Check OIA_SERVICE_TOKEN matches SERVICE_TOKEN |
| ERR-21 | SERVICE_TOKEN not configured | 503 | — | No | Set SECRET and redeploy |
