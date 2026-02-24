# Orchestration Kafka & Redis Integration Plan

## Context

The orchestration module currently dispatches jobs to `pipeline-orchestrator-svc` via **HTTP POST** and receives results via **HTTP PATCH callback**. The user's design document (v1.5) requires transitioning to **Kafka-based event-driven messaging** with **Redis state management** to support:

1. Kafka trigger dispatch (replacing HTTP dispatch)
2. Real-time agent trace streaming (new — "AI is thinking..." display)
3. Kafka-based result consumption (replacing HTTP callback)
4. Enhanced Redis state for UI polling (current_node, progress_percent, last_thought)
5. Chat history injection into pipeline payloads
6. Final result auto-saved as ChatMessage

The feature flag `ORCHESTRATION_KAFKA_ENABLED` gates the new Kafka path; existing HTTP flow remains as fallback.

---

## Phase 1: Settings, Topics & Feature Flag

**Files:**
- `brand_automator/settings.py` (~line 685)
- `deployment/docker-compose.yml` (backend, celery-worker, celery-beat env sections)

**Changes:**

1. Add to `settings.py` after the `KAFKA_SASL_CONFIG` block:
```python
# Orchestration Kafka Integration
ORCHESTRATION_KAFKA_ENABLED = config("ORCHESTRATION_KAFKA_ENABLED", default=False, cast=bool)
KAFKA_TOPIC_PIPELINE_TRIGGER = "pipeline-trigger-topic"
KAFKA_TOPIC_AGENT_TRACE = "agent-trace-topic"
KAFKA_TOPIC_PIPELINE_RESULT = "pipeline-result-topic"
KAFKA_TOPIC_ORCHESTRATION_DLQ = "orchestration-dlq"
ORCHESTRATION_KAFKA_GROUP_ID = "orchestration-result-consumers"
```

2. Add Celery beat schedules gated on the flag (after `KAFKA_CONSUMERS_ENABLED` block ~line 880):
```python
if ORCHESTRATION_KAFKA_ENABLED:
    CELERY_BEAT_SCHEDULE.update({
        "consume-pipeline-results-every-10s": {
            "task": "orchestration.tasks.consume_pipeline_results",
            "schedule": 10.0,
        },
        "consume-agent-traces-every-5s": {
            "task": "orchestration.tasks.consume_agent_traces",
            "schedule": 5.0,
        },
    })
```

3. Add `ORCHESTRATION_KAFKA_ENABLED=${ORCHESTRATION_KAFKA_ENABLED:-false}` to backend, celery-worker, and celery-beat services in `deployment/docker-compose.yml`.

**Verification:** `python manage.py shell -c "from django.conf import settings; print(settings.ORCHESTRATION_KAFKA_ENABLED)"`

---

## Phase 2: Shared Result Handler (Extract from Views)

Extract the callback logic from `orchestration/views.py:130-208` into a reusable function so both HTTP callback and Kafka consumer can use it.

**New file:** `orchestration/result_handler.py`

**Function:** `handle_pipeline_result(job_id, status, progress, result_data, error_message, resolved_manifest_id) -> bool`

- Atomic `select_for_update()` row lock (same as current callback)
- Updates job fields (progress, status, result_data, error_message, manifest)
- Caches in Redis (`job:status:{job_id}`)
- On COMPLETED: calls `_save_final_chat_message(job)` — creates an assistant `ChatMessage` with the result summary in the originating `ChatSession` (looked up via `input_context["session_id"]`)

**Modified file:** `orchestration/views.py`

- Refactor `callback()` to delegate to `handle_pipeline_result()` (keeps token auth in the view, delegates logic to handler)
- Keeps HTTP callback endpoint fully functional as fallback

**Reuse:**
- Row-locking pattern from current `views.py:130-191`
- Redis caching pattern from current `views.py:193-208`

---

## Phase 3: Chat History Injection

**Modified file:** `ai_services/views.py` (~line 250)

In `_process_chat_message()`, before creating the `AnalysisJob`, fetch recent chat history:

```python
history_msgs = ChatMessage.objects.filter(session=session).order_by("-created_at")[:10]
chat_history = [{"role": m.role, "content": m.content} for m in reversed(history_msgs)]
job_context["chat_history"] = chat_history
```

**Modified file:** `orchestration/services.py` (`_build_payload()` ~line 163)

Pass `chat_history` through in the dispatch payload. The orchestrator receives it inside `input_context` and can use it for context-aware AI reasoning.

---

## Phase 4: Kafka Trigger Producer

**New file:** `orchestration/kafka_producer.py`

**Class:** `KafkaTriggerProducer` with a `dispatch(job) -> bool` method that:

1. Reuses `OrchestratorDispatcher._build_payload(job)` to build the same payload
2. Publishes to `pipeline-trigger-topic` via `KafkaProducerService.send()` (from `kafka_service/consumer.py:391`)
3. On success: sets `job.status = RUNNING`, `job.started_at = now()`
4. On failure: returns False (Celery retry handles it)
5. Uses `tenant_id` as Kafka message key for partitioning

**Modified file:** `orchestration/tasks.py`

Modify `dispatch_job_task` to branch:
```python
if settings.ORCHESTRATION_KAFKA_ENABLED:
    dispatcher = KafkaTriggerProducer()
else:
    dispatcher = OrchestratorDispatcher()  # existing HTTP flow
success = dispatcher.dispatch(job)
```

Both paths share the same retry/failure handling.

---

## Phase 5: Kafka Consumers (Results + Traces)

**New file:** `orchestration/kafka_consumers.py`

### ResultConsumer
- Consumes from `pipeline-result-topic`
- Deserializes JSON payload
- Calls `handle_pipeline_result()` from Phase 2
- Payload schema: `{job_id, session_id, status, final_response, result_data, sources}`

### TraceConsumer
- Consumes from `agent-trace-topic`
- Updates Redis hash `job:status:{job_id}` with:
  - `current_node`, `progress_percent`, `last_thought`
  - Updated `progress` dict with per-agent status
- Maps orchestrator statuses (`started/completed/failed`) to frontend statuses (`running/done/failed`)
- Does NOT update DB on every trace event (Redis-only for performance)

**Modified file:** `orchestration/tasks.py`

Add two new Celery tasks:
```python
@shared_task
def consume_pipeline_results(max_messages=50, timeout=5.0):
    ResultConsumer().consume(max_messages, timeout)

@shared_task
def consume_agent_traces(max_messages=100, timeout=2.0):
    TraceConsumer().consume(max_messages, timeout)
```

These follow the exact pattern from `kafka_service/tasks.py:consume_gateway_logs`.

---

## Phase 6: Redis State Enhancements

**Modified file:** `orchestration/views.py` — Enhance `quick_status` response

Add `current_node`, `progress_percent`, `last_thought` fields to the response (both from cache and DB fallback). Add a `_calc_percent(progress)` static helper.

**Modified file:** `ai_services/views.py` — Enhance session lock for pipeline jobs

After pipeline intent is detected and job is created, extend the lock TTL:
```python
cache.set(f"lock:chat:session:{session.session_id}", str(job.job_id), timeout=300)
```
This changes the lock from 30s (normal chat) to 5 minutes (pipeline jobs), matching the design doc's `lock:chat:session:{session_id}` pattern.

---

## Phase 7: Frontend — Quick-Status Polling & Trace Display

**Modified file:** `src/types/orchestration.ts`

Add `QuickStatus` interface:
```typescript
export interface QuickStatus {
  status: JobStatus;
  progress: Record<string, AgentProgress>;
  current_node: string | null;
  progress_percent: number;
  last_thought: string | null;
  result_data?: Record<string, unknown>;
  manifest_name?: string | null;
  error_message?: string;
}
```

**Modified file:** `src/lib/orchestration.ts`

Add `getJobQuickStatus(jobId)` — calls `GET /orchestration/jobs/{jobId}/quick-status/`

**Modified file:** `src/hooks/usePollingJob.ts`

Switch to `getJobQuickStatus()` for in-flight jobs (lighter weight than full `getJob()`). On terminal state, fetch full job for complete `result_data`.

**Modified file:** `src/components/pipelines/ThoughtTrace.tsx`

Add `last_thought` display below the active node — shows slate-gray italic text like "Searching SEC filings for NVIDIA..." beneath the running step.

---

## Phase 8: Tests

### New test files:
- `orchestration/tests/test_result_handler.py` — 8 tests: status transitions, Redis caching, ChatMessage creation, row locking, missing job
- `orchestration/tests/test_kafka_producer.py` — 5 tests: payload schema, job status update, Kafka error handling, tenant key
- `orchestration/tests/test_kafka_consumers.py` — 6 tests: result consumer delegates to handler, trace consumer updates Redis, status mapping, missing fields

### Modified test files:
- `orchestration/tests/test_tasks.py` — Add tests for Kafka vs HTTP dispatch branching
- `orchestration/tests/test_views.py` — Update callback tests to verify delegated behavior
- `ai_services/tests/test_views.py` — Test chat history injection in pipeline job context

---

## Files Summary

| File | Action | Phase |
|------|--------|-------|
| `brand_automator/settings.py` | Modify — add topics, flag, beat schedules | 1 |
| `deployment/docker-compose.yml` | Modify — add env vars | 1 |
| `orchestration/result_handler.py` | **New** — shared result processing | 2 |
| `orchestration/views.py` | Modify — refactor callback, enhance quick_status | 2, 6 |
| `ai_services/views.py` | Modify — inject chat history, extend lock TTL | 3, 6 |
| `orchestration/services.py` | Modify — pass chat_history in payload | 3 |
| `orchestration/kafka_producer.py` | **New** — Kafka trigger publisher | 4 |
| `orchestration/tasks.py` | Modify — Kafka dispatch branch, consumer tasks | 4, 5 |
| `orchestration/kafka_consumers.py` | **New** — result + trace consumers | 5 |
| `src/types/orchestration.ts` | Modify — add QuickStatus type | 7 |
| `src/lib/orchestration.ts` | Modify — add getJobQuickStatus | 7 |
| `src/hooks/usePollingJob.ts` | Modify — use quick-status endpoint | 7 |
| `src/components/pipelines/ThoughtTrace.tsx` | Modify — add last_thought display | 7 |
| `orchestration/tests/test_result_handler.py` | **New** | 8 |
| `orchestration/tests/test_kafka_producer.py` | **New** | 8 |
| `orchestration/tests/test_kafka_consumers.py` | **New** | 8 |
| `orchestration/tests/test_tasks.py` | Modify | 8 |
| `ai_services/tests/test_views.py` | Modify | 8 |

---

## Key Design Decisions

1. **Feature flag pattern**: `ORCHESTRATION_KAFKA_ENABLED` follows the proven `ONBOARDING_KAFKA_ENABLED` pattern. HTTP fallback is always available.

2. **Reuse `KafkaProducerService`** (from `kafka_service/consumer.py:363-430`) — simpler than `KafkaProducerAdapter` and doesn't require domain models.

3. **No WebSocket for traces**: The design doc mentions WebSocket for `agent-trace-topic`. Instead, traces write to Redis and the frontend polls `quick-status` every 3s — delivering near-real-time trace display without new WebSocket infrastructure. WebSocket can be added later as a performance optimization.

4. **Dual delivery tolerance**: Both HTTP callback and Kafka result consumer may fire. `handle_pipeline_result()` uses `select_for_update()` row lock and idempotent status transitions, preventing double-processing.

5. **Chat history in `input_context`**: Rather than adding a separate field, chat_history is nested in the existing `input_context` JSONField. The orchestrator accesses it as `state["input_context"]["chat_history"]`.

6. **Final ChatMessage auto-creation**: When a pipeline completes, the result handler creates an assistant ChatMessage with the summary, so users see the result in their chat history without relying solely on the inline card.

---

## Verification (End-to-End)

```bash
# 1. Run backend tests
cd ai-brand-automator
python -m pytest orchestration/tests/ -v
python -m pytest ai_services/tests/ -v

# 2. Frontend build
cd ai-brand-automator-frontend
npm run build

# 3. Test with Kafka disabled (HTTP fallback — existing behavior)
ORCHESTRATION_KAFKA_ENABLED=false python manage.py shell
# Send a chat message, verify pipeline dispatch works via HTTP

# 4. Test with Kafka enabled
ORCHESTRATION_KAFKA_ENABLED=true docker compose --profile with-kafka up
# Send a chat message, verify:
#   - Trigger published to pipeline-trigger-topic
#   - Traces appear in Redis (check job:status:{job_id})
#   - Result consumed and AnalysisJob updated
#   - Final ChatMessage created in session
#   - Frontend shows last_thought in ThoughtTrace
```
