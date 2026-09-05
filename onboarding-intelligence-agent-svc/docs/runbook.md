# OIA Operational Runbook

Service: `onboarding-intelligence-agent-svc` (port 8120)

---

## DLQ Handling

**Alert**: `OIA_DLQ_NotEmpty`

1. Check DLQ message rate:
   ```bash
   curl -s http://localhost:8120/metrics | grep oia_dlq_messages_total
   ```

2. List DLQ messages (requires Kafka access):
   ```bash
   rpk topic consume oia-commands-dlq --num 10 --format json
   ```

3. Replay a message — re-publish to the commands topic with the original idempotency key:
   ```bash
   rpk topic produce agent.commands.onboarding-intelligence-agent \
     --key "<original-key>" < message.json
   ```

4. If a message has been replayed 3 times and still fails, archive it:
   ```bash
   rpk topic produce oia-commands-archive --key "<key>" < message.json
   ```

5. Reset the DLQ depth metric by restarting the service (gauge resets on startup).

---

## Stuck Session

**Alert**: watchdog log `watchdog_stuck_session`

The watchdog runs every 60s, scanning Redis for `oia:v1:*:session:*` keys with a `last_heartbeat` field older than 300s (5 min). When found, it calls Django's `POST /api/v1/onboarding/internal/sessions/{pk}/finalize-stuck/` to transition MEETING_LIVE to GATHERED.

1. Check for stuck sessions manually:
   ```bash
   redis-cli -n 2 --scan --pattern "oia:v1:*:session:*" | while read key; do
     hb=$(redis-cli -n 2 HGET "$key" last_heartbeat)
     [ -n "$hb" ] && echo "$key last_heartbeat=$hb"
   done
   ```

2. Manual finalization (if watchdog is down):
   ```bash
   curl -X POST http://django:8001/api/v1/onboarding/internal/sessions/<pk>/finalize-stuck/ \
     -H "X-Service-Token: $ORCHESTRATOR_SERVICE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "manual_operator"}'
   ```

3. Verify the session transitioned:
   ```bash
   curl http://django:8001/api/v1/onboarding/sessions/<pk>/ \
     -H "Authorization: Bearer $JWT" | jq .status
   # Expected: "GATHERED"
   ```

4. The live lock (90s TTL) expires naturally — no manual cleanup needed.

---

## GDPR Operations

### Erasure

Trigger per-tenant erasure via the Django endpoint:
```bash
curl -X POST http://django:8001/api/v1/onboarding/erasure/ \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<session-id>"}'
```

This deletes: session Redis keys (`oia:v1:<tenant>:session:*`), transcripts, recordings, provenance records, and FieldProvenance rows.

### Retention Enforcement

Retention is enforced by the M-03 retention service. Check the last enforcement run:
```bash
redis-cli -n 2 GET "oia:v1:retention:last_run"
```

### What Gets Deleted

| Data | Location | Erasure | Retention |
|------|----------|---------|-----------|
| Session state | Redis DB 2 | Immediate key delete | TTL-based (4h sliding) |
| Transcripts | Django DB | CASCADE from session | `RETENTION_DAYS_DEFAULT` (365d) |
| Recordings | GCS + Django DB | GCS delete + DB cascade | `RETENTION_DAYS_DEFAULT` |
| Provenance | Django DB | CASCADE from session | `RETENTION_DAYS_DEFAULT` |
| Prompt cache | Redis DB 2 | Not tenant-scoped | N/A |

---

## Guardrail Review Cycle

**Alert**: Elevated `oia_guardrail_triggers_total` rate

1. Query trigger counts by rule:
   ```promql
   topk(10, sum by (rule_id) (increase(oia_guardrail_triggers_total[24h])))
   ```

2. Check which rules are firing in the last hour:
   ```bash
   curl -s http://localhost:8120/metrics | grep oia_guardrail_triggers_total
   ```

3. Tune thresholds in config (via env vars):
   - `OIA_SCOPE_THRESHOLD` — scope check sensitivity (default: 0.55)
   - `OIA_INPUT_MAX_TOKENS` — input length limit (default: 4096)
   - `OIA_OG03_KEY_CONFIDENCE_THRESHOLD` — output key confidence (default: 0.6)

4. Review rule definitions in `app/logic/guardrail_rules/` and the chain order in `app/logic/guardrails.py`.

---

## Prompt Incident

When a prompt version causes unexpected behaviour:

1. Bust the local prompt cache:
   ```bash
   curl -X POST http://localhost:8120/v1/admin/cache-bust \
     -H "X-Service-Token: $OIA_SERVICE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"prompt_name": "<prompt-name>"}'
   ```

2. Revert in POI (Prompt Optimization Service):
   ```bash
   curl -X POST http://poi:8110/api/v1/lifecycle/rollback \
     -H "X-User-Role: admin" \
     -H "Content-Type: application/json" \
     -d '{"prompt_name": "<prompt-name>", "reason": "incident"}'
   ```

3. Verify sessions pick up the new version:
   ```bash
   # The next session will resolve a fresh prompt version from Redis/MLflow.
   # Existing sessions keep their resolved version until reconnect.
   redis-cli -n 2 KEYS "poi:prompt:<prompt-name>:*"
   # Should be empty after cache bust.
   ```

4. Check prompt loader logs:
   ```bash
   # Look for prompt_resolved or prompt_cache_miss entries
   kubectl logs -l app=oia --tail=100 | grep prompt_
   ```

---

## Circuit Breaker

**Alert**: `OIA_CircuitBreakerOpen`

1. Check all breaker states:
   ```bash
   curl -s http://localhost:8120/ready | jq .dependencies
   curl -s http://localhost:8120/health/diagnostics | jq .breakers
   ```

2. Dependencies and their impact when OPEN:
   - `redis` — **critical**: session state unavailable, service not ready
   - `kafka` — audit trail stops, events queued locally
   - `backend` — Django writes fail, research briefs not persisted
   - `stt` — live transcription degrades to record-only mode
   - `tavily` — research degrades to operator-provided info only
   - `llm` — synthesis and scoring unavailable
   - `vision`/`poi` — OCR and prompt optimization degraded

3. Breakers auto-recover via half-open trial. Force a probe by sending a request through the protected path.

---

## Circuit Breaker Drill (N-03)

Run the automated drill to verify every degraded mode and recovery path:

```bash
# Unit drill (no network dependencies)
pytest tests/test_circuit_breakers.py -k "Drill or Recovery" -v

# Integration drill (requires Redis + Kafka/Redpanda)
pytest tests/test_circuit_breakers.py -k "vision_recovery_drains" -v
pytest tests/integration/test_kafka_roundtrip.py -k "replay or archive" -v
```

### Drill checklist

| Dependency | Degraded Mode | How to Induce | Drilled? | Notes |
|------------|---------------|---------------|----------|-------|
| `stt` | `RECORD_ONLY` | Force open → call `stream()` | Yes | `STTUnavailable` raised |
| `llm` | `MANUAL_CHECKBOXES` | Force open → call `generate()` | Yes | `LLMUnavailable` raised |
| `vision` | `GEMINI_ONLY_OCR` | Force open → call `analyze()` | Yes | `VisionUnavailable` raised |
| `ocr` | `GEMINI_ONLY_OCR` | Force open (vision breaker) → call `detect_text()` | Yes | `OCRUnavailable` raised; OCR drain on recovery verified |
| `backend` | `REDIS_OUTBOX` | Force open → call any write | Yes | Returns `None` (swallowed); **outbox buffering not yet implemented** |
| `poi` | `CACHED_THEN_HARDCODED` | Force open → `before_call()` | Yes | `user_message` is `null` by design |
| `gcs` | `LOCAL_DISK_SPOOL` | Force open → `before_call()` | Mechanism only | **Provider is a stub (F-02)**; `LOCAL_DISK_SPOOL` not exercisable end-to-end |
| `tavily` | `SKIP_RESEARCH` | Force open → call `search()` | Yes | `TavilyUnavailable` raised |

### DLQ replay procedure

1. Check the DLQ depth:
   ```bash
   rpk topic consume agent.dlq.onboarding-intelligence --offset end -n 0
   ```

2. Replay via admin endpoint:
   ```bash
   curl -X POST http://localhost:8120/v1/admin/dlq/replay \
     -H "X-Service-Token: $OIA_SERVICE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"batch_size": 10}'
   ```

3. Review the response: `replayed` messages go back to their original topic with the same `idempotency_key`; `archived` messages (3+ attempts) go to `agent.archive.onboarding-intelligence`.

4. Check the archive topic for poison messages:
   ```bash
   rpk topic consume agent.archive.onboarding-intelligence --offset start
   ```

---

## Event Queue Overflow

**Alert**: `OIA_EventsDropped`

The event emitter uses a bounded queue (1000 items). When full, events are dropped to protect the meeting.

1. Check current state:
   ```bash
   curl -s http://localhost:8120/metrics | grep oia_events_dropped_total
   ```

2. Root cause is usually Kafka being unreachable. Check Kafka connectivity:
   ```bash
   curl -s http://localhost:8120/ready | jq .dependencies.kafka
   ```

3. Events are also logged and recorded as span events, so the audit trail survives in logs even when Kafka drops.

---

## STT Latency

**Alert**: `OIA_STT_HighLatency`

The `oia_stt_partial_latency_ms` histogram measures the time to emit a partial transcript to the WebSocket client. A p95 above 2s degrades the live meeting experience.

1. Check current latency:
   ```bash
   curl -s http://localhost:8120/metrics | grep oia_stt_partial_latency_ms
   ```

2. Common causes:
   - GCP Speech-to-Text API throttling — check quotas in Cloud Console
   - Network latency between Cloud Run and GCP STT endpoint
   - Redis contention when writing partial results to session state

3. Check the STT breaker state:
   ```bash
   curl -s http://localhost:8120/ready | jq .dependencies.stt
   ```

4. If STT is in OPEN state, the service automatically degrades to record-only mode. Breakers auto-recover via half-open trials.

---

## Sufficiency Latency

**Alert**: `OIA_SufficiencyHighLatency`

The `oia_sufficiency_latency_ms` histogram measures sufficiency scoring time. A p95 above 5s slows live meeting feedback loops.

1. Check current latency:
   ```bash
   curl -s http://localhost:8120/metrics | grep oia_sufficiency_latency_ms
   ```

2. Common causes:
   - Gemini API latency spike — check LLM breaker state
   - Large transcript context exceeding token limits

3. Check LLM breaker:
   ```bash
   curl -s http://localhost:8120/ready | jq .dependencies
   curl -s http://localhost:8120/metrics | grep oia_circuit_breaker_state
   ```

4. If latency is sustained, consider reducing `OIA_SCOPE_THRESHOLD` to decrease evaluation frequency.

---

## Ungrounded Facts

**Alert**: `OIA_DroppedUngroundedSpike`

The `oia_dropped_ungrounded_total` counter tracks facts dropped during PROCESS extraction because they lacked source evidence.

1. Check current rate:
   ```bash
   curl -s http://localhost:8120/metrics | grep oia_dropped_ungrounded_total
   ```

2. A sustained rate above 0.5/s for 5 minutes indicates:
   - Model regression — the LLM is generating claims without grounding them in evidence
   - Evidence quality issue — uploaded documents have low OCR confidence
   - Prompt drift — check prompt versions via POI

3. Review recent PROCESS job results to identify affected sessions and inspect the evidence bundles.
