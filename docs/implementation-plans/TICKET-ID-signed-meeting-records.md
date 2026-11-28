# Implementation Plan: Signed Meeting Records and Contractual Questions (TICKET-ID)

**Status:** Approved (by the user, 2026-11-25) — step 1 of §5.8 in progress
**Date:** 2026-11-25
**Target Environment:** GCP — Production
**Design:** [contractual-documents-design.md](contractual-documents-design.md) (decisions D1–D8 accepted as recommended on 2026-11-25)

> Development on this story may not begin until Status = Approved.
>
> `TICKET-ID` is a placeholder. No ticket number was given; it must be filled in
> before the branch is created.

---

## 1. User Story

**As** an agency running onboarding meetings with a client,
**I want** each meeting's description and clean transcript turned into a
document both parties sign, that can be downloaded and shared, with every new
recording in the session added as its own dated and signed section,
**so that** there is no later confusion about what the two parties discussed and
agreed.

**Addition (2026-11-25):** the first meeting's questionnaire must include the
mandatory questions needed to complete the signed document (customer name,
company legal name, and other contractual information), starting from a template
with the custom questions built on top.

### Acceptance criteria

| # | Criterion |
|---|---|
| AC-1 | Each recording with a description or clean transcript can be turned into a Meeting Record containing numbered agreements, description, clean transcript, attendance, consent, and meeting date and time. |
| AC-2 | Issuing a record freezes its content. Afterwards neither the record nor the recording's description and transcript can be changed by any endpoint. |
| AC-3 | One authorised signatory per party must sign; more can be added. The client signs without an account through an emailed link and a one-time code. |
| AC-4 | A signatory can sign, sign with remarks, or decline with a reason. Text is never edited. A remark added after another party signed must be acknowledged by that party before completion. |
| AC-5 | Every action is written to an append-only audit trail, printed in the PDF as a certificate of completion. |
| AC-6 | The record downloads as a PDF. Before completion it is watermarked as not fully signed. All parties are emailed the final PDF. |
| AC-7 | A Session Binder PDF compiles every record in the session in date order, each with its own signature section. Adding a meeting never alters an existing record. |
| AC-8 | Share links expire, can be revoked, can carry a passcode, and log every access. |
| AC-9 | Anyone can check a PDF or record number against the stored fingerprint. |
| AC-10 | Issued records are exempt from the retention sweep and held from erasure for a tenant-set period (default 7 years); held erasure requests are logged. |
| AC-11 | Every questionnaire for a company whose contractual details are incomplete includes the mandatory contractual questions, placed first, in addition to the requested number of custom questions. |
| AC-12 | Answers to contractual questions are extracted to company fields through the existing review flow, and a record cannot be issued while a required party detail is missing or unreviewed. |
| AC-13 | Mandatory questions already answered and reviewed are not asked again in later meetings. |

## 2. Assumptions

1. The agency is the tenant and the client is the tenant's single `Company`.
2. Volume: up to 200 records per month across all tenants in the first year, about 2 MB per PDF, three signatories on average, about 10 emails per record.
3. Decisions D1–D8 stand as recommended: record is evidence and a signed services agreement prevails; one signatory per party; no client account; in-house signing behind an interface; sign with remarks or decline; 7-year hold; admins and editors may share.
4. Clause wording is a draft until a lawyer reviews it. The clause is versioned so wording can change without a code release.
5. English only for clause text and emails in this release.
6. A production email provider will be supplied by the team. Today `EMAIL_BACKEND` defaults to the console backend, so nothing is delivered. This is a launch blocker for signing, not for records and PDFs.
7. The embedded cryptographic PDF seal is out of this plan (design phase 4).
8. Public endpoints are exposed through Kong locally by adding routes in `deployment/docker/kong/kong.yaml`, following the existing `invite-accept-route`. The skill notes record that Kong is not deployed to Cloud Run, so in production the backend is reached directly; to be confirmed with the team.
9. `fpdf2` (already a dependency) is adequate for the layout. No new PDF library.
10. Contractual details that are sensitive identifiers (tax number, bank details) are **not** asked aloud in a recorded meeting. See §5.5.
11. Existing recordings, including recording 85, can be issued once signatories are added and party details completed.

## 3. Tech Stack

- Python 3.12 + Django REST Framework (backend, app label `onboarding_sessions`). Default stack, no deviation.
- Next.js 15 + TypeScript (frontend).
- FastAPI OIA service: small prompt and type-hint changes only.
- Celery (existing queues) for email and PDF generation.

## 4. Scope and Non-Goals

**In scope:** design phases 1–3 (record and PDF, signing, sharing and verification, legal hold) plus contractual questions.

**Not in scope**

- Drafting a services agreement (terms, pricing, liability).
- A third-party signing provider; only the interface it would plug into.
- Embedded PDF seal with a platform certificate.
- Certified or qualified signatures, government ID checks.
- Repairing older recordings whose transcripts were mixed before the per-recording fix.
- Languages other than English.
- Legal review itself. This plan delivers the mechanism, not a legal opinion.

**What this does not deliver:** a guarantee of enforceability. It delivers
attribution, consent, integrity and an audit trail, which is what makes the
record credible evidence.

## 5. Detailed Design

### 5.1 Data Model / Migrations

One new migration in `apps/onboarding/migrations/`, one in `onboarding/migrations/`. No existing migration is edited.

**New models** (all with `tenant`, `created_at`, `updated_at`, `TenantScopedManager`):

| Model | Key fields | Constraints |
|---|---|---|
| `MeetingRecord` | `session`, `recording`, `record_number`, `version`, `supersedes`, `status`, `snapshot` (JSON), `content_hash`, `clause_version`, `issued_at`, `issued_by`, `expires_at`, `completed_at`, `pdf_gcs_path`, `pdf_hash`, `legal_hold_until` | Unique `(tenant, record_number)`; one non-terminal record per recording |
| `RecordSignatory` | `record`, `party`, `name`, `email`, `title`, `user`, `required`, `status`, `token_hash`, `token_expires_at`, `code_hash`, `code_expires_at`, `code_attempts`, `signed_at`, `typed_name`, `remarks`, `remarks_acknowledged_at`, `decline_reason`, `ip_address`, `user_agent`, `consent_version` | Unique `(record, email)` |
| `RecordEvent` | `record`, `signatory`, `actor_user`, `event_type`, `detail`, `ip_address`, `occurred_at` | Insert-only: `save()` rejects updates, `delete()` raises |
| `RecordShare` | `record` or `session`, `token_hash`, `created_by`, `recipient_email`, `passcode_hash`, `expires_at`, `revoked_at`, `access_count`, `last_accessed_at` | Check: exactly one of `record`, `session` |

**Changed models**

| Model | Change |
|---|---|
| `Question` | Add `category` (`BRAND` default, `CONTRACTUAL`) and `mandatory` (bool, default false) |
| `Company` | Add `signatory_name`, `signatory_title`, `signatory_email`, `billing_contact_email`, `registered_address`, `registration_number` (all nullable text) |
| `RetentionConfig` | Add `signed_record_hold_days` (default 2555) |

`legal_name` and `decision_maker` already exist and are reused.

### 5.2 API Contract

**Authenticated**, under `/api/v1/onboarding/`, tenant-scoped, admin or editor:

| Method and path | Result |
|---|---|
| `GET sessions/<pk>/records/` | Records for a session with status and signatories |
| `POST recordings/<pk>/records/` | Create DRAFT. 409 if a non-terminal record exists; 400 if nothing to record |
| `GET records/<pk>/` | Detail, signatories, events, readiness checklist |
| `PUT records/<pk>/signatories/` | Replace signatories. DRAFT only |
| `POST records/<pk>/issue/` | Freeze, fingerprint, send. 409 if readiness checklist fails |
| `POST records/<pk>/sign/` | Agency signatory signs |
| `POST records/<pk>/acknowledge-remarks/` | Agency acknowledges a later remark |
| `POST records/<pk>/void/` | Void with reason. 409 if COMPLETED |
| `POST records/<pk>/remind/` | Resend to pending signatories |
| `POST records/<pk>/supersede/` | New DRAFT version from a DECLINED, VOIDED or EXPIRED record |
| `GET records/<pk>/pdf/` | Short-lived download link |
| `GET sessions/<pk>/binder/` | Short-lived binder download link |
| `POST records/<pk>/shares/`, `POST sessions/<pk>/shares/` | Create share link; returns the token once |
| `DELETE shares/<pk>/` | Revoke |

**Public** (no login, token in path, throttled per token and per IP):

| Method and path | Result |
|---|---|
| `GET public/records/sign/<token>/` | Parties, meeting date, masked email, status |
| `POST public/records/sign/<token>/code/` | Email a one-time code |
| `POST public/records/sign/<token>/verify/` | Exchange code for a 30-minute signing session; returns the record content |
| `POST public/records/sign/<token>/submit/` | `action`: `sign`, `sign_with_remarks`, `decline`, `acknowledge_remarks` |
| `GET public/records/shared/<token>/` | Read-only content and download link; passcode in header when set |
| `POST public/records/verify/` | PDF upload or `record_number` + hash; returns match or no match, nothing else |

Unknown, expired or revoked tokens all return the same 404, so a caller cannot tell them apart.

### 5.3 Business Logic / Services

New package `apps/onboarding/records/`:

| Module | Responsibility |
|---|---|
| `agreements.py` | Split the `## Agreements` bullets out of the stored description into numbered items by text parsing. No model call, no rewording. Returns the rest of the description unchanged. |
| `snapshot.py` | Build the frozen snapshot (parties, meeting metadata, attendees, consent, agreements, description, transcript lines, completeness, clause text and version). Canonical JSON (sorted keys, UTF-8, fixed separators) and SHA-256. |
| `readiness.py` | Checklist before issue: content present; one required signatory per party with email; required party details present and reviewed; transcript completeness acknowledged if gaps exist. |
| `lifecycle.py` | State transitions under `select_for_update`; writes a `RecordEvent` for each. |
| `signing.py` | `SigningProvider` interface and the in-house implementation: token and code generation, hashing, verification, signature capture. |
| `pdf.py` | `build_record_pdf(snapshot, signatories, events)` and `build_binder_pdf(records)` with `fpdf2`. Pure functions of their inputs, so output can be tested without storage. |
| `storage.py` | Write-once upload of snapshot and PDF to GCS; signed download links via the existing `gcs_service`. |
| `sharing.py` | Share token and passcode handling, access logging. |
| `emails.py` | Signing request, reminder, completion, decline and remark notices. |

**Source freeze (AC-2).** `update_recording_summary` and the process callback
skip `description` and `transcript_clean` when the recording has a record in
any state other than DRAFT, and log that they did.

**Erasure and retention (AC-10).** The `django_sessions` and `gcs_blobs` erasure
stores and `enforce_retention_windows` skip recordings and objects under an
active hold and report them as held in the completion report. A new
`signed_records` artifact type is registered so the store registry's
completeness check covers it.

**Signing rules**

- Tokens are 32 random bytes, URL-safe, stored as SHA-256 hashes; default life 14 days.
- Codes are 6 digits, 10-minute life, 5 attempts, then a new code is required.
- The submit call must carry the content fingerprint the signer was shown; a mismatch is rejected.
- The record becomes COMPLETED when every required signatory has signed and no remark is unacknowledged.

### 5.4 Async / Background Jobs

| Task | Queue | Trigger |
|---|---|---|
| `send_record_email` | `celery` | Issue, remind, complete, decline, remark |
| `finalize_record_pdf` | `celery` | Completion: build PDF, store, hash, email parties |
| `expire_records` | Beat, daily | ISSUED or PARTIALLY_SIGNED past `expires_at` become EXPIRED |

Draft and in-progress PDFs are built on request and not stored.

### 5.5 Contractual Questions

**Recommendation: a fixed template owned by Django, merged with the generated
questions — not generated by the model.**

Reasoning. A model asked to "include the contractual questions" will usually
do it, sometimes reword them, and occasionally drop one when trimming to the
requested count (the existing trim removes questions from the best-covered
group). For details a signature depends on, "usually" is not acceptable. A
fixed list is guaranteed, reviewable by a lawyer, and identical for every
client.

**How it works**

1. `apps/onboarding/contract_fields.py` (pure data, like `field_map.py`) defines
   each mandatory item: question text, target company field, whether it is
   required to issue a record, and how it may be collected.
2. When a questionnaire is written (`_write_questions` path in `views.py` and
   the template `clone` action), Django prepends every mandatory question whose
   target field is still empty or unreviewed, with `category=CONTRACTUAL`,
   `mandatory=True`. They are **in addition to** the requested count.
3. The OIA generator is told which fields the mandatory set covers and
   instructed not to ask about them, so custom questions are not spent on
   duplicates. Its trim and top-up logic never sees mandatory questions.
4. Mandatory questions cannot be deleted or skipped in the questionnaire editor;
   their wording is fixed.
5. In the meeting they appear first, under a "Contract details" heading, and
   are scored and extracted through the existing live and process flow.
   Extracted values go through the existing review step.
6. In later meetings, only items still missing are asked (AC-13).

**Starting template**

| Question | Field | Needed to issue | Collected |
|---|---|---|---|
| Registered legal name of the company | `legal_name` | Yes | Spoken, confirmed in writing |
| Registered business address | `registered_address` | Yes | Spoken, confirmed in writing |
| Full name of the person authorised to sign | `signatory_name` | Yes | Spoken, confirmed in writing |
| Their title or role | `signatory_title` | Yes | Spoken |
| Their email address for signing | `signatory_email` | Yes | Written only |
| Who makes brand and campaign decisions | `decision_maker` | No | Spoken |
| Billing contact email | `billing_contact_email` | No | Written only |
| Company registration number | `registration_number` | No | Written only |

Tenants can add their own mandatory questions later; not in this release.

**Three limits worth knowing**

- **Speech-to-text is weakest exactly here.** Legal names, addresses and email
  addresses are the things it mishears most. So spoken answers are treated as a
  first draft: the agency confirms them in review, and the client sees and
  confirms their own party details on the signing page before signing. "Written
  only" items are entered in the Prepare screen, never extracted from audio.
- **Do not collect tax or bank identifiers by voice.** They would sit in a
  recording and three transcript tiers and be printed in a shared document. They
  are left out of the template.
- **Not everything is known in the first meeting.** The person in the room may
  not be the authorised signatory. Missing items block issuing the record, not
  the meeting; they can be filled in the Prepare screen.

**OIA changes (small)**

- `generate_questionnaire.py`: accept `covered_fields` in hints and add one
  prompt line excluding them.
- `field_types.py`: type hints for the six new company fields.
- Django passes `covered_fields` with the generation request; the field
  vocabulary endpoint already serves new fields once they are in `field_map.py`.

**As built (step 1) — where it differs from the above**

- The covered topics travel on the existing field-vocabulary endpoint
  (`covered: [{field, topic}]`) rather than on each generation request. The
  agent already fetches that endpoint once and caches it, and the list is a
  property of the schema, not of a request.
- Only the three spoken details gained extraction type hints
  (`registered_address`, `signatory_name`, `signatory_title`). The three
  written-only ones are deliberately not extraction targets, and Django's
  company-fields endpoint refuses them from the agent as a backstop.
- A detail the agent extracted but nobody has confirmed still counts as
  outstanding, so its question is asked again.
- Mandatory questions are left out of the WF1/WF2/WF3 coverage figure.
- There is no questionnaire editor in the frontend today, so "cannot delete"
  is enforced by the backend (`rewrite` and `drop` return 409); the checklist
  shows a "contract details · required" tag instead of a separate heading, to
  keep one numbered list.
- Written-only details are entered on the existing Company Info form, in a new
  "Contract details" block, until the Prepare screen exists (step 2).
- The Review tab's field total rises from 39 to 45.

### 5.6 Frontend

| Piece | Detail |
|---|---|
| `DocumentsTab.tsx` | New tab on the session screen: one row per meeting (date, time, status, signatories), actions Prepare, Issue, Sign, Remind, Download, Share, Void; Download Binder |
| `RecordPrepare.tsx` | Preview, signatory editor, party-detail form, readiness checklist |
| `RecordDocument.tsx` | Shared read-only renderer used by preview, signing and shared view |
| `app/sign/[token]/page.tsx` | Public signing ceremony; no `useAuth` |
| `app/shared/[token]/page.tsx` | Public read-only view |
| `app/verify/page.tsx` | Public verification |
| `QuestionChecklist.tsx` | "Contract details" group, mandatory badge, no delete |
| `src/lib/meeting-records.ts` | Typed client; authenticated calls through `apiClient`, public calls through a token-only helper in the same module |

### 5.7 Deployment

| Place | Change |
|---|---|
| Migrations | `migrate_schemas --shared` on deploy (existing step) |
| `deployment/docker/kong/kong.yaml`, `kong-local.yaml` | Public route for `/api/v1/onboarding/public/` without JWT, modelled on `invite-accept-route`. Needs team agreement |
| Backend env | `EMAIL_*` for a real provider; `RECORDS_BUCKET` (or prefix), `RECORDS_LINK_TTL_DAYS`, `FRONTEND_BASE_URL` for links |
| GCS | Retention policy on the signed-records prefix or bucket (`deployment/gcp/` script) |
| Celery Beat | `expire_records` added to `CELERY_BEAT_SCHEDULE` |
| OIA service | Rebuild and redeploy for the prompt and type-hint change |
| New services | None, so no build-matrix or deploy-matrix registration is needed |

### 5.8 Delivery Order

Each step is a separate PR and leaves the system working.

1. **Contractual questions**: company fields, `Question.category`/`mandatory`, template, merge, OIA hint, checklist UI. Independent of everything below, and it means new first meetings start collecting the details straight away.
2. **Record and PDF**: models, agreement numbering, snapshot, source freeze, PDF, Documents tab, download, binder.
3. **Signing**: signatories, tokens and codes, public signing page, audit trail, certificate, emails.
4. **Sharing, verification, legal hold**.

## 6. Testing Strategy

Project rule: no mocks. Tests use the real Postgres test database, real Redis,
and Django's in-memory email backend (the repository's existing autouse
fixture, which captures real rendered messages). GCS tests use the real bucket
under a test prefix and carry the `gcp` marker.

### 6.1 Unit Tests

- **Scope:** agreement parsing, canonical snapshot and hashing, readiness checklist, lifecycle transitions, token and code handling, mandatory-question merge, PDF builders, OIA prompt exclusion.
- **Tools:** `pytest` + `pytest-django` (backend); `pytest` (OIA); Jest + Testing Library (frontend).
- **Runs in CI at:** backend test job, OIA service test job, frontend test job.
- **Example cases:**
  - `test_agreements_split_preserves_text_exactly` — bullets come out word for word, numbered in order.
  - `test_description_without_agreements_yields_empty_list` — no section, no items, description untouched.
  - `test_issue_blocked_when_client_signatory_missing` — readiness names the missing item.
  - `test_completed_record_cannot_be_voided` — transition refused.
  - `test_event_row_rejects_update_and_delete` — audit trail is insert-only.
  - `test_code_locks_after_five_attempts` — sixth attempt fails even with the right code.
  - `test_mandatory_questions_prepended_only_for_missing_fields` — reviewed fields are not asked again.
  - `test_generator_prompt_excludes_covered_fields` — OIA prompt lists the exclusions.
  - `test_pdf_contains_every_agreement_and_signature_block` — text extracted from the built PDF.

### 6.2 Property-Based Tests

- **Scope:** invariants where a silent failure would undermine the record.
- **Tools:** `hypothesis`.
- **Runs in CI at:** the separate property-test job (`pytest -m property`).
- **Example cases:**
  - `test_snapshot_hash_is_stable_under_key_order` — any reordering of the same content gives the same fingerprint.
  - `test_any_content_change_changes_hash` — changing one character anywhere changes it.
  - `test_agreement_split_then_join_is_lossless` — for arbitrary markdown, numbered items plus remainder reproduce the original text.
  - `test_no_transition_sequence_leaves_completed` — arbitrary action sequences never move a COMPLETED record.
  - `test_token_hash_never_equals_token` and tokens never collide across generated batches.

### 6.3 Integration Tests

- **Scope:** endpoints against the real database; tenant isolation; source freeze; erasure and retention hold; question write path.
- **Tools:** DRF `APIClient` with `SERVER_NAME=localhost`, Postgres test database, real Redis. Celery runs eagerly in these tests, so task wiring is verified but broker delivery is not.
- **Runs in CI at:** backend test job.
- **Example cases:**
  - `test_full_signing_flow_reaches_completed` — create, add signatories, issue, client code and sign, agency sign, PDF stored and hash matches.
  - `test_summary_update_cannot_change_issued_recording` — description and transcript unchanged after the OIA callback.
  - `test_other_tenant_cannot_read_or_sign_record` — 404 across tenants.
  - `test_expired_and_revoked_tokens_are_indistinguishable` — same response body and status.
  - `test_remark_after_first_signature_requires_acknowledgement` — record stays PARTIALLY_SIGNED until acknowledged.
  - `test_retention_sweep_skips_held_recording` and `test_erasure_reports_held_record`.
  - `test_binder_unchanged_records_keep_their_hash_when_meeting_added`.
  - `test_questionnaire_generate_adds_mandatory_beyond_requested_count`.

### 6.4 End-to-End Tests

- **Scope:** the user journey through the full local Docker Compose stack (frontend, Kong, backend, OIA, Redis, Postgres).
- **Tools:** Playwright (`npm run test:e2e`).
- **Runs in CI at:** the existing end-to-end stage; if that stage does not start the OIA service, the questionnaire case runs locally only and that is stated in the PR.
- **Example cases:**
  - `test_agency_prepares_and_issues_record` — Documents tab to issued state.
  - `test_client_signs_from_email_link` — link and code read from the backend's captured email, sign, completion page.
  - `test_client_declines_with_reason_and_agency_supersedes`.
  - `test_shared_link_stops_working_after_revoke`.
  - `test_downloaded_pdf_verifies_and_tampered_pdf_does_not`.
  - `test_first_meeting_checklist_shows_contract_details_first`.

## 7. GCP Cost Estimate

Cloud Storage prices below were read from the Cloud Billing Catalog API on
2026-11-25. Costs are computed at the full unit price, ignoring the free
allowances the catalog lists (first 5 GiB of storage, 5,000 Class A and 50,000
Class B operations, 100 GiB of download per month); at this volume those
allowances would in practice cover most of it if not already used elsewhere in
the project.

| GCP Service | Resource / Tier | Usage Assumption | Unit Price | Monthly Cost | Source |
|---|---|---|---|---|---|
| Cloud Storage | Standard, US Regional (us-central1) | 200 records/mo × ~2.5 MB, 7-year hold; ~6 GiB after year 1, ~42 GiB at year 7 | $0.020/GiB-month | $0.12 (yr 1) to $0.84 (yr 7) | Verified via GCP Billing Catalog API on 2026-11-25 |
| Cloud Storage operations | Regional Standard Class A | ~1,000 writes | $0.000005/op | $0.005 | Verified via GCP Billing Catalog API on 2026-11-25 |
| Cloud Storage operations | Regional Standard Class B | ~5,000 reads | $0.0000004/op | $0.002 | Verified via GCP Billing Catalog API on 2026-11-25 |
| Network egress | Download, worldwide excluding Asia and Australia | ~2 GiB of PDF downloads | $0.12/GiB | $0.24 | Verified via GCP Billing Catalog API on 2026-11-25 |
| Cloud Run (backend, worker) | Existing services | ~10,000 extra requests, ~200 PDF builds at ~2 s | Existing instances | ~$0 incremental | Estimate, not priced; no new service |
| Database | Existing database | 4 small tables, < 50 MB/yr | Existing | $0 incremental | Estimate, not priced |
| Email provider (not GCP) | Transactional email | ~2,000 emails/mo | Provider-dependent | $0–20 | Not priced; provider not chosen |

**Total: about $0.37/month in year 1, rising to about $1.09/month by year 7**
of GCP spend at the assumed volume, plus the email provider. Cost scales with
records issued and with PDF size; set a billing alert after launch rather than
treating this as exact.

## 8. Branching & PR Workflow

- **Branch:** `feature/TICKET-ID-signed-meeting-records`, created from `development_main`
- All commits for this user story happen on this branch only — no direct commits to `development_main`
- **Pull Request:** opened from this branch, targeting `development_main`
- PR description links this implementation plan and states its approval status
- PR shows all four testing layers (6.1–6.4) passing in CI before merge is allowed
- **Merge:** into `development_main` once required reviews and CI are green (squash-merge, unless team convention specifies otherwise)

The four delivery steps in §5.8 are separate PRs, each from its own branch
named `feature/TICKET-ID-signed-meeting-records-<step>`.

## 9. Risks & Open Questions

| # | Item | Position |
|---|---|---|
| R1 | Clause wording has not had legal review | Ship behind a tenant setting; do not enable signing in production until reviewed |
| R2 | No production email provider is configured | Blocks step 3 in production. Needs a provider and sending domain from the team |
| R3 | Public route needs a Kong change; Kong config is coordination-only | Raise with the team before step 3; confirm how production reaches the backend |
| R4 | Signers sign AI-generated text | Precedence clause, mandatory review, remarks, decline |
| R5 | Client's confirmed party details may differ from what was extracted | Signing page shows party details; the client's correction is recorded as a remark and the agency can supersede |
| R6 | Older recordings may hold mixed transcripts | Readiness checklist warns; agency decides before issuing |
| R7 | `fpdf2` and long transcripts (hundreds of pages) | Measure build time in step 2; move build fully to Celery if over a few seconds |
| R8 | Local OIA suite has a known failing and a hanging test unrelated to this work | CI is the gate for the OIA change |
| R9 | Existing three red migration tests on `development_main` | Not caused by the new migrations; do not attribute |

**Open questions**

1. Ticket ID for the branch name.
2. Which email provider and sender address?
3. Should the starting template include anything beyond the eight items in §5.5?
4. Is seven years the right default hold, and may a tenant shorten it?
5. Which jurisdictions should the lawyer's review cover?

## 10. Approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Reviewer | Product owner | Approved; start with step 1 | 2026-11-25 |

**Development may not begin until Status = Approved.**
