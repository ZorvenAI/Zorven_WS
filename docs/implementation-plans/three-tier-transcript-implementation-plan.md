# Three-Tier Transcript Processing — Implementation Plan

**Author:** Claude Code
**Date:** 2026-11-21
**Status:** DRAFT — awaiting approval before implementation begins
**Design doc:** `docs/implementation-plans/three-tier-transcript-design.md` (approved)
**Supersedes:** Nothing — first implementation plan for this feature.
**Linked from:** The design document's §7 (Migration Plan) references this.
**User instruction:** "I approve it please author a implementation plan to implement this."
**Skill note:** The `zorven-implementation-plan` skill's reference files
(`testing-strategy.md`, `gcp-cost-estimation.md`, `git-workflow.md`,
`implementation-plan-template.md`) do not exist yet. This plan follows the
conventions established by A-02, A-05, and A-03 plans, not the missing
template. Sections 6–8 are improvised from those prior plans.

---

## 1. Scope

Implement the approved three-tier transcript design across the OIA service,
the Django backend, and the Next.js frontend. The three tiers are:

| Tier | Name | Producer | Visible to GM |
|------|------|----------|---------------|
| T1 | Raw transcript | STT (existing) | No (GCS diagnostics only) |
| T2 | Clean transcript | OIA LLM background task | Yes |
| T3 | Description | OIA LLM background task (fed by T2) | Yes |

T2 and T3 run as concurrent `asyncio.Task`s in LIVE mode and as a sequential
single-pass in PROCESS mode. PROCESS mode output replaces LIVE previews as
the legally binding record.

### What this plan does NOT deliver

- Real-time token-by-token SSE streaming of T2/T3
- Speaker diarization improvements
- Batch processing of uploaded recordings (post-meeting)
- UI for accessing raw transcripts (GCS IAM only)
- Editable descriptions (explicitly prohibited — legally bound content)

---

## 2. Stories

The work is decomposed into 10 stories across 3 epics, ordered for sequential
implementation with minimal cross-dependency.

### Epic T — OIA Service (Transcript Processing Core)

| # | Story | Depends on | Delivers |
|---|-------|------------|----------|
| T-01 | Config + Redis key builders | — | New settings in `config.py`, new `TenantKeys` methods |
| T-02 | TranscriptCleaner module | T-01 | `app/logic/transcript_cleaner.py` with `run()` and `run_batch()` |
| T-03 | DescriptionGenerator module | T-01 | `app/logic/description_generator.py` with `run()` and `run_batch()` |
| T-04 | WS handler integration (LIVE) | T-02, T-03 | Spawn/cancel T2+T3 tasks in `ws.py` start/stop |
| T-05 | PROCESS mode integration | T-02, T-03 | T2+T3 steps in `process_executor.py` |
| T-06 | GCS finalization + manifest | T-04 | Upload T1/T2/T3 to GCS, write manifest.json |

### Epic D — Django Backend

| # | Story | Depends on | Delivers |
|---|-------|------------|----------|
| D-01 | Model + migration + serializer | — | 5 new fields on `MeetingRecording`, API exposure |
| D-02 | Backend client + callback | T-06 | OIA → Django callback writes T2/T3/GCS paths |

### Epic F — Frontend

| # | Story | Depends on | Delivers |
|---|-------|------------|----------|
| F-01 | DescriptionTab component | D-01 | New tab showing T3, read-only |
| F-02 | Tab bar + clean transcript toggle | F-01 | Description tab in nav, T2/T1 toggle in Meeting |

---

## 3. Story Details

### T-01: Config + Redis Key Builders

**Goal:** Add configuration settings and Redis key builders needed by T2 and
T3.

**Changes:**

`onboarding-intelligence-agent-svc/app/core/config.py` — modify + add to `Settings`:
```python
# Existing field — change default:
PROCESS_MODEL: str = "claude-sonnet-4"  # was "gemini-2.0-flash"

# ── Transcript cleaning (Three-Tier, Design §6) ─────
CLEAN_INTERVAL_S: int = 30
CLEAN_MIN_SEGMENTS: int = 5
DESCRIPTION_INTERVAL_S: int = 60
DESCRIPTION_MIN_CHARS: int = 200
FINALIZE_TIMEOUT_S: int = 30
CLEAN_MODEL: str = "claude-sonnet-4"
DESCRIPTION_MODEL: str = "claude-sonnet-4"
```

`onboarding-intelligence-agent-svc/app/cache/redis_manager.py` — add to
`TenantKeys`:
```python
def transcript_clean(self, session_id: str) -> str:
    """String (JSON) · 24 h · T2 complete clean transcript."""
    return f"{self._scope}live:{session_id}:transcript_clean"

def clean_version(self, session_id: str) -> str:
    """String (int) · 24 h · T2 generation counter."""
    return f"{self._scope}live:{session_id}:clean_version"

def description(self, session_id: str) -> str:
    """String (JSON) · 24 h · T3 current description."""
    return f"{self._scope}live:{session_id}:description"

def desc_version(self, session_id: str) -> str:
    """String (int) · 24 h · T3 generation counter."""
    return f"{self._scope}live:{session_id}:desc_version"
```

All keys under existing `oia:v1:` prefix, DB 2. TTL set to `TTL_SESSION`
(existing constant, 24h).

**Acceptance criteria:**
1. All 4 new keys are built through `TenantKeys` — no inline formatting
2. `test_redis_key_isolation.py` automatically covers the new builders (it
   reflects over all methods)
3. All settings have documented defaults and are exposed via `OIA_` env prefix
4. Existing tests pass without modification

**Tests:**
- Unit: verify key format for each new builder method
- Unit: verify config defaults parse correctly and `CLEAN_MODEL` falls back to
  `PROCESS_MODEL` at usage site (not in config)

---

### T-02: TranscriptCleaner Module

**Goal:** Implement the T2 cleaner as an async loop that re-cleans the full
raw transcript on each cycle.

**File:** `onboarding-intelligence-agent-svc/app/logic/transcript_cleaner.py`

**Class:** `TranscriptCleaner`

**Constructor receives:**
- `redis: RedisManager`
- `keys: TenantKeys`
- `session_id: str`
- `llm: LLMProvider`
- `storage: StorageProvider` (for GCS finalization)
- `settings: Settings`
- `send_ws: Callable` (to push `transcript.clean_progress` frames)

**Methods:**

| Method | Mode | Behaviour |
|--------|------|-----------|
| `run(cancel: asyncio.Event)` | LIVE | Loop: sleep `CLEAN_INTERVAL_S`, read all T1 from Redis `LRANGE`, skip if no new segments, LLM clean, atomic `SET` to Redis, increment version, push WS frame |
| `finalize()` | LIVE | Final re-clean of complete transcript, flush to GCS |
| `run_batch(raw_segments: list[dict])` | PROCESS | Single-pass clean, return cleaned text |

**Concurrency guards:**
- Single-task design — no overlap possible since `run()` awaits the LLM call
  synchronously within each iteration
- T1 read via `LRANGE` is atomic — snapshot read
- Skip cycle when `len(all_segments) == last_segment_count` (no new data)
- Cancellation token checked before each LLM call
- Final flush on stop (`finalize()`)

**LLM prompt:** As specified in design doc §4.1 (the cleaning prompt).

**Error handling:**
- LLM failure: log warning, skip cycle, retry next interval (cursor does not
  advance semantically since we always read all segments)
- GCS failure: use existing `gcs` circuit breaker + spool fallback
- Timeout: each LLM call bounded by `ANALYSIS_TIMEOUT_S`

**Tests:**
- Integration: seed T1 segments into real Redis, run one cleaner cycle, verify
  T2 is written to Redis with correct key
- Integration: verify `run_batch()` with real LLM produces valid output
- Integration: verify `finalize()` uploads to real GCS
- Integration: verify skip when no new segments
- Integration: verify cancellation stops the loop

---

### T-03: DescriptionGenerator Module

**Goal:** Implement the T3 generator as an async loop that regenerates the
full description from T2 on each cycle.

**File:** `onboarding-intelligence-agent-svc/app/logic/description_generator.py`

**Class:** `DescriptionGenerator`

**Constructor receives:** Same shape as `TranscriptCleaner` but reads T2
instead of T1. `send_ws` pushes `description.updated` frames.

**Methods:**

| Method | Mode | Behaviour |
|--------|------|-----------|
| `run(cancel: asyncio.Event)` | LIVE | Loop: sleep `DESCRIPTION_INTERVAL_S`, read T2 from Redis `GET`, skip if `len < DESCRIPTION_MIN_CHARS`, LLM generate, `SET` to Redis, increment version, push WS frame |
| `finalize()` | LIVE | Final generation with complete T2, flush to GCS |
| `run_batch(clean_transcript: str)` | PROCESS | Single-pass generation, return description text |

**Concurrency guards:**
- Single-task, sequential iterations
- T3 reads T2 via atomic `GET` (T2 writes via atomic `SET`)
- T3 skips if T2 has fewer than `DESCRIPTION_MIN_CHARS` characters

**LLM prompt:** As specified in design doc §4.2 (the description prompt).

**Tests:**
- Integration: seed T2 text into real Redis, run one generator cycle, verify
  T3 is written
- Integration: verify skip when T2 is below `DESCRIPTION_MIN_CHARS`
- Integration: verify `run_batch()` with real LLM
- Integration: verify `finalize()` uploads to real GCS

---

### T-04: WS Handler Integration (LIVE mode)

**Goal:** Spawn T2 and T3 tasks when recording starts, cancel and finalize
when recording stops or WS disconnects.

**File:** `onboarding-intelligence-agent-svc/app/api/ws.py`

**Changes in `_handle_control` on `start` command:**

After spawning the STT task (existing code), create and store:
```python
cancel_event = asyncio.Event()
t2_task = asyncio.create_task(cleaner.run(cancel_event), name=f"t2-clean-{session_id}")
t3_task = asyncio.create_task(desc_gen.run(cancel_event), name=f"t3-desc-{session_id}")
stt_state["t2_task"] = t2_task
stt_state["t3_task"] = t3_task
stt_state["t2t3_cancel"] = cancel_event
```

**Changes on `stop` command and WS disconnect cleanup:**

```python
cancel_event.set()
await cleaner.finalize()
await desc_gen.finalize()
await asyncio.wait_for(
    asyncio.gather(t2_task, t3_task, return_exceptions=True),
    timeout=settings.FINALIZE_TIMEOUT_S,
)
```

**New WS frame types pushed to frontend:**
- `transcript.clean_progress` — sent after each T2 cycle
- `description.updated` — sent after each T3 cycle

The `send_ws` callback is a closure over the WebSocket's `send_json` that
wraps the frame in the existing envelope format.

**Tests:**
- Integration: full WS session with fake STT, verify T2 and T3 frames arrive
  after recording starts
- Integration: verify T2/T3 tasks are cancelled on stop
- Integration: verify cleanup on disconnect (WS close without stop)

---

### T-05: PROCESS Mode Integration

**Goal:** Add T2 and T3 as sequential steps in the PROCESS executor, before
existing field extraction.

**File:** `onboarding-intelligence-agent-svc/app/logic/process_executor.py`

**Changes in `_run_job`:**

After evidence assembly and before field extraction, insert:

```python
# T2: clean the raw transcript
raw_segments = await self._load_raw_transcript(keys, session_id)
if raw_segments:
    cleaner = TranscriptCleaner(...)
    clean_text = await cleaner.run_batch(raw_segments)
    await self._redis.client.set(
        keys.transcript_clean(session_id), clean_text, ex=TTL_SESSION
    )

    # T3: generate description from clean transcript
    if len(clean_text) >= self._settings.DESCRIPTION_MIN_CHARS:
        desc_gen = DescriptionGenerator(...)
        description_text = await desc_gen.run_batch(clean_text)
        await self._redis.client.set(
            keys.description(session_id), description_text, ex=TTL_SESSION
        )
```

The callback payload gains `transcript_clean`, `description`, and their GCS
paths.

**Tests:**
- Integration: submit a PROCESS job with real Redis + LLM, verify T2 and T3
  are produced
- Integration: verify callback includes new fields
- Integration: verify GCS upload of T1/T2/T3

---

### T-06: GCS Finalization + Manifest

**Goal:** Upload all three transcript tiers to GCS under the session-scoped
prefix and write a `manifest.json`.

**Changes:**

Extend the existing `StorageProvider` (or add a helper in
`app/providers/storage.py`) with:

```python
async def upload_transcript_tier(
    self, tenant_id: str, session_id: str, tier: str, content: str | list
) -> str:
    """Upload a transcript tier (raw/clean/description) to GCS.

    Returns the GCS path.
    """
    path = f"{LANDING_PREFIX}/{tenant_id}/{session_id}/transcript/{tier}.json"
    ...
```

And a `write_manifest` method that writes `manifest.json` listing all
artefacts for the session.

**GCS paths:**
```
_landing/oia/{tenant_id}/{session_id}/transcript/raw.json
_landing/oia/{tenant_id}/{session_id}/transcript/clean.json
_landing/oia/{tenant_id}/{session_id}/transcript/description.json
_landing/oia/{tenant_id}/{session_id}/manifest.json
```

Uses existing `gcs` circuit breaker. On breaker open, falls back to local
spool (existing mechanism).

**Tests:**
- Integration: upload all three tiers to real GCS, verify paths
- Integration: verify manifest.json contents
- Integration: verify circuit breaker fallback for transcript uploads

---

### D-01: Model + Migration + Serializer

**Goal:** Add 5 new fields to `MeetingRecording` and expose T2 and T3 through
the API serializer.

**File:** `ai-brand-automator/apps/onboarding/models.py`

**New fields on `MeetingRecording`:**
```python
transcript_clean = models.JSONField(
    default=list, blank=True,
    help_text="T2 — cleaned transcript. Same schema as transcript but noise removed."
)
transcript_clean_gcs_path = models.CharField(
    max_length=500, blank=True, default="",
    help_text="GCS path to clean transcript JSON"
)
description = models.TextField(
    blank=True, default="",
    help_text="T3 — structured brand-building description from clean transcript"
)
description_gcs_path = models.CharField(
    max_length=500, blank=True, default="",
    help_text="GCS path to description document"
)
raw_transcript_gcs_path = models.CharField(
    max_length=500, blank=True, default="",
    help_text="GCS path to raw (T1) transcript — diagnostics only"
)
```

All fields are nullable/blank with defaults — no data migration needed.
Existing recordings see empty values.

**Serializer changes** (`apps/onboarding/serializers.py`):

`MeetingRecordingSerializer`:
- Add `has_description` SerializerMethodField (same pattern as `has_summary`)
- Add `has_clean_transcript` SerializerMethodField
- Add `transcript_clean` and `description` to detail serializer (not list)
- `transcript_clean_gcs_path`, `description_gcs_path`, `raw_transcript_gcs_path`
  are **internal only** — not exposed in the API (same reasoning as existing
  `transcript_gcs_path` exclusion)

**Internal endpoint update:**

The existing `RECORDING_SUMMARY_PATH` endpoint (used by OIA's
`BackendClient.update_recording_summary`) needs to accept the new fields in
its payload. Update the internal view to handle `transcript_clean`,
`description`, and GCS path fields.

**Migration:** `python manage.py makemigrations` → new migration file in
`apps/onboarding/migrations/`.

**Tests:**
- Existing test patterns: test model creation with new fields
- Test serializer includes `has_description` and `has_clean_transcript`
- Test that GCS paths are excluded from API response
- Use `SERVER_NAME = "localhost"` in fixtures (existing convention)

---

### D-02: Backend Client + Callback

**Goal:** Extend OIA's `BackendClient` to write T2, T3, and GCS paths back to
Django.

**File:** `onboarding-intelligence-agent-svc/app/services/backend_client.py`

**Changes:**

Extend `update_recording_summary` (or add a new method) to accept:
```python
async def update_recording_transcript_tiers(
    self,
    tenant_id: str,
    recording_id: str,
    transcript_clean: list[dict] | None = None,
    description: str | None = None,
    raw_transcript_gcs_path: str = "",
    transcript_clean_gcs_path: str = "",
    description_gcs_path: str = "",
) -> None:
```

This calls the internal Django endpoint which writes the fields to
`MeetingRecording`.

**Tests:**
- Integration: call the method against real Django backend, verify fields are
  saved

---

### F-01: DescriptionTab Component

**Goal:** New frontend component that displays the T3 description document,
updating as the meeting progresses.

**File:** `ai-brand-automator-frontend/src/components/onboarding/DescriptionTab.tsx`

**Behaviour:**
- During recording: polls for T3 updates (or receives via WS `description.updated` frame)
- Shows "Generating description..." spinner while T3 hasn't produced output yet
- After recording stops: shows final description
- Read-only — no edit controls (legally bound content)
- Renders structured sections (Business Identity, Products & Services, etc.)
  with section headers
- Uses existing Digital Twilight design system: `glass-card`, `bg-brand-midnight`,
  `text-brand-silver`

**Data source:** Fetches from the recording detail API endpoint which now
includes `description`.

**Tests:**
- Jest: renders loading state when no description
- Jest: renders structured description with sections
- Jest: no edit controls present (read-only assertion)

---

### F-02: Tab Bar + Clean Transcript Toggle

**Goal:** Add the Description tab to the nav bar and add a T2/T1 toggle in
the Meeting view.

**File changes:**

`OnboardingUnified.tsx`:
- Add new tab: `Overview | Meeting | Description | Review | Calendar`
- Description tab visible when session has a recording (`showMeetingTab`
  condition)
- Import and render `DescriptionTab` component

`MeetingTab.tsx` (or transcript sub-component):
- After recording stops: show T2 (clean transcript) by default
- Add toggle: "Clean" / "Raw" to switch between T2 and T1 view
- During recording: continue showing real-time raw segments (latency matters)

`RecordingsLibrary.tsx`:
- Replace `has_summary` badge with `has_description`
- Clicking a recording opens description view
- Transcript shown in detail drawer uses T2 by default

**Tests:**
- Jest: Description tab renders between Meeting and Review
- Jest: tab visibility tied to recording existence
- Jest: clean/raw toggle present after recording stops

---

## 4. Implementation Order

```
Phase 1 — Foundation (no UI, no user-visible change)
  T-01  Config + Redis key builders
  D-01  Model + migration + serializer (can run in parallel with T-01)

Phase 2 — OIA Core (backend processing)
  T-02  TranscriptCleaner
  T-03  DescriptionGenerator (can run in parallel with T-02)

Phase 3 — Integration
  T-04  WS handler integration (LIVE)
  T-05  PROCESS mode integration (can run in parallel with T-04)
  T-06  GCS finalization + manifest
  D-02  Backend client + callback

Phase 4 — Frontend
  F-01  DescriptionTab component
  F-02  Tab bar + clean transcript toggle
```

Each phase requires the previous phase to be complete. Within a phase,
parallelizable stories are noted.

---

## 5. Assumptions and Decisions

### Assumptions

1. **A-1:** The existing `LLMProvider` can handle the T2/T3 prompts without
   modification — it already supports Gemini and Anthropic models.
2. **A-2:** The T2/T3 LLM calls are within the existing token budgets. A
   60-minute meeting produces ~15K tokens of raw transcript; each T2 cycle
   processes incrementally more. Total cost across all T2 cycles is roughly
   10× a single pass (design doc §3.1).
3. **A-3:** The existing `gcs` circuit breaker and local spool fallback are
   sufficient for T1/T2/T3 uploads — no new breaker needed.
4. **A-4:** The GCS `_landing/oia/` prefix structure already exists (from
   audio recording uploads) — we're adding a `transcript/` subdirectory.
5. **A-5:** `PROCESS_MODEL` changes from `gemini-2.0-flash` to
   `claude-sonnet-4`. All three models (`PROCESS_MODEL`, `CLEAN_MODEL`,
   `DESCRIPTION_MODEL`) default to Claude Sonnet 4 for quality and
   consistency. Per-tier override via env vars is still possible.

### Decisions needing user's call

1. **DC-1: T2/T3 prompt model.** RESOLVED — Use `claude-sonnet-4` for both
   `CLEAN_MODEL` and `DESCRIPTION_MODEL`. The content is legally bound and
   quality matters more than cost. Claude Sonnet 4 is already used by
   audience-persona, voc, brand-positioning, and other OIA-adjacent services.
   The `PROCESS_MODEL` also changes from `gemini-2.0-flash` to
   `claude-sonnet-4` for consistency across the entire transcript pipeline.

2. **DC-2: Description section structure.** RESOLVED — Flat narrative with
   `##` headers, not collapsible sections. Simpler to implement and reads
   naturally.

---

## 6. Testing Strategy

> Note: The `references/testing-strategy.md` file does not exist yet. This
> section follows the conventions from A-05 and A-03 plans.

### 6.1 Unit Tests

Minimal for this feature — the core logic is LLM calls and Redis
reads/writes, which are integration concerns.

- Config parsing and defaults
- Redis key format assertions
- Prompt assembly (verify template interpolation, not LLM output)

### 6.2 Property Tests

Not applicable for this feature. The LLM output is non-deterministic and not
suitable for property-based testing.

### 6.3 Integration Tests

The bulk of the testing. Per the project convention: **no mocks, real services
only.**

| Test | Real deps | Verifies |
|------|-----------|----------|
| T2 reads T1 from Redis, writes T2 | Redis | Key schema, atomic SET, version counter |
| T3 reads T2, generates description | Redis + LLM | End-to-end T2→T3 pipeline |
| T2/T3 finalize uploads to GCS | Redis + GCS | Correct paths, circuit breaker |
| WS session spawns T2/T3 | Redis + WS | Tasks start on `start`, cancel on `stop` |
| PROCESS job runs T2→T3 sequentially | Redis + LLM | Single-pass output quality |
| Backend callback writes all fields | Redis + Django | Fields saved to MeetingRecording |
| Manifest written correctly | GCS | All artefacts listed |

### 6.4 End-to-End Tests

Docker Compose with all services. Full flow:

1. Start recording via WS
2. Send audio (fake STT)
3. Verify T2 frames arrive during recording
4. Verify T3 frames arrive during recording
5. Stop recording
6. Verify GCS contains raw.json, clean.json, description.json, manifest.json
7. Verify Django MeetingRecording has all 5 new fields populated

---

## 7. GCP Cost Estimation

> Note: The `references/gcp-cost-estimation.md` file does not exist yet. This
> section is improvised from the design doc's cost analysis.

### LLM Cost (Claude Sonnet 4)

Claude Sonnet 4 pricing: $3/M input, $15/M output.

**Per meeting (60 minutes, ~15K tokens raw transcript):**

| Component | Input tokens | Output tokens | Calls | Est. cost |
|-----------|-------------|---------------|-------|-----------|
| T2 LIVE (30s intervals, 120 cycles) | ~900K total | ~900K total | 120 | ~$16.20 |
| T3 LIVE (60s intervals, 60 cycles) | ~600K total | ~300K total | 60 | ~$6.30 |
| T2 PROCESS (single pass) | ~15K | ~15K | 1 | ~$0.27 |
| T3 PROCESS (single pass) | ~15K | ~5K | 1 | ~$0.12 |

**Monthly estimate (50 meetings/month):** ~$1,145 in LLM costs.

**Cost note:** This is significantly higher than Gemini Flash (~$7.50/month)
but the content is legally bound — a cleaning error that subtly changes what a
customer said is a legal liability that no cost saving justifies. The config
allows per-tier model override if cost becomes a concern for LIVE previews
(which are replaced by PROCESS output anyway).

### GCS Storage

Three JSON files per meeting: ~100KB total. 50 meetings/month = 5MB/month.
Negligible cost.

### Redis

T2/T3 keys total ~1MB per hour of meeting. 24h TTL. Well within existing
Memorystore capacity (0.7% usage).

---

## 8. Git Workflow

> Note: The `references/git-workflow.md` file does not exist yet. This section
> follows conventions from the memory `feedback_branch_workflow.md`.

### Branch strategy

Feature branches from `development_main`, PRs target `development_main`.
Merge to `main` only after all stories are complete and tested.

### Branch naming

```
feat/oia-three-tier-transcript
```

One branch for all stories since they form a cohesive feature. If the PR
grows too large, split at phase boundaries.

### Conventional commits

One commit per story:

```
feat(oia): add T2/T3 config and Redis key builders (T-01)
feat(oia): implement TranscriptCleaner module (T-02)
feat(oia): implement DescriptionGenerator module (T-03)
feat(oia): integrate T2/T3 with WS handler (T-04)
feat(oia): integrate T2/T3 with PROCESS executor (T-05)
feat(oia): add GCS transcript finalization and manifest (T-06)
feat(onboarding): add T2/T3 fields to MeetingRecording model (D-01)
feat(oia): extend backend client for T2/T3 callback (D-02)
feat(onboarding-ui): add DescriptionTab component (F-01)
feat(onboarding-ui): add Description tab and clean transcript toggle (F-02)
```

---

## 9. Deployment

### Docker Compose

No new service or container. Changes deploy with the existing
`onboarding-intelligence-agent-svc` and `ai-brand-automator` containers.

New environment variables (all optional with defaults):
```yaml
# In onboarding-intelligence-agent-svc
OIA_CLEAN_INTERVAL_S: ${OIA_CLEAN_INTERVAL_S:-30}
OIA_CLEAN_MIN_SEGMENTS: ${OIA_CLEAN_MIN_SEGMENTS:-5}
OIA_DESCRIPTION_INTERVAL_S: ${OIA_DESCRIPTION_INTERVAL_S:-60}
OIA_DESCRIPTION_MIN_CHARS: ${OIA_DESCRIPTION_MIN_CHARS:-200}
OIA_FINALIZE_TIMEOUT_S: ${OIA_FINALIZE_TIMEOUT_S:-30}
OIA_CLEAN_MODEL: ${OIA_CLEAN_MODEL:-}
OIA_DESCRIPTION_MODEL: ${OIA_DESCRIPTION_MODEL:-}
```

### GCP Cloud Run

No new service. The existing `onboarding-intelligence-agent-svc` Cloud Run
service picks up the new code on deploy. The `--timeout=3600` already
accommodates long meetings.

### Django Migration

Must run before the OIA service sends callbacks with the new fields:

```bash
python manage.py makemigrations
python manage.py migrate_schemas --shared --noinput
```

**Deployment order:**
1. Deploy Django backend (migration runs)
2. Deploy OIA service (new code sends callbacks to new fields)
3. Deploy frontend (new Description tab)

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| T2 LLM latency blocks the cleaner loop | Medium | Low | Each iteration awaits independently; recording is unaffected; timeout per call |
| T2 cleaning alters speaker meaning | Low | High | Prompt instructs preservation; raw T1 always available in GCS; PROCESS re-runs produce the binding record |
| GCS upload fails during finalization | Low | Medium | Existing circuit breaker + spool; manifest tracks what landed |
| Redis memory pressure from T2/T3 keys | Low | Low | TTL on all keys; ~1 MB per meeting hour; Memorystore at 0.7% |
| PROCESS T2+T3 exceeds PROCESS_TIMEOUT_S | Low | Medium | Monitor timing; increase timeout if needed; sequential single-pass is fast |
| Frontend renders stale T2 during LIVE→PROCESS transition | Medium | Low | PROCESS callback replaces LIVE data; frontend refetches on status change |

---

## 11. Doc-vs-Reality Conflicts

| Conflict | Resolution |
|----------|------------|
| Design says "summary tab renamed to Description" | The existing "Review" tab shows `process_summary` and is NOT renamed. A **new** "Description" tab is added between Meeting and Review. The design doc §3.8.1 already clarifies this. |
| Design says T1 stored in `Recording.transcript` (existing field) | Confirmed: the existing `transcript` JSONField already stores raw segments. No change needed for T1 storage — only the new `raw_transcript_gcs_path` field for GCS. |
| Design lists `CLEAN_MIN_SEGMENTS` but `TenantKeys` has no segment-count key | The min-segments check is local to `TranscriptCleaner` — it compares `len(segments)` to the config value. No Redis key needed. |
| `BackendClient.update_recording_summary` path is `/api/v1/onboarding/internal/recordings/{recording_id}/summary/` | The existing endpoint handles `summary` and `transcript` fields. We either extend it to accept T2/T3 fields or add a sibling endpoint. Extending is simpler — the internal view already does `update_fields`. |

---

## 12. Open Items

None — all design questions and implementation decisions are resolved.
DC-1 (Claude Sonnet 4 for all models) and DC-2 (flat narrative) confirmed.
