# OIA Manual Test Runbook

For verifying the Onboarding Intelligence Agent by hand before promoting
`development_main` to `main`. Written 2026-10-28, against the service as it
stands on `development_main`.

**Why this exists.** OIA has **never been deployed** and has never run outside
a test harness: no image has been pushed to Artifact Registry, and
`deploy-gcp.yml` triggers on `main` only, where the service's code has not yet
landed. Everything below runs locally. A green run here is the evidence for
the promote-to-`main` decision, not a formality.

---

## 0. Before you start — the five-minute setup

### 0.1 Refresh ADC. This is the one that will waste your afternoon.

```bash
gcloud auth application-default login
```

Google STT authenticates through **Application Default Credentials**, not
through `gcloud auth login`. They are separate credentials, and the container
mounts the ADC file directly:

```yaml
- ~/.config/gcloud/application_default_credentials.json:/gcloud/application_default_credentials.json:ro
```

As of writing this file was six weeks stale. A stale ADC surfaces as an STT
failure that reads like a code bug, so do this first and do not skip it.

### 0.2 Put two keys in `deployment/.env`

| Key | Used for | Where to get it |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini — questionnaire generation, analysis, summaries | `gcloud secrets versions access latest --secret=GOOGLE_API_KEY` |
| `TAVILY_API_KEY` | PREP research retrieval | `gcloud secrets versions access latest --secret=TAVILY_API_KEY` |

Compose reads both. `GOOGLE_API_KEY` was empty in `deployment/.env` when this
was written, and without it PREP degrades instead of generating — which looks
like a bug but is a config gap. The service tells them apart on purpose: a
missing key degrades with a distinct reason, not a breaker trip.

### 0.3 Confirmed already working

Checked 2026-10-28, no action needed: `speech.googleapis.com` enabled, bucket
`zorven-raw-assets` exists, `GOOGLE_API_KEY` present in Secret Manager.

### 0.4 Check Docker disk before you build

```bash
docker run --rm alpine df -h / | tail -1
```

The full stack needs several GB. At 100% full, builds fail at
`apt-get install` with `exit code: 100`, which reads like a Dockerfile fault
and is not one. If you are short:

```bash
docker builder prune -f        # build cache only, rebuilds on demand
docker image prune -a -f       # unused images; more disruptive
```

---

## 1. Hardware

| Item | Needed for | Notes |
|---|---|---|
| Laptop or USB mic | All LIVE testing | Enough for steps 2–3 and most of 4 |
| A second person, **or** a phone playing recorded speech | Speaker attribution, interruption markers | A phone is a perfectly good "speaker 2" |
| **Headphones for every speaker** | Any multi-speaker test | Without these each mic hears the other and attribution results mean nothing |
| A physical document or a second screen | OCR of documents shown mid-meeting | Any invoice or brochure |
| Multi-channel interface — **Scarlett 2i2** or **Zoom H6** | Epic O multi-mic **only** | See §6. Optional; everything else works without it |

**Browser: use Chrome.** `useMeetingRecorder.ts` negotiates
`audio/webm;codecs=opus` (falling back through `audio/webm` and
`ogg;codecs=opus`). Safari does not support that reliably and will fail at the
recorder, not the server.

---

## 2. Bring the stack up

```bash
cd deployment
docker compose up -d redis postgres backend frontend
docker compose --profile with-monitoring up -d
docker compose up -d onboarding-intelligence-agent-svc
```

| Surface | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Django backend | http://localhost:8001 |
| OIA | http://localhost:8120 |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

**Open Grafana before you test anything.** The "Onboarding Intelligence Agent"
dashboard shows STT partial latency, active WebSocket sessions, circuit
breaker state and guardrail trigger rate. When a step misbehaves it usually
tells you why in one glance, and twelve alert rules are evaluating behind it.

Health gate — do not proceed until this returns 200:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8120/health
```

`/health` returns 200 only when every required dependency answers, within 2 s.
A 503 here means a dependency is down and every step below will fail
confusingly.

---

## 3. The gate that catches everyone

**The LIVE socket refuses to open unless the session is already prepared.**
You cannot jump to the meeting screen. Four hard gates in
`app/logic/live_handshake.py`:

| Close code | Meaning | What to fix |
|---|---|---|
| **4401** | Invalid or expired ticket | Re-enter from the session page so a fresh ticket is minted |
| **4403** | Consent missing or revoked | Record consent for the subject |
| **4404** | Session not found, or questionnaire not `APPROVED` | Approve the questionnaire |
| **4409** | Another socket is already live | Close the other tab; the lock is keyed per company and clears on a clean close |

If the socket closes the instant it opens, **read the close code before
anything else** — it names the gate you missed. The codes are deliberately
distinct so a client cannot confuse an eligibility problem with a consent
problem.

---

## 4. The test sequence

Run these in order. Each builds state the next one needs.

### Step 1 — PREP (no audio)

1. `http://localhost:3000/onboarding`
2. Walk `step-1` → `step-5`, creating a session for a real small business
   (a real one makes the research legible).
3. Generate the questionnaire.
4. **Approve** it.

**Expect:** a brief with sourced facts, and questions derived from it.

**Verify deliberately:** every fact should carry a source. The skill drops any
fact whose `source_url` was not in the retrieved set, and OG-01 demotes
anything still unsourced — demoted, never deleted, because an unsourceable
claim becomes a question. **A fluent, plausible, unsourced claim is the exact
failure this design exists to prevent**, so if you see one, that is a finding
worth filing.

If the brief is empty and labelled degraded, check `TAVILY_API_KEY` before
suspecting the code.

### Step 2 — LIVE, one mic, clean stop

1. Record consent for the subject.
2. Open `/onboarding/sessions/{id}/meeting`.
3. Grant microphone permission.
4. Talk for about two minutes. Mention a couple of things the questionnaire
   asks about.
5. Press **stop**.

**Expect:** partial transcript within ~2 s of speech; final segments
replacing partials; questions attaching to evidence as you answer them; a
summary afterwards.

**Watch in Grafana:** "STT Partial Latency p50/p95" — the NFR is p95 ≤ 2 s.
This has **never been verified against a running instance**, so whatever you
see is the first real datapoint. Note it down.

### Step 3 — LIVE, dropped connection ← the important one

1. Start a recording as in step 2 and speak for a minute.
2. **Close the browser tab outright.** Do not press stop.
3. Reopen the session and look at the summary.

**Expect:** the recording is reported as **partial / truncated**, naming
roughly how much was not transcribed.

**This is the #677 / #679 / #685 fix and the sharpest regression test in the
whole runbook.** Until recently a dropped socket recorded *no* interruption at
all, and the transcript finalised as "coverage not assessed" instead of
"partial — N minutes missing". If you see a claim of **completeness** here,
stop and file it: a truncated transcript asserting it is complete is worse
than one admitting it does not know.

**Then immediately start a new recording on the same company.** It must be
allowed. If you get **4409**, the live lock outlived the dead socket — that
was #680/#681, and a regression there locks an operator out of their own
meeting for up to 90 seconds.

### Step 4 — LIVE, two speakers

With headphones on both sides, you and a second voice alternate for a few
minutes.

**Expect:** segments attributed per speaker, and the voice roll call mapping
names to mics if you used it.

### Step 5 — Documents and OCR

Hold a document up to the camera, or share a screen showing one, during a
recording.

**Expect:** the document's text extracted and attached as evidence.

**Privacy check worth doing explicitly:** `ocr_text` is deliberately **not**
in the RAG metadata (a B-02 deferral), so confirm extracted document text is
not leaking into places it should not. There is an unresolved NFR-PRIV-02
question in that area — see `project_b02_deferrals_for_h03`.

### Step 6 — PROCESS and review

Open `/onboarding/sessions/{id}/review`.

**Expect:** fields populated with provenance; key findings; the ability to
edit and have the edit recorded.

**Verify:**
- Each field's provenance names where the value came from.
- Editing a field logs EVT-109 — and that event carries **no field values**,
  only `field_name`, `action`, `edit_distance`, `classification`. If a value
  appears in that payload, it is a privacy defect.
- **Retention settings** (Owner/Admin only): shorten the window and confirm
  you are shown the number of affected items **and asked to confirm before
  anything is deleted**. The preview must not persist. The motivating quote
  for that story is *"we lost eight months of onboarding data by changing a
  dropdown"*, so the confirm step is the point.

---

## 5. Legal header check

Finalise a recording and read the generated header.

Coverage is **tri-state** by design:

| Value | Means |
|---|---|
| complete | A `transcript.stopped` marker exists and no gap was found |
| partial | A gap was measured; the header says how much is missing |
| not assessed | Neither could be established |

**"Not assessed" is an acceptable answer. A false claim of completeness is
not.** If a recording you truncated in step 3 reports complete, that is a
serious finding.

---

## 6. Multi-mic (Epic O) — optional, and known-unverified

Only attempt this with a **Scarlett 2i2** or **Zoom H6**.

Issue **#665** is open precisely because
`getUserMedia({ channelCount: N })` has **never been verified on real
multi-channel hardware**. O-09's AC-1 and AC-2 are blocked on that verdict.

So if you have the hardware, the single most valuable thing you can report is
narrow: **does the browser expose N discrete channels from that interface, and
does each channel carry only its own mic?** Check it in
`useAudioDevices.ts` / `useMeetingRecorder.ts` territory, and post the answer
on #665 either way. A negative answer is just as useful — it would mean the
design needs N separate devices rather than one multi-channel device.

---

## 7. Known issues — do not file these again

| Issue | Status |
|---|---|
| **#688** | The WS marker test suite is unstable in combined runs. Harness-only: production path proven unaffected, writes measured at 1–4 ms. Does not affect manual testing |
| **#665** | Multi-mic hardware spike, blocked as above |
| `test_redact_pii` failures locally | `presidio_analyzer` is not installed locally; green in CI |
| 3 `test_migrations.py` failures | Pre-existing on `development_main` |

---

## 8. When you are done

Record, for the promote-to-`main` decision:

1. Which steps passed, and the **STT p95 latency** you actually observed.
2. Any step-3 or step-5 finding, which are the two that touch legal and
   privacy claims.
3. Whether anything in Grafana fired or looked wrong.

Then two things remain before `main`:

- **The promote merge itself is awkward and needs care.** `main`'s only
  unique commit is #643, a 519-file squash that added OIA wholesale and
  destroyed shared ancestry, so a plain merge reports **57 conflicts** in
  files nobody edited twice. Resolving in favour of `development_main` is
  correct — verified: no file exists on `main` that is absent from
  `development_main`, and `main`'s apparently-unique lines are superseded
  code (hardcoded `speaker=0`, the unshielded `lock.release()`). Do not
  hand-resolve those 57 files one by one.
- **Merging to `main` triggers the deploy**, which will be OIA's first ever.
  Expect first-deploy issues — secret wiring, and the `--timeout=3600`
  Cloud Run setting a WebSocket needs, since the 300 s default severs
  meetings at five minutes. Do it when you can watch it.
