# Project Guidelines

- Monorepo: Django core API (`ai-brand-automator/`), Next.js frontend (`ai-brand-automator-frontend/`), 10 FastAPI microservices, and an Odoo Community submodule (`vendor/odoo/community/`).
- Read first: `ARCHITECTURE.md`, `.github/copilot-instructions.md`, `CLAUDE.md`, and service-local `CLAUDE.md` before edits.
- Prefer the closest instruction file to your target code (service-local guidance wins).
- Do not modify without explicit request: `docs/LICENSE.md`, `credentials/`, `deployment/config/kong/`, `.github/workflows/ci-cd.yml`, `ai-brand-automator/db.sqlite3`, `vendor/`.

## Code Style

- Backend: `black` (88) + `flake8`; use `decouple.config()` for env vars (never `os.environ`).
- Frontend: TypeScript strict + ESLint; use `apiClient` from `@/lib/api` (never raw `fetch`).
- Multi-tenancy: always `getattr(request, 'tenant', None)`; never direct `request.tenant`.
- Tenant query pattern: `Q(tenant=tenant) | Q(tenant__isnull=True)` for backward compatibility.
- Pipeline apps (`data_ingestion`, `media_curation`, `rag_index`) must stay Hexagonal (Pydantic domain + ports/adapters).

## Architecture

- Request flow: Next.js -> Kong -> Django API.
- Orchestration flow: Django dispatch -> `pipeline-orchestrator-svc` (direct sequential execution) -> agent services -> Django callback.
- The orchestrator executes nodes sequentially via topological sort — **not** through LangGraph's `ainvoke`/`astream`. LangGraph is a dependency but not used at runtime.
- Dynamic skill loading: `pipeline-orchestrator-svc/skills/` contains 41 `.md` skill files (15 general + 26 Odoo-specific) resolved per-node at execution time.
- Callback updates in `orchestration/views.py` must use `transaction.atomic()` + `select_for_update()`.
- Chat supports auto-detect pipelines; Pipeline UI supports manifest-driven pipelines.
- `brand-equity-calculator-svc` (port 8090) is **public/unauthenticated** and uses Anthropic Claude (not Gemini).
- `odoo-mcp-server-svc` (port 8095) bridges Odoo ERP via MCP protocol — RBAC engine with 16 YAML role definitions, 101 tools across 14 categories.
- Onboarding is a 5-step wizard: Company Info → Brand Voice → Target Audience → Asset Upload → Review. On completion, a PDF of all onboarding data is generated via `fpdf2` and fed into the RAG pipeline.
- Redis DB allocation: 0=Django/Celery, 1=Orchestrator, 2=Discovery, 3=Intelligence, 4=Titling, 5=Content, 6=Social, 7=RAG Uploader, 8=Brand Equity, 9=Odoo MCP.

## Build and Test

- Backend run: `cd ai-brand-automator && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:8001`
- Backend checks: `cd ai-brand-automator && black --check . && flake8 . && pytest -v`
- Frontend checks: `cd ai-brand-automator-frontend && npm run lint && npx tsc --noEmit && npm test`
- Orchestrator tests: `cd pipeline-orchestrator-svc && pytest tests/ -v`
- Discovery tests: `cd discovery-agent-svc && pytest tests/ -v`
- Intelligence tests: `cd intelligence-agent-svc && pytest tests/ -v`
- Brand equity tests: `cd brand-equity-calculator-svc && pytest tests/ -v`
- Integration tests: `cd tests/integration && pytest -v`
- Migrations: `cd ai-brand-automator && python manage.py makemigrations && python manage.py migrate_schemas --shared --noinput`
- Seed data: `python manage.py seed_manifests` (pipeline manifests), `python manage.py seed_subscription_plans` (Stripe plans)
- Full stack: `cd deployment && docker compose up --build`

## Project Conventions

- ViewSets: use `select_related()` for FKs, `get_serializer_class()` for action serializers, `perform_create()` to attach tenant.
- ViewSets with per-action permissions use `RoleBasedPermissionMixin` with a `role_permissions` dict mapping actions to `IsTenantViewer`/`IsTenantEditor`/`IsTenantAdmin`.
- Frontend protected pages must call `useAuth()`.
- Role-dependent UI using tenant context must guard hydration with `hasMounted`.
- Polling uses recursive `setTimeout` (not `setInterval`) to avoid overlapping requests.
- Onboarding steps use `apiClient.patch()` (not PUT) to preserve fields set by other steps; company ID threaded via `localStorage`.
- PDF generation (`generate_onboarding_pdf`) uses `fpdf2` with Helvetica — sanitize Unicode to Latin-1 via `_sanitize()` before writing text.
- If orchestration manifests change, run `python manage.py seed_manifests`.
- Each microservice uses its own env-var prefix (e.g., `DISCOVERY_`, `CONTENT_`, `ODOO_MCP_`); see service-local `CLAUDE.md`.

## Integration Points

- `X-Service-Token`: Django -> Orchestrator dispatch/cancel; Content/Social Agent -> Django blog/post creation.
- `X-Callback-Token`: Orchestrator -> Django callbacks.
- `X-Worker-Token`: chat-titling worker -> Django.
- `X-Tenant-ID`: Content/Social Agent and Orchestrator -> Django/Odoo MCP for tenant routing.
- Kafka topics: `pipeline-trigger-topic`, `pipeline-result-topic`, `agent-trace-topic`, `data-ingestion-topic`, `media-curation-topic`, `chat-titling-topic`, `odoo-mcp-audit-topic`, `odoo-tenant-events-topic`, `tenant-provisioning-topic`.
- Key files: `ai-brand-automator/orchestration/views.py`, `ai-brand-automator/orchestration/services.py`, `pipeline-orchestrator-svc/app/services/job_executor.py`, `pipeline-orchestrator-svc/app/factory/node_registry.py`, `pipeline-orchestrator-svc/app/skills/`, `odoo-mcp-server-svc/app/tools/registry.py`, `odoo-mcp-server-svc/app/rbac/engine.py`, `ai-brand-automator-frontend/src/hooks/usePollingJob.ts`, `ai-brand-automator-frontend/src/lib/api.ts`.

## Security

- Use validators: `sanitize_text_input()`, `sanitize_ai_prompt()`, `validate_file_upload()`.
- Keep Kong assumptions explicit (`KONG_ENABLED=true` only when running behind Kong).
- Keep callback payload limits and manifest URL allowlist (SSRF protection) intact.
- Keep Neon SSL settings enforced: `sslmode=require`, `channel_binding=require`.
- `brand-equity-calculator-svc` is **public/unauthenticated** — no JWT required.
- Odoo MCP RBAC: role YAML files in `odoo-mcp-server-svc/config/roles/` control tool access per tenant role.
