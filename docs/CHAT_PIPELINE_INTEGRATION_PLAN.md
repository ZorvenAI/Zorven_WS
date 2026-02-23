# Integrate AI Chat with Pipeline Orchestration

## Context

The AI chat (`POST /ai/chat/`) and pipeline orchestration (`POST /api/v1/orchestration/jobs/`) are separate, disconnected systems. This integration links them so that when a user sends an analysis request in the chat, it automatically triggers a pipeline job and shows progress/results inline in the conversation.

**Before:**
- Chat uses `GeminiAIService.chat_with_brand_context()` — a keyword-matching stub returning canned responses
- Pipeline jobs are created separately via the `/dashboard/ai-assistant` page
- No connection between the two systems

**After:**
- Chat detects analysis-intent messages → creates an AnalysisJob → returns job_id in response
- Conversational messages still get normal AI responses
- Frontend chat renders pipeline progress (ThoughtTrace) and results (ResultDashboard) inline

## Files Modified

| # | File | Repo | Change |
|---|------|------|--------|
| 1 | `ai_services/services.py` | backend | Added `classify_intent()` static method to `GeminiAIService` |
| 2 | `ai_services/views.py` | backend | Added pipeline dispatch branch in `chat_with_ai()` view |
| 3 | `src/components/chat/ChatInterface.tsx` | frontend | Extended `Message` interface with `pipelineJobId`, extract from API response |
| 4 | `src/components/chat/MessageBubble.tsx` | frontend | Added `PipelineInlineCard` component with ThoughtTrace/ResultDashboard |
| 5 | `ai_services/tests/test_views.py` | backend | Added `TestChatWithAIPipelineIntegration` test class (3 tests) |

## Architecture

### Intent Classification (`classify_intent()`)

Keyword/pattern matching that scores messages as `"pipeline"` or `"conversation"`:
- **Pipeline keywords** (score +1 each): analyze, analyse, valuation, brand equity, brand valuation, iso 10668, royalty relief, brand strength, bsi, npv, market research, competitor analysis, run pipeline, run analysis, perform analysis, evaluate brand, assess brand
- **Pipeline phrases** (score +2 each): "can you analyze", "run a", "perform a", "evaluate my", "assess my", "calculate", "what is my brand worth", "how strong is my brand"
- **Threshold**: score >= 2 → pipeline intent

### Chat Response Format (Extended)

```json
{
  "session_id": "uuid",
  "response": "I've started a brand analysis pipeline...",
  "pipeline_job": {
    "job_id": "uuid",
    "status": "queued"
  },
  "session": { ... }
}
```

When no pipeline is triggered, `pipeline_job` is `null`. The `response` field always contains a string for backward compatibility.

### Frontend Inline Pipeline Card

The `PipelineInlineCard` component in `MessageBubble.tsx`:
1. Uses `usePollingJob(jobId)` to poll job status every 3 seconds
2. While `queued`/`running`: renders `ThoughtTrace` (vertical stepper with agent progress)
3. On `completed`: renders `ResultDashboard` (structured results with BrandEquityDashboard)
4. On `failed`: shows error message

### Data Flow

```
User sends "Analyze brand equity for Acme Corp" in chat
    ↓
POST /ai/chat/ { message: "..." }
    ↓
classify_intent() → { intent: "pipeline", confidence: 0.9 }
    ↓
Create AnalysisJob (status=QUEUED, input_context={source: "chat", session_id: "..."})
    ↓
dispatch_job_task.delay(job.id) → Celery → OrchestratorDispatcher → pipeline-orchestrator-svc
    ↓
Response: { response: "...", pipeline_job: { job_id: "...", status: "queued" } }
    ↓
Frontend renders PipelineInlineCard → usePollingJob polls GET /orchestration/jobs/{job_id}/
    ↓
ThoughtTrace shows progress → ResultDashboard shows final results
```

## Key Design Decisions

1. **Keyword-based intent classification** — Simple, predictable, no API cost. Can upgrade to Gemini classification later.
2. **Additive response format** — `pipeline_job` field is additive. Old clients unaffected.
3. **Reuses existing components** — `usePollingJob`, `ThoughtTrace`, `ResultDashboard` from the pipelines feature.
4. **Lazy imports** — Orchestration models/tasks imported inside the pipeline branch to avoid circular imports.
5. **Chat session linkage** — Pipeline job's `input_context` stores `{source: "chat", session_id: "..."}` for traceability.

## Verification

- **28/28 backend tests pass** (including 3 new pipeline integration tests)
- **Frontend builds with zero TypeScript errors** (25 pages compiled)
- Manual E2E: send analysis message → pipeline card appears → send conversational message → normal text response
