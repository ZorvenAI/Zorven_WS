# Implementation Plan: Odoo Community Integration & MCP Server

## Context

This plan implements two major features from `docs/Odoo_MCP_Server_Design_Document_v2_0.docx`:
1. **Git Submodule Integration**: Add Odoo Community Edition 19.0 as a submodule at `vendor/odoo/community/`
2. **Odoo MCP Server**: Build `odoo-mcp-server-svc`, a FastAPI microservice exposing all Odoo module APIs as 100+ MCP tools with multi-tenancy, RBAC, and RAG integration. 26 Odoo-specific skills are added to the **centralized skill store** in `pipeline-orchestrator-svc/skills/` (not in the new service).

The MCP server bridges AI agents and Odoo ERP, translating tool invocations into Odoo XML-RPC/JSON-RPC calls. It supports tenant-scoped databases, hierarchical RBAC, and integrates with the existing RAG uploader service.

## Key Deviations from Design Document

| Design Doc | Actual | Reason |
|------------|--------|--------|
| Port 8090 | **Port 8095** | 8090 taken by brand-equity-calculator-svc |
| Redis DB 8 | **Redis DB 9** | DB 8 taken by brand-equity-calculator-svc |
| `src/` directory | **`app/` directory** | All 8 existing microservices use `app/` |
| No env prefix specified | **`ODOO_MCP_` prefix** | Follows existing convention (BRAND_EQUITY_, DISCOVERY_, etc.) |
| Skills in `odoo-mcp-server-svc/skills/` | **Skills in `pipeline-orchestrator-svc/skills/`** | Skills are centralized in the orchestrator. Agent services are skill-agnostic — they receive `skill_context` via `config` dict in HTTP payloads. The Odoo MCP server consumes skills the same way content-agent and social-agent do. |

## Reference Patterns (Reuse These)

| Pattern | Reference File |
|---------|---------------|
| FastAPI lifespan + CORS | `brand-equity-calculator-svc/app/main.py` |
| Pydantic BaseSettings | `brand-equity-calculator-svc/app/core/config.py` |
| RedisManager (fail-open) | `brand-equity-calculator-svc/app/cache/redis_manager.py` |
| MCP Server (tools/resources/prompts) | `ai-brand-automator/automation/mcp_server.py` |
| Skill definitions (centralized) | `pipeline-orchestrator-svc/skills/*.md` — 26 new Odoo skills added here |
| Skill consumption pattern | `content-agent-service/app/services/content_executor.py:174` — `config.get("skill_context", "")` |
| Skill loader/registry/router (orchestrator only) | `pipeline-orchestrator-svc/app/skills/` — NO duplication in new service |
| Docker service config | `deployment/docker-compose.yml` |
| Test fixtures (AsyncClient) | `brand-equity-calculator-svc/tests/conftest.py` |

---

## Phase 1: Repository Setup & Git Submodule

**Objective**: Add Odoo CE as submodule, create base directory structure.

**Files to create/modify**:
- `vendor/odoo/community/` - Git submodule (`git submodule add -b 19.0 --depth 1 https://github.com/odoo/odoo.git vendor/odoo/community`)
- `.gitmodules` - Submodule config (branch 19.0, shallow=true)
- `.gitignore` - Add `vendor/odoo/community/**/*.pyc`, `vendor/odoo/community/**/__pycache__/`
- `scripts/odoo-sync.sh` - Upstream sync automation script
- `odoo-mcp-server-svc/` - Empty service directory with `app/__init__.py`, `tests/__init__.py`

**Verify**: `git submodule status` shows Odoo pinned at 19.0, `ls vendor/odoo/community/odoo/addons/` confirms modules present

---

## Phase 2: Core Service Scaffold (FastAPI + Config + Health)

**Objective**: Minimal runnable FastAPI service matching existing microservice patterns.

**Files to create**:
- `odoo-mcp-server-svc/app/main.py` - FastAPI app with lifespan (init Redis, log startup)
- `odoo-mcp-server-svc/app/core/config.py` - `Settings(BaseSettings)` with `ODOO_MCP_` prefix. Key fields: `ODOO_URL`, `ODOO_MASTER_PASSWORD`, `MCP_TRANSPORT`, `PORT=8095`, `REDIS_URL=redis://localhost:6379/9`, `TENANT_MODEL`, `RBAC_ENFORCEMENT`, `RBAC_ROLES_DIR`, `RAG_SERVICE_URL`, `RAG_ENABLED`, pool sizes, rate limits, Kafka, logging
- `odoo-mcp-server-svc/app/core/logging_config.py` - `setup_logging()` (suppress uvicorn.access, httpx, xmlrpc)
- `odoo-mcp-server-svc/app/cache/redis_manager.py` - Async Redis wrapper, fail-open, key patterns: `odoo_mcp:schema:{tenant_id}:{model}`, `odoo_mcp:session:{tenant_id}`, `odoo_mcp:rbac:{tenant_id}:{role}`, `odoo_mcp:rate:{tenant_id}`
- `odoo-mcp-server-svc/app/api/routes.py` - `GET /health` returning status/version/odoo_connected
- `odoo-mcp-server-svc/app/api/schemas.py` - `HealthResponse`, `MCPRequest`, `MCPResponse` Pydantic models
- `odoo-mcp-server-svc/pyproject.toml` - pytest asyncio_mode="auto", black, mypy
- `odoo-mcp-server-svc/requirements.txt` - fastapi, uvicorn, pydantic, pydantic-settings, httpx, redis, mcp>=1.0.0, pyyaml
- `odoo-mcp-server-svc/requirements-dev.txt` - pytest, pytest-asyncio, pytest-httpx, black, mypy
- `odoo-mcp-server-svc/tests/conftest.py` - AsyncClient fixture with ASGITransport
- `odoo-mcp-server-svc/tests/test_health.py` - GET /health returns 200

**Verify**: `uvicorn app.main:app --port 8095` starts, `curl localhost:8095/health` returns JSON, `pytest tests/ -v` passes

---

## Phase 3: Odoo RPC Client Layer

**Objective**: Async XML-RPC/JSON-RPC client with tenant-scoped connection pooling.

**Files to create**:
- `odoo-mcp-server-svc/app/services/odoo_rpc_client.py` - `OdooRPCClient` class with: `authenticate()`, `execute_kw()`, `search_read()`, `search_count()`, `create()`, `write()`, `unlink()`, `fields_get()`. Uses `asyncio.to_thread()` to wrap synchronous `xmlrpc.client`, or `httpx.AsyncClient` for JSON-RPC. Retry logic (3 attempts, exponential backoff for 5xx/timeout).
- `odoo-mcp-server-svc/app/services/connection_pool.py` - `TenantConnectionPool`: per-tenant connection state (url, db, uid, password), pool size from settings, `get_connection()`, `release_connection()`, `close_all()`
- `odoo-mcp-server-svc/app/services/errors.py` - Exception hierarchy: `OdooMCPError` > `OdooConnectionError`, `OdooAuthenticationError`, `OdooAccessError`, `OdooValidationError`, `OdooNotFoundError`, `TenantNotFoundError`, `RBACDeniedError`
- `odoo-mcp-server-svc/tests/test_odoo_rpc_client.py` - Mock RPC responses, test auth, CRUD, retry, timeout
- `odoo-mcp-server-svc/tests/test_connection_pool.py` - Pool create/acquire/release, size limits, tenant isolation

---

## Phase 4: Multi-Tenancy Layer

**Objective**: Tenant resolution, context propagation, 3 tenancy models.

**Files to create**:
- `odoo-mcp-server-svc/app/tenancy/models.py` - `TenantConfig` (tenant_id, odoo_url, odoo_db, plan_tier, allowed_modules, pool_size, rate_limit) + `TenantContext` (config, odoo_uid, user_roles, company_id) Pydantic models
- `odoo-mcp-server-svc/app/tenancy/resolver.py` - `TenantResolver`: JWT `tenant_id` -> `TenantConfig` from registry -> authenticate with Odoo -> return `TenantContext`. Supports dedicated_db, shared_instance, shared_db models.
- `odoo-mcp-server-svc/app/tenancy/registry.py` - `TenantRegistry`: loads tenant configs from env/config/DB, caches in Redis with `TENANT_CACHE_TTL`
- `odoo-mcp-server-svc/app/tenancy/middleware.py` - FastAPI dependency `get_tenant_context(request)`: extracts JWT/X-Tenant-ID -> calls resolver -> raises 401/403 on failure
- `odoo-mcp-server-svc/tests/test_tenant_resolver.py` - Test each tenancy model, JWT extraction, cache
- `odoo-mcp-server-svc/tests/test_tenant_registry.py` - Config loading, Redis caching
- `odoo-mcp-server-svc/tests/test_tenant_middleware.py` - Dependency injection, 401/403

---

## Phase 5: RBAC Engine

**Objective**: Hierarchical RBAC with 4-level permissions and YAML role definitions.

**Files to create**:
- `odoo-mcp-server-svc/app/rbac/models.py` - `Permission` (tool, models, operations, fields_allowed, fields_denied, domain_filter), `RoleDefinition` (name, inherits, permissions), `PolicyDecision` enum (ALLOW/DENY/DENY_FIELD/ESCALATE), `PolicyResult`
- `odoo-mcp-server-svc/app/rbac/loader.py` - `load_role_definitions(roles_dir)`: reads YAML files, validates, returns indexed dict
- `odoo-mcp-server-svc/app/rbac/evaluator.py` - `PolicyEvaluator`: 3-phase pipeline (Token Extraction -> Policy Resolution with inheritance flattening -> Decision/Enforcement). Caches in Redis.
- `odoo-mcp-server-svc/app/rbac/engine.py` - `RBACEngine`: wraps evaluator with enforcement modes (enforcing/permissive/disabled), `check_access()`, `enforce_or_raise()`
- **17 YAML role definitions** in `odoo-mcp-server-svc/config/roles/`:
  - Platform: `super_admin.yaml`, `tenant_owner.yaml`, `tenant_admin.yaml`
  - Sales: `sales_user.yaml`, `sales_manager.yaml`
  - Accounting: `account_user.yaml`, `account_manager.yaml`
  - Inventory: `stock_user.yaml`, `stock_manager.yaml`
  - HR: `hr_user.yaml`, `hr_manager.yaml`
  - Project: `project_user.yaml`, `project_manager.yaml`
  - Other: `marketing_user.yaml`, `website_editor.yaml`, `readonly_viewer.yaml`
- `odoo-mcp-server-svc/tests/test_rbac_loader.py`, `test_rbac_evaluator.py`, `test_rbac_engine.py`

---

## Phase 6: MCP Protocol Transport Layer

**Objective**: MCP server with Streamable HTTP + SSE, using `mcp` Python SDK.

**Files to create**:
- `odoo-mcp-server-svc/app/mcp/server.py` - `create_mcp_server() -> Server` using `mcp.server.Server`. Registers `@server.list_tools()`, `@server.call_tool()`, `@server.list_resources()`, `@server.read_resource()`, `@server.list_prompts()`, `@server.get_prompt()`. Same pattern as `ai-brand-automator/automation/mcp_server.py`.
- `odoo-mcp-server-svc/app/mcp/transport.py` - Streamable HTTP handler (`POST /mcp`), SSE handler (`GET /mcp/sse`), tenant resolution per request
- Update `app/api/routes.py` - Wire `/mcp` and `/mcp/sse` endpoints
- Update `app/main.py` - Initialize MCP server in lifespan
- `odoo-mcp-server-svc/tests/test_mcp_transport.py`, `test_mcp_server.py`

---

## Phase 7: Tool Registry & Generic ORM Tools

**Objective**: Dynamic tool registry + 8 Generic ORM tools as foundation.

**Files to create**:
- `odoo-mcp-server-svc/app/tools/registry.py` - `ToolRegistry`: register, get_tool, list_tools by domain
- `odoo-mcp-server-svc/app/tools/base.py` - `BaseTool` ABC with `name`, `description`, `domain`, `input_schema`, `required_model`, `required_operation`, `async execute(arguments, context)`
- `odoo-mcp-server-svc/app/tools/dispatcher.py` - `ToolDispatcher`: RBAC check -> execute -> field redaction -> domain injection -> audit logging -> structured JSON response
- `odoo-mcp-server-svc/app/tools/generic/orm_tools.py` - 8 tools: `OdooSearchTool`, `OdooReadTool`, `OdooCreateTool`, `OdooWriteTool`, `OdooDeleteTool`, `OdooSearchReadTool`, `OdooGetFieldsTool`, `OdooExecuteMethodTool`
- `odoo-mcp-server-svc/tests/test_tool_registry.py`, `test_generic_orm_tools.py`, `test_tool_dispatcher.py`

---

## Phase 8: Domain Tools — CRM, Sales, Accounting (30 tools)

**Objective**: First batch of domain-specific tools.

**Files to create**:
- `odoo-mcp-server-svc/app/tools/crm/tools.py` - **10 tools**: SearchLeads, CreateLead, UpdateLead, MoveStage, AssignSalesperson, LogActivity, MarkWon, MarkLost, GetPipelineStats, MergeLeads (model: `crm.lead`)
- `odoo-mcp-server-svc/app/tools/sales/tools.py` - **10 tools**: CreateQuotation, AddOrderLine, ConfirmOrder, CancelOrder, CreateInvoice, ApplyDiscount, SearchOrders, GetOrderDetails, UpdatePricelist, SendQuotation (model: `sale.order`)
- `odoo-mcp-server-svc/app/tools/accounting/tools.py` - **10 tools**: CreateInvoice, CreateBill, PostEntry, RegisterPayment, Reconcile, GetBalance, GenerateReport, CreateJournalEntry, ManageTaxes, BankReconcile (model: `account.move`)
- Tests: `test_crm_tools.py`, `test_sales_tools.py`, `test_accounting_tools.py`

---

## Phase 9: Domain Tools — Inventory, Manufacturing, HR (30 tools)

**Files to create**:
- `odoo-mcp-server-svc/app/tools/inventory/tools.py` - **11 tools**: CheckAvailability, CreateTransfer, ValidateTransfer, CreateAdjustment, GetValuation, ManageLocations, ForecastReport, CreateRFQ, ConfirmPurchaseOrder, ReceiveProducts, CreatePurchaseBill
- `odoo-mcp-server-svc/app/tools/manufacturing/tools.py` - **8 tools**: CreateBOM, CreateProduction, StartProduction, CompleteProduction, PlanSchedule, QualityCheck, SearchManufacturingOrders, GetCapacity
- `odoo-mcp-server-svc/app/tools/hr/tools.py` - **11 tools**: CreateEmployee, UpdateEmployee, SearchEmployees, RequestLeave, ApproveLeave, GetLeaveBalance, CreateJobPosting, TrackApplicant, RecordAttendance, GeneratePayslip, GetOrgChart
- Tests: `test_inventory_tools.py`, `test_manufacturing_tools.py`, `test_hr_tools.py`

---

## Phase 10: Domain Tools — Project, Website, Marketing, Comms, Admin (25 tools)

**Files to create**:
- `odoo-mcp-server-svc/app/tools/project/tools.py` - **4 tools**: CreateTask, UpdateTask, LogTimesheet, GetProfitability
- `odoo-mcp-server-svc/app/tools/website/tools.py` - **3 tools**: CreatePage, ListProducts, ProcessEcommerceOrder
- `odoo-mcp-server-svc/app/tools/marketing/tools.py` - **3 tools**: CreateCampaign, SendMailing, SchedulePost
- `odoo-mcp-server-svc/app/tools/comms/tools.py` - **3 tools**: SendMessage, CreateEvent, CreateContact
- `odoo-mcp-server-svc/app/tools/admin/tools.py` - **12 tools**: CreateUser, UpdatePermissions, ListModules, InstallModule, GetSettings, UpdateSettings, ExportData, ImportData, CheckPermissions, ListRoles, AssignRole, AuditLog
- Tests: `test_project_tools.py`, `test_website_tools.py`, `test_marketing_tools.py`, `test_comms_tools.py`, `test_admin_tools.py`

---

## Phase 11: MCP Resources & Prompts

**Objective**: 11 Odoo resources + 8 workflow prompts.

**Files to create**:
- `odoo-mcp-server-svc/app/mcp/resources.py` - **11 resources**: `odoo://schema/{model}`, `odoo://config/modules`, `odoo://config/company`, `odoo://config/users`, `odoo://dashboard/sales`, `odoo://dashboard/inventory`, `odoo://dashboard/accounting`, `odoo://dashboard/hr`, `odoo://rbac/effective_roles`, `odoo://rbac/pending_approvals`, `odoo://tenant/info`
- `odoo-mcp-server-svc/app/mcp/prompts.py` - **8 prompts**: order_to_cash, procure_to_pay, month_end_close, new_employee_onboard, inventory_cycle_count, customer_complaint, production_run, tenant_setup_wizard
- Tests: `test_mcp_resources.py`, `test_mcp_prompts.py`

---

## Phase 12: Skills (Centralized), Kafka, Observability

**Objective**: Add 26 Odoo-specific skills to the centralized orchestrator skill store, add skill_context consumption in the Odoo MCP server, Kafka integration, metrics/audit.

### Skill Architecture (Centralized — Matching Existing Pattern)

Skills follow the existing centralized architecture:
1. **All skills live in `pipeline-orchestrator-svc/skills/`** — the single source of truth
2. The **orchestrator's SkillRouter** resolves matching skills per-node based on `target_agents` + prompt trigger keywords
3. Matched skills are injected as `skill_context` (formatted Markdown string) into the node's `config` dict
4. The **ExternalWrapper** passes `config` (including `skill_context`) in the HTTP payload to the agent service
5. The **Odoo MCP server** extracts `skill_context` from `request.config` and uses it (same as content-agent and social-agent)

**No skill loader/registry/router code is needed in `odoo-mcp-server-svc`** — the orchestrator handles all skill resolution.

### Files to create (Skills — in pipeline-orchestrator-svc):
- **26 skill `.md` files** in `pipeline-orchestrator-svc/skills/` with `target_agents: [odoo_mcp]`:
  - `odoo-sales-pipeline.md` (triggers: lead, pipeline, opportunity, sales funnel, conversion)
  - `odoo-quotation-management.md` (triggers: quotation, quote, order, sales order)
  - `odoo-pricing-strategy.md` (triggers: price, discount, pricelist, loyalty)
  - `odoo-accounts-receivable.md` (triggers: invoice, payment, receivable, collection)
  - `odoo-accounts-payable.md` (triggers: bill, vendor, expense, payable)
  - `odoo-financial-reporting.md` (triggers: balance sheet, P&L, profit, financial report)
  - `odoo-multi-currency.md` (triggers: currency, exchange rate, foreign)
  - `odoo-warehouse-ops.md` (triggers: stock, picking, transfer, warehouse, delivery)
  - `odoo-procurement.md` (triggers: purchase, RFQ, vendor, replenishment)
  - `odoo-inventory-valuation.md` (triggers: valuation, FIFO, AVCO, costing)
  - `odoo-production-planning.md` (triggers: BOM, manufacturing, production, work order)
  - `odoo-quality-control.md` (triggers: quality, QC, inspection, defect)
  - `odoo-employee-management.md` (triggers: employee, department, job, org chart)
  - `odoo-recruitment.md` (triggers: recruit, applicant, hiring, interview, job posting)
  - `odoo-leave-management.md` (triggers: leave, time off, vacation, holiday, absence)
  - `odoo-payroll-admin.md` (triggers: payroll, salary, payslip, wage, compensation)
  - `odoo-project-management.md` (triggers: project, task, milestone, sprint, Kanban)
  - `odoo-time-tracking.md` (triggers: timesheet, hours, billing rate, time tracking)
  - `odoo-email-campaigns.md` (triggers: email, mailing, campaign, newsletter, list)
  - `odoo-social-publishing.md` (triggers: social, post, schedule, platform)
  - `odoo-content-management.md` (triggers: website, page, blog, SEO, CMS)
  - `odoo-ecommerce-ops.md` (triggers: ecommerce, cart, checkout, catalog, online)
  - `odoo-user-management.md` (triggers: user, access, group, permission)
  - `odoo-system-config.md` (triggers: setting, config, module, install)
  - `odoo-tenant-admin.md` (triggers: tenant, provision, database, company)
  - `odoo-data-export-import.md` (triggers: export, import, CSV, data migration)

  Each skill follows existing format:
  ```yaml
  ---
  name: odoo-sales-pipeline
  version: "1.0"
  description: Sales pipeline management and lead scoring for Odoo CRM
  target_agents:
    - odoo_mcp
  triggers:
    - "lead"
    - "pipeline"
    - "opportunity"
  priority: 8
  max_tokens: 400
  ---
  # Markdown body with Odoo-specific instructions for the LLM
  ```

### Files to modify (Pipeline Orchestrator — node registry + external wrapper):
- `pipeline-orchestrator-svc/app/factory/node_registry.py` — Register `odoo_mcp` as an external node pointing to `http://odoo-mcp-server:8095/execute`
- Orchestrator's ExternalWrapper already handles skill injection — no changes needed

### Files to create (Odoo MCP Server — skill consumption):
- The `odoo-mcp-server-svc/app/api/routes.py` **execute endpoint** (`POST /execute`) receives `ExecuteRequest` with `config` dict
- `odoo-mcp-server-svc/app/api/schemas.py` — Add `ExecuteRequest` schema matching other agent services: `input_prompt`, `input_context`, `tenant_context`, `config` (contains `skill_context`), `previous_outputs`
- In tool execution logic: extract `skill_context = config.get("skill_context", "")` and inject into LLM/tool context (same pattern as `content-agent-service/app/services/content_executor.py:174`)

### Files to create (Kafka & Observability — in odoo-mcp-server-svc):
- `odoo-mcp-server-svc/app/messaging/kafka_producer.py` - Produces to `odoo-mcp-audit-topic`, `odoo-tenant-events-topic` (fail-open)
- `odoo-mcp-server-svc/app/messaging/kafka_consumer.py` - Consumes `tenant-provisioning-topic` (fail-open)
- `odoo-mcp-server-svc/app/observability/metrics.py` - Prometheus: tool_calls_total, tool_latency_seconds, rbac_decisions_total, odoo_rpc_latency_seconds
- `odoo-mcp-server-svc/app/observability/audit.py` - Structured audit logging (tenant_id, user_id, tool, model, operation, duration)
- Tests: `odoo-mcp-server-svc/tests/test_skill_consumption.py` (verify skill_context extracted from config), `test_kafka_messaging.py`, `test_audit.py`

---

## Phase 13: RAG Store Integration

**Objective**: Connect to rag-uploader-agent-service for knowledge retrieval, 8 RAG tools, 5 RAG resources.

**Files to create**:
- `odoo-mcp-server-svc/app/rag/client.py` - `RAGClient`: async HTTP client to rag-uploader-agent-service at `RAG_SERVICE_URL`. Methods: `query()`, `upload_document()`, `list_documents()`, `delete_document()`, `get_stats()`. Tenant-aware (namespace isolation by tenant_id).
- `odoo-mcp-server-svc/app/rag/middleware.py` - `RAGContextMiddleware`: intercepts tools annotated with `rag_context_enabled=True`, builds semantic query from tool params, injects retrieved context as `background_context`. Respects `RAG_CONTEXT_MAX_TOKENS`.
- `odoo-mcp-server-svc/app/rag/sync.py` - `OdooRAGSync`: Kafka consumer for `odoo.record.changed`, nightly cron for `RAG_SYNC_MODELS`, `INDEXABLE_MODELS` config
- `odoo-mcp-server-svc/app/tools/rag/tools.py` - **8 tools**: QueryKnowledge, UploadDocument, ListDocuments, DeleteDocument, EnrichContext, IndexOdooRecord, SearchByMetadata, GetStoreStats
- Update `app/mcp/resources.py` - **5 RAG resources**: `rag://knowledge/{query}`, `rag://documents/list`, `rag://documents/{doc_id}`, `rag://context/{model}/{record_id}`, `rag://stats`
- Tests: `test_rag_client.py`, `test_rag_middleware.py`, `test_rag_sync.py`, `test_rag_tools.py`, `test_rag_resources.py`

---

## Infrastructure (Parallel with Phases 2+)

### Docker & Deployment
- `odoo-mcp-server-svc/Dockerfile` - Python 3.12-slim, expose 8095
- Update `deployment/docker-compose.yml` - Add `odoo-mcp-server` service (port 8095, Redis DB 9, depends_on redis, healthcheck curl /health)

### CI/CD
- Update `.github/workflows/ci-cd.yml` - Add `odoo-mcp-server-tests` job (Python 3.12, pytest -m "not integration", coverage upload)

### Documentation
- `odoo-mcp-server-svc/CLAUDE.md` - Service-specific guidance (architecture, env vars, Redis keys, build/test commands)
- Update root `CLAUDE.md` - Add to monorepo layout, service ports (8095), Redis DB (9), Kafka topics, auth headers, env prefix, key files
- Update `AGENTS.md` - "9 FastAPI services"
- Save implementation plan to `docs/ODOO_MCP_SERVER_IMPLEMENTATION_PLAN.md`

---

## Complete Directory Structure

```
odoo-mcp-server-svc/                    # NEW SERVICE
├── app/
│   ├── main.py
│   ├── api/           (routes.py, schemas.py)        # /health, /mcp, /mcp/sse, /execute
│   ├── core/          (config.py, logging_config.py)
│   ├── cache/         (redis_manager.py)
│   ├── mcp/           (server.py, transport.py, resources.py, prompts.py)
│   ├── tools/
│   │   ├── registry.py, base.py, dispatcher.py
│   │   ├── generic/   (orm_tools.py — 8 tools)
│   │   ├── crm/       (tools.py — 10 tools)
│   │   ├── sales/     (tools.py — 10 tools)
│   │   ├── accounting/ (tools.py — 10 tools)
│   │   ├── inventory/ (tools.py — 11 tools)
│   │   ├── manufacturing/ (tools.py — 8 tools)
│   │   ├── hr/        (tools.py — 11 tools)
│   │   ├── project/   (tools.py — 4 tools)
│   │   ├── website/   (tools.py — 3 tools)
│   │   ├── marketing/ (tools.py — 3 tools)
│   │   ├── comms/     (tools.py — 3 tools)
│   │   ├── admin/     (tools.py — 12 tools)
│   │   └── rag/       (tools.py — 8 tools)
│   ├── services/      (odoo_rpc_client.py, connection_pool.py, errors.py)
│   ├── tenancy/       (models.py, resolver.py, registry.py, middleware.py)
│   ├── rbac/          (models.py, loader.py, evaluator.py, engine.py)
│   ├── rag/           (client.py, middleware.py, sync.py)
│   ├── messaging/     (kafka_producer.py, kafka_consumer.py)
│   └── observability/ (metrics.py, audit.py)
├── config/roles/      (17 YAML role definitions)
├── tests/             (~35 test files)
├── Dockerfile
├── CLAUDE.md
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt

pipeline-orchestrator-svc/skills/       # MODIFIED — add 26 Odoo skills here
├── odoo-sales-pipeline.md              # (centralized, target_agents: [odoo_mcp])
├── odoo-quotation-management.md
├── odoo-pricing-strategy.md
├── odoo-accounts-receivable.md
├── odoo-accounts-payable.md
├── odoo-financial-reporting.md
├── odoo-multi-currency.md
├── odoo-warehouse-ops.md
├── odoo-procurement.md
├── odoo-inventory-valuation.md
├── odoo-production-planning.md
├── odoo-quality-control.md
├── odoo-employee-management.md
├── odoo-recruitment.md
├── odoo-leave-management.md
├── odoo-payroll-admin.md
├── odoo-project-management.md
├── odoo-time-tracking.md
├── odoo-email-campaigns.md
├── odoo-social-publishing.md
├── odoo-content-management.md
├── odoo-ecommerce-ops.md
├── odoo-user-management.md
├── odoo-system-config.md
├── odoo-tenant-admin.md
├── odoo-data-export-import.md
└── (15 existing skills remain unchanged)

pipeline-orchestrator-svc/app/factory/  # MODIFIED — register odoo_mcp node
└── node_registry.py                    # Add odoo_mcp as external node

vendor/odoo/community/                  # NEW — Git submodule (Odoo CE 19.0)
scripts/odoo-sync.sh                    # NEW — Submodule sync script
```

### Skill Data Flow (for Odoo MCP Server)
```
pipeline-orchestrator-svc/skills/odoo-*.md     (26 skill definitions)
    ↓ loaded at orchestrator startup
SkillRegistry indexes by target_agents: [odoo_mcp]
    ↓ matched by trigger keywords in user prompt
SkillRouter.resolve_skills_for_node("odoo_mcp", prompt)
    ↓ returns {skill_context: "...", skill_names: [...]}
JobExecutor merges into node config
    ↓ ExternalWrapper POST to odoo-mcp-server-svc/execute
odoo-mcp-server-svc extracts config.get("skill_context", "")
    ↓ injected into tool execution context / LLM prompt
```

## Summary

| Category | Count |
|----------|-------|
| New source files (odoo-mcp-server-svc) | ~70 |
| New test files | ~35 |
| New skill files in pipeline-orchestrator-svc/skills/ | 26 (centralized, `target_agents: [odoo_mcp]`) |
| New YAML role files (odoo-mcp-server-svc/config/roles/) | 17 |
| MCP Tools | 101 (8 ORM + 10 CRM + 10 Sales + 10 Accounting + 11 Inventory + 8 Mfg + 11 HR + 4 Project + 3 Website + 3 Marketing + 3 Comms + 12 Admin + 8 RAG) |
| MCP Resources | 16 (11 Odoo + 5 RAG) |
| MCP Prompts | 8 |
| Phases | 13 + infrastructure |
| Modified existing services | pipeline-orchestrator-svc (node registry + 26 skills) |

## Verification Strategy

After each phase, run:
```bash
cd odoo-mcp-server-svc
pytest tests/ -v -m "not integration"  # Unit tests
black app/ tests/ --check              # Format check
```

End-to-end verification (after Phase 13):
```bash
# Start service
uvicorn app.main:app --port 8095

# Health check
curl http://localhost:8095/health

# MCP tool discovery (via MCP client or curl to /mcp)
# Verify 101 tools, 16 resources, 8 prompts returned

# Full test suite
pytest tests/ -v --cov=app --cov-report=term-missing
```
