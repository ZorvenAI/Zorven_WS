# Implementation Plan: Mark a Truncated Live Transcript (#662 remainder)

> **Status: awaiting approval. No code written.**
>
> Authoring note, required by `.claude/skills/zorven-implementation-plan`: that
> skill is still a partial transcription and its four reference files
> (`references/testing-strategy.md`, `references/gcp-cost-estimation.md`,
> `references/git-workflow.md`,
> `assets/implementation-plan-template.md`) **do not exist**. So this plan is
> *not* authored "using the skill". The numbering follows what the skill
> fragment establishes — §6 testing split 6.1–6.4, §7 GCP cost, §8 git
> workflow — and the rest of the structure, the section contents and the
> testing depth are **improvised**. The specifics those files were meant to
> supply (exact `gcloud` cost commands, the real template's section list, the
> git boilerplate) are reconstructed from this repo's conventions, not from
> the source. Please drop the four files in when you have them.

## 1. Problem Statement

When the LIVE WebSocket drops mid-meeting, transcription stops. Audio upload is
deliberately independent (F-03, §4.3), so the recording finalises normally:
status `SUMMARIZED`, `has_transcript: true`, and O-06 assembles a **legal
transcript header** over a record that stops at the moment of the drop. Nothing
anywhere says the transcript is partial.

#666 fixed the two visibility halves of #662 — the client now replays its
`start` frame on reconnect (`useLiveSocket.ts:112`), and `MeetingView` surfaces
`reconnecting` and `closed` (`MeetingView.tsx:277`). What remains is the half
that matters after the meeting is over: **the artefact does not record its own
incompleteness.**

Three items remain. They are listed in priority order and §9 recommends
splitting them.

| Item | Why it matters |
|---|---|
| A · Mark truncation | A legal document that implies completeness when it is partial is the actual harm in #662 |
| B · Recover from terminal `closed` | After 5 failed attempts the socket is dead for the rest of the meeting with no way back |
| C · Resolve dead `get_stream_map()` | Reads as the designed resume path; is never called |

## 2. Current Architecture (verified, not assumed)

Every line reference below was checked against `development_main` at
`3f851293`.

- **The frame buffer survives the drop.** `SummarizeRecording._read_transcript`
  (`app/skills/summarize_recording.py:120`) reads the Redis list
  `keys.live_frames(session_id)` at finalisation. That list is why the
  truncation is observable at all.
- **Segments carry absolute times.** `extract_transcript_segments`
  (`summarize_recording.py:203`) keeps `t_start`/`t_end` as absolute epoch
  floats and filters on `t_start < started_at or t_end > stopped_at`. So
  transcript coverage is directly comparable to the recording window.
- **The write-back contract is `summary` + `transcript`.**
  `backend_client.update_recording_summary` (`backend_client.py:430`) PATCHes
  `/api/v1/onboarding/internal/recordings/{id}/summary/`. Django's
  `update_recording_summary` (`views.py:2757`) sets `summary`, validates and
  stores `transcript`, then forces `status = SUMMARIZED` (`views.py:2815`).
- **The legal header is assembled in Django.** `assemble_header`
  (`apps/onboarding/transcript_assembler.py:27`) builds date, time, session,
  attendees and consent. It already receives `recording.started_at` and
  `stopped_at`, so it knows the window — it just has nothing to compare
  against.
- **`RecordingStatus`** (`models.py:431`) is `RECORDING, UPLOADED,
  TRANSCRIBED, SUMMARIZED, FAILED`. There is no partial state.
- **No truncation concept exists anywhere.** `MeetingRecording` has no such
  field, and `has_transcript` (`serializers.py:387`) is a
  `SerializerMethodField` over transcript presence only.
- **`get_stream_map()`** is defined at `app/logic/live_session.py:744` and
  called from nowhere in `app/` or `tests/`.

## 3. Design Approach

### 3.1 The obvious detector is wrong, and this is the core finding

The tempting rule is "transcript ends well before the recording does →
truncated". **It produces false positives on honest recordings.** An operator
who says "thanks, I'll send that over" and stops the recording forty seconds
later leaves a forty-second tail gap with nothing wrong. Marking that
recording's legal header "partial" is its own correctness bug, and a header
that cries wolf will be ignored precisely when it is right.

Silence and death are indistinguishable from the transcript alone. Truncation
therefore needs a **positive signal that STT stopped while recording
continued**, not an inference from absence.

### 3.2 Sentinel frames in the buffer that already survives

`app/api/ws.py` already tears the STT tasks down on close — the per-stream
tasks at `ws.py:1366-1379` and the single-stream task at `ws.py:1386-1391`,
plus the queue sentinels around `ws.py:1838`. Have that teardown also append a sentinel to the same Redis frame
buffer the finaliser reads:

```json
{"type": "transcript.interrupted", "at": <epoch>, "reason": "socket_closed"}
{"type": "transcript.resumed",     "at": <epoch>}
```

This is attractive for three reasons: the buffer is already durable and
already read at finalisation; sentinels are additive, so every existing reader
that filters on `type != "transcript.final"` ignores them untouched; and the
record becomes an *interval list* rather than a boolean, so the header can say
how much is missing and where.

### 3.3 Coverage computed where the sentinels are, stored where it is queryable

`SummarizeRecording` computes a coverage block and includes it in the `summary`
dict it already sends:

```python
"transcript_coverage": {
    "complete": False,
    "gaps": [{"from": 1738281234.5, "to": 1738281501.2, "reason": "socket_closed"}],
    "missing_s": 266.7,
    "recording_s": 1802.0,
}
```

Django persists the two facts worth querying onto `MeetingRecording` —
`transcript_complete: bool` (default `True`) and `transcript_missing_s:
PositiveIntegerField` — and leaves the gap intervals in the `summary` JSON.

A migration for two fields rather than reading the blob, because "this legal
document is partial" is a question the library list has to answer for every row
at once, and because a nullable boolean is a schema promise while
`summary["transcript_coverage"]["complete"]` is a hope about a free-form dict.

### 3.4 What the header says

`assemble_header` gains a `transcript_completeness` block, and
`LegalTranscriptHeader.tsx` renders it as a prominent warning when
`complete is False` — stating the missing duration and that the audio is intact
and re-transcribable, which is the actionable part (#662: "the audio itself is
safe — the GCS upload path is unaffected").

## 4. Story Breakdown

### 662-A: Mark a truncated transcript

**AC-1**: A socket close while a recording is active appends a
`transcript.interrupted` sentinel to the session's live frame buffer.
**AC-2**: Re-establishment appends `transcript.resumed`.
**AC-3**: Finalisation of an interrupted recording yields
`transcript_coverage.complete is False` with one gap per interruption and a
`missing_s` within 1 s of the true sum.
**AC-4**: A recording that was never interrupted yields `complete is True`,
**including when it has a long silent tail** — the §3.1 false positive, asserted
directly.
**AC-5**: `MeetingRecording.transcript_complete` is `False` and
`transcript_missing_s` is set after an interrupted finalisation; both default
to complete for every existing row.
**AC-6**: The legal header carries `transcript_completeness`, and the UI shows
a warning naming the missing duration and the re-transcribe route.
**AC-7**: `has_transcript` stays `True` — there *is* a transcript, and flipping
it would hide the partial one rather than qualify it.

### 662-B: Recover from terminal `closed`

**AC-1**: `useLiveSocket` exposes a manual `reconnect()` that resets the
attempt budget.
**AC-2**: The `closed` banner offers "Retry transcription", which re-opens and
replays the stored `start` frame.
**AC-3**: A successful manual retry appends `transcript.resumed`, so the gap
closes rather than running to the end of the recording.

### 662-C: Resolve `get_stream_map()`

**Recommendation: delete it.** The client-side `start` replay #666 landed is the
simpler contract and is already load-bearing. Keeping a server-side resume
helper that nothing calls invites someone to assume the path exists — which is
how #662 was written up in the first place ("hint this path was designed and
not finished"). Deleting it is reversible; the design note in #662 and this
plan record why.

## 5. Dependency Graph

```
662-A (sentinels → coverage → field → header)   ← the legal correctness fix
662-B (manual retry) → emits transcript.resumed, so A must land first
662-C (delete dead code) — independent, no dependants
```

**Critical path**: 662-A alone. B and C are each a day's work behind it.

## 6. Testing Strategy

No mocks, per this project's standing rule: real Redis for the buffer, the real
PATCH endpoint for the write-back.

### 6.1 Unit

| Area | Test |
|---|---|
| Coverage maths | sentinel pairs → gap intervals; unclosed interruption runs to `stopped_at`; two interruptions → two gaps |
| **False positive** | 5-minute recording, last segment at 02:00, no sentinel → `complete is True` (AC-4) |
| Sentinel tolerance | existing readers skip unknown `type` values unchanged |
| Header | `assemble_header` emits `transcript_completeness`; absent coverage → complete |
| Serializer | `transcript_complete` surfaces; `has_transcript` unchanged |

### 6.2 Property (hypothesis)

Random interleavings of `final` frames and interrupted/resumed sentinels:
`missing_s` never exceeds `recording_s`, is never negative, and
`complete is False` **iff** at least one sentinel is present — the invariant
§3.1 is about.

### 6.3 Integration

Real Redis: write frames and sentinels, run `SummarizeRecording`, assert the
coverage block. Then PATCH the real Django endpoint and assert both columns.

### 6.4 E2E

Playwright: start a recording, kill the socket server-side mid-meeting, let it
finalise, assert the library row and the rendered header both say partial. This
is the only test that would have caught the original bug end to end.

## 7. GCP Cost Estimation

**No new cost.** No new service, no new Redis keys (sentinels are appended to an
existing list under its existing TTL), no new storage class, two scalar columns.
Sentinel volume is bounded by reconnect attempts (≤6 per recording).

Reconstructed without the `gcloud` procedure the missing
`references/gcp-cost-estimation.md` specifies; the conclusion "no new
chargeable resource" does not depend on it, but say so if you want the real
commands run.

## 8. Git Workflow

- Branch from `development_main`, PR back into `development_main` — never
  `main` while OIA epics are open.
- One PR per story: 662-A, then 662-B, then 662-C.
- Each PR must pass: `black` (23.12.1 for `ai-brand-automator/`, ≥24 for the
  service — the hook resolves this per tree), `flake8`, `mypy app/`,
  `pytest -m unit`, `npx tsc --noEmit`, `npm run lint`, and
  `scripts/check_weak_assertions.py`.
- Migration via `makemigrations` then `migrate_schemas --shared`; never edit an
  existing migration.

## 9. Assumptions

1. `stopped_at` is trustworthy as the recording's end. If the stop frame is
   itself lost to the drop, coverage is measured against a `stopped_at` that
   may be the server's close time — the gap is then understated, never
   overstated, which fails in the safe direction.
2. The frame buffer's TTL outlives finalisation. It must already, or
   `_read_transcript` would return nothing today.
3. Sentinels are cheap enough to write on a close path that is already doing
   Redis work.
4. Existing rows are complete. The migration defaults to `True`, which is a
   claim about history we cannot verify — see §10.2.
5. `transcript_missing_s` as whole seconds is sufficient precision for a legal
   header.

## 10. Decisions Needing Your Call

### 10.1 Two columns, or read the summary blob?

A migration adds two queryable columns; the alternative stores nothing new and
reads `summary["transcript_coverage"]`.

**Recommendation: the columns.** The library list has to answer "is this
partial?" for every row, and a free-form dict cannot be filtered or indexed.

### 10.2 What do we claim about recordings already finalised?

The migration must default `transcript_complete` to something. `True` asserts
every existing recording is complete, which we cannot know — any of them may
already be truncated by this bug.

**Recommendation: default `True`, and make the field nullable with `None`
meaning "never assessed", backfilling nothing.** The header then distinguishes
"complete", "partial", and "unknown — recorded before truncation was
detected", which is the only honest set of three. This costs a nullable
boolean and one extra UI branch.

### 10.3 Does a partial transcript still auto-dispatch PROCESS?

J-01 extracts brand fields from the transcript. Extraction over a transcript
missing ten minutes will produce confident, wrong field values with full
provenance.

**Recommendation: let it dispatch, but pass the coverage through so extracted
fields inherit a lower confidence ceiling.** Blocking PROCESS would strand the
session; silently extracting from a partial record repeats #662's mistake one
layer up. This may deserve its own card rather than riding in 662-A — flag it
and I will write it up separately.

## 11. What This Plan Does NOT Deliver

- **Re-transcription.** The header will tell the operator the audio is intact
  and re-transcribable; nothing here implements a re-transcribe action. That is
  a new story.
- **Preventing the drop.** This marks the damage; it does not make the socket
  survive Cloud Run's hour cap or a network blip.
- **Server-side resume of STT.** 662-C deletes that path rather than building
  it (§4, 662-C).
- **Retroactive assessment of existing recordings.** §10.2 leaves them
  `unknown` by design.
- **Anything about O-09 / multi-channel.** Separate and parked (#665).
