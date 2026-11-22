# Implementation Plan: Replace the In-App Calendar with Google Calendar as System of Record (TICKET-ID)

**Status:** Rejected — cancelled by the product owner on 2026-11-02 (Google Calendar integration deferred) <!-- Draft | Pending Review | Approved | Rejected -->
**Date:** 2026-11-02
**Target Environment:** GCP — Production (`zorven-503517`, `us-central1`)

> Development on this story may not begin until Status = Approved.
> `TICKET-ID` is a placeholder — suggested `D-04` (next in Epic D), to be confirmed.

---

## 1. User Story

**As an** Admin running onboarding meetings,
**I want** onboarding meetings to live in Google Calendar rather than in a calendar Zorven builds and syncs itself,
**so that** scheduling, rescheduling, invitations, reminders and time-zone handling are done by a mature calendar, and Zorven stops maintaining a second calendar plus a two-way sync between them.

### What exists today (verified 2026-11-02 against `development_main` @ `7f08306b`)

| Layer | Code | Size | Role |
|---|---|---|---|
| Frontend | `ai-brand-automator-frontend/src/components/onboarding/CalendarPane.tsx` | 432 lines | Self-built month/week grid, schedule form, cancel |
| Frontend | `src/lib/onboarding-sessions.ts` (calendar helpers, lines 97–138, 351–413) | ~100 lines | `listMeetings`, `createMeeting`, `updateMeeting` (unused), `cancelMeeting` |
| Backend | `apps/onboarding/models.py` `ScheduledMeeting`, `CalendarSyncConflict`, `MeetingOrigin`, `ConflictWinner` | ~250 lines | Local event store (source of truth) + conflict log |
| Backend | `apps/onboarding/views.py:2601` `ScheduledMeetingViewSet` → `/api/v1/onboarding/calendar/events/` | ~180 lines | CRUD + `cancel` action |
| Backend | `apps/integrations/sync.py` | 580 lines | Two-way pull/push, ownership tags, conflict rules, backoff |
| Backend | `apps/integrations/calendar_api.py` | 332 lines | Raw Google Calendar REST client (list/insert/patch/delete) |
| Backend | `apps/integrations/google_calendar.py` | 197 lines | OAuth: auth URL, code exchange, refresh, revoke |
| Backend | `apps/integrations/views.py`, `models.py` (`CalendarConnection`), `tasks.py` | 356 + 146 + 121 | Connect/callback/disconnect/status/sync endpoints; hourly token refresh; 3-min `sync_calendars` Beat task |
| Tests | `test_calendar_sync.py` (870), `test_calendar_push.py` (589), `test_google_calendar.py` (588), `test_secrets.py` (225), `onboarding/tests/test_calendar.py` (712), `CalendarPane.test.tsx` (300) | ~3,280 lines | |
| OIA service | `onboarding-intelligence-agent-svc` | — | **No calendar code.** Only an unenforced `CALENDAR_OAUTH_CONNECT` RBAC capability (`app/rbac/engine.py:64,160`). The live-session precheck does not consult meetings. |

So "the present calendar code" is two things: **(a)** a self-built calendar UI and local event store, and **(b)** a two-way sync engine that keeps (a) consistent with Google. This story removes both and makes Google Calendar the only calendar.

### Acceptance Criteria

- **AC-1 — Google is the system of record.** Creating an onboarding meeting creates a Google Calendar event on the tenant's connected calendar. Zorven stores only a link (session ↔ Google event ID), never its own copy of the time, title or attendees.
- **AC-2 — Changes made in Google are reflected without sync.** A meeting rescheduled, retitled or deleted in Google Calendar shows its current state in Zorven on the next page load (≤ 60 s cache), with no Beat task involved.
- **AC-3 — Onboarding meetings only.** The onboarding pane lists only events Zorven created for this tenant (filtered by a private extended property). The operator's personal events are never fetched, stored, or shown — Google Calendar itself is the "single view".
- **AC-4 — Connection is required to schedule, not to onboard.** A tenant with no connection sees a "Connect Google Calendar" prompt (Admin/Owner) or "Ask an Admin to connect Google Calendar" (Editor). Sessions, recording and PROCESS work unchanged without a connection.
- **AC-5 — Failures are legible and non-destructive.** If Google is unreachable or the grant is revoked, scheduling returns a specific error (`calendar_unavailable` / `calendar_needs_reconnect`), no local link is left orphaned, and no Google event is left without a link.
- **AC-6 — Idempotent creation.** A retried create (network blip, double click, Cloud Run retry) never produces two Google events for one meeting.
- **AC-7 — RBAC unchanged.** Owner/Admin connect and disconnect; Owner/Admin/Editor schedule and cancel; Viewer reads only. Server-side, unchanged from FR-CAL-02 / Design §15.
- **AC-8 — Erasure reaches Google.** Erasing a session (FR-GDPR) deletes its Google events, not just the local link.
- **AC-9 — The in-house calendar code is gone.** `sync.py`, `CalendarSyncConflict`, the `sync_calendars` Beat task, the sync bookkeeping columns, and the self-built month/week grid are deleted, along with their tests.

---

## 2. Assumptions

1. **Interpretation of "replace with Google Calendar".** Read as *Google Calendar becomes the system of record and the self-built grid goes away* — not "embed Google's calendar widget in an iframe" (rejected, see §9 R-6) and not "swap the grid for a third-party React calendar library" (that keeps the sync problem). **Needs confirmation — this is decision Q-1.**
2. **This reverses documented decision D-01 / FR-CAL-01** ("in-app calendar always present, requires no setup"). The requirements (v1.3 §7.2), design (v2.2 §3 D-01, §10.2, §11) and backlog (Epic D) need amending as part of this story. Rationale for reversal: D-01's only stated benefit was "zero OAuth friction in the common case"; scheduling is not on the critical path of onboarding (the OIA precheck never reads meetings), so requiring OAuth for scheduling only costs friction on an optional feature.
3. **The Google integration has never run in any environment.** Verified 2026-11-02:
   - No `GOOGLE_OAUTH_*` secrets in Secret Manager for `zorven-503517`; prod `zorven-backend` (rev `00010-jmn`) has no OAuth env vars.
   - `calendar-json.googleapis.com` is **not enabled** in `zorven-503517`.
   - Local `deployment/.env` has no OAuth client; local DB has 0 `CalendarConnection`, 0 Google-origin meetings, 0 conflicts, 3 app meetings.
   - **Inferred, not verified:** prod has 0 `CalendarConnection` rows and 0 pushed events, because connect cannot succeed without a client ID. To be confirmed with a read-only count before the contract migration (§5.1 step 3).
   Consequence: there is no synced data to migrate — only local-only app meetings.
4. **One Google account per tenant**, as today (`one_live_calendar_connection_per_tenant`). Meetings are created on that account's `primary` calendar. Per-user connections are out of scope.
5. **Usage volume:** ≤ 50 tenants, ≤ 200 onboarding meetings/month, ≤ 5,000 calendar-pane loads/month in the first year. Calendar API default quota is 1,000,000 queries/day/project and per-user rate limits apply; this is 3–4 orders of magnitude below them. *(Quota figures from public Google documentation — not verified via gcloud.)*
6. **OAuth client lives in `zorven-503517`.** The Calendar API must be enabled in the project that owns the OAuth client; we assume that is the prod project.
7. **OAuth consent screen will be published ("In production").** In "Testing" status Google expires refresh tokens after 7 days, which would silently break every tenant weekly. `calendar.events` is a **sensitive scope**: external users beyond 100 require Google's OAuth app verification (typically days to weeks). See R-1.
8. **Attendees:** as today, only the organiser's email is added — nothing in the data model records who the meeting is with (gap already noted in `sync.py:event_body`). Inviting the brand owner is out of scope (Q-3).
9. **Tech stack:** Python 3.12 + Django 4.2 + DRF (Zorven default) for the backend; Next.js 15 / React 19 / TypeScript for the frontend. No signals suggesting a different stack.
10. **Backend Redis** (not OIA's DB 2 — ERRATA-01 governs the OIA service only) is used for a 60 s read cache and the short-lived access token. Existing Memorystore instance; no new instance.
11. **Testing rule:** Per the standing team rule, tests do not use `mock`/`patch`. Google-touching tests run against a **real dedicated test Google account** whose refresh token is held as a CI secret. Pure-function unit tests need no test doubles.

---

## 3. Tech Stack

- Backend: Python 3.12 + Django 4.2 + Django REST Framework (Zorven default). Existing `requests`-based Google client retained — no new SDK dependency (`google-api-python-client` adds ~15 MB and a discovery-document fetch for 4 calls we already make).
- Frontend: Next.js 15 + React 19 + TypeScript strict, `apiClient` only, `lucide-react` icons, "Digital Twilight" design tokens.
- Celery: one Beat task removed, none added.
- OIA FastAPI service: **no change** (see §4).

---

## 4. Scope & Non-Goals

### In scope
- Backend: Google-first create/cancel/reschedule; live read-through listing filtered by private extended properties; Redis cache; deterministic event IDs; compensation on partial failure; erasure deletes Google events.
- Backend: delete the sync engine, conflict model, `sync_calendars` task, sync bookkeeping columns, and `origin`/`provider_*`/time columns on `ScheduledMeeting` (expand → contract across two PRs).
- Frontend: replace the self-built grid with an **Onboarding Meetings panel** — connection card (connect / reconnect / disconnect, handles `?connected=` / `?error=` from the OAuth callback), upcoming-meetings list with "Open in Google Calendar" and "Open session" links, schedule form, cancel, reschedule.
- Infra: OAuth client, consent screen, Calendar API enablement, Secret Manager secrets, compose `.env` entries, CI secret for test account.
- Docs: amend requirements FR-CAL-01/03, design D-01/§10.2/§11, backlog Epic D, `implementation-plan-remaining-work.md`, `MANUAL-TEST-RUNBOOK.md` (add a calendar step).

### Non-goals
- **OIA FastAPI service changes.** It holds no calendar code and must not gain any (Design §19: "the agent never holds calendar credentials"). The unused `CALENDAR_OAUTH_CONNECT` capability stays — it mirrors the design's RBAC table.
- Google Meet links on events (Q-2), inviting the brand owner (Q-3), Outlook / Microsoft 365 / `.ics` providers, per-user (rather than per-tenant) connections, free/busy or availability booking, push notifications via `events.watch`.
- Showing the operator's non-onboarding events in Zorven (deliberately dropped — AC-3).

---

## 5. Detailed Design

### 5.0 Target architecture

```
Before                                          After
──────                                          ─────
CalendarPane (own grid) ──► ScheduledMeeting     MeetingsPanel (list) ──► /calendar/events/ ──► Google events.list
                              (source of truth)                                  │ (filtered by private ext. props,
sync_calendars every 3 min ◄──► Google                                           │  Redis 60 s cache)
  pull + push + conflict rules + backoff                                          ▼
                                                                         ScheduledMeeting = link only
                                                                         (session, google_event_id, status)
```

Google holds time, title, timezone, attendees, reminders. Zorven holds only *which session an event belongs to* and *whether that link is live*.

### 5.1 Data Model / Migrations

Two migration phases so a Cloud Run rolling deploy never runs old code against a dropped column (expand → contract).

**`ScheduledMeeting` after this story (`apps/onboarding/models.py`):**

| Field | Change |
|---|---|
| `tenant`, `session`, `organiser`, `created_at`, `updated_at` | kept |
| `status` | kept; gains transient `PENDING` (link written, Google insert not yet confirmed — §5.3) |
| `meeting_uuid` | **new** `UUIDField(default=uuid4, unique=True)` — input to the deterministic Google event ID, which must exist before the insert |
| `provider_event_id` | **renamed `google_event_id`**, required (non-blank) after contract |
| `session` | becomes **non-null** — only onboarding meetings exist now |
| `origin` | dropped (everything is app-created) |
| `starts_at`, `ends_at`, `timezone`, `title` | dropped — Google is the source; kept *during* expand phase only |
| `provider_updated_at`, `provider_synced_at` | dropped |
| Constraints | keep `one_scheduled_meeting_per_session`; keep `one_meeting_per_provider_event` (renamed `one_meeting_per_google_event`); drop `meeting_ends_after_it_starts`, `meeting_timezone_is_not_an_offset`; drop index `(tenant, starts_at)`, add `(tenant, status)` |

**`CalendarSyncConflict`:** model and admin deleted.

**`CalendarConnection` (`apps/integrations/models.py`):** drop `sync_token`, `last_sync_at`, `last_sync_error`, `sync_failures`, `sync_backoff_until`. Keep everything else (encrypted `_refresh_token`, `status`, `scope`, `account_email`, `connected_by`, `last_refreshed_at`).

**Migration sequence**
1. **PR 1 (expand)** — `onboarding/0022_scheduledmeeting_google_link.py`: add `meeting_uuid` (backfilled for existing rows), add `PENDING` to status choices and widen `one_scheduled_meeting_per_session` to cover `PENDING`; make `starts_at/ends_at/timezone` nullable so new rows needn't write them. No column drops.
2. **Between PR 1 and PR 3** — management command `python manage.py reconcile_legacy_meetings [--dry-run]`:
   - For each `SCHEDULED` meeting with empty `provider_event_id`:
     - `starts_at` in the past → set `status=CANCELLED` (history kept).
     - future, tenant has a `CONNECTED` connection → create the Google event (same code path as create) and store its ID.
     - future, no connection → leave as-is and **report** (tenant, session, start) so the operator can reschedule after connecting.
   - Read-only prod count first: `CalendarConnection.objects.count()`, `ScheduledMeeting.objects.filter(provider_event_id="").count()` — confirms Assumption 3.
3. **PR 3 (contract)** — `onboarding/0023_drop_inhouse_calendar.py`:
   - data step: remaining `SCHEDULED` rows with no Google event → `CANCELLED` (reported in step 2; nothing silently lost — row survives as history)
   - delete `CalendarSyncConflict`; drop columns listed above; rename `provider_event_id` → `google_event_id`; `session` non-null (rows with null session are `GOOGLE`-origin, verified 0 locally, deleted).
   - `integrations/0003_drop_sync_bookkeeping.py`: drop the five sync columns.
   All new migration files; no existing migration edited. Applied with `migrate_schemas --shared --noinput`.

### 5.2 API Contract

Paths unchanged so the frontend helper module keeps working through the transition. All under `/api/v1/`, JWT auth, tenant-scoped via `getattr(request, "tenant", None)`.

| Method & path | Role | Behaviour |
|---|---|---|
| `GET onboarding/calendar/events/?from=&to=` | Viewer+ | Live `events.list` on the tenant's calendar with `privateExtendedProperty=zorven_tenant=<ns>:<tenant_id>`, `singleEvents=true`, `timeMin/timeMax`. Joins results to local links by `google_event_id`. Cached 60 s per (tenant, window). |
| `POST onboarding/calendar/events/` | Editor+ | Body `{session, starts_at, ends_at, timezone, title?}` → creates the Google event, then the link. `201` with the meeting. |
| `PATCH onboarding/calendar/events/{id}/` | Editor+ | Body subset of `{starts_at, ends_at, timezone, title}` → `events.patch`. Reschedule. |
| `POST onboarding/calendar/events/{id}/cancel/` | Editor+ | `events.delete` (`sendUpdates=all`), link → `CANCELLED`. 404/410 from Google treated as success. |
| `GET/POST integrations/google-calendar/{connect,callback,disconnect,status}/` | Admin+ (callback unauthenticated, state-checked) | Unchanged. |
| `POST integrations/google-calendar/sync/` | — | **Removed** (nothing to sync). |

**Meeting representation** (field names kept so `ScheduledMeeting` TS type changes minimally):

```json
{
  "id": 41,
  "session": "8d1c…",
  "company": "Acme",
  "title": "Onboarding — Acme",
  "starts_at": "2026-11-10T15:00:00Z",
  "ends_at": "2026-11-10T16:00:00Z",
  "timezone": "America/Chicago",
  "status": "SCHEDULED",
  "html_link": "https://www.google.com/calendar/event?eid=…",
  "editable": true
}
```
`origin` is removed from the payload. Times/title/timezone come from Google, never the DB.

**Errors** (stable `code` field so the UI can render specific prompts — AC-4/AC-5):

| Condition | Status | `code` |
|---|---|---|
| Tenant has no connection | 409 | `calendar_not_connected` |
| Connection `NEEDS_RECONNECT`, or Google returns `invalid_grant` / 401 | 409 | `calendar_needs_reconnect` (connection marked `NEEDS_RECONNECT`) |
| Google 5xx / timeout / 429 after retry | 503 | `calendar_unavailable` (with `Retry-After`) |
| Session already has a live meeting | 400 | `meeting_exists` (current #692 behaviour preserved) |
| Validation (bad zone, ends ≤ starts) | 400 | field errors |

### 5.3 Business Logic / Services

New module `apps/integrations/calendar_service.py` — the only thing views call. `calendar_api.py` stays as the thin REST client (its `list_events` gains `private_extended_property` and `time_min/time_max` params; sync-token handling removed). `google_calendar.py` (OAuth) is unchanged.

**Access tokens.** `get_access_token(connection)`: Redis key `calendar:at:{tenant_id}`, value Fernet-encrypted via `automation.encryption.encrypt_token`, TTL `expires_in − 120 s`. On miss, `google_calendar.refresh()`. `invalid_grant` → mark `NEEDS_RECONNECT`, raise `CalendarNeedsReconnect`. (Today each sync cycle refreshes; with live reads we would otherwise refresh on every page load.)

**Event identity & tagging.**
- Event ID is client-supplied and deterministic: `base32hex(sha256(f"{ns}:{tenant_id}:{meeting_uuid}"))[:40].lower()` — valid Google ID charset `[a-v0-9]`, length 5–1024. A new `meeting_uuid` (UUIDField, default uuid4) is added to `ScheduledMeeting` in 0022 for this, because the integer PK does not exist until after the insert. Retrying `events.insert` with the same ID returns 409 from Google → treated as "already created" → `events.get` and continue. **This is what makes AC-6 hold.**
- Private extended properties (each an exact-match filterable key, unlike today's single colon-joined `zorven_meeting_ref`):
  `zorven_ns=<CALENDAR_SYNC_NAMESPACE>`, `zorven_tenant=<ns>:<tenant_id>`, `zorven_meeting=<meeting_uuid>`. Namespace keeps staging and prod apart when both connect the same account; tenant keeps two tenants on one account apart — both reasons already documented in `sync.py:namespace()` / `owned_meeting_id()` and carried over.
- No PII in tags or titles beyond the company name the operator already sees; default title `Onboarding — {company.name}`.

**Create (`schedule_meeting`)**
1. `select_for_update` on the session; check no live `SCHEDULED` link (→ 400 `meeting_exists`).
2. Create the link row with `status=PENDING` (new transient status) and `meeting_uuid` inside the transaction; commit. The partial unique constraint now also covers `PENDING`, so a concurrent second create loses at the DB.
3. Outside the transaction: `events.insert` with the deterministic ID.
4. Success → link `status=SCHEDULED`, `google_event_id` set; invalidate the tenant's list cache.
5. Failure → link row deleted (compensation); error mapped per §5.2. A `PENDING` row older than 10 min is swept by `cleanup_pending_meetings` (see §5.4) in case the process died between 2 and 4 — it does `events.get` first and promotes to `SCHEDULED` if the event exists, otherwise deletes the row.

**List (`list_meetings`)** — cache lookup `calendar:list:{tenant_id}:{from}:{to}` (60 s). On miss: `events.list` with the tenant filter, all pages, `singleEvents=true`. Join to links by `google_event_id`. **Lazy reconcile:** a `SCHEDULED` link whose event came back `status=cancelled` or is absent from a window that covers its last-known instant is marked `CANCELLED` — this is how a deletion made in Google releases the session (AC-2) without a poller. Events carrying our tenant tag but no local link (e.g. link erased) are shown read-only with `editable:false`.

**Reschedule / cancel** — `events.patch` / `events.delete` with `sendUpdates=all`; invalidate cache. On `PATCH`, the clash check is unchanged.

**Erasure (AC-8)** — `apps/onboarding/erasure/stores/django_sessions.py` gains a Google step before deleting links: `events.delete` per live `google_event_id`. If the tenant has no usable connection, the erasure proceeds locally and records a `residual_external_events` entry in the erasure log naming the event IDs (never content) so an operator can remove them — consistent with how GCS residue is handled in `gcs_blobs.py`.

**Deleted:** `apps/integrations/sync.py` entirely; `views.sync_now`; `ScheduledMeetingViewSet._refuse_if_external`; serializer `origin` handling; `CalendarSyncConflictAdmin`.

**Observability** — structured logs `calendar_event_created|patched|deleted|list_cache_miss|google_error` with `tenant_id`, `meeting_uuid`, Google status code; never tokens, titles, or attendee emails (NFR-PRIV-02). Existing Prometheus scrape gets a counter `calendar_google_requests_total{op,outcome}`.

### 5.4 Async / Background Jobs

| Task | Change |
|---|---|
| `integrations.sync_calendars` (every 180 s) | **Removed** from `CELERY_BEAT_SCHEDULE` in PR 1 (stops pull/push immediately); task code deleted in PR 3. |
| `integrations.refresh_calendar_tokens` (hourly) | **Kept** — still the mechanism that marks a revoked grant `NEEDS_RECONNECT` before the operator hits it (D-02 AC-4). Now also warms the Redis access-token cache. |
| `integrations.cleanup_pending_meetings` (new, every 10 min) | Resolves `PENDING` links older than 10 min (§5.3 create step 5). Runs on the existing `orchestration`-routed worker; touches only rows that crashed mid-create — normally zero. |

Beat uses `DatabaseScheduler`: PR 1's release notes include removing the `sync_calendars` row from `django_celery_beat_periodictask` (settings change alone does not delete an existing DB row).

### 5.5 Frontend

- **Delete** `CalendarPane.tsx` and its test; **add** `components/onboarding/MeetingsPanel.tsx` (target < 250 lines) rendered where `CalendarPane` was in `OnboardingHome.tsx:239`.
  - **Connection card** — `GET integrations/google-calendar/status/`. States: not connected (Admin+: "Connect Google Calendar" → `GET connect/` → `window.location.assign(url)`; Editor/Viewer: "Ask an Admin to connect"), connected (account email, Disconnect for Admin+), needs reconnect (specific prompt). Reads and then clears `?connected=` / `?error=` from the callback redirect.
  - **Upcoming meetings** — chronological list for the next 30 days (`from=now`, `to=now+30d`), each row: local time (viewer zone, "booked in {zone}" when different — logic carried from `CalendarPane`), company, "Open in Google Calendar" (`html_link`, `target=_blank rel=noopener`), "Open session" → `/onboarding/sessions/{session}`, and for Editor+ Reschedule / Cancel.
  - **Schedule form** — session select, `datetime-local` start, minutes (default 60), optional title. Disabled with an explanatory line when not connected.
  - Error codes from §5.2 map to specific messages; no generic "something went wrong".
- `lib/onboarding-sessions.ts`: drop `MeetingOrigin`; add `html_link`; add typed helpers `getCalendarConnection`, `connectCalendar`, `disconnectCalendar`; `updateMeeting` becomes used (reschedule).
- `useAuth()`, `hasMounted` guard, `useTenantRole()` gating, `apiClient` only — per root CLAUDE.md.

### 5.6 Infrastructure (Phase 0 — prerequisite, blocks PR 1 deploy)

1. Enable `calendar-json.googleapis.com` in `zorven-503517`.
2. Create OAuth consent screen (External, scopes `calendar.events`, `openid`, `email`), publish to "In production", submit for sensitive-scope verification (R-1).
3. Create an OAuth 2.0 Web client; redirect URIs `https://api.zorven.ai/api/v1/integrations/google-calendar/callback/` and `http://localhost:8001/...` (local).
4. Create secrets `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` in Secret Manager; grant the backend and worker service accounts `secretAccessor`. **These are already referenced by `deployment/gcp/08-deploy-services.sh:74,162`, so the next backend/worker deploy fails until they exist — independent of this story.**
5. Local: document `GOOGLE_OAUTH_CLIENT_ID/SECRET` in `deployment/.env.example`.
6. CI: dedicated Google account `calendar-ci@<domain>` with a dedicated calendar; its refresh token stored as GitHub secret `GOOGLE_CALENDAR_TEST_REFRESH_TOKEN` (plus client ID/secret). `.github/workflows/ci-cd.yml` is "coordinate with team" — the workflow change is listed as a team-reviewed item, not made unilaterally.

---

## 6. Testing Strategy

No `mock` / `patch` anywhere (standing team rule). Google is exercised for real through the CI test account; Postgres and Redis are the real services the suite already uses. The existing local fake-endpoint approach (`GOOGLE_OAUTH_BASE` pointing at a local server) is retired along with the sync tests.

### 6.1 Unit Tests
- **Scope:** pure functions with no I/O — event-ID derivation, extended-property tag building/parsing, Google event body construction, Google response → meeting representation, error-code mapping, cache-key building, serializer validation (zone, ends > starts), RBAC permission classes on the viewset.
- **Tools:** `pytest` + `pytest-django`, `factory_boy` factories from `apps/onboarding/tests/factories.py`.
- **Runs in CI at:** `backend-tests` job (`pytest -m "not property"`), frontend `npm test`.
- **Example cases:**
  - `test_event_id_is_deterministic_and_google_valid` — same inputs → same ID; charset `[a-v0-9]`, length within 5–1024.
  - `test_tags_carry_namespace_tenant_and_meeting` — three separate private properties, no PII.
  - `test_google_cancelled_event_maps_to_cancelled_status`
  - `test_invalid_grant_maps_to_needs_reconnect_409`
  - `test_viewer_cannot_create_editor_can` (APIClient, permission layer only, with `SERVER_NAME="localhost"`)
  - Frontend (Jest + RTL): `MeetingsPanel` renders not-connected / needs-reconnect / connected states; Editor sees Ask-an-Admin rather than Connect; schedule form disabled when not connected; viewer-zone rendering carried over from the old pane's tests. **Open point:** the existing frontend suite stubs the API helpers with `jest.mock`; whether the no-mocks rule extends to Jest component tests is Q-5, and these cases are written whichever way Q-5 resolves.

### 6.2 Property-Based Tests
- **Scope:** invariants that matter for correctness across inputs.
- **Tools:** `hypothesis` (`@pytest.mark.property`).
- **Runs in CI at:** `backend-property-tests` job (`pytest -m property`).
- **Example cases:**
  - `test_event_id_injective_over_meeting_uuids` — distinct `(ns, tenant, uuid)` never collide in the generated sample.
  - `test_tag_roundtrip` — `parse(build(ns, tenant, uuid)) == (ns, tenant, uuid)` for arbitrary namespaces incl. `:` characters.
  - `test_instant_roundtrip_any_iana_zone` — for any zone in `zoneinfo.available_timezones()` and any instant (incl. DST transitions), building the Google body and parsing Google's response yields the same UTC instant and zone. (Replaces `test_dst_transition_rendering`'s guarantee now that Google renders.)
  - `test_list_window_rejects_inverted_or_oversized_ranges`

### 6.3 Integration Tests
- **Scope:** real Postgres + real Redis + **real Google Calendar** (CI test account). Celery tasks run eagerly (`CELERY_TASK_ALWAYS_EAGER=True`) for determinism — this verifies task logic, not broker delivery.
- **Tools:** `pytest-django` (`db`, `transactional_db`), DRF `APIClient`, real Redis on :6379, `@pytest.mark.integration` + new marker `google` (skipped with an explicit reason when `GOOGLE_CALENDAR_TEST_REFRESH_TOKEN` is absent — so local runs without the secret say *why* they skipped instead of passing vacuously). Each test tags events with a per-run namespace `ci-<run_id>` and a session-scoped fixture deletes everything carrying that namespace at teardown.
- **Runs in CI at:** `backend-integration` job, required on PRs touching `apps/integrations/**` or `apps/onboarding/**calendar**`.
- **Example cases:**
  - `test_create_creates_google_event_and_link` — event exists in Google with our tags; link row `SCHEDULED`.
  - `test_retry_with_same_uuid_creates_one_event` — two inserts, one Google event (AC-6).
  - `test_event_deleted_in_google_releases_session_on_next_list` — delete via API directly, list → link `CANCELLED`, session schedulable (AC-2).
  - `test_reschedule_in_google_is_reflected_after_cache_ttl` — patch via API directly; list after cache invalidation shows new time.
  - `test_personal_events_never_returned` — an untagged event on the same calendar is absent from the list (AC-3).
  - `test_two_tenants_same_account_isolated` — tenant B never sees tenant A's events.
  - `test_revoked_grant_marks_needs_reconnect` — uses a deliberately revoked token secret.
  - `test_erasure_deletes_google_events` (AC-8).
  - `test_reconcile_legacy_meetings_dry_run_reports_and_changes_nothing`
  - `test_cleanup_pending_promotes_or_deletes`

### 6.4 End-to-End Tests
- **Scope:** full user journey through the real local stack.
- **Tools:** Playwright (`npm run test:e2e`) against `docker compose up` (backend, db, redis, frontend; Kong not required). Google consent cannot be automated, so the e2e setup seeds a `CalendarConnection` from `GOOGLE_CALENDAR_TEST_REFRESH_TOKEN` via a management command (`seed_test_calendar_connection`, refuses to run when `DEBUG=False`).
- **Runs in CI at:** `frontend-e2e` job (existing `npm run test:e2e` step), gated on the Google secret being present.
- **Example cases:**
  - `calendar.spec.ts › admin without connection sees Connect prompt; editor sees Ask-an-Admin`
  - `calendar.spec.ts › editor schedules a meeting, it appears with an Open-in-Google link, and the event exists in Google` (asserted via the Calendar API in the test)
  - `calendar.spec.ts › cancel removes the event from Google and frees the session`
  - `calendar.spec.ts › meeting row links to its session page`
- **Manual:** add "Step 1b — schedule the onboarding meeting" to `MANUAL-TEST-RUNBOOK.md` covering the real consent screen, which automation cannot reach.

---

## 7. GCP Cost Estimate (per month)

| GCP Service | Resource / Tier | Usage Assumption | Unit Price | Monthly Cost | Source |
|---|---|---|---|---|---|
| Google Calendar API | `calendar-json.googleapis.com` | ≤ 30,000 calls/mo (5k pane loads × cache misses + creates/patches/deletes + hourly refresh) | No billable SKU — API has no entry in the Cloud Billing Catalog; quota-limited, not metered | **$0.00** | Verified via GCP Billing Catalog API on 2026-11-02 (absence of SKU) |
| Secret Manager | 2 new secrets (`GOOGLE_OAUTH_CLIENT_ID`, `_SECRET`), 1 active version each | Project total stays under 6 free active versions? **Unknown** — billed as if not free | $0.06 / active version / month (first 6 free) | **$0.12** (worst case) | Verified via GCP Billing Catalog API on 2026-11-02 |
| Secret Manager | Access operations | ~2 per cold start × ~300 cold starts | $0.03 / 10,000 (first 10,000 free) | **$0.00** | Verified via GCP Billing Catalog API on 2026-11-02 |
| Cloud Run — `zorven-celery-worker` | 1 instance, `minScale=1 maxScale=1`, CPU always allocated | Removing the 3-min `sync_calendars` task | Always-on instance is billed regardless of work | **$0.00** change | Verified via `gcloud run services describe` on 2026-11-02 |
| Cloud Run — `zorven-backend` | Existing service | +5,000 requests/mo, ~300 ms each incl. Google round-trip | Negligible vs. existing baseline (< 1 vCPU-hour/month) | **< $0.10** | Estimate from existing service config; per-request SKU not separately queried |
| Memorystore for Redis | Existing `zorven-redis` (1 GB BASIC) | < 1 MB of new keys, 60 s TTL | Instance already provisioned | **$0.00** | Existing resource — no new capacity |

**Total: ≈ $0.22/month incremental (upper bound).** Net effect is effectively cost-neutral; the deleted 3-min poller saves no money because the worker is pinned always-on.

_Estimate method: Verified via GCP Billing Catalog API on 2026-11-02 (Secret Manager SKUs; Calendar API has no SKU) and `gcloud run services describe` for worker scaling. Free-tier allowances noted per row. Actual cost depends on real traffic; recommend keeping the existing project budget alert rather than adding a new one._

---

## 8. Branching & PR Workflow

- **Branch:** `feature/TICKET-ID-google-calendar-system-of-record`, created from `development_main` *(`TICKET-ID` must be filled in before the branch is created — suggested `D-04`)*
- All commits for this user story happen on that feature branch only — no direct commits to `development_main`
- **Pull Request:** opened from the feature branch, targeting `development_main`
  - PR description links this implementation plan and states its approval status
  - PR shows all four testing layers (6.1–6.4) passing in CI before merge is allowed
- **Merge:** into `development_main` once required reviews and CI are green (squash-merge)

Delivery is split into PRs off sub-branches of the feature branch so the expand/contract migration is safe under Cloud Run rolling deploys:

| PR | Branch | Contents | Deployable alone? |
|---|---|---|---|
| 0 | — (infra, no code) | §5.6 steps 1–5 | Yes — also unblocks the currently-broken deploy |
| 1 | `feature/TICKET-ID-gcal-backend` | `calendar_service.py`, Google-first viewset, cache, deterministic IDs, `PENDING` status, migration 0022 (expand), remove `sync_calendars` from Beat, `reconcile_legacy_meetings`, `cleanup_pending_meetings`, erasure step, tests 6.1–6.3 | Yes — old pane still works against the same endpoints (minus Google-origin rows) |
| 2 | `feature/TICKET-ID-gcal-frontend` | `MeetingsPanel`, connection card, helper/type changes, delete `CalendarPane`, Jest + Playwright | Yes, after PR 1 |
| 3 | `feature/TICKET-ID-gcal-contract` | Migrations 0023 + integrations 0003, delete `sync.py` / conflict model / sync tests / `sync_now`, docs amendments (requirements, design, backlog, runbook) | Only after `reconcile_legacy_meetings` has run in prod |

Commit messages: conventional (`feat(onboarding): …`, `refactor(integrations): …`). Backend formatted with `black==23.12.1` + `flake8`.

---

## 9. Risks & Open Questions

### Risks
- **R-1 — Google OAuth verification (high).** `calendar.events` is a sensitive scope. Until Google verifies the app, external users see an "unverified app" warning and the app is capped at 100 users; in "Testing" status refresh tokens die after 7 days. With Google now *mandatory* for scheduling this moves from nice-to-have to launch-blocking for scheduling. Start Phase 0 verification immediately; it is calendar-days, not engineering-days.
- **R-2 — Scheduling now depends on Google availability.** D-03 AC-3 ("in-app calendar continues to function fully") no longer holds: if Google is down, scheduling returns 503. Mitigated by AC-4 — onboarding itself never depended on meetings — and by the 60 s cache keeping the list readable through brief blips.
- **R-3 — Deploy currently broken.** `08-deploy-services.sh` references OAuth secrets that do not exist (§5.6.4). Fix in Phase 0 regardless of approval.
- **R-4 — Losing the "single view" of external events.** Today's design shows the operator's other Google events read-only in the pane. This plan drops that on purpose (privacy: today any Editor in the tenant would see the connected Admin's personal appointments, and they get copied into Zorven's DB). If operators valued it, Q-4 offers a free/busy-only alternative.
- **R-5 — Lazy reconcile window.** A meeting deleted in Google is only marked `CANCELLED` when a list call covers its time window; a session can look "booked" to a direct API client until then. Create re-checks the blocking link with `events.get` before returning `meeting_exists`, so the operator is never actually blocked.
- **R-6 — Iframe embed considered and rejected.** Embedding `calendar.google.com/calendar/embed` would show the operator's whole calendar, only works for a viewer signed into that same Google account, breaks under third-party-cookie restrictions, and cannot create/cancel or link to sessions.
- **R-7 — CI dependence on a real Google account.** Rate limits or token revocation on `calendar-ci@` would redden CI for unrelated reasons. Mitigation: per-run namespace cleanup, `google` marker skipped with an explicit reason when the secret is missing, and a runbook note for rotating the token.

### Open questions (need answers before approval)
- **Q-1 — Confirm the interpretation:** Google as system of record + self-built grid removed (this plan) vs. keep the local store and only swap the UI. This is the decision everything else rests on.
- **Q-2 — Google Meet links?** One extra field (`conferenceData.createRequest`) gives every onboarding meeting a Meet link. Cheap, but it changes where the meeting happens; the recording flow today is in-browser. Recommend: out of scope, follow-up story.
- **Q-3 — Invite the brand owner?** Needs a contact email on `Company` or the session; no story adds one today. Recommend: follow-up story.
- **Q-4 — Is the external-events "single view" needed?** If yes, a free/busy overlay (`freebusy.query`, shows busy blocks only, no titles) restores it without copying personal events. Recommend: not needed.
- **Q-5 — Does the no-mocks rule extend to Jest component tests?** The frontend suite uses `jest.mock` for API helpers throughout. Options: allow it for component rendering only, or run component tests against the local backend.
- **Q-6 — Who owns the Google Cloud OAuth verification submission** (needs a privacy policy URL, homepage, and possibly a demo video)?
- **Q-7 — Ticket ID** for the branch name.

---

## 10. Approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Reviewer | | | |

**Development may not begin until Status = Approved.**
