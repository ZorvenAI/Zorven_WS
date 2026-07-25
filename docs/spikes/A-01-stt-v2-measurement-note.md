# A-01 — STT v2 Streaming Latency Measurement Note

**Date**: 2026-07-25
**Spike**: A-01 — Google STT v2 streaming latency and diarization
**Status**: Complete
**Blocks**: F-05 (live transcript relay), F-06 (batch backfill)

## Environment

- **OS**: macOS Darwin 25.3.0
- **Python**: 3.13.9
- **GCP Project**: zorven-503517
- **Location**: global
- **Model**: long (default STT v2 recognizer model)
- **Audio Fixture**: TTS-generated 2-speaker onboarding dialog (69.6s, 16kHz LINEAR16 mono)
- **Speakers**: Google TTS en-US-Standard-D (male) and en-US-Standard-E (female)
- **Network**: Local development machine
- **Date**: 2026-07-25

## AC-1: Streaming Latency

**Question**: Can STT v2 streaming deliver partial transcripts within 2 seconds of utterance onset?

### Results

| Recognizer | Samples | p50 (ms) | p95 (ms) | Min (ms) | Max (ms) | Mean (ms) | Verdict |
|---|---|---|---|---|---|---|---|
| oia-spike-en-us | 577 | 13.4 | 410.1 | 0.0 | 1918.5 | 119.0 | **PASS** |
| oia-spike-auto | 577 | 7.9 | 413.8 | 0.0 | 2527.9 | 118.9 | **PASS** |

**Budget**: 2000ms
**Verdict rules**: PASS = p95 <= 2000ms, MARGINAL = p50 <= 2000ms < p95, FAIL = p50 > 2000ms

**Finding**: Both recognizer configurations comfortably pass the 2-second latency budget. Median latency is under 15ms — the API returns partial transcripts almost immediately as audio is received. The p95 of ~410ms means 95% of partials arrive within half a second. The max of ~2.5s on the auto recognizer suggests occasional outliers at utterance boundaries, but these are rare.

**Recommendation for F-05**: The 2-second latency budget is achievable with significant headroom. LIVE mode can rely on STT v2 streaming for real-time transcript display.

## AC-2: Diarization

**Question**: Does two-speaker diarization work reliably, and do labels survive reconnects?

### Results

**Critical finding: STT v2 StreamingRecognize does NOT support speaker diarization.**

Both streaming and batch recognition with the `long` model reject diarization configuration with:
- Streaming: `400 StreamingRecognize does not support Speaker Diarization`
- Batch: `400 Recognize does not support Speaker Diarization for the requested model`

This was an assumption in the implementation plan (Assumption #4) that proved incorrect.

**Reconnect test**: Stream reconnection works correctly — a new stream ID is generated and transcription continues. However, since diarization is not available, speaker label stability across reconnects is not applicable.

**Recommendation for F-05/F-06**: Speaker attribution cannot rely on STT v2 diarization. Alternative approaches:
1. **Voice embeddings**: Use a separate speaker identification model (e.g., pyannote.audio, Resemblyzer) alongside STT v2 streaming
2. **Client-side separation**: If the meeting platform provides separate audio tracks per participant, route each to its own STT stream
3. **Post-processing**: Use a batch diarization service (e.g., Google's Chirp 2 model if it supports diarization, or a third-party like AssemblyAI) for the PROCESS mode

## AC-3: Cost

**Question**: What does it cost per 60-minute meeting?

### Cost Estimate

| Component | Calculation | Cost |
|---|---|---|
| Streaming (1 hour) | 240 x 15s intervals x $0.004/15s | $0.96 |
| Diarization increment | Not applicable (not supported) | $0.00 |
| Batch backfill (5% loss) | 12 x 15s intervals x $0.004/15s | $0.05 |
| **Total per meeting hour** | | **$1.01** |

**Price source**: Published Google Cloud STT v2 pricing ($0.016/min for `long` model streaming)

**Finding**: At ~$1.01/hour, STT v2 streaming is cost-effective for meeting transcription. For a tenant running 20 one-hour meetings per month, the STT cost would be ~$20.20/month.

**Note**: Pricing was calculated from published rates. Actual billing should be verified against the GCP billing console (may lag 24-48h).

## AC-4: Language Mode

**Question**: Should STT language be fixed per tenant or auto-detected per session?

### Comparison

| Metric | Fixed (en-US) | Multi-language (auto) | Delta |
|---|---|---|---|
| p50 latency | 13.4ms | 7.9ms | -5.5ms (auto faster) |
| p95 latency | 410.1ms | 413.8ms | +3.7ms (negligible) |
| Max latency | 1918.5ms | 2527.9ms | +609.4ms |
| Mean latency | 119.0ms | 118.9ms | -0.1ms (negligible) |
| Batch confidence | 0.983-0.992 | N/A (tested separately) | — |

**Finding**: Multi-language recognition performs nearly identically to fixed-language on English-only audio. The p50 is actually slightly faster, while the max is higher (single outlier). There is no meaningful latency or accuracy penalty for using multi-language mode.

**Cost impact**: Both use the same `long` model pricing — no cost difference between fixed and multi-language.

**Recommendation**: See `docs/decisions/OD-002-stt-language-mode.md` for the formal decision. Given the negligible performance difference, either approach is viable. Fixed per-tenant offers predictability; auto-detect offers flexibility.

## Key Discoveries

1. **STT v2 streaming diarization is not supported** — This is the most impactful finding. F-05 LIVE mode needs an alternative speaker attribution strategy.
2. **Latency is excellent** — p50 under 15ms means near-real-time transcript display is achievable with no special optimization.
3. **Cost is low** — ~$1/hour makes STT v2 viable even for high-volume tenants.
4. **Multi-language has no penalty** — The auto-detect recognizer performs as well as fixed English.
5. **Reconnection works** — Stream reconnects produce new stream IDs and transcription resumes cleanly.
6. **The `long` model location must be `global`** — Regional endpoints (e.g., `us-central1`) are not supported.

## Data Files

- `spike-stt-v2/measurements_20260725_185112.jsonl` — en-US recognizer measurements (577 samples)
- `spike-stt-v2/measurements_20260725_185231.jsonl` — auto recognizer measurements (577 samples)
- `tests/fixtures/two_speaker_onboarding_sample.wav` — TTS-generated two-speaker fixture (69.6s)
