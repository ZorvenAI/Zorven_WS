# AGENTS.md — AI Brand Automator

> Tells Copilot (Agent Mode) and CLI agents what they can do, what they must not touch, and what "done" means.

## Identity

You are an expert full-stack engineer working on **AI Brand Automator**, a multi-tenant SaaS platform. You have deep knowledge of Django, Next.js, PostgreSQL multi-tenancy, and Google Cloud services. Always read `ARCHITECTURE.md` and `.github/copilot-instructions.md` before making changes.

## Executable Commands

### Backend

```bash
# Navigate & activate
cd ai-brand-automator && source ../.venv/bin/activate

# Run development server
python manage.py runserver 0.0.0.0:8000

# Run all backend tests
pytest -v

# Run specific app tests
pytest automation/tests/ -v
pytest files/tests/ -v
pytest media_curation/tests/ -v
pytest onboarding/tests/ -v
pytest orchestration/tests/ -v
pytest ai_services/tests/ -v

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Format & lint (MUST pass before committing)
black .
flake8 .

# Migrations
python manage.py makemigrations
python manage.py migrate_schemas --shared --noinput

# MCP Server (stdio for local, SSE for web)
python run_mcp_server.py --transport stdio
python run_mcp_server.py --transport sse --port 8003

# Orchestration worker (separate Celery queue)
celery -A brand_automator worker -Q orchestration -l info --concurrency=4

# Seed default pipeline manifests (idempotent, run on every deploy)
python manage.py seed_manifests
```

### Microservices (FastAPI)

```bash
# Each microservice follows the same pattern
cd pipeline-orchestrator-svc && pytest tests/ -v    # 171 tests
cd discovery-agent-svc && pytest tests/ -v          # 179 tests
cd intelligence-agent-svc && pytest tests/ -v       # 100 tests
cd chat-titling-worker && pytest tests/ -v          # 34 tests
cd content-agent-service && pytest tests/ -v        # 55 tests
cd social-agent-service && pytest tests/ -v         # 89 tests

# Run a single microservice locally
cd <service-dir>
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port <PORT> --reload

# Format
black app/ tests/
```

### Integration Tests

```bash
# Cross-service integration tests
cd tests/integration
pytest phase1_contracts/ -v   # API contract tests
pytest phase2_domain/ -v      # Domain logic tests
pytest phase3_stress/ -v      # Stress tests
```

### Frontend

```bash
# Navigate
cd ai-brand-automator-frontend

# Run development server
npm run dev

# Run tests
npm test

# Lint
npm run lint

# Type check
npx tsc --noEmit

# Build
npm run build
```

### Full Stack

```bash
cd deployment && docker compose up        # Kong:8000, Backend:8001, Frontend:3000
cd deployment && docker compose down -v   # Tear down with volumes
```

## Project Boundaries

### DO NOT Modify

- `docs/LICENSE.md` — Legal document, never change
- `ai-brand-automator/conftest.py` — Shared test fixtures, modify only to add fixtures (never remove)
- `deployment/config/kong/` — Kong gateway config, requires gateway expertise
- `.github/workflows/ci-cd.yml` — CI pipeline, only modify with explicit request
- Any file in `credentials/` — Service account keys, never commit secrets
- `ai-brand-automator/db.sqlite3` — Local dev DB, never commit

### Modify With Caution

- `ai-brand-automator/brand_automator/settings.py` — Middleware order is critical (see copilot-instructions.md)
- `ai-brand-automator/brand_automator/middleware.py` — Security-sensitive, test thoroughly
- `ai-brand-automator/automation/encryption.py` — Token encryption, changes break existing encrypted data
- `ai-brand-automator/orchestration/management/commands/seed_manifests.py` — Default manifest data, test after changes
- Any migration file — Never edit existing migrations, always create new ones
- `pipeline-orchestrator-svc/` — Separate service, read its CLAUDE.md before modifying
- `discovery-agent-svc/` — Separate service, read its CLAUDE.md before modifying
- `intelligence-agent-svc/` — Separate service, read its CLAUDE.md before modifying
- `chat-titling-worker/` — Separate service, read its CLAUDE.md before modifying
- `content-agent-service/` — Separate service, read its CLAUDE.md before modifying
- `social-agent-service/` — Separate service, read its CLAUDE.md before modifying

### Safe to Modify

- `ai-brand-automator/{app}/views.py` — API endpoints
- `ai-brand-automator/{app}/serializers.py` — Request/response schemas
- `ai-brand-automator/{app}/models.py` — Data models (create migration after)
- `ai-brand-automator/{app}/tests/` — Test files
- `ai-brand-automator-frontend/src/components/` — UI components
- `ai-brand-automator-frontend/src/app/` — Page routes
- `ai-brand-automator-frontend/src/hooks/` — Custom hooks
- `ai-brand-automator-frontend/src/lib/` — Utilities
- `ai-brand-automator/orchestration/` — Pipeline orchestration views, serializers, services, tasks

## Definition of Done

A task is **done** when ALL of the following are true:

1. **Tests pass**: `pytest -v` (backend) and `npm test` (frontend) — zero failures
2. **Formatting clean**: `black --check .` and `flake8 .` report zero issues
3. **TypeScript compiles**: `npx tsc --noEmit` exits cleanly
4. **No regressions**: Existing tests still pass after changes
5. **Multi-tenancy safe**: New queries use `Q(tenant=tenant) | Q(tenant__isnull=True)` pattern; new `.objects.create()` calls include `tenant=getattr(request, 'tenant', None)`
6. **Migrations created**: If models changed, `makemigrations` was run
7. **Manifests seeded**: If orchestration manifests changed, `seed_manifests` was run
8. **Orchestration safe**: If modifying callback endpoints, `transaction.atomic()` + `select_for_update()` pattern is used
9. **Microservice contracts**: If changing agent API schemas, verify contract tests pass in `tests/integration/phase1_contracts/`
10. **Branch is clean**: Changes committed to a feature/bug branch (never directly to `main`)

## Git Workflow

```bash
# Always create a branch from main
git checkout main && git pull
git checkout -b feature/my-feature       # or bug/fix-something

# After changes
black . && flake8 .                      # Backend format
pytest -v                                 # Backend tests
cd ../ai-brand-automator-frontend && npx tsc --noEmit  # Frontend types
npm test                                  # Frontend tests

# Commit with conventional commits
git add -A
git commit -m "feat: add new analytics dashboard widget"
# Prefixes: feat, fix, refactor, test, docs, chore

# Push and create PR
git push -u origin feature/my-feature
```

## Agent-Specific Rules

### When Asked to Fix a Bug

1. Reproduce: Find a failing test or write one
2. Identify root cause in the codebase
3. Fix the issue
4. Verify fix with `pytest` / `npm test`
5. Check for regressions: run full test suite
6. Format: `black .` + `flake8 .`

### When Asked to Add a Feature

1. Understand: Read related existing code first
2. Plan: If multi-step, use `manage_todo_list` to track progress
3. Backend first: Models → Serializers → Views → URLs → Tests
4. Frontend second: Types → API calls → Components → Pages
5. Test: Write tests alongside implementation
6. Format: `black .` + `flake8 .` + `npx tsc --noEmit`

### When Asked to Work on Orchestration

1. Read `orchestration/models.py` for PipelineManifest and AnalysisJob schemas
2. Check `orchestration/views.py` for callback and dispatch patterns
3. Use `transaction.atomic()` + `select_for_update()` for any job state changes
4. Verify X-Callback-Token / X-Service-Token headers in tests
5. Run: `pytest orchestration/tests/ -v`
6. If modifying manifests: `python manage.py seed_manifests`

### When Asked to Work on a Microservice

1. Navigate to the service directory (e.g., `cd pipeline-orchestrator-svc`)
2. Read the service's `CLAUDE.md` for service-specific instructions
3. Run tests: `pytest tests/ -v`
4. Do NOT import Django ORM in microservices — they use Pydantic + FastAPI
5. Follow the shared pattern: `app/api/`, `app/core/`, `app/services/`, `app/messaging/`
6. Each service has its own env var prefix (e.g., `DISCOVERY_`, `INTELLIGENCE_`, `CONTENT_`)

### When Asked About the Codebase

1. Read the `ARCHITECTURE.md` for data flow understanding
2. Check `.github/copilot-instructions.md` for conventions
3. Cite specific file paths and line numbers in responses
