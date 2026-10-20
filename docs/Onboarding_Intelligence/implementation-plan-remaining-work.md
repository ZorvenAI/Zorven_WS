# OIA Implementation Plan — Remaining Work

> **Skill disclosure**: The `zorven-implementation-plan` skill was invoked but
> its four reference files (`implementation-plan-template.md`,
> `testing-strategy.md`, `gcp-cost-estimation.md`, `git-workflow.md`) are
> missing. This plan follows the skill's established conventions (read sources
> first, verify ACs against codebase, surface doc-vs-reality conflicts, no
> mocks, deployment coverage, state what the story does not deliver, numbered
> assumptions) but the section numbering and structure are improvised.

---

## 0. Executive Summary

**The OIA implementation is ~99% complete by story count, which overstates
how much is operationally live** — see §3.2, where M-04's dashboard and seven
alert rules exist as files that nothing loads. A story-by-story codebase
verification against all 66 active stories in the backlog v2.1 reveals that
every epic (A through N) has been implemented across all three layers: the
agent service, the Django backend, and the Next.js frontend.

The previous cross-reference audit (2026-09-06) correctly identified the agent
service as complete but stated that "the remaining work is Django backend and
frontend." That assessment was wrong. Both layers were already substantially
built at the time of the audit — approximately 23,000 lines of production code
and 10,000 lines of tests on the Django side, and 7,000 lines of components
plus 5,600 lines of tests on the frontend side.

**Remaining work** (updated 2026-10-20): the frontend component is done
(§3.1, M-03 AC-3) and the Grafana item turned out not to be a registration
gap at all but an undecided infrastructure build needing §7 cost treatment
(§3.2). What is left is that decision, the §3.3 verification pass, and the
hardware-blocked O-09 spike. The original wording of this line, kept below
for the record, read: one frontend component (M-03 AC-3), one operational
registration gap (Grafana dashboard provisioning), and a verification pass to
confirm all acceptance criteria are met end-to-end.

---

## 1. Verification Methodology

Every story's acceptance criteria were checked against the codebase by:

1. Grepping for story IDs (e.g., `L-01`, `M-05`) across all three codebases
2. Reading the implementing files (models, views, serializers, components, hooks)
3. Confirming test files exist and reference the correct ACs
4. Checking deployment registration points (docker-compose, CI, GCP deploy)
5. Checking Celery Beat schedule entries for periodic tasks
6. Checking frontend routes and component wiring

### 1.1 Code Inventory

| Layer | Location | Production Lines | Test Lines |
|-------|----------|-----------------|------------|
| Agent service | `onboarding-intelligence-agent-svc/` | ~12,000 | ~8,000 |
| Django backend | `ai-brand-automator/apps/onboarding/` | ~6,300 | ~10,300 |
| Django integrations | `ai-brand-automator/apps/integrations/` | ~1,100 | — |
| Frontend components | `src/components/onboarding/` (24 files) | ~7,200 | ~5,600 |
| Frontend hooks | `src/hooks/` (7 OIA hooks) | ~1,044 | — |
| Frontend API layer | `src/lib/onboarding-sessions.ts` | ~744 | — |

---

## 2. Story-by-Story Status

### Epic A — Foundations (6 stories, 14 pts) ✅ COMPLETE

All stories verified. A-04 withdrawn per ERRATA-01.

- A-01: STT spike landed (`docs/spikes/`)
- A-02: WebSocket spike landed
- A-03: Redis isolation baseline, Kafka, observability — all in agent service
- A-05: Scaffold complete (port 8120, `OIA_` prefix, health probes)
- A-06: Agent skeleton — registry, guardrail chain, RBAC evaluator

### Epic B — Data Model and Session APIs (8 stories, 19 pts) ✅ COMPLETE

All models in `apps/onboarding/models.py` (1193 lines). All APIs in
`apps/onboarding/views.py` (3087 lines). 17 migrations. 28 test files.

- B-01: OnboardingSession, Questionnaire, Question, MeetingRecording, ConsentRecord, FieldProvenance
- B-02: BrandAsset extension for meeting evidence
- B-03: Company approved onboarding fields + `ONBOARDING_FIELDS` list
- B-04: Session CRUD + state machine (`legal_next_states` on serializer)
- B-05: FieldProvenance grounding check constraint (DB-level)
- B-06: Provenance APIs (list, confirm, edit with KEY/SECONDARY gating)
- B-07: Consent API (grant/revoke with erasure cascade)
- B-08: Recording lifecycle APIs (open/stop/upload-session/transcript)

### Epic C — PREP Mode (5 stories, 14 pts) ✅ COMPLETE

Agent service: `PrepExecutor`, `ResearchBusiness` (SKL-OIA-01),
`GenerateQuestionnaire` (SKL-OIA-02), `RefineQuestionnaire` (SKL-OIA-03),
`PrepConversation` (SKL-OIA-15).

Django: `QuestionnaireViewSet` (rewrite, drop, reorder, approve, revise,
clone), `create_questionnaire` internal endpoint.

Frontend: `QuestionChecklist` component (200 lines).

### Epic D — Calendar and Scheduling (3 stories, 8 pts) ✅ COMPLETE

- D-01: `ScheduledMeetingViewSet` + `CalendarPane` (374 lines)
- D-02: Google Calendar OAuth (`apps/integrations/views.py`, 357 lines)
  + `refresh_calendar_tokens` Beat task (every 6 hours)
- D-03: Two-way sync (`apps/integrations/sync.py`, 581 lines)
  + `sync_calendars` Beat task (every 15 minutes)

### Epic E — Interface Shell (2 stories, 5 pts) ✅ COMPLETE

- E-01: `OnboardingHome` (243 lines) at `/onboarding`
- E-02: `MeetingView` (254 lines) at `/onboarding/sessions/[sessionId]/meeting`

### Epic F — Recording and Transcription (6 stories, 18 pts) ✅ COMPLETE

- F-01: `ConsentModal` (201 lines), consent API
- F-02: `RecorderControl` (215 lines) + `useMeetingRecorder` hook (269 lines)
- F-03: `useChunkUploader` (223 lines) + `resumable-upload.ts` (143 lines)
- F-04: `useLiveSocket` (185 lines) + `app/api/ws.py` in agent service
- F-05: STT adapter in agent service
- F-06: PII redaction pipeline in agent service

### Epic G — Live Meeting Assist (6 stories, 17 pts) ✅ COMPLETE

All skills (SKL-OIA-04 through 07, 16) implemented in agent service.
`QuestionChecklist` reflects sufficiency signals. Coverage tracking via
`useLiveSocket`.

### Epic H — Document Capture and OCR (4 stories, 11 pts) ✅ COMPLETE

- H-01: `CaptureControl` (277 lines)
- H-02: `SnippetControl` (284 lines) + `useSnippetRecorder` (222 lines)
- H-03: Image OCR pipeline (agent service SKL-OIA-10)
- H-04: Video snippet OCR (agent service SKL-OIA-11)

### Epic I — Recordings Library (3 stories, 8 pts) ✅ COMPLETE

- I-01: `RecordingsLibrary` (288 lines) + `useLibraryPolling` (90 lines)
- I-02: `RecordingPlayer` (356 lines) + `SummarizeRecording` skill (SKL-OIA-08)
  + `trigger_recording_summary` Celery task
- I-03: `TranscriptView` (379 lines)

### Epic J — Processing and Auto-fill (6 stories, 19 pts) ✅ COMPLETE

- J-01: `ProcessButton` (228 lines) + `dispatch_process` task
- J-02: Evidence assembly (SKL-OIA-09)
- J-03: Field extraction + `field_map.py` + `patch_company_fields` endpoint
- J-04: Grounding enforcement + output guardrails
- J-05: Conflict detection + escalation
- J-06: Auto-generation: `internal_generate_brand_strategy`,
  `internal_generate_brand_identity` endpoints

### Epic K — Review, Wizard Extension and PDF (5 stories, 12 pts) ✅ COMPLETE

- K-01: `OnboardingReview` (409 lines) + `KeyFindingsReview` (495 lines)
  at `/onboarding/sessions/[sessionId]/review`
- K-02: `ProvenanceCard` (210 lines) + `ProvenanceDrawer` (138 lines)
  + confirm/edit actions + golden candidate emission
- K-03: `useWizardProvenance` (75 lines) extending wizard forms
- K-04: `MeetingEvidence` (227 lines) + `session_evidence` endpoint
- K-05: `build_onboarding_pdf` updated with "Meeting Evidence" and
  "Key Findings" sections (onboarding/views.py:160-243)
  + `test_pdf_snapshot.py` verifying K-05 ACs

### Epic L — Prompt Optimization Integration (5 stories, 13 pts) ✅ COMPLETE

- L-01: `app/prompts/loader.py` (4-step resolution chain), `fallbacks.py`
  (8 versioned fallback prompts), `mapping.py` (prompt ID catalog).
  Session pinning in `process_executor.py` and `ws.py`. Tests:
  `test_prompt_loading.py`, `test_prompt_loader.py`.
- L-02: `RecordGoldenCandidates` skill (SKL-OIA-13), Kafka topic
  `onboarding.golden-dataset.candidates`, `emit_golden_candidate` Celery
  task on Django side. Tests: `test_kafka_roundtrip.py`.
- L-03: Prompt version persistence — `patch_session_prompt_versions`
  Django endpoint, `backend_client.persist_prompt_versions()` in agent.
  Tests: `test_prompt_version_persistence.py`, `test_process_callback_versions.py`.
- L-04: Tenant prompt customization — `PromptState.TENANT_OVERRIDE`
  transition in POI lifecycle, `optimize_tenant_oia.py` task with dataset
  floor check, resolution chain step 1 prefers tenant variants.
  Tests: `test_tenant_prompt_customization.py` in POI.
- L-05: Cache invalidation — `POST /v1/admin/cache-bust` endpoint in
  agent service, `test_cache_bust_scoped_to_prefix` in
  `test_redis_key_isolation.py`, fallback schema-validity tests.

### Epic M — Security, GDPR and Operations (5 stories, 13 pts) — 1 GAP

- M-01 ✅: All 24 guardrail rules registered (`_register_guardrails` in
  `main.py`), `input_guardrails.py` (10 IG rules), `output_guardrails.py`
  (6 OG rules), `pg08.py`, `guardrails.py` (PG rules).
  Tests: `test_guardrails.py` (21 KB), `test_guardrail_integration.py`.
- M-02 ✅: `ErasureCascade` with 6 stores in fixed order, `ErasureLog`
  model, registry-driven cascade, consent revocation enters same path.
  Tests: `test_erasure_cascade.py`, `test_erasure_registry.py`,
  `test_erasure_api.py`.
- M-03 ✅ (closed, see §3.1): Backend — `RetentionConfig` model, CRUD
  endpoints (`/api/v1/onboarding/retention/`), `enforce_retention_windows`
  Beat task (03:00 UTC daily), RBAC on Owner/Admin only. The
  `RetentionSettings` frontend component and its tests shipped, and AC-3 was
  verified sub-requirement by sub-requirement rather than by the component's
  existence — which is what turned up the untested preview guarantee the
  story rests on.
- M-04 ⚠️ (file written, not provisioned — see §3.2): Grafana dashboard (`deployment/grafana/dashboards/oia.json`),
  runbook (`docs/runbook.md`), Prometheus metrics (`app/metrics.py`),
  stuck-session watchdog (`app/logic/watchdog.py`), health/readiness
  probes. Django side: `finalize_stuck_session` endpoint.
  Tests: `test_watchdog.py`, `test_health.py`.
- M-05 ✅: Per-user rate limiter (`rate_limiter.py`), IG-07 wired,
  live-session lock (`live_lock.py`) keyed on company with configurable
  `max_concurrent_sessions`, circuit key exception in isolation test.
  Tests: `test_ws_handshake.py`, `test_session_state.py`.

### Epic N — End-to-End Hardening (3 stories, 8 pts) ✅ COMPLETE

- N-01: Five e2e test files (`test_prep_to_questionnaire.py`,
  `test_live_meeting.py`, `test_process_to_review.py`,
  `test_degraded_stt.py`, `test_gdpr_erasure.py`). Shared fakes in
  `tests/fakes/models.py`.
- N-02: Load test (`test_nfr_perf.py`) with `OIA_LOAD_TARGET` for
  deployed-path measurement. 45-minute session stability test in
  `test_live_meeting.py`.
- N-03: Breaker drill tests in `test_circuit_breakers.py`, DLQ replay
  in `test_kafka_roundtrip.py`.

---

## 3. Remaining Work

### 3.1 ~~Code Gap~~ CLOSED: RetentionSettings Frontend Component (M-03 AC-3)

**Verified 2026-10-19 against all five sub-requirements, not against the
component's existence.** The component ships and all five are implemented
front and back:

| Sub-requirement | Where |
|---|---|
| 1. `GET /api/v1/onboarding/retention/` on load | `getRetentionConfig()` in `lib/onboarding-sessions.ts` |
| 2. Form, updating `retention_days` via `PATCH` | `updateRetentionConfig()` |
| 3. Preview when the new value is shorter | `previewRetentionConfig()` → `PATCH …?preview=true`, called only when `days < currentDays` |
| 4. Confirmation dialog with the affected count | `role="alert"` block in `RetentionSettings.tsx`, with Confirm and Revert |
| 5. Owner/Admin only | `useTenantRole().isAdmin` in the component **and** `IsTenantAdmin` on `RetentionConfigView` |

Eleven frontend tests cover the five, including "shortening calls preview
(not update)" and "reverting after preview restores the original value
without saving".

**What this verification found.** The server-side guarantee the whole story
rests on was **untested**: `test_shortening_warns_with_counts` PATCHes
*without* `?preview=true`, so no test exercised the preview path at all.
Moving `config.save()` above the early return in `RetentionConfigView.patch`
left every existing test green while making the UI's confirmation dialog a
formality — the operator would be asked to approve a change already made.
That is precisely the accident the backlog quotes ("we lost eight months of
onboarding data by changing a dropdown").

Closed by three tests in `apps/onboarding/tests/test_retention.py`:
`test_preview_reports_the_impact_without_persisting` (fails against the
simulated regression), `test_preview_deletes_nothing` (a guard against
enforcement being wired into the request path; it cannot fail as the view
stands, and says so), and `test_a_patch_without_preview_does_persist` as the
control, without which a view that never saved would look correct.

**Remaining for M-03 AC-3: nothing.** The component is mountable wherever the
OIA admin settings live; no dedicated settings route was ever part of this
AC.

### 3.2 Operational Gap: Grafana Dashboard Provisioning — CHECKED 2026-10-20

The `oia.json` dashboard exists in `onboarding-intelligence-agent-svc/deployment/grafana/dashboards/` but the top-level `deployment/` directory has no Grafana provisioning configuration. The POI service has the same pattern (`prompt-optimization-svc/deployment/grafana/dashboards/`).

**Action**: Verify that the GCP Cloud Run deployment picks up the dashboard
from the service's own directory, or copy it to a central provisioning
location. This is an operational check, not a code change.

**Result: neither option in that action exists. The gap is wider than a
missing provisioning file — there is no Grafana anywhere, and nothing that
could serve this dashboard's queries.**

What was checked, and what each showed:

| Check | Finding |
|---|---|
| `grep -rln grafana deployment/ .github/` | **no matches at all** — not compose, not a GCP script, not CI |
| Grafana/Prometheus service in `deployment/docker-compose.yml` | none; the only "monitoring" hit is a comment on the trend agent |
| `deployment/gcp/*.sh` | no provisioning step; `01-setup-project.sh` grants only `roles/monitoring.metricWriter` |
| Cloud Run services matching `grafana\|prom` | **not verified** — see below |
| `oia.json` itself | 10 panels, **13 PromQL targets, datasource type `prometheus`** |

So the dashboard cannot render even if it were loaded: it asks 13 PromQL
questions and the deployed stack has no Prometheus to ask. `roles/monitoring.metricWriter`
points at Cloud Monitoring, which does not answer PromQL unless Managed
Service for Prometheus is enabled and scraping these services.

`prompt-optimization-svc/deployment/grafana/dashboards/prompt_optimization.json`
is in exactly the same position, so this is a fleet-wide gap rather than an
OIA one.

**The dashboards are not the only orphans.** Both services also ship
Prometheus **alert rules** that the first version of this inventory missed:

| File | Contents |
|---|---|
| `onboarding-intelligence-agent-svc/deployment/prometheus/alerts/oia.yml` | 7 alerts — `OIA_STT_HighLatency`, `OIA_SufficiencyHighLatency`, `OIA_DLQ_Active`, `OIA_CircuitBreakerOpen`, `OIA_DroppedUngroundedSpike`, `OIA_EventsDropped`, `OIA_SufficiencyDropsActive`, wired to the `ALERT_*` thresholds in `app/metrics.py` |
| `prompt-optimization-svc/deployment/prometheus/alerts/prompt_optimization.yml` | same pattern |

These matter more than the dashboard: a dashboard nobody opens is a missed
insight, but an alert that never fires is a missed outage. Any option below
has to mount `rule_files` as well as the dashboard directories, or it leaves
M-04's alerting exactly as dead as it is today, one directory over.

**M-04 was marked ✅ until this check; it now reads ⚠️ at line 194.** The file
does exist and its queries match the metric names the service exports, which
is why that tick was not unreasonable — but nothing renders it, so no
operator can currently see any of it. "The dashboard is written" and "the
dashboard is live" are separate claims, and only the first was true.

**Nothing on the GCP side was verified. Every finding above is repo-only.**
`gcloud run services list`, `gcloud monitoring dashboards list` and
`gcloud services list` all fail with "Reauthentication failed. cannot prompt
during non-interactive execution" and need an interactive `gcloud auth login`.

An earlier draft of this section reported "Cloud Run services matching
grafana|prom: none" as a checked finding. **That was wrong, and worth
recording as a method error rather than quietly fixing**: the command exited
1 and printed nothing, and the check was a `grep` over its combined output,
so the error text matched nothing and read as a clean negative. A probe whose
failure mode looks identical to its pass mode proves nothing. Re-run with the
exit status checked, not the output pattern.

Still to establish, once credentials are live (all read-only):

- whether Managed Service for Prometheus is enabled on `zorven-503517`
- whether anything is actually scraping these two services
- whether a Cloud Monitoring dashboard was created by hand outside the repo

**Options, neither started — this needs a decision, not more checking:**

- **A. Self-hosted, local-dev only.** Add Prometheus + Grafana to
  `deployment/docker-compose.yml` behind a `with-monitoring` profile,
  mounting both services' `deployment/grafana/dashboards/` **and**
  `deployment/prometheus/alerts/` directories, with a datasource scraping
  `/metrics`. Self-contained and verifiable on a laptop; does nothing for
  production.

  **The scrape config is two targets, not 27.** Only
  `onboarding-intelligence-agent-svc` and `prompt-optimization-svc` expose
  `/metrics` or even depend on `prometheus_client`; Django has no metrics
  route either. A scrape config for the other 25 would poll 404s. An earlier
  draft of this section said "27 services" and estimated half a day from it —
  the real surface is small enough that the work is mostly compose plumbing
  and provisioning YAML, not per-service instrumentation. Instrumenting the
  other services is a separate, much larger question nobody has asked yet.
- **B. GCP-native.** Enable Managed Service for Prometheus and get these two
  services scraped, then point Grafana (or Cloud Monitoring) at it. The only
  path that reaches a production operator, and the one with real monthly cost
  — Managed Prometheus bills per sample ingested, so it needs the §7 cost
  treatment before being committed to.

  **Correction to an earlier draft, which claimed B would be "half-done" if
  Managed Prometheus turned out to be enabled.** That is not how it reaches
  Cloud Run. GMP's managed collection targets GKE workloads; Cloud Run needs
  a per-service **sidecar collector** (or push through the Prometheus-compatible
  write API). So there is no central scrape config that can pick these up,
  and GMP merely being on changes nothing on its own — each of the two
  services still needs a redeploy with a sidecar. Confirm the current
  sidecar/collection story before this framing drives the A-vs-B choice.

Converting `oia.json` to Cloud Monitoring's own dashboard format is a third
path, but it is a rewrite rather than a copy: the formats are not
interchangeable, and the 13 PromQL expressions would each need an MQL or
PromQL-on-Cloud-Monitoring equivalent.

### 3.3 Verification Pass

Before declaring production-ready, the following should be verified:

| Check | Command | Expected |
|-------|---------|----------|
| Django unit tests | `cd ai-brand-automator && pytest apps/onboarding/tests/ -v` | All green |
| Django integrations tests | `cd ai-brand-automator && pytest apps/integrations/tests/ -v` | All green |
| Agent unit tests | `cd onboarding-intelligence-agent-svc && pytest -m unit -q` | All green |
| Agent integration tests | `pytest -m integration -q` | All green (needs Redis on :6379) |
| Agent e2e tests | `pytest -m e2e -q` | All green (needs Docker) |
| Agent load tests | `pytest -m load --collect-only` | Collects; full run needs `OIA_LOAD_TARGET` |
| Frontend tests | `cd ai-brand-automator-frontend && npm test` | All green |
| Frontend build | `npm run build` | No type errors |
| Black formatting | `black --check apps/ && black --check ../onboarding-intelligence-agent-svc/app/` | No diffs |
| Flake8 | `flake8 apps/ && flake8 ../onboarding-intelligence-agent-svc/app/` | No errors |

**Run 2026-10-20. Eight of the ten pass. Two do not, and a third passes only
on a reading of "green" that hides something.**

| # | Check | Result |
|---|---|---|
| 1 | Django unit (`apps/onboarding/tests/`) | ⚠️ **3 failed, 759 passed** — all three in `test_migrations.py`, pre-existing and already documented as red on `development_main` |
| 2 | Django integrations (`apps/integrations/tests/`) | ✅ **86 passed** (4m56s) |
| 3 | Agent unit (`-m unit`) | ⚠️ **7 failed, 801 passed, 4 skipped** — all seven in `test_redact_pii.py`, `presidio_analyzer` is not installed locally; green in CI |
| 4 | Agent integration (`-m integration`) | ❌ **7 failed, 295 passed, 22 skipped** — see breakdown |
| 5 | Agent e2e (`-m e2e`) | ⚠️ **13 passed, 13 skipped** — and CI never runs this suite at all |
| 6 | Agent load (`--collect-only`) | ✅ 4 collected |
| 7 | Frontend tests | ✅ **41 suites, 542 passed, 1 skipped** |
| 8 | Frontend build | ✅ exit 0, no type errors |
| 9 | Black | ✅ `apps/` clean under CI's pinned 23.12.1; service clean under 26.5.1 (its requirement is `>=24.0.0`, so that is CI-equivalent) |
| 10 | Flake8 | ✅ clean on both trees |

**Check 4's seven failures, classified:**

| Failures | Cause |
|---|---|
| 4 × `test_watchdog.py` | **Leftover data in the shared dev Redis, not a code fault.** `tests/e2e/test_gdpr_erasure.py:44` seeds every key with `r.set(k, "test-data")`, including `keys.session(sid)` — where production writes a *hash*. The watchdog scans `oia:v1:*:session:*` and calls `hget` on each match, so that one string raises `WRONGTYPE` and takes down the whole scan pass. `_parse_session_key` filters key *shape* (`:summary`, five parts) but never type. |
| 1 × `test_watchdog.py::test_stuck_session_watchdog_finalises` | A different cause in the same file: the test deletes its own `watchdog:sess-stuck` claim key *after* its assertion, and claims carry a 120 s TTL, so any earlier failed run of this test makes the next one fail with `closed == 0` for two minutes. Self-inflicted once anything upstream goes red. |
| 1 × `test_outbox.py::test_drain_replays_entries_fifo` | Same class: `assert 142 == 2`, where 142 was the depth of an outbox left by earlier runs. The backend is unreachable in tests, so nothing drains and each run adds to it. |
| 1 × `test_ws_transcript_markers.py` | The known #680 residue. |

**Both causes were proved by remedy, not inferred.** Deleting exactly the
three non-hash keys took `test_watchdog.py` from 5 failed to 1 failed / 4
passed; clearing the one stale claim key then gave **26 passed** across
`test_watchdog.py` and `test_outbox.py` together, with no code change.

Checked against the commit before #681 (`40e55313`) with that PR's two files
reverted: the watchdog and outbox tests fail there too, so none of this is a
regression from the live-lock work.

**A latent robustness issue worth its own decision, not fixed here.** The
watchdog's failure mode in production is a `WRONGTYPE` in a background task
that halts the *entire* scan pass for *every* tenant — so stuck sessions
silently stop being finalised. No production writer puts a non-hash at that
path today (the only one found is the e2e fixture above), so this is latent
rather than live, but DB 2 is shared with ten other services and the guard
checks shape, not type. A type check, or an `hget` wrapped per key, would
contain it to one bad key instead of the whole pass.

**Check 5 needs its expectation rewritten.** The table says "All green (needs
Docker)", which made Docker look like the binding constraint. Docker was
running (29.6.2) and is not the issue: **10 of the 13 skips are "no Gemini key
is configured — nothing would be generated"** and one is "OIA_TEST_E2E not
set". Neither is set in CI either, and CI's OIA job runs
`-m "not integration and not e2e"` and `-m integration` — **so `-m e2e` runs
nowhere, in CI or locally**. The PREP end-to-end path is unverified
everywhere. That is a gap in the verification strategy rather than a test
failure, and no amount of running this check locally will close it.

**Runtime, which the table does not mention.** Measured: check 1 **25m06s**,
check 2 4m56s, check 5 4m26s, check 4 3m41s, check 3 1m01s, the rest under a
minute. **Roughly 40 minutes of wall-clock for the full pass**, three
quarters of it in the two Django suites. Anyone treating §3.3 as a quick
pre-release gate should plan for that, or split the Django suites out to run
in parallel with the rest.

**What to do about the environmental failures.** Checks 3 and 4 cannot go
green on this machine without (a) installing `presidio_analyzer`, and (b)
clearing the shared dev Redis of keys that earlier runs left at paths
production uses for different types. The second is the more interesting one:
the suite is not self-isolating, so "green" currently depends on run history.
Both are test-environment work, deliberately not bundled into this
verification pass.


---

## 4. Doc-vs-Reality Conflicts

### 4.1 Previous audit overstated remaining scope

The cross-reference audit (2026-09-06) concluded that "remaining work" was
the Django backend and Next.js frontend. In reality, both were ~99% complete
at the time of the audit. The agent service cross-reference was thorough but
the Django/frontend verification was insufficiently deep — it looked at
directory structure rather than verifying story-by-story AC coverage.

**Recommendation**: No action needed. This plan supersedes the previous
audit's scope assessment.

### 4.2 M-03 labeled "Backend" but has a frontend AC

The backlog labels M-03 as "2 pts · Backend" but AC-3 requires a frontend
component (`frontend/__tests__/RetentionSettings.test.tsx`). This is a
labeling error in the backlog.

**Recommendation**: Build the frontend component anyway — the AC is clear.

### 4.3 Celery task routing for OIA tasks

`apps.onboarding.*` and `apps.integrations.*` tasks are not in `celery.py`'s
`task_routes` — they hit the default `celery` queue. This works but means
OIA tasks compete with general-purpose work.

**Recommendation**: Add routing rules for OIA tasks to the `orchestration`
queue (or a new `onboarding` queue) as a follow-up optimization. Not
blocking production readiness.

---

## 5. Assumptions

1. The `RetentionSettings` component follows the existing OIA frontend
   patterns: functional component, `useAuth()`, `apiClient`, Digital
   Twilight theme, `glass-card` styling.
2. The retention preview endpoint (how many records would be affected by
   shortening) either exists or can be derived from the existing
   `enforce_retention_windows` logic with a dry-run parameter.
3. The Grafana dashboard is deployed via the service's own directory
   rather than a central provisioning config.
4. No new Django migrations are needed — the `RetentionConfig` model
   already exists.
5. The verification pass uses real services (Redis, Kafka where
   configured) per the no-mocks rule.

---

## 6. Testing

### 6.1 Unit Tests

- `RetentionSettings.test.tsx`: Renders form, calls preview on value decrease,
  shows warning with count, calls update on confirmation, disables for
  non-Owner/Admin roles.

### 6.2 Property Tests

None required for this scope.

### 6.3 Integration Tests

- Verify the retention config CRUD roundtrip from the frontend API helpers
  through the Django endpoint and back.

### 6.4 E2E Tests

- The existing N-01 suite covers GDPR erasure. The retention settings
  component should be exercised in a new test or appended to the existing
  `test_gdpr_erasure.py` as a "configure retention, verify enforcement"
  scenario.

---

## 7. GCP Cost Estimation

No new GCP resources required. The remaining work is a single frontend
component with no new services, containers, or infrastructure.

---

## 8. Git Workflow

- **Branch**: `feat/oia-m03-retention-frontend` from `development_main`
- **PR target**: `development_main`
- **Commit prefix**: `feat(oia):`
- **Merge to `main`**: Only after all OIA stories are complete and tested.
  Per the branch workflow feedback, feature branches + PRs target
  `development_main` during OIA.

---

## 9. Delivery Estimate

| Item | Points | Effort |
|------|--------|--------|
| RetentionSettings component + test | 1 | ~2 hours |
| API helpers in onboarding-sessions.ts | 0 | included above |
| Grafana provisioning verification | 0 | ~30 minutes |
| Full verification pass (all test suites) | 0 | ~2 hours |
| **Total** | **1** | **~4.5 hours** |

---

## 10. What This Plan Does NOT Deliver

1. **A settings route/page**: The RetentionSettings component is a
   self-contained form. Where it mounts is a product decision beyond OIA.
2. **Celery queue optimization**: OIA tasks work on the default queue.
   Routing them to a dedicated queue is a follow-up.
3. **Load test execution**: The load tests exist (N-02) but require a
   deployed target with `OIA_LOAD_TARGET`. Execution is a deployment
   activity, not a code activity.
4. **Production deployment**: This plan covers code completion, not the
   deploy-to-production runbook.
