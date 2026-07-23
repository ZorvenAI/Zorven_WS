# prompt-optimization-svc

Centralized prompt management and optimization platform for all 15 Zorven AI agent services. Stores every system prompt as a versioned MLflow artifact, automatically improves them over time using GEPA, and safely deploys improved prompts through mandatory canary deployments.

**Port:** 8110 | **Env Prefix:** `POI_` | **Redis:** DB 2 (prompt cache), DB 26 (general)

## What This Service Does

### The Problem

Without this service, every agent has a static, hand-written prompt that never improves. The prompt you wrote on day 1 is the same prompt running 6 months later, regardless of how well it actually performs.

### The Solution

The service provides two core capabilities:

**1. Prompt Registry** — All 39+ system prompts across 15 agents live in MLflow as versioned, trackable artifacts with a full lifecycle state machine (DRAFT → STAGING → CANARY → PRODUCTION → ARCHIVED). Only one version per prompt can be PRODUCTION at any time.

**2. Prompt Optimization** — GEPA (Guided Evolutionary Prompt Architecture) automatically improves prompts using a reflection-based LLM loop, with mandatory validation gates and safe canary deployments.

### The Value

- **Prompts evolve** — GEPA analyzes where prompts are weak (using 32 custom scorers) and generates improved versions
- **Safety net** — No prompt goes live without proving it's at least 5% better (OPT-03), and any individual skill regression >3% gets flagged for human review (OPT-04)
- **Canary deployment** — New prompts serve only 10% of traffic for 24 hours before full rollout, with auto-rollback on regression
- **Tenant customization** — Different tenants can have different prompts (e.g., a luxury brand vs. a tech startup)
- **Zero-downtime** — Agents always have a hardcoded fallback prompt, so even if MLflow and Redis both go down, the system keeps working
- **Self-improving** — Better prompts → better agent outputs → better golden examples → even better prompts

---

## How It Works

### The Role of MLflow

MLflow serves as the **version-controlled prompt database** — think of it as "Git for prompts":

| Capability | How MLflow Is Used |
|---|---|
| **Version tracking** | Every prompt has versions (v1, v2, v3...) with full history |
| **State machine** | Each version has a lifecycle state: DRAFT → STAGING → CANARY → PRODUCTION |
| **Metadata** | Each version stores: who optimized it, when, what scores it got, which agent it belongs to |
| **Experiment tracking** | Every GEPA optimization run is logged as an MLflow experiment with traces, scores, and artifacts |
| **Rollback** | If a prompt causes issues, roll back to the previous PRODUCTION version instantly |

### The Role of GEPA

GEPA is the **optimization engine** — an LLM-based prompt improver built into MLflow. It modifies the system prompt text (rewording instructions, adding constraints, restructuring sections) to make agent outputs better.

#### The Optimization Loop

```
1. Load golden dataset (real examples of good agent outputs)
   ↓
2. Split: 80% training / 20% held-out validation
   ↓
3. GEPA Reflection Loop (Claude Sonnet 4.6):
   ┌──────────────────────────────────────────┐
   │  a. Run current prompt on training data   │
   │  b. Score outputs with 32 custom scorers  │
   │  c. Reflection model analyzes failures:   │
   │     "JSON compliance is 0.6 — the prompt  │
   │      doesn't enforce schema strictly"     │
   │  d. Generate mutated prompt candidates    │
   │  e. Evaluate mutations against scorers    │
   │  f. Keep best candidates (Pareto frontier)│
   │  g. Repeat until budget exhausted         │
   └──────────────────────────────────────────┘
   ↓
4. Best candidate evaluated on held-out 20%
   ↓
5. Validation gates:
   - Must be ≥5% better overall (OPT-03)
   - No individual scorer can regress >3% (OPT-04)
   ↓
6. If passes → Canary deployment (10% traffic, 24 hours)
   If fails → REJECTED
   If regression detected → PENDING_APPROVAL (human review)
```

### Seed Prompts → Optimization → Better Prompts

```
Day 1:  Hand-written seed prompts → v1 PRODUCTION
        ↓
Week 1: Agents run in production, golden examples accumulate
        (high-quality outputs mined as training data, score > 0.8)
        ↓
Week 2: First GEPA optimization cycle runs
        - Generates improved candidate (v2)
        - Validated against held-out set
        - If passes → v2 goes to CANARY (10% traffic)
        ↓
Week 2+1d: Canary passes → v2 promoted to PRODUCTION
           v1 moved to ARCHIVED
        ↓
Week 4: Next cycle generates v3 from v2
        (each cycle builds on the current PRODUCTION prompt)
        ↓
Month 3: Prompts significantly better than seed versions
```

### How Both Flows (Workspace + Chat) Use Prompts

Both the **Workflow Workspace** and the **Chat Interface** execute through the same pipeline, and both use prompts from this service.

#### Flow 1: Workflow Workspace (Manifest-Driven)

```
User clicks "Run" in Workspace UI
  → Django creates AnalysisJob → dispatches to Orchestrator
  → Orchestrator reads manifest (fixed DAG) → executes nodes sequentially
  → Each agent (e.g., market-research-svc) loads its prompt:
      AgentPromptClient.load("zorven-wf1-mra-skill-synthesis")
        ├─ Tier 1: Redis cache (DB 2)     → sub-ms
        ├─ Tier 2: MLflow API             → ~50ms
        └─ Tier 3: Hardcoded fallback     → 0ms
  → Agent calls Claude/Gemini with loaded prompt → returns result
```

#### Flow 2: Chat Interface (Auto-Detect)

```
User types: "Analyze the luxury watch market in Europe"
  → Django creates AnalysisJob → dispatches to Orchestrator
  → No manifest → PipelineComposer auto-detects workflow:
      Tier 1: Keyword match → "market" → WF1 pipeline (deterministic)
      Tier 2: Gemini dynamic composition (if Tier 1 fails)
  → Same execution from here → identical prompt loading
```

**The key point:** Once the orchestrator picks the nodes, both flows are identical. Every agent loads its prompt through the same three-tier chain, regardless of whether the pipeline was triggered from Workspace or Chat.

#### Complete Architecture Diagram

```
                    ┌─────────────────┐
                    │  prompt-optim   │
                    │  -ization-svc   │
                    │  (MLflow + GEPA)│
                    │                 │
                    │  Stores all     │
                    │  PRODUCTION     │
                    │  prompts        │
                    └────────┬────────┘
                             │
                    GET /v1/prompts/{name}/production
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──┐  ┌───────▼────┐  ┌──────▼─────┐
    │ MRA :8021  │  │ BPA :8031  │  │ CGA :8042  │  ... 15 agents
    │            │  │            │  │            │
    │ Redis→MLflow→Fallback     │  │            │
    └─────────▲──┘  └───────▲────┘  └──────▲─────┘
              │              │              │
              │    HTTP POST /v1/execute    │
              │              │              │
         ┌────┴──────────────┴──────────────┴────┐
         │        pipeline-orchestrator-svc       │
         │                                        │
         │  Workspace: manifest-driven execution  │
         │  Chat: PipelineComposer auto-detect    │
         └────────────────▲───────────────────────┘
                          │
                   POST /v1/jobs/dispatch
                          │
                ┌─────────┴──────────┐
                │  Django Backend    │
                │  (dispatches jobs) │
                └─────────▲──────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
    ┌─────────┴──────┐    ┌──────────┴─────────┐
    │  Workspace UI  │    │   Chat Interface   │
    │  (React Flow)  │    │   (auto-detect)    │
    └────────────────┘    └────────────────────┘
```

---

## Guardrails (OPT-01 through OPT-12)

| Guardrail | Rule | Enforced In |
|-----------|------|-------------|
| OPT-01 | Minimum 3 golden examples | `guardrails.py` |
| OPT-02 | $25/agent cost cap | `guardrails.py` |
| OPT-03 | ≥5% aggregate improvement | `candidate_validator.py` |
| OPT-04 | >3% scorer regression → human review | `candidate_validator.py` |
| OPT-05 | Human approval for critical agents (adpub, coa) | `approval_gate.py` |
| OPT-06 | Prompt length < 3× original | `guardrails.py` |
| OPT-07 | Distributed optimization lock | `prompt_cache.py` |
| OPT-08 | 30-day version retention | MLflow version history |
| OPT-09 | 12-pattern prompt injection scan | `guardrails.py` |
| OPT-10 | Tenant data isolation | `guardrails.py` |
| OPT-11 | Template placeholder invariance | `gepa_guardrails.py` |
| OPT-12 | Schema preamble protection | `preamble_validator.py` |

---

## Celery Beat Schedule

| Task | Schedule | Purpose |
|------|----------|---------|
| `mine-golden-examples-weekly` | Saturday 07:00 UTC | Mine quality examples from production |
| `optimize-wf1-pipeline-monthly` | 2nd Sunday 06:00 UTC | WF1 agents (MRA, CIA, APA, TCIA, VoCA) |
| `optimize-wf2-pipeline-monthly` | 3rd Sunday 06:00 UTC | WF2 agents (BPA, BAA, BPV, NTA, BSA) |
| `optimize-wf3-creative-pipeline` | Sunday 06:00 UTC | WF3 creative agents (CAA, CGA, ADPUB) |
| `optimize-wf3-optimization-loop` | Sunday 06:30 UTC | WF3 optimization agents (COA, ILA) |
| `prompt-health-check-daily` | Daily 10:00 UTC | Score PRODUCTION prompts, auto-rollback on >15% regression |
| `canary-health-check` | Every 15 min | Monitor active canaries, auto-promote/rollback |

---

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8110 --reload
```

## Testing

```bash
pytest tests/ -v                      # All tests
pytest tests/ -m "not integration" -v # Unit only (no Redis/Kafka)
pytest tests/ -m e2e -v               # E2E tests

# Format
black app/ tests/
```

## Health Check

```bash
curl http://localhost:8110/health
```

Returns dependency status for MLflow, Redis, Kafka, and PostgreSQL.

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POI_MLFLOW_TRACKING_URI` | `http://mlflow-server:5000` | MLflow server |
| `POI_DATABASE_URL` | `postgresql://...` | Shared MLflow PostgreSQL |
| `POI_PROMPT_CACHE_REDIS_URL` | `redis://localhost:6379/2` | Prompt cache (DB 2) |
| `POI_REDIS_URL` | `redis://localhost:6379/26` | General cache + Celery broker |
| `POI_KAFKA_BOOTSTRAP_SERVERS` | `""` (disabled) | Kafka for lifecycle events |
| `POI_ANTHROPIC_API_KEY` | `""` | Required for GEPA optimization |
| `POI_GEPA_MODEL_NAME` | `claude-sonnet-4-6` | GEPA reflection model |
| `POI_CRITICAL_AGENTS` | `adpub,coa` | Require human approval |

See the [Operational Runbook](docs/operational_runbook.md) for the full list of 26 variables.

## Database Migrations

```bash
alembic upgrade head           # Apply all (also runs on startup)
alembic downgrade -1           # Rollback last
alembic current                # Show current revision
```

## Documentation

- [Operational Runbook](docs/operational_runbook.md) — Incident response, recovery procedures, operational reference
- [CLAUDE.md](CLAUDE.md) — Development guide for Claude Code
- [Audit Report](../docs/Optimize_prompts/prompt_optimization_svc_audit_report_2026_07_21.md) — Production readiness audit
