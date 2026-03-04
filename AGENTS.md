# Project Guidelines

- Monorepo: Django core API (`ai-brand-automator/`), Next.js frontend (`ai-brand-automator-frontend/`), and 9 FastAPI services.
- Read first: `ARCHITECTURE.md`, `.github/copilot-instructions.md`, `CLAUDE.md`, and service-local `CLAUDE.md` before edits.
- Prefer the closest instruction file to your target code (service-local guidance wins).
- Do not modify without explicit request: `docs/LICENSE.md`, `credentials/`, `deployment/config/kong/`, `.github/workflows/ci-cd.yml`, `ai-brand-automator/db.sqlite3`.

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
- Dynamic skill loading: `pipeline-orchestrator-svc/skills/` contains `.md` skill files resolved per-node at execution time.
- Callback updates in `orchestration/views.py` must use `transaction.atomic()` + `select_for_update()`.
- Chat supports auto-detect pipelines; Pipeline UI supports manifest-driven pipelines.
- `brand-equity-calculator-svc` (port 8090) is **public/unauthenticated** and uses Anthropic Claude (not Gemini).

## Build and Test

- Backend run: `cd ai-brand-automator && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:8001`
- Backend checks: `cd ai-brand-automator && black --check . && flake8 . && pytest -v`
- Frontend checks: `cd ai-brand-automator-frontend && npm run lint && npx tsc --noEmit && npm test`
- Orchestrator tests: `cd pipeline-orchestrator-svc && pytest tests/ -v`
- Integration tests: `cd tests/integration && pytest -v`
- Migrations: `cd ai-brand-automator && python manage.py makemigrations && python manage.py migrate_schemas --shared --noinput`

## Project Conventions

- ViewSets: use `select_related()` for FKs, `get_serializer_class()` for action serializers, `perform_create()` to attach tenant.
- Frontend protected pages must call `useAuth()`.
- Role-dependent UI using tenant context must guard hydration with `hasMounted`.
- Polling uses recursive `setTimeout` (not `setInterval`) to avoid overlapping requests.
- If orchestration manifests change, run `python manage.py seed_manifests`.

## Integration Points

- `X-Service-Token`: Django -> Orchestrator dispatch/cancel.
- `X-Callback-Token`: Orchestrator -> Django callbacks.
- `X-Worker-Token`: chat-titling worker -> Django.
- Key files: `ai-brand-automator/orchestration/views.py`, `ai-brand-automator/orchestration/services.py`, `pipeline-orchestrator-svc/app/services/job_executor.py`, `pipeline-orchestrator-svc/app/factory/node_registry.py`, `pipeline-orchestrator-svc/app/skills/`, `ai-brand-automator-frontend/src/hooks/usePollingJob.ts`, `ai-brand-automator-frontend/src/lib/api.ts`.

## Security

- Use validators: `sanitize_text_input()`, `sanitize_ai_prompt()`, `validate_file_upload()`.
- Keep Kong assumptions explicit (`KONG_ENABLED=true` only when running behind Kong).
- Keep callback payload limits and manifest URL allowlist (SSRF protection) intact.
- Keep Neon SSL settings enforced: `sslmode=require`, `channel_binding=require`.
