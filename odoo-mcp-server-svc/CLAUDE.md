# CLAUDE.md

This file provides guidance to Claude Code when working with this service.

## What This Service Does

`odoo-mcp-server-svc` is a FastAPI microservice (port 8095) that bridges AI agents and Odoo ERP by exposing all Odoo module APIs as 100+ MCP tools. Supports multi-tenancy (3 models), hierarchical RBAC (17 roles), and RAG integration via the rag-uploader-agent-service.

## Build & Run Commands

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8095 --reload

# Tests
pytest tests/ -v
pytest tests/ -m "not integration" -v

# Format
black app/ tests/
```

## Architecture

- `app/api/` — Routes (GET /health, POST /execute, POST /mcp, GET /mcp/sse) + Pydantic schemas
- `app/core/` — Config (ODOO_MCP_ prefix), logging
- `app/cache/` — RedisManager (schema cache, session cache, RBAC cache, rate limiting)
- `app/mcp/` — MCP server (tools/resources/prompts), transport (Streamable HTTP, SSE)
- `app/tools/` — Tool registry, base tool, dispatcher + 13 domain tool modules (101 tools total)
- `app/services/` — OdooRPCClient (XML-RPC), TenantConnectionPool, error hierarchy
- `app/tenancy/` — TenantConfig, TenantResolver, TenantRegistry, middleware
- `app/rbac/` — PolicyEvaluator, RBACEngine (enforcing/permissive/disabled), YAML role loader
- `app/rag/` — RAGClient, RAGContextMiddleware, OdooRAGSync
- `app/messaging/` — Kafka producer (audit, tenant events), consumer (provisioning)
- `app/observability/` — Metrics collector, structured audit logger

## Key Contracts

**POST /execute** — Receives X-Tenant-ID header from orchestrator
```json
Request:  { input_prompt, input_context, tenant_context, config, previous_outputs }
Response: { status, findings, recommendations, data, error }
```
Skill context extracted via `config.get("skill_context", "")` (same as content-agent).

**POST /mcp** — MCP Streamable HTTP transport (JSON-RPC)
**GET /mcp/sse** — MCP SSE transport

## Environment Variables

All prefixed with `ODOO_MCP_`:
- `ODOO_URL` — Odoo server URL (default http://localhost:8069)
- `ODOO_MASTER_PASSWORD` — Odoo admin password
- `REDIS_URL` — default redis://localhost:6379/9
- `MCP_TRANSPORT` — streamable-http | sse
- `TENANT_MODEL` — dedicated_db | shared_instance | shared_db
- `RBAC_ENFORCEMENT` — enforcing | permissive | disabled
- `RBAC_ROLES_DIR` — default config/roles
- `RAG_SERVICE_URL` — default http://localhost:8070
- `RAG_ENABLED` — default false
- `KAFKA_BOOTSTRAP_SERVERS` — empty = Kafka disabled
- `SERVICE_TOKEN` — default dev-service-token
- `PORT` — default 8095

## Redis Key Patterns (DB 9)

- `odoo_mcp:schema:{tenant_id}:{model}` — 1h TTL
- `odoo_mcp:session:{tenant_id}` — 30m TTL
- `odoo_mcp:rbac:{tenant_id}:{role}` — 5m TTL
- `odoo_mcp:rate:{tenant_id}` — 60s TTL
- `odoo_mcp:result:{md5}` — 4h TTL

## MCP Tool Domains

| Domain | Tools | Primary Models |
|--------|-------|----------------|
| generic | 8 | Any model (ORM operations) |
| crm | 10 | crm.lead |
| sales | 10 | sale.order |
| accounting | 10 | account.move |
| inventory | 11 | stock.picking, purchase.order |
| manufacturing | 8 | mrp.production, mrp.bom |
| hr | 11 | hr.employee, hr.leave |
| project | 4 | project.task |
| website | 3 | website.page |
| marketing | 3 | mailing.mailing |
| comms | 3 | mail.message, calendar.event |
| admin | 12 | res.users, ir.module.module |
| rag | 8 | RAG knowledge store |

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `odoo-mcp-audit-topic` | Produce | Tool call audit trail |
| `odoo-tenant-events-topic` | Produce | Tenant lifecycle events |
| `tenant-provisioning-topic` | Consume | New tenant provisioning |

## Skills

26 Odoo-specific skills are centralized in `pipeline-orchestrator-svc/skills/odoo-*.md`. The orchestrator's SkillRouter injects matching skills as `skill_context` in the `config` dict.
