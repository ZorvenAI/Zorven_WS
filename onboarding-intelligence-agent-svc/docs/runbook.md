# OIA Operational Runbook

Service: `onboarding-intelligence-agent-svc` (port 8120)

---

## DLQ Handling

**Alert**: `OIA_DLQ_NotEmpty`

1. Check DLQ depth:
   ```bash
   curl -s http://localhost:8120/health/diagnostics | jq .dlq_depth
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
