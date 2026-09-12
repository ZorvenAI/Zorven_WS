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

**The OIA implementation is ~99% complete.** A story-by-story codebase
verification against all 66 active stories in the backlog v2.1 reveals that
every epic (A through N) has been implemented across all three layers: the
agent service, the Django backend, and the Next.js frontend.

The previous cross-reference audit (2026-09-06) correctly identified the agent
service as complete but stated that "the remaining work is Django backend and
frontend." That assessment was wrong. Both layers were already substantially
built at the time of the audit — approximately 23,000 lines of production code
and 10,000 lines of tests on the Django side, and 7,000 lines of components
plus 5,600 lines of tests on the frontend side.

**Remaining work**: one frontend component (M-03 AC-3), one operational
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
- M-03 ⚠️ **PARTIAL**: Backend complete — `RetentionConfig` model, CRUD
  endpoints (`/api/v1/onboarding/retention/`), `enforce_retention_windows`
  Beat task (03:00 UTC daily), RBAC on Owner/Admin only.
  **MISSING**: `RetentionSettings` frontend component (M-03 AC-3 —
  "they are told how much existing evidence that will delete and when").
  The backlog names `frontend/__tests__/RetentionSettings.test.tsx`.
- M-04 ✅: Grafana dashboard (`deployment/grafana/dashboards/oia.json`),
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

### 3.1 Code Gap: RetentionSettings Frontend Component (M-03 AC-3)

**Story**: M-03 · Configurable retention and enforcement
**AC-3**: "Shortening retention is not retroactively destructive without warning"
**What's missing**: A frontend component that:
1. Calls `GET /api/v1/onboarding/retention/` to fetch current config
2. Provides a form to update `retention_days` via `PATCH`
3. When the new value is shorter than the current value, calls a preview
   endpoint to show how many sessions/recordings would be affected
4. Renders a confirmation dialog with the affected count before saving
5. Only available to Owner/Admin roles

**Backend support already exists**:
- `RetentionConfig` model with per-tenant default of 365 days
- CRUD endpoints at `/api/v1/onboarding/retention/`
- RBAC enforced (Owner/Admin only)
- The `enforce_retention_windows` Beat task handles actual enforcement

**Estimate**: 1 story point. The component is small (a settings form with a
confirmation dialog), and the backend is already complete.

**Files to create**:
- `src/components/onboarding/RetentionSettings.tsx` — the form + warning
- `src/__tests__/RetentionSettings.test.tsx` — per backlog naming
- Update to `src/lib/onboarding-sessions.ts` — add `getRetentionConfig()`
  and `updateRetentionConfig()` API helpers

**Does not deliver**: A dedicated settings route/page. This component should
be mountable wherever the OIA admin settings live. If no settings page
exists yet, the component can be placed behind a route created for this
purpose or embedded in an existing admin area.

### 3.2 Operational Gap: Grafana Dashboard Provisioning

The `oia.json` dashboard exists in `onboarding-intelligence-agent-svc/deployment/grafana/dashboards/` but the top-level `deployment/` directory has no Grafana provisioning configuration. The POI service has the same pattern (`prompt-optimization-svc/deployment/grafana/dashboards/`).

**Action**: Verify that the GCP Cloud Run deployment picks up the dashboard
from the service's own directory, or copy it to a central provisioning
location. This is an operational check, not a code change.

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
