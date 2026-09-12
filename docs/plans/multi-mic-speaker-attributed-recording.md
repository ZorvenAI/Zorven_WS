# Implementation Plan: Multi-Mic Speaker-Attributed Recording with Voice Roll Call

**Status**: Approved (2026-09-12).
**Date**: 2026-09-12
**Scope**: Epic O (new) — crosses Django backend, Next.js frontend, OIA service.

> **Note**: This plan was authored without the implementation-plan-template
> (the reference file does not yet exist). Sections 6–8 are improvised rather
> than generated from the skill's templates.

---

## 1. Problem Statement

Today the meeting recorder captures a single audio stream from one
microphone. Google STT v2 streaming does not support speaker diarization
(spike A-01), so every transcript line carries `speaker=0`. For legal-grade
transcripts the system must:

- Attribute every utterance to a named participant.
- Record attendance, consent, date and time automatically — no manual entry.
- Produce a transcript that stands as a legal record of who said what, when,
  and who was present.

## 2. Current Architecture (what exists)

| Layer | State |
|---|---|
| `useMeetingRecorder.ts` | Single `getUserMedia({audio: …})` → one `MediaRecorder` → opus chunks |
| `RecorderControl.tsx` | Sends `{type:'start', recording_id, codec, sample_rate, operator_speaker?}` |
| `StartFrame` (schemas.py) | Has `operator_speaker: int | None = None` (unused today) |
| `TranscriptPartial/Final` | Carry `speaker: int` — hardcoded to `0` in `_emit_partial` / `_emit_final` |
| `LiveSessionManager` | Has `set_operator_speaker` / `get_operator_speaker` in Redis |
| `MeetingRecording.transcript` | `[{text, speaker, t_start, t_end, redaction_applied}]` — speaker always `0` |
| `ConsentRecord` | Tracks subject_name, method, scope, granted_at — no link to mic/attendee |
| STT adapter | One `stt.stream()` call per recording session; no multi-stream support |

**Key insight**: The `speaker: int` field already exists end-to-end but is
always `0`. The `operator_speaker` field on `StartFrame` was forward-designed
for this. The architecture is waiting for multiple streams to give it real
speaker IDs.

## 3. Design Approach

### 3.1 Separate mics, separate STT streams — no diarization needed

Each participant is assigned a mic (audio input device). Each mic feeds its
own STT stream. Since we know which mic belongs to whom, every transcript
segment gets a named speaker — without relying on ML-based diarization.

This is architecturally superior to diarization because:
- **Deterministic**: a legal transcript cannot have "Speaker A (78% confidence)".
- **Works with STT v2**: no API limitation to work around.
- **Cost is linear**: N mics = N STT streams, predictable.

### 3.2 Voice roll call — no manual entry

Before recording starts, the system enters an **attendance phase**:
1. The operator clicks "Start meeting" (not "Start recording").
2. The system announces: "Roll call — each participant, please state your
   name into your microphone."
3. Each participant speaks their name. The system captures a short STT
   segment from their mic, extracts the name, and logs it.
4. The operator confirms the attendee list on screen (voice: "Confirmed" or
   click).
5. Recording begins with mics mapped to named attendees.

### 3.3 Automatic metadata — zero manual entry

| Field | Source | When |
|---|---|---|
| Date & time | `new Date()` / server `auto_now_add` | Meeting start |
| Attendees | Voice roll call STT | Attendance phase |
| Consent | Existing `ConsentRecord` | Already captured before meeting |
| Mic ↔ Speaker map | Attendance phase result | Before recording |
| Recording duration | `AudioContext.currentTime` | Continuous |

## 4. Story Breakdown

### Epic O: Multi-Mic Speaker-Attributed Recording

#### O-01: Mic Device Enumeration and Selection UI

**What**: Add a mic selection step before recording. Enumerate available
audio input devices via `navigator.mediaDevices.enumerateDevices()`. Display
a list of detected microphones. Allow the operator to assign a role to each
(e.g., "Operator", "Participant 1", "Participant 2").

**Frontend changes**:
- New component `MicSetup.tsx` — shows available mics, lets operator assign
  roles, test each mic (audio level meter via `AnalyserNode`).
- New hook `useAudioDevices.ts` — wraps `enumerateDevices()`, filters for
  `kind === 'audioinput'`, handles permission-gated labels (browsers show
  "Default" until `getUserMedia` is granted).
- `RightRail.tsx` — add "Set up microphones" button before recording can start.

**Backend changes**: None — this is purely client-side device enumeration.

**Acceptance criteria**:
- AC-1: All connected audio input devices are listed with their labels.
- AC-2: Each mic can be tested (shows live audio level).
- AC-3: At least one mic must be assigned before proceeding.
- AC-4: Device labels are resolved (getUserMedia called first to unlock labels).
- AC-5: Device changes (plug/unplug) update the list via `devicechange` event.

---

#### O-02: Multi-Stream Audio Capture

**What**: Open a separate `MediaRecorder` per assigned mic. Each produces its
own chunk stream tagged with a `streamIndex`.

**Frontend changes**:
- Refactor `useMeetingRecorder.ts` → `useMultiMicRecorder.ts`:
  - Accepts `devices: {deviceId: string, speakerIndex: number, name: string}[]`.
  - Opens one `getUserMedia({audio: {deviceId: {exact: id}}})` per device.
  - Creates one `MediaRecorder` per stream, same opus codec.
  - Chunks are tagged: `{blob, index, streamIndex}`.
  - Single `AudioContext` with multiple sources for elapsed time.
- `RecorderControl.tsx` — passes device list from O-01's setup.

**Backend changes**: None yet — chunks are still uploaded as a single
interleaved stream to GCS via the existing uploader.

**Acceptance criteria**:
- AC-1: N microphones produce N independent chunk streams.
- AC-2: Each chunk carries its `streamIndex` for downstream attribution.
- AC-3: Elapsed timer is accurate across all streams (single AudioContext).
- AC-4: Tab title shows "● Recording" as before.
- AC-5: Stopping releases all mic tracks.

---

#### O-03: Multi-Stream WebSocket Protocol

**What**: Extend the WS protocol so the frontend can send audio from
multiple mics, each routed to its own STT stream on the backend.

**Frontend changes**:
- Binary frames get a 1-byte prefix: `streamIndex` (0–255), followed by the
  audio bytes. This is zero-copy (prepend one byte to the ArrayBuffer).
- `StartFrame` extended: `streams: [{stream_index: int, device_label: string, speaker_name: string, speaker_role: string}]`.

**Backend changes** (`ws.py`):
- Parse the 1-byte stream prefix from binary frames.
- Route audio to per-stream `audio_q` queues (one per `streamIndex`).
- Spawn one `_stt_loop` task per stream.
- Each `_stt_loop` tags its `TranscriptPartial/Final` with the correct
  `speaker` index from the stream map.

**Schema changes** (`schemas.py`):
- `StartFrame.streams: list[StreamDescriptor] | None = None` (backwards
  compatible — `None` means single-stream legacy mode).
- `StreamDescriptor`: `{stream_index: int, speaker_name: str, speaker_role: str}`.
- `TranscriptFinal` gets `speaker_name: str | None = None`.

**Acceptance criteria**:
- AC-1: Legacy single-stream clients still work (no prefix = stream 0).
- AC-2: Each stream gets its own STT loop and circuit breaker state.
- AC-3: Transcript frames carry the correct `speaker` index.
- AC-4: Stream failure is isolated — one mic's STT failing does not stop others.
- AC-5: `stop` frame drains all streams.

---

#### O-04: Speaker-Labelled Live Transcript UI

**What**: Update the live transcript display to show speaker names with
each line.

**Frontend changes**:
- `AgentFeedbackStream.tsx` — transcript items show speaker name (e.g.,
  "**John Smith**: We've been open for…").
- `MeetingView.tsx` — maintain a `streamMap: Map<number, {name, role}>` from
  the start frame, pass to AgentFeedbackStream.
- `useLiveSocket.ts` — parse `speaker_name` from transcript frames.

**Backend changes**: None — the data is already in the frames from O-03.

**Acceptance criteria**:
- AC-1: Each transcript line is prefixed with the speaker's name.
- AC-2: Different speakers are visually distinguished (colour/indent).
- AC-3: Partial transcripts show the current speaker's name.
- AC-4: When speaker is unknown (legacy `speaker=0`), no name is shown.

---

#### O-05: Voice Roll Call — Attendance Phase

**What**: Before recording starts, run a voice-driven attendance phase
where each participant speaks their name into their assigned mic.

**Frontend changes**:
- New component `AttendanceRollCall.tsx`:
  - Enters attendance mode after mic setup (O-01).
  - For each assigned mic: opens a short STT capture (5-second window), runs
    STT to extract the spoken name, displays: "Mic 1: [detected name]".
  - Operator sees the full list and confirms (voice "Confirmed" or button).
- The flow: Mic Setup → Roll Call → Confirm → Recording starts.
- The captured names populate the `streams` array in the `StartFrame`.

**Backend changes**:
- New REST endpoint `POST /onboarding/sessions/{id}/attendance/`:
  - Accepts `{attendees: [{name, role, mic_label}]}`.
  - Creates `MeetingAttendee` records.
  - Returns the attendee list with IDs.

**Django model** (new):
```python
class MeetingAttendee(models.Model):
    tenant = models.ForeignKey(Tenant, ...)
    session = models.ForeignKey(OnboardingSession, related_name="attendees")
    recording = models.ForeignKey(MeetingRecording, null=True, related_name="attendees")
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=50)  # "operator", "participant"
    mic_label = models.CharField(max_length=255, blank=True)
    stream_index = models.PositiveSmallIntegerField()
    checked_in_at = models.DateTimeField(auto_now_add=True)
    voice_sample_gcs_path = models.CharField(max_length=500, blank=True)
```

**Acceptance criteria**:
- AC-1: Each participant speaks their name; the system captures it via STT.
- AC-2: The operator sees and confirms the detected names before recording.
- AC-3: Names are persisted as `MeetingAttendee` records.
- AC-4: No manual text entry required — voice or confirmation button only.
- AC-5: Roll call audio is captured but not stored long-term (ephemeral).

---

#### O-06: Meeting Metadata Assembly — Legal Transcript Header

**What**: When a recording is finalised, assemble a legal transcript header
with all automatically captured metadata.

**Backend changes** (`views.py` / new `transcript_assembler.py`):
- On `finaliseRecording`, build a transcript document:
  ```
  MEETING TRANSCRIPT
  ─────────────────
  Date:       2026-09-12
  Time:       14:30 UTC
  Session:    #6 — Pomodoro Pizza
  
  ATTENDEES
  ─────────
  1. John Smith (Operator) — Mic: Built-in Microphone
     Checked in: 14:30:05 UTC
  2. Mario Rossi (Participant) — Mic: External USB Mic
     Checked in: 14:30:12 UTC
  
  CONSENT
  ───────
  Subject: Pomodoro Owner
  Method:  Checkbox
  Granted: 2026-09-09 10:15 UTC
  Scope:   Audio, Transcript, Captured Media
  
  TRANSCRIPT
  ──────────
  [14:30:15] John Smith: Good afternoon, thanks for joining...
  [14:31:02] Mario Rossi: Thank you, happy to be here...
  ```
- Store as structured JSON in `MeetingRecording.transcript` and render to
  plain text for export.
- `MeetingRecording.summary` extended with `{attendees, consent_snapshot,
  started_at_utc}`.

**Frontend changes**:
- `RecordingsLibrary.tsx` — recording detail view shows the formatted
  transcript with speaker names, timestamps, and the header block.

**Acceptance criteria**:
- AC-1: Date and time are auto-captured at recording start (server time).
- AC-2: Attendee list is populated from O-05's roll call.
- AC-3: Consent details are pulled from the existing `ConsentRecord`.
- AC-4: Every transcript line has `[timestamp] Speaker Name: text`.
- AC-5: No field in the header requires manual entry.

---

#### O-07: Multi-Stream GCS Upload

**What**: Upload multiple audio streams to GCS — one file per mic — so the
raw audio is speaker-separated for legal archive.

**Frontend changes**:
- `useChunkUploader.ts` → support multiple upload sessions (one per stream).
- Each stream gets its own resumable upload URL from
  `POST /recordings/{id}/upload-session/` with a `stream_index` param.

**Backend changes**:
- `_open_upload_session` accepts `stream_index`, creates a per-stream GCS
  object path: `recordings/{id}/stream-{index}.webm`.
- `MeetingRecording` gets a new field: `stream_assets` (JSONField) —
  `[{stream_index, gcs_path, brand_asset_id, speaker_name}]`.
- Finalisation creates one `BrandAsset` per stream.

**Acceptance criteria**:
- AC-1: Each mic's audio is uploaded as a separate GCS object.
- AC-2: The local bound (10 min) is applied per stream.
- AC-3: Degraded mode is per-stream — one failing upload does not stop others.
- AC-4: Finalisation is atomic across all streams.

---

#### O-08: Speaker-Attributed Transcript Persistence

**What**: Store the speaker-attributed transcript with names (not just
integer indices) in the `MeetingRecording.transcript` JSON field.

**Backend changes** (`ws.py`):
- `_emit_final` resolves `speaker` index to `speaker_name` from the session's
  stream map (stored in Redis by O-03).
- Buffered transcript segments include `speaker_name`.
- When recording is finalised, the transcript JSON includes:
  ```json
  [
    {"text": "Good afternoon...", "speaker": 0, "speaker_name": "John Smith",
     "t_start": 0.5, "t_end": 3.2, "redaction_applied": false}
  ]
  ```

**Model changes**:
- `MeetingRecording.transcript` help_text updated to include `speaker_name`.
- No schema change needed — JSONField is schemaless.

**Acceptance criteria**:
- AC-1: Every transcript segment has `speaker_name` when multi-mic is active.
- AC-2: Legacy single-mic recordings continue to work with `speaker_name: null`.
- AC-3: The PROCESS pipeline can read speaker names from the transcript.

## 5. Dependency Graph

```
O-01 (Mic Setup UI)
  └─→ O-02 (Multi-Stream Capture)
        ├─→ O-03 (Multi-Stream WS Protocol)
        │     ├─→ O-04 (Speaker-Labelled Transcript UI)
        │     └─→ O-08 (Speaker-Attributed Persistence)
        └─→ O-07 (Multi-Stream GCS Upload)

O-01 → O-05 (Voice Roll Call) → O-06 (Legal Transcript Header)

O-03 + O-05 + O-08 → O-06 (all must land before the legal doc assembler)
```

**Critical path**: O-01 → O-02 → O-03 → O-08 → O-06

## 6. Testing Strategy

### 6.1 Unit Tests

| Story | Tests |
|---|---|
| O-01 | `useAudioDevices` returns filtered device list; handles permission-gated labels |
| O-02 | Multi-recorder produces tagged chunks; stop releases all tracks |
| O-03 | Binary prefix parsing; stream routing; legacy (no prefix) backward compat |
| O-04 | Speaker name renders in transcript items; unknown speaker handled |
| O-05 | Attendance records created; name extraction from STT result |
| O-06 | Header assembly with all metadata fields; missing data handled gracefully |
| O-07 | Per-stream upload sessions; per-stream bound enforcement |
| O-08 | Speaker name resolution from stream map; legacy fallback |

### 6.2 Integration Tests

- **Multi-stream STT** (O-03): Two parallel STT streams against real Google
  STT, verifying independent results with correct speaker tags. Requires
  `OIA_STT_PROVIDER != fake`.
- **Attendance API** (O-05): Create attendees → verify in DB → verify in
  recording metadata.
- **Legal transcript assembly** (O-06): Full flow from attendance through
  recording to final transcript document. Verify all header fields populated.

### 6.3 E2E Tests

- Full meeting flow: mic setup → roll call → record with 2 mics → stop →
  verify speaker-labelled transcript with legal header.

## 7. GCP Cost Estimation

| Resource | Current | After (2-mic meeting) | After (3-mic) |
|---|---|---|---|
| STT v2 streaming | 1 stream/meeting | 2 streams | 3 streams |
| STT cost (per hour) | ~$1.44 | ~$2.88 | ~$4.32 |
| GCS storage | 1 file/recording | 2–3 files | 3–4 files |
| GCS cost delta | Negligible | Negligible | Negligible |

STT is the dominant cost. Linear scaling with mic count. For a typical
onboarding meeting (30–60 min), 2-mic cost is ~$1.44–$2.88 per meeting.

## 8. Git Workflow

- Branch from `development_main`.
- One PR per story (O-01 through O-08).
- PR back into `development_main`.
- Each PR must pass: `black`, `flake8`, `mypy`, `pytest -m unit`, `npx tsc --noEmit`, `npm run lint`.

## 9. Assumptions

1. **Two mics is the common case.** The design supports N mics but the
   primary UX is optimised for operator + one participant. The roll call
   and setup UI should be fast for 2 participants, not cumbersome for the
   common case to support 10.

2. **Browser supports multiple simultaneous `getUserMedia` calls.** Tested
   in Chrome 120+: multiple calls with `{deviceId: {exact: id}}` open
   independent streams. Firefox requires sequential calls. Safari is
   untested but not a target browser (AC-2 of F-02 already excludes it for
   opus).

3. **One WebSocket carries all streams.** Opening N WebSocket connections
   would multiply the auth/consent/handshake logic. A 1-byte stream prefix
   on binary frames is simpler and uses existing infra.

4. **STT v2 supports N concurrent streams per client.** Google's quota
   default is 100 concurrent streams per project. At 2–3 per meeting this
   is not a constraint until ~35 simultaneous meetings.

5. **Voice roll call uses the same STT adapter.** The short (5s) roll call
   capture runs through the existing `GoogleSTTAdapter` with a brief audio
   window, not a separate recognition API.

## 10. Decisions Needing Your Call

1. **Max mic count**: Should we cap at 2 (operator + participant), 4, or
   unlimited? **Recommendation**: Cap at 4 for v1 — keeps the setup UI
   simple and bounds STT cost. Raise if a real need appears.

2. **Roll call: voice-only or allow operator override?** If STT
   mishears "Mario Rossi" as "Mario Rossy", should the operator be able to
   correct it by voice ("Correction: R-O-S-S-I") or by clicking and typing?
   **Recommendation**: Allow a click-to-edit fallback on the confirmation
   screen. Pure voice correction is fragile for spelling, and the goal is
   accuracy in the legal transcript.

3. **Separate GCS files per mic (O-07) vs. single interleaved file?**
   Separate files preserve per-speaker audio for legal purposes and
   re-analysis. Single file is simpler. **Recommendation**: Separate files —
   the legal use case demands it, and the existing uploader generalises
   cleanly.

4. **Roll call is mandatory vs. optional?** Should the operator be able to
   skip roll call and just assign names manually in the mic setup?
   **Recommendation**: Optional — some meetings may have known participants
   and the operator can type names in mic setup (O-01). Roll call is the
   "no manual entry" path but shouldn't block simple setups.

5. **Should the voice roll call record a voice sample for future speaker
   identification?** Storing a 5-second voice print per participant could
   enable automatic speaker recognition in future meetings.
   **Recommendation**: Capture and store the sample (O-05 `voice_sample_gcs_path`),
   but don't build recognition yet. It's cheap to store and expensive to
   re-collect.

## 11. What This Plan Does NOT Deliver

- **Automatic speaker recognition** (identifying who is speaking without mic
  assignment). That requires ML voice embeddings and is a separate epic.
- **Video recording** — modality stays AUDIO.
- **Remote/virtual meeting integration** (Zoom/Teams/Meet capture). This is
  for in-person meetings with physical microphones.
- **Real-time speaker change detection** within a single mic stream. Each mic
  is assumed to capture one speaker.
- **Transcript export to PDF**. O-06 produces structured data; rendering to
  PDF is a follow-on story (likely in Epic K).
