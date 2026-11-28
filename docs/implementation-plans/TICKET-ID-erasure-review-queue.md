# Implementation Plan: Erasure Review Queue (TICKET-ID)

**Follows:** PR #705 (erasure holds sessions with signed meeting records),
`TICKET-ID-signed-meeting-records.md` AC-10, `contractual-documents-design.md`
decision D7 (legal hold for a period the workspace sets).
**Status:** Draft — awaiting approval. No code until approved.

## 1. User Story

As a workspace **owner or admin**, I want to see the erasure requests that were
held back because the person's sessions contain signed meeting records, and to
decide each one, so that GDPR erasure requests are answered on time and signed
agreements are not destroyed by accident.

### Acceptance criteria

- **AC-1:** An owner or admin can list the held erasure requests for their
  workspace: who the request is about, when it was made, why, and which
  sessions and meeting records are held. Editors and viewers get 403. Another
  workspace's requests are never visible (404 on direct access).
- **AC-2:** Each held request can be resolved in one of two ways, and both need
  a written reason (at least 10 characters):
  - **Keep under legal hold:** the held sessions stay until a hold-until date,
    which defaults to the workspace's hold period (D7, default 7 years). The
    request leaves the queue as decided.
  - **Erase anyway:** the held sessions are erased with the normal cascade,
    including their signed records and audit trail. The person resolving it
    must type the subject's name to confirm.
- **AC-3:** Every decision is recorded: who decided, when, which outcome, the
  reason, and the hold-until date for a kept request. A decided request cannot
  be decided again (409).
- **AC-4:** A kept request is not re-queued by the daily retention job before
  its hold-until date. On that date it returns to the queue. An erased request
  is never re-queued.
- **AC-5:** Erase anyway leaves a tombstone in the erasure log: the record
  numbers and fingerprints only, with no personal data. This is proof that a
  signed record existed and why it's gone.
- **AC-6:** The queue is reachable from a new **Privacy** page (owner/admin
  only), which also hosts the existing, currently unrendered
  `RetentionSettings` and a new legal-hold-period setting.
- **AC-7:** Held requests waiting 25 days or more are highlighted. GDPR gives
  one month to respond (Art. 12(3)).

## 2. Assumptions

1. Only owners and admins decide, the same roles that can already request an
   erasure (`IsTenantAdmin`).
2. Erase anyway erases only the sessions that were held. Everything else in the
   request was already erased by the first run.
3. One decision covers the whole request, not each session separately. A
   request that needs a split can be kept, and a narrower request raised.
4. The hold period is a whole number of years from 1 to 25, default 7 (D7).
   Changing it affects only future decisions, not existing hold-until dates.
5. The 25-day highlight is fixed in code.
6. Issued records never go back to draft, so a held session stays held until
   someone decides.

## 3. Tech Stack

Django 4.2 + DRF (`apps.onboarding`, label `onboarding_sessions`), Celery for
the erase-anyway cascade, Next.js 15 + React 19 with `apiClient`, the Digital
Twilight design system, Jest + Testing Library, Playwright, and pytest against
the real Postgres (Neon) and Redis used by the existing erasure tests.

## 4. Scope and Non-Goals

**In scope**
- New fields on `ErasureLog` for the decision, a hold-period field on
  `RetentionConfig`, and a migration with a backfill.
- Four API endpoints: list held requests, keep, erase anyway, and get/set the
  hold period (an extension of the existing retention endpoint).
- A way for the erasure cascade to erase held sessions, used only by erase
  anyway.
- The retention job honours hold-until dates.
- A Privacy page with the queue, the retention settings and the hold period.

**Not in scope**
- Emailing admins when something is held (§9 Q1).
- Exporting held data to the subject (subject access is a separate GDPR right).
- Per-session decisions within one request.
- Any change to *which* sessions get held. That is #705's logic, unchanged.

## 5. Detailed Design

### 5.1 Data Model / Migrations

One migration (next free number) in `onboarding_sessions`:

`ErasureLog`, new fields:

| Field | Type | Notes |
|---|---|---|
| `review_status` | `CharField(16)`: `""`, `PENDING`, `KEPT`, `ERASED` | Default `""` (nothing held). The cascade sets `PENDING` when it holds anything |
| `reviewed_by` | FK `auth.User`, `SET_NULL`, nullable | |
| `reviewed_at` | `DateTimeField`, nullable | |
| `review_reason` | `TextField`, blank | |
| `hold_until` | `DateField`, nullable | Set when kept |

An index on `(tenant, review_status)` speeds up the queue query.

`RetentionConfig`, new field: `legal_hold_years`
(`PositiveSmallIntegerField`, default 7, with a check constraint for 1–25).

**Backfill:** rows whose `completion_report.manual_review_required` is true get
`review_status=PENDING`, so requests held since #705 appear in the queue. The
migration's reverse removes the fields. Existing migrations are not edited.

The decision lives on `ErasureLog` rather than a new model because one request
has exactly one current decision, and `ErasureLog` is already the per-request
record that the API and the retention job read.

### 5.2 API Contract

All `IsAuthenticated` + `IsTenantAdmin`, all tenant-scoped (another tenant's id
gives 404).

**`GET /api/v1/onboarding/erasure/review/`**: held requests, oldest first.
`?status=KEPT|ERASED` lists decided ones instead.
```json
[{
  "id": 42,
  "subject_name": "Maria Rossi",
  "reason": "retention_enforcement",
  "requested_at": "2026-11-02T10:00:00Z",
  "days_waiting": 26,
  "overdue": true,
  "held": [{"session_id": "6", "company_name": "Pomodoro",
            "records": [{"record_number": "MR-000085-v1", "status": "COMPLETED"}]}],
  "review_status": "PENDING",
  "reviewed_by": null, "reviewed_at": null, "review_reason": "", "hold_until": null
}]
```

**`POST .../review/<id>/keep/`**, body `{"reason": "...", "hold_until": "2033-11-28"}`.
`hold_until` is optional and defaults to today plus the workspace's hold
period. Returns `200` with the updated request. Errors: `400` if the reason is
under 10 characters or the date isn't in the future; `409` if the request was
already decided or isn't held.

**`POST .../review/<id>/erase/`**, body `{"reason": "...", "confirm_subject": "Maria Rossi"}`.
Returns `202`; the cascade runs in Celery. Errors: `400` if `confirm_subject`
doesn't match the subject exactly or the reason is too short; `409` if already
decided.

**`GET/PATCH /api/v1/onboarding/retention/`** (existing) gains
`legal_hold_years`. It is validated to 1–25, and only owner/admin can set it,
as with the existing fields.

### 5.3 Business Logic / Services

- **Cascade:** `ErasureCascade.execute(..., force_session_ids=None)`. The
  #705 held-session filter skips the ids in `force_session_ids`; nothing else
  changes. When the cascade holds anything, it sets `review_status=PENDING` on
  the log as well as filling the report fields it fills today.
- **`erasure/review.py`:**
  - `keep(log, user, reason, hold_until=None)`: locks the row
    (`select_for_update`), checks it is `PENDING`, works out `hold_until`,
    writes the review fields, logs `erasure_review_kept`.
  - `erase_anyway(log, user, reason, confirm_subject)`: same lock and check;
    records the reviewer and reason, and queues `execute_erasure_cascade` with
    the held session ids and the log id. The status stays `PENDING` while the
    task runs. On success the task builds the tombstone from the records
    before deleting them, then sets `ERASED`. On failure it leaves `PENDING`
    and writes the error into the report, so the request stays in the queue.
- **Retention job:** skips a subject whose latest log is `PENDING`, or `KEPT`
  with `hold_until` in the future. A `KEPT` log past its `hold_until` is set
  back to `PENDING`, so it returns to the queue (AC-4). `ERASED` subjects have
  no sessions left, so they drop out on their own.

### 5.4 Async / Background Jobs

Erase anyway reuses `execute_erasure_cascade`, extended to take
`force_session_ids` and the review log's id. The return of expired holds runs
inside the existing daily `enforce_retention_windows` job. No new beat job.

### 5.5 Frontend

- **Route `/privacy`**: owners and admins only; others are redirected to
  `/dashboard`. A **Privacy** nav entry is shown under the same condition as
  Team.
- **`ErasureReviewQueue`**: a table of held requests showing subject, days
  waiting, and the held sessions and records. Rows waiting 25+ days are marked
  overdue. Each row has two actions:
  - **Keep**: an inline form with a required reason and a hold-until date,
    pre-filled from the hold period.
  - **Erase anyway**: an inline form with a reason, a field to type the
    subject's name, and a plain warning that signed records and their audit
    trail will be permanently deleted. Confirm stays disabled until the typed
    name matches.
  - A **Decided** tab lists kept and erased requests with reviewer, date,
    reason and hold-until (read-only).
- **`RetentionSettings`** (already built) is rendered on the page, with the
  hold period added next to the retention window.
- API calls go through `apiClient`, in `src/lib/erasure-review.ts`.

### 5.6 Deployment

No new service, environment variable or infrastructure. One migration, applied
by the existing `zorven-migrations` Cloud Run job on deploy and with
`migrate_schemas --shared` locally. No Kong change: the routes sit under the
existing JWT-protected `/api/v1`. Docker Compose is unchanged.

### 5.7 Delivery Order

1. Migration, model fields and backfill.
2. Cascade `force_session_ids`; the cascade sets `PENDING`; the tombstone.
3. Decision service and the review endpoints; hold period on the retention
   endpoint.
4. Retention job: honour `hold_until` and return expired holds to the queue.
5. Frontend: API client, queue component, Privacy page, nav, hold-period field.
6. Tests at each step, then a manual check in the browser on local Docker.

## 6. Testing Strategy

Real Postgres and Redis, as the existing erasure tests use. No mocks of our own
code or data stores.

### 6.1 Unit Tests
- Decision rules: a reason under 10 characters is refused; the confirmation
  must match the subject exactly; a decided request refuses a second decision;
  a request that isn't held refuses both; `hold_until` must be in the future
  and defaults to today plus the hold period.
- `days_waiting` and `overdue` at 24, 25 and 26 days.
- The tombstone holds record numbers and fingerprints and no names, emails or
  text.
- Frontend (Jest): held rows render with the overdue style; Erase stays
  disabled until the typed name matches; both forms need a reason; the Decided
  tab shows reviewer, reason and hold-until; a non-admin never sees the page or
  the nav entry.

### 6.2 Property-Based Tests
- Hypothesis: for any mix of sessions with and without signed records, the
  default run erases exactly the unheld sessions, and a run forcing the held
  ids erases all of them. The result doesn't depend on order.

### 6.3 Integration Tests
- Admin through the API: list → keep → gone from pending, listed as decided
  with `hold_until`; the held sessions and records still exist.
- Erase anyway: list → erase → task runs → held sessions, their records and
  their audit events are gone; status `ERASED`; reviewer, reason and tombstone
  recorded.
- Editors and viewers get 403 on every endpoint; another tenant's request
  gives 404.
- Two simultaneous decisions on one request → exactly one succeeds, the other
  gets 409.
- Retention job: skips `PENDING` and in-date `KEPT`; returns an expired `KEPT`
  to `PENDING`; the backfill puts #705-era held requests in the queue.
- The hold period validates 1–25 and only owner/admin can set it.

### 6.4 End-to-End Tests
- Playwright on `/privacy`, with the API served by `page.route` like the
  existing layout spec: an admin keeps a request with a reason and it moves to
  Decided; Erase only becomes clickable after the name is typed.
- Manual on local Docker: hold a real request with a signed record, as in the
  #701 browser check, then keep one and erase another in the UI, and check the
  database and the tombstone.

## 7. GCP Cost Estimate

| Item | Change | Monthly cost |
|---|---|---|
| Cloud Run: backend, celery-worker | A few extra requests and one task per decision | ~$0 (within existing capacity) |
| Database (Neon) | Five columns and an index on a small table, one column on another | ~$0 |
| Memorystore, Pub/Sub, GCS | None | $0 |
| **Total** | | **~$0 / month** |

Estimated from the change itself rather than pulled from `gcloud` billing:
it creates no resources, and erasure decisions are rare (single digits a month
per workspace).

## 8. Branching & PR Workflow

- Branch `feature/erasure-review-queue` from `development_main`.
- One PR into `development_main`, using conventional commits (`feat:`, `test:`).
- CI must be green (backend, frontend, OIA unaffected) before merging.
- Reaches `main` with the next production release, per the two-tier workflow.

## 9. Risks & Open Questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | Notify admins (email or in-app) when something is held? | **Not in this story.** The overdue highlight covers the deadline. Add email once Mailgun works again. |
| Q2 | Who decides: owner and admin, or owner only? | **Owner and admin**, the same people who can request an erasure. |
| Q3 | Default hold period? | **7 years**, as D7 suggests. Your legal advice may say otherwise; it's one setting. |
| Q4 | Can someone undo a "keep" before its date (decide again)? | **No in this story.** A decided request is final. Releasing a hold early would be a separate action with its own reason, added if needed. |

**Risk:** erase anyway permanently destroys signed records. The typed-name
confirmation, the required reason, the recorded reviewer and the tombstone make
it deliberate and traceable. It can't be undone, by design.

## 10. Approval

Development starts only once this plan is explicitly approved, including
answers to Q1–Q4 or acceptance of the recommendations.
