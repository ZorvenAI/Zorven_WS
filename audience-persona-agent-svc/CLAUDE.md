# CLAUDE.md — audience-persona-agent-svc

## Overview

**Audience Persona Agent (APA)** — Agent 1.3 in Workflow 1: Brand Discovery & Research. Follows MRA (1.1) and CIA (1.2). Researches, constructs, and maintains data-grounded buyer personas with demographics, psychographics, behavioral patterns, motivations, objections, preferred channels, and buying journey maps. Integrates Odoo CRM customer data and survey responses as first-party data sources.

- **Port**: 8023
- **Redis DB**: 13
- **Env prefix**: `APA_`
- **LLM**: Claude Sonnet 4
- **Kafka audit topic**: `audience-persona-audit-topic`
- **Kafka command topic**: `agent.commands.audience-persona-agent`

## Build & Test

```bash
# Install
pip install -r requirements.txt

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8023 --reload

# Test
pytest tests/ -v                        # All 162 tests
pytest tests/ -m "not integration" -v   # Unit only (skip Redis-dependent)
pytest tests/test_skills/ -v            # Skills only
pytest tests/test_skills/test_persona_synthesizer.py -v  # Single file
pytest -k "test_meta" -v                # By name pattern

# Format
black app/ tests/
```

## Architecture

### PAOR Engine Flow

```
IDLE → L1 INPUT GUARDRAILS → PLANNING (Claude decomposes)
  → RESEARCHING: Phase 1 parallel (SKL-APA-01..06 + 05b + 05c)
  → PROFILING: SKL-APA-07 → SKL-APA-08
  → SYNTHESIZING: SKL-APA-09
  → MAPPING: SKL-APA-10
  → L3 OUTPUT GUARDRAILS → PERSISTING: SKL-APA-11 → COMPLETED
```

### Two-Layer Skill Architecture

- **Layer 1**: Orchestrator `.md` skills in `pipeline-orchestrator-svc/skills/` (3 files)
- **Layer 2**: 14 executable Python skills in `app/skills/` (SKL-APA-01..12 + 05b + 05c)

### Skill Registry (14 skills)

| ID | File | Description | CB | Roles |
|----|------|-------------|-----|-------|
| SKL-APA-01 | `audience_landscape_research.py` | Tavily audience demographics search | tavily | all |
| SKL-APA-02 | `forum_community_miner.py` | Forum/Reddit/Quora community mining | tavily | all |
| SKL-APA-03 | `social_listening_analyzer.py` | Social media behavior analysis | tavily | all |
| SKL-APA-04 | `buyer_role_extractor.py` | B2B buying committee role extraction | tavily | all |
| SKL-APA-05 | `review_needs_miner.py` | G2/Capterra review mining | tavily | all |
| SKL-APA-05b | `odoo_survey_data_extractor.py` | Odoo survey response extraction | odoo_survey | O/A/E |
| SKL-APA-05c | `odoo_crm_customer_extractor.py` | Odoo CRM customer segmentation | odoo_crm | O/A/E |
| SKL-APA-06 | `rag_context_retrieval.py` | Prior persona analyses from RAG | rag_store | all |
| SKL-APA-07 | `demographic_profile_builder.py` | Claude demographic profiling | llm | O/A/E |
| SKL-APA-08 | `psychographic_behavioral_profiler.py` | Claude psychographic profiling | llm | O/A/E |
| SKL-APA-09 | `persona_synthesizer.py` | Claude persona synthesis + differentiation | llm | O/A/E |
| SKL-APA-10 | `buying_journey_mapper.py` | Claude buying journey mapping | llm | O/A/E |
| SKL-APA-11 | `persona_report_persister.py` | GCS + RAG + Registry persistence | gcs | O/A |
| SKL-APA-12 | `human_escalation.py` | Kafka human review escalation | kafka | all |

**CB** = Circuit Breaker dependency. **Roles**: O=OWNER, A=ADMIN, E=EDITOR. Odoo skills only registered when `APA_ODOO_ENABLED=true`.

### API Endpoints

- `GET /health` — No auth
- `POST /v1/execute` — Orchestrator dispatch (X-Service-Token)
- `POST /v1/personas` — Alias endpoint (X-Service-Token)

### Upstream Data (when in combined pipeline)

| Source | Key | Used By |
|--------|-----|---------|
| MRA | `previous_outputs["market_research"]` | SKL-APA-01, 07, 10 |
| CIA | `previous_outputs["competitor_intelligence"]` | SKL-APA-05, 08, 09, 10 |
| Odoo CRM | SKL-APA-05c (XML-RPC) | SKL-APA-07, 09 |
| Odoo Survey | SKL-APA-05b (XML-RPC) | SKL-APA-07, 08 |

### Circuit Breakers (8)

tavily, httpx, odoo_survey, odoo_crm, llm, rag_store, gcs, kafka

### Redis Keys (prefix: `apa`, DB 13)

- `apa:result:{md5}` — 4h TTL
- `apa:rate:{tenant_id}` — 60s TTL
- `apa:{tid}:odoo:survey_cache:{id}` — 1h TTL
- `apa:{tid}:odoo:crm_segments` — 1h TTL
- `apa:{tid}:registry:personas` — persistent Hash
- `apa:{tid}:registry:version:{slug}:{ver}` — 180d TTL
- `apa:{tid}:idempotency:{key}` — 24h TTL

### Persona Registry

Redis Hash-based registry at `app/registry/persona_registry.py`:
- CRUD: `upsert_persona()`, `get_persona()`, `get_all_personas()`, `delete_persona()`
- Evolution detection: compares profile fields on update, emits `PERSONA_EVOLUTION_DETECTED`
- Version snapshots: `apa:{tid}:registry:version:{slug}:{ver}` with 180d TTL
- Models: `PersonaRegistryEntry`, `PersonaEvolution` in `app/registry/models.py`

### Kafka Consumer

`app/messaging/kafka_consumer.py` — `ScheduledScanConsumer` consumes from `agent.commands.audience-persona-agent`:
- Supports `scan_type`: `full` (re-research) or `incremental` (update existing)
- Idempotency via Redis key
- Command schema: `app/messaging/command_schemas.py`

## Guardrails

### Three-Layer System (`app/logic/guardrails.py`)

**Layer 1 — Input (9 rules)**: IG-01 injection, IG-02 scam, IG-03 scope, IG-04 PII redaction, IG-05 tenant, IG-06 size, IG-07 rate limit, IG-08 bias, IG-09 COPPA

**Layer 2 — Plan+Tool (9 rules)**: PG-01 planning, PG-02 allowlist, PG-03 write perms, PG-04 concurrency, PG-05 RBAC, PG-06 irreversible logging, PG-07 token budget, PG-08 persona cap, PG-09 robots.txt

**Layer 3 — Output (8 rules)**: OG-01 grounding, OG-02 PII scrub, OG-03 uncertainty, OG-04 hallucination clamp, OG-05 tenant isolation, OG-06 size limit, OG-07 anti-stereotyping (keyword + LLM judge), OG-08 age-appropriate

### APA-Specific Rules

- **IG-08**: Demographic Bias Detector — blocks stereotyping of protected groups
- **IG-09**: Minor Protection Filter — blocks targeting under-13 (COPPA)
- **OG-07**: Anti-Stereotyping Guard — keyword scan + optional LLM judge (score > 0.3)
- **OG-08**: Age-Appropriate Content Check — flags 13-17 targeting for ADMIN review
- **PG-08**: Persona count cap (default 5, max 8)
- **PG-09**: Forum scraping ethics — `check_robots_txt()` validates scraping permission

## Key Patterns

- Never use fictional human names for personas — use descriptive segment labels
- CRM-first naming when `has_sufficient_data=true` (10+ customers from SKL-APA-05c)
- `data_source` field: `crm_grounded` vs `research_based`
- Odoo integration gated by `APA_ODOO_ENABLED=false`
- All operations fail-open on Redis/Kafka errors
- LLM skills use `_parse_json_response()` and `_count_tokens()` local helpers
- Stub mode: returns minimal persona when Anthropic client is None

## Adding a New Skill

1. Create `app/skills/your_skill.py` extending `BaseSkill`:
   ```python
   from app.skills.base import BaseSkill
   from app.skills.models import SkillContext, SkillMeta, SkillResult

   class YourSkill(BaseSkill):
       meta = SkillMeta(
           skill_id="SKL-APA-XX",
           name="your_skill",
           description="...",
           allowed_roles=["OWNER", "ADMIN", "EDITOR"],
           timeout_ms=30000,
           circuit_breaker_dependency="llm",  # or tavily, httpx, etc.
       )

       async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
           # Implementation
           return SkillResult(skill_id=self.meta.skill_id, success=True, data={...})
   ```

2. Register in `app/main.py` lifespan:
   ```python
   from app.skills.your_skill import YourSkill
   skill_registry.register(YourSkill(...))
   ```

3. Add to `_VALID_SKILL_IDS` in `app/logic/guardrails.py`

4. Add to `app/rbac/engine.py` permission matrix

5. Add test in `tests/test_skills/test_your_skill.py`

## File Structure

```
app/
├── api/            # Routes, schemas, middleware
├── cache/          # RedisManager (apa:* keys)
├── circuit_breaker/# CircuitBreaker implementation
├── core/           # Config (APA_ env prefix)
├── events/         # EventEmitter + EventType catalog
├── logic/          # PersonaAnalyzer (PAOR), ThreeLayerGuardrails
├── messaging/      # KafkaProducer, ScheduledScanConsumer, command schemas
├── rbac/           # RBACEngine + permission matrix
├── registry/       # PersonaRegistry (Redis Hash) + Pydantic models
├── services/       # Executor, TavilySearchClient, WebScraperClient, OdooRPCClient
├── skills/         # 14 skill implementations + BaseSkill + SkillRegistry
└── main.py         # FastAPI app + lifespan (skill registration)

tests/
├── conftest.py          # Shared fixtures (mock Anthropic/Tavily/Odoo/Redis/Registry)
├── integration/         # Full pipeline + registry lifecycle tests
├── test_messaging/      # Kafka consumer + command schema tests
├── test_registry/       # PersonaRegistry CRUD + evolution tests
├── test_services/       # OdooRPCClient tests
└── test_skills/         # 14 skill unit tests
```
