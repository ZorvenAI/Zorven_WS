# Three-Tier Transcript Processing — Design Document

**Author:** Claude Code  
**Date:** 2026-11-21  
**Status:** DRAFT — open questions resolved, awaiting final approval  
**Scope:** OIA LIVE + PROCESS mode transcript pipeline, GCS persistence, frontend Description tab

---

## 1. Problem Statement

The transcript captured during a live onboarding meeting is noisy — it contains
filler words, repetitions, false starts, and STT artefacts. Today the raw
transcript is the only version stored and displayed. A growth manager reading it
must mentally filter the noise to extract what matters for brand building, which
is error-prone and time-consuming.

The growth manager needs two things the raw transcript does not give them:

1. A **clean transcript** — the same conversation, same speakers, same order,
   but with noise removed so it reads like a professional meeting record.
2. A **description** — not a summary but the *outcome* of the onboarding: what
   the customer wants for their brand, structured so it provides concrete leads
   for the brand-building workflow (WF1 → WF2 → WF3).

---

## 2. Requirements

### 2.1 Three Transcript Tiers

| Tier | Name | Produced by | When | Stored in | Visible to GM |
|------|------|-------------|------|-----------|---------------|
| T1 | **Raw transcript** | STT provider (Google Cloud STT) | Real-time during recording | GCS + Recording.transcript (existing) | No (GCS-only, diagnostics) |
| T2 | **Clean transcript** | OIA LLM (concurrent background thread) | LIVE: starts when recording starts, full re-clean each cycle. PROCESS: single final pass. | GCS + new DB field | Yes |
| T3 | **Description** | OIA LLM (concurrent background thread, fed by T2) | LIVE: starts as soon as T2 produces first output. PROCESS: single final pass after T2. | GCS + new DB field | Yes (renamed "Description" tab) |

### 2.2 Concurrency Model

```
Recording starts
    |
    +--- [existing] STT thread: audio -> T1 raw segments -> Redis -> WS feedback
    |
    +--- [NEW] T2 Cleaner thread: consumes T1 segments -> produces T2 clean text
    |         \_ writes incremental results to Redis + periodic GCS flush
    |
    \--- [NEW] T3 Description thread: consumes T2 output -> produces T3 description
              \_ writes incremental results to Redis + periodic GCS flush
```

All three threads run concurrently for the duration of the recording. T2
consumes T1's output; T3 consumes T2's output. Each is an independent
`asyncio.Task` with its own cancellation scope.

### 2.3 Frontend Changes

- Rename the **"Summary"** concept to **"Description"** wherever it appears as
  a tab label visible to the growth manager.
- The existing "Review" tab's `process_summary` data is a different concept
  (PROCESS mode output) and is NOT renamed.
- The **Meeting tab** continues showing real-time agent feedback (field
  mapping, sufficiency, follow-ups).
- A new **"Description"** sub-panel (or renamed tab) shows the T3 description
  document, updating live as the meeting progresses.
- The **clean transcript** (T2) replaces the raw transcript in any
  growth-manager-facing transcript view.

### 2.4 GCS Persistence

All meeting artefacts are persisted to GCS under a session-scoped prefix:

```
_landing/oia/{tenant_id}/{session_id}/
  +-- recordings/
  |   +-- {recording_id}.opus              # composed audio (existing)
  |   \-- {recording_id}_stream_{n}.opus   # per-mic audio (existing)
  +-- transcript/
  |   +-- raw.json                         # T1 -- full raw transcript
  |   +-- clean.json                       # T2 -- cleaned transcript
  |   \-- description.json                 # T3 -- brand-building description
  +-- captures/
  |   +-- photo_{timestamp}.jpg            # captured photos (existing)
  |   \-- video_{timestamp}.mp4            # captured videos (existing)
  \-- manifest.json                        # inventory of all artefacts
```

### 2.5 Access Control

| Artefact | Growth Manager | Admin | Diagnostics |
|----------|---------------|-------|-------------|
| T1 raw transcript | Hidden (GCS only) | GCS console | Full access |
| T2 clean transcript | Read | Read | Full access |
| T3 description | Read | Read | Full access |
| Audio recordings | Playback (signed URL) | Full | Full |
| Photos/videos | View | Full | Full |

---

## 3. Detailed Design

### 3.1 T2 Cleaner — Concurrent Background Thread

**Entry point:** A new `asyncio.Task` spawned in the WebSocket handler's
`_handle_control` when a `start` command is received (same point that starts
STT).

**Input:** T1 raw transcript segments from Redis. The cleaner reads the same
`oia:v1:{tenant}:live:{session}:transcript` list that the existing analysis
pipeline reads, using a trailing cursor.

**Processing model — Full-transcript re-clean:**

T2 uses a **full-transcript** approach rather than windowed/chunked cleaning.
Each cycle re-cleans the entire accumulated transcript. This is more expensive
per LLM call but produces significantly better output: the LLM sees full
conversational context, can resolve cross-reference ambiguities, and produces
a coherent document rather than stitched-together windows.

```
+-----------------------------------------------------+
| T1 segments accumulate in Redis                     |
|                                                     |
|  seg_0  seg_1  seg_2  seg_3  seg_4  seg_5  ...      |
|  |<------------- full re-clean ----------------->|  |
|                                                     |
|  Every cycle reads ALL segments and re-cleans the   |
|  entire transcript, replacing the previous T2.      |
+-----------------------------------------------------+
```

- Every `CLEAN_INTERVAL_S` seconds (default: 30), T2 reads **all** T1
  segments accumulated so far.
- It sends the full raw transcript to the LLM with a cleaning prompt:
  - Remove filler words, false starts, repetitions
  - Preserve meaning, speaker attribution, chronological order
  - Maintain proper sentence structure
  - Keep domain-specific terms and proper nouns intact
- The LLM returns the complete cleaned transcript, which **replaces** the
  previous T2 version (not appended).
- Written atomically to Redis via `SET` under
  `oia:v1:{tenant}:live:{session}:transcript_clean` and periodically flushed
  to GCS.
- A `clean_version` counter increments on each successful cycle so the
  frontend knows when to re-fetch.

**Cost note:** Full-transcript re-cleaning sends growing input on each cycle.
For a 60-minute meeting producing ~15K tokens of raw transcript, the final
cycle processes the full 15K. Total LLM cost across all cycles (assuming 30s
intervals) is roughly 10x a single pass. This is acceptable because (a) the
content is legally significant and accuracy matters more than cost, and (b) the
earlier cycles give the growth manager a live preview while the meeting is
still running.

**Concurrency guards:**

| Race condition | Mitigation |
|----------------|------------|
| T2 reads T1 while STT writes | Redis `LRANGE` is atomic; snapshot read means no data loss |
| Two T2 iterations overlap | Single-task design — next iteration waits for the LLM call to return |
| Recording stops mid-clean | Cancellation token checked before each LLM call; final flush on stop |
| WebSocket drops | Cleanup handler flushes T2 state to GCS before exiting |
| Multiple WS connections | Existing single-writer lock (Redis) prevents duplicate cleaners |

**Error handling:**

- LLM failure: log, skip the window, retry on next interval. Raw segments
  remain in Redis for the next attempt (cursor does not advance on failure).
- GCS failure: circuit breaker (existing `gcs` breaker) + local spool fallback.
- Timeout: each LLM call bounded by `ANALYSIS_TIMEOUT_S` (existing setting).

### 3.2 T3 Description Generator — Concurrent Background Thread

**Entry point:** Spawned alongside T2 when recording starts. Consumes T2's
output.

**Input:** T2 clean transcript from Redis
(`oia:v1:{tenant}:live:{session}:transcript_clean`).

**Processing model — Accumulate-and-regenerate:**

Unlike T2 (which appends), T3 **regenerates the full description** each cycle
because a description is a holistic document, not a stream of segments. Each
cycle:

1. Read all T2 clean text accumulated so far.
2. Send to the LLM with a description-generation prompt that extracts:
   - **Business identity**: company name, industry, location, founding story
   - **Products/services**: what they offer, pricing model, differentiators
   - **Target audience**: who they serve, demographics, psychographics
   - **Brand aspirations**: desired positioning, tone, values, personality
   - **Competitive landscape**: named competitors, differentiation strategy
   - **Marketing goals**: channels, campaigns, budget constraints
   - **Customer pain points**: problems they solve, unmet needs
   - **Success metrics**: how they measure success, KPIs
3. The output is a structured document, not a bullet list — it reads as a
   narrative brief that a brand strategist can act on.
4. Written to Redis under
   `oia:v1:{tenant}:live:{session}:description` and flushed to GCS.

**Cycle interval:** `DESCRIPTION_INTERVAL_S` (default: 60) — longer than T2
because regeneration is more expensive and the description evolves slowly.

**Concurrency guards:**

| Race condition | Mitigation |
|----------------|------------|
| T3 reads T2 while T2 writes | Redis `GET` on a single key (T2 writes atomically via `SET`) |
| T3 overlaps with itself | Single-task, sequential iterations |
| T2 is empty on first T3 cycle | T3 skips if T2 has fewer than `MIN_CLEAN_CHARS` (default: 200) characters |
| Recording stops | Final T3 regeneration with all accumulated T2 text, then GCS flush |

### 3.3 Django Model Changes

**`MeetingRecording` model** (existing, in `apps/onboarding/models.py`):

```python
# New fields
transcript_clean = models.JSONField(
    default=list,
    blank=True,
    help_text=(
        "T2 -- cleaned transcript segments. Same schema as `transcript` "
        "but with noise removed by LLM post-processing."
    ),
)
transcript_clean_gcs_path = models.CharField(
    max_length=500, blank=True, default="",
    help_text="GCS path to the full clean transcript JSON",
)
description = models.TextField(
    blank=True, default="",
    help_text=(
        "T3 -- structured brand-building description derived from the "
        "clean transcript. Narrative format, not a summary."
    ),
)
description_gcs_path = models.CharField(
    max_length=500, blank=True, default="",
    help_text="GCS path to the description document",
)
raw_transcript_gcs_path = models.CharField(
    max_length=500, blank=True, default="",
    help_text="GCS path to the raw (T1) transcript JSON -- diagnostics only",
)
```

### 3.4 OIA Service Changes

#### 3.4.1 New module: `app/logic/transcript_cleaner.py`

```python
class TranscriptCleaner:
    """T2 -- concurrent background cleaner for raw transcript segments.

    Uses full-transcript re-cleaning: each cycle reads ALL T1 segments
    and produces a complete cleaned version that replaces the previous one.
    """

    def __init__(self, session: LiveSession, llm: LLMProvider, storage: StorageProvider):
        ...

    async def run(self, cancel: asyncio.Event) -> None:
        """Main loop: read all T1 -> re-clean full transcript -> write T2."""
        while not cancel.is_set():
            await asyncio.sleep(CLEAN_INTERVAL_S)
            all_segments = await self._read_all_raw_segments()
            if len(all_segments) == self._last_segment_count:
                continue  # no new data since last cycle
            self._last_segment_count = len(all_segments)
            cleaned = await self._clean_full(all_segments)
            await self._write_clean(cleaned)  # atomic SET, replaces previous

    async def finalize(self) -> None:
        """Final re-clean of complete transcript and flush to GCS."""

    async def run_batch(self, raw_segments: list[dict]) -> str:
        """PROCESS mode: single-pass clean of a complete transcript."""
        return await self._clean_full(raw_segments)
```

#### 3.4.2 New module: `app/logic/description_generator.py`

```python
class DescriptionGenerator:
    """T3 -- concurrent background description generator from clean transcript."""

    def __init__(self, session: LiveSession, llm: LLMProvider, storage: StorageProvider):
        ...

    async def run(self, cancel: asyncio.Event) -> None:
        """Main loop: accumulate T2 -> regenerate description. Runs until cancel is set."""
        while not cancel.is_set():
            await asyncio.sleep(DESCRIPTION_INTERVAL_S)
            clean_text = await self._read_all_clean()
            if len(clean_text) < MIN_CLEAN_CHARS:
                continue
            description = await self._generate(clean_text)
            await self._write_description(description)

    async def finalize(self) -> None:
        """Final generation with complete clean transcript, flush to GCS."""

    async def run_batch(self, clean_transcript: str) -> str:
        """PROCESS mode: single-pass description from a complete clean transcript."""
        return await self._generate(clean_transcript)
```

#### 3.4.3 WebSocket handler integration (`app/api/ws.py`)

In `_handle_control` when processing a `start` command, after spawning STT:

```python
# Spawn T2 cleaner
cancel_event = asyncio.Event()
t2_task = asyncio.create_task(
    cleaner.run(cancel_event),
    name=f"t2-clean-{session_id}",
)

# Spawn T3 description generator
t3_task = asyncio.create_task(
    desc_gen.run(cancel_event),
    name=f"t3-desc-{session_id}",
)

# Store references for cleanup
stt_state["t2_task"] = t2_task
stt_state["t3_task"] = t3_task
stt_state["t2t3_cancel"] = cancel_event
```

On `stop` command or WebSocket disconnect:

```python
cancel_event.set()           # signal both threads to stop
await cleaner.finalize()     # process remaining segments
await desc_gen.finalize()    # final description generation
# Wait for tasks to complete with timeout
await asyncio.wait_for(
    asyncio.gather(t2_task, t3_task, return_exceptions=True),
    timeout=30.0,
)
```

#### 3.4.4 Real-time WebSocket frames

New frame types pushed to the frontend:

```json
// T2 progress
{
  "type": "transcript.clean_progress",
  "segments_cleaned": 42,
  "segments_total": 60,
  "last_cleaned_text": "..."
}

// T3 progress
{
  "type": "description.updated",
  "version": 3,
  "description": "...",
  "sections": ["business_identity", "target_audience"]
}
```

### 3.5 PROCESS Mode Integration

PROCESS mode (`POST /v1/process`) runs T2 and T3 as a **single sequential
pass** after the meeting ends, using the complete T1 transcript:

```
PROCESS receives complete T1
    |
    +-- T2 cleaner.run_batch(all_raw_segments) -> complete clean transcript
    |
    +-- T3 desc_gen.run_batch(clean_transcript) -> final description
    |
    +-- Upload T1, T2, T3 to GCS
    +-- Update Django MeetingRecording fields
    +-- Register as BrandAssets (existing SKL-OIA-11)
```

This produces the highest-quality output because:
- T2 sees the **entire** conversation with full context
- T3 sees the **entire** cleaned transcript, not an evolving partial
- No time pressure — the LLM can take as long as needed

PROCESS mode T2/T3 output **replaces** any LIVE mode partial output. The LIVE
versions are previews; the PROCESS versions are the legally binding record.

The PROCESS executor (`app/logic/process_executor.py`) gains two new steps
inserted before the existing SKL-OIA-11 (asset registration):

1. `TranscriptCleaner.run_batch()` — produces T2
2. `DescriptionGenerator.run_batch()` — produces T3

Both write their output to Redis (for caching) and return it to the executor,
which passes it to the callback and GCS upload.

### 3.6 Redis Key Schema

All under the existing `oia:v1:` prefix, DB 2:

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `oia:v1:{tenant}:live:{session}:transcript` | LIST | 24h | T1 raw segments (existing) |
| `oia:v1:{tenant}:live:{session}:transcript_clean` | STRING (JSON) | 24h | T2 complete clean transcript |
| `oia:v1:{tenant}:live:{session}:clean_version` | STRING (int) | 24h | T2 generation counter |
| `oia:v1:{tenant}:live:{session}:description` | STRING (JSON) | 24h | T3 current description |
| `oia:v1:{tenant}:live:{session}:desc_version` | STRING (int) | 24h | T3 generation counter |

All keys built through `TenantKeys` (existing `RedisManager.keys_for()`).

### 3.7 GCS Persistence — Full Asset Manifest

After recording stops, a finalization step uploads all artefacts and writes a
manifest:

```json
{
  "session_id": "6",
  "tenant_id": "pomodoro",
  "finalized_at": "2026-11-21T14:30:00Z",
  "artefacts": [
    {
      "type": "audio",
      "path": "_landing/oia/pomodoro/6/recordings/rec_42.opus",
      "stream_index": 0,
      "speaker": "Operator",
      "duration_s": 1200
    },
    {
      "type": "audio",
      "path": "_landing/oia/pomodoro/6/recordings/rec_42_stream_1.opus",
      "stream_index": 1,
      "speaker": "Client",
      "duration_s": 1200
    },
    {
      "type": "transcript_raw",
      "path": "_landing/oia/pomodoro/6/transcript/raw.json",
      "segments": 847,
      "format": "json_lines"
    },
    {
      "type": "transcript_clean",
      "path": "_landing/oia/pomodoro/6/transcript/clean.json",
      "segments": 847,
      "format": "structured_json"
    },
    {
      "type": "description",
      "path": "_landing/oia/pomodoro/6/transcript/description.json",
      "version": 5,
      "sections": 8
    },
    {
      "type": "photo",
      "path": "_landing/oia/pomodoro/6/captures/photo_1732195800.jpg"
    },
    {
      "type": "video",
      "path": "_landing/oia/pomodoro/6/captures/video_1732196400.mp4"
    }
  ]
}
```

### 3.8 Frontend Changes

#### 3.8.1 Tab Rename

In `OnboardingUnified.tsx`, the tab that currently renders `KeyFindingsReview`
is not being renamed — that is the "Review" tab showing PROCESS mode output.

The **new "Description" tab** is added to the tab bar between "Meeting" and
"Review":

```
Overview | Meeting | Description | Review | Calendar
```

It is visible whenever the session has a recording (same visibility rule as
Meeting).

#### 3.8.2 Description Tab Component

New component: `DescriptionTab.tsx`

- Polls or receives via WebSocket the T3 description document.
- Renders the description as a structured narrative with section headers.
- Shows a "Generating..." indicator while the description is being built.
- After recording stops, shows the final version.

#### 3.8.3 Clean Transcript in Meeting View

The transcript panel in `MeetingView.tsx` currently shows raw segments. After
this change:

- During recording: continues showing real-time raw segments (latency matters).
- After recording stops: switches to showing the T2 clean transcript.
- A toggle allows viewing raw vs. clean (for operators who want to verify).

#### 3.8.4 Recordings Library

`RecordingsLibrary.tsx` already shows recordings with a `has_summary` badge.
After this change:

- Shows `has_description` badge instead.
- Clicking a recording opens the description view.
- The transcript shown in the detail drawer uses T2 (clean) by default.

---

## 4. LLM Prompt Design

### 4.1 T2 Cleaning Prompt

```
You are a professional meeting transcript editor. Clean the following raw
speech-to-text transcript segment. Rules:

1. Remove filler words (um, uh, like, you know, so, basically)
2. Remove false starts and self-corrections (keep only the corrected version)
3. Remove repetitions (keep only one instance)
4. Fix obvious STT errors where context makes the intended word clear
5. Preserve the speaker's exact meaning -- do not add, remove, or rephrase ideas
6. Preserve speaker labels and chronological order
7. Maintain domain-specific terms, proper nouns, numbers, and dates exactly
8. Produce clean, grammatically correct sentences
9. Do NOT summarize -- the output should be the same conversation, just cleaner

Speaker labels: {speaker_map}

Raw segment:
{raw_text}

Cleaned segment:
```

### 4.2 T3 Description Prompt

```
You are an expert brand strategist reviewing an onboarding conversation.
From the transcript below, produce a structured brand-building brief that
a growth manager can act on. This is NOT a summary -- it is the actionable
outcome of the onboarding.

Structure your output with these sections (omit any section with no evidence):

## Business Identity
Company name, industry, location, founding story, years in operation.

## Products & Services
What they offer, pricing model, delivery method, differentiators.

## Target Audience
Who they serve: demographics, psychographics, buying behaviour.

## Brand Aspirations
Desired positioning, tone, values, personality traits they want to project.

## Competitive Landscape
Named competitors, how the customer differentiates, market gaps they see.

## Marketing Goals
Channels they want to use, campaign ideas, budget constraints, timeline.

## Customer Pain Points
Problems their customers face, unmet needs, friction in current experience.

## Success Metrics
How they measure success, KPIs, growth targets, revenue goals.

For each section, cite the speaker and approximate timestamp. If the customer
was unclear or contradictory on a point, flag it as "needs clarification"
rather than guessing.

Transcript:
{clean_transcript}
```

---

## 5. Sequence Diagram

```
Browser                OIA WS Handler       T2 Cleaner     T3 Desc Gen    Redis       GCS
  |                         |                    |              |            |           |
  |-- start recording ----->|                    |              |            |           |
  |                         |-- spawn STT ------>|              |            |           |
  |                         |-- spawn T2 ------->|              |            |           |
  |                         |-- spawn T3 ------->|------------->|            |           |
  |                         |                    |              |            |           |
  |<- transcript.partial ---|                    |              |            |           |
  |<- transcript.final -----|-- write T1 ------->|------------->|----------->|           |
  |                         |                    |              |            |           |
  |                         |                    |-- read T1 -->|<-----------|           |
  |                         |                    |-- LLM clean->|            |           |
  |                         |                    |-- write T2 ->|----------->|           |
  |<- clean_progress -------|<-------------------|              |            |           |
  |                         |                    |              |            |           |
  |                         |                    |              |-- read T2->|           |
  |                         |                    |              |-- LLM desc>|           |
  |                         |                    |              |-- write T3>|           |
  |<- description.updated --|<-------------------|--------------|            |           |
  |                         |                    |              |            |           |
  |-- stop recording ------>|                    |              |            |           |
  |                         |-- cancel.set() --->|------------->|            |           |
  |                         |-- finalize T2 ---->|              |            |           |
  |                         |-- finalize T3 ---->|------------->|            |           |
  |                         |-- upload T1 ------>|------------->|----------->|---------->|
  |                         |-- upload T2 ------>|------------->|----------->|---------->|
  |                         |-- upload T3 ------>|------------->|----------->|---------->|
  |                         |-- write manifest ->|------------->|----------->|---------->|
  |                         |-- update Django -->|              |            |           |
  |<- recording.finalized --|                    |              |            |           |
```

---

## 6. Configuration

New settings in `app/core/config.py` (env prefix `OIA_`):

| Setting | Default | Purpose |
|---------|---------|---------|
| `CLEAN_INTERVAL_S` | 30 | How often T2 polls for new raw segments |
| `CLEAN_MIN_SEGMENTS` | 5 | Minimum new segments before T2 runs a cleaning cycle |
| `DESCRIPTION_INTERVAL_S` | 60 | How often T3 regenerates the description |
| `DESCRIPTION_MIN_CHARS` | 200 | Minimum T2 characters before T3 runs |
| `CLEAN_MODEL` | (from LLM provider) | Model for T2 cleaning |
| `DESCRIPTION_MODEL` | (from LLM provider) | Model for T3 description |
| `FINALIZE_TIMEOUT_S` | 30 | Max wait for T2/T3 finalization on stop |

---

## 7. Migration Plan

1. **Django migration**: Add new fields to `MeetingRecording` (nullable/blank,
   no data migration needed).
2. **OIA service**: New modules (`transcript_cleaner.py`,
   `description_generator.py`) + WS handler integration.
3. **Frontend**: New `DescriptionTab` component + tab bar update + clean
   transcript toggle.
4. **GCS path convention**: New prefix structure under existing
   `_landing/oia/` -- no migration of existing data.
5. **Existing recordings**: `transcript_clean` and `description` remain empty
   for pre-existing recordings. The growth manager sees "No clean transcript
   available" with a link to the raw version.

---

## 8. Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit | T2 cursor logic, segment batching | pytest, no network |
| Unit | T3 prompt assembly, section parsing | pytest, no network |
| Integration | T2 reads T1 from Redis, writes T2 | Real Redis |
| Integration | T3 reads T2, generates description | Real Redis + LLM |
| Integration | GCS finalization writes all artefacts | Real GCS |
| E2E | Full recording -> T1 -> T2 -> T3 -> GCS | Docker, real services |
| Frontend | Description tab renders, toggles | Jest + React Testing Library |
| Frontend | Clean transcript replaces raw after stop | Jest |

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM latency blocks T2/T3 | Medium | Low | Independent tasks; timeouts per call; recording unaffected |
| T2 cleaning alters meaning | Low | High | Prompt instructs preservation; raw T1 always available |
| GCS quota exhaustion | Low | Medium | Existing circuit breaker + spool; manifest tracks what landed |
| Redis memory pressure from T2/T3 keys | Low | Medium | TTL on all keys; total data ~1 MB per hour of meeting |
| Description quality varies | Medium | Medium | Regeneration on each cycle improves as more data arrives; final pass on stop |

---

## 10. Resolved Design Decisions

1. **T2 uses full-transcript re-cleaning (not chunked/windowed).**
   Each cycle re-cleans the entire accumulated transcript. Higher LLM cost but
   significantly better coherence and accuracy. The content is legally
   significant, so quality takes priority over cost.

2. **Description (T3) is read-only — not editable by the growth manager.**
   The transcript and description are legally bound records of what the
   customer said during onboarding. They form the basis for final contractual
   documentation. Allowing edits would compromise the evidentiary chain. If a
   growth manager needs to annotate, that is a separate layer (out of scope).

3. **T2/T3 run in both LIVE and PROCESS mode.**
   LIVE mode produces incremental previews while the meeting is running.
   PROCESS mode re-runs T2/T3 as a single sequential pass on the complete
   transcript, producing the highest-quality final output. The PROCESS
   versions replace the LIVE previews and become the legally binding record.
   If PROCESS takes longer, that is acceptable — quality over speed.

---

## 11. Out of Scope

- Real-time streaming of T2/T3 results token-by-token (SSE). The design uses
  periodic WebSocket frames.
- Speaker diarization improvements (depends on upstream STT v2 support).
- T2/T3 for recordings uploaded after the meeting (batch processing). This
  could be added in a follow-up.
- Access control changes for the raw transcript (currently accessible via GCS
  IAM; a UI for it is deferred).
