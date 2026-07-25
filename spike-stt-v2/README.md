# spike-stt-v2 — A-01: STT v2 Streaming Latency Spike

Timeboxed 2-day spike measuring Google Cloud Speech-to-Text v2 streaming latency and diarization quality. Answers four questions before LIVE mode implementation begins (F-05, F-06).

## Prerequisites

1. **Enable Speech-to-Text API**:
   ```bash
   gcloud services enable speech.googleapis.com
   ```

2. **Set environment variables**:
   ```bash
   export OIA_SPIKE_PROJECT_ID=your-gcp-project-id
   # Optional: export OIA_SPIKE_CREDENTIALS_JSON='{"type":"service_account",...}'
   # Optional: export OIA_SPIKE_CREDENTIALS_PATH=/path/to/sa.json
   # Default: uses Application Default Credentials (gcloud auth application-default login)
   ```

3. **Create recognizer resources** (one-time):
   ```bash
   pip install -r requirements.txt
   python create_recognizers.py
   ```

## Run the Spike Relay

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8120
```

Open http://localhost:8120 in Chrome. Select a recognizer, click **Start Session**, and speak. The page shows real-time latency measurements.

## Run Tests

```bash
# Unit + property tests (no GCP required)
cd spike-stt-v2
pytest tests/test_measurement.py tests/test_stt_client.py -v

# Integration tests (requires GCP credentials + recognizer resources)
pytest tests/test_stt_integration.py tests/test_e2e_relay.py -v -m integration

# All tests
pytest tests/ -v
```

## Acceptance Criteria

| AC | Question | Metric |
|----|----------|--------|
| AC-1 | Streaming latency ≤ 2s? | p95 of utterance-onset → first-partial |
| AC-2 | Diarization works? Labels survive reconnect? | Misattribution rate, label stability |
| AC-3 | Cost per 60-min meeting? | $/hour (streaming + diarization + backfill) |
| AC-4 | Fixed vs auto language? | Latency/cost delta between recognizers |

## Deliverables

- `docs/spikes/A-01-stt-v2-measurement-note.md` — measurement report
- `docs/decisions/OD-002-stt-language-mode.md` — language mode ADR
- `tests/fixtures/two_speaker_onboarding_sample.wav` — audio fixture for F-05 tests
