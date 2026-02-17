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
- Any migration file — Never edit existing migrations, always create new ones

### Safe to Modify

- `ai-brand-automator/{app}/views.py` — API endpoints
- `ai-brand-automator/{app}/serializers.py` — Request/response schemas
- `ai-brand-automator/{app}/models.py` — Data models (create migration after)
- `ai-brand-automator/{app}/tests/` — Test files
- `ai-brand-automator-frontend/src/components/` — UI components
- `ai-brand-automator-frontend/src/app/` — Page routes
- `ai-brand-automator-frontend/src/hooks/` — Custom hooks
- `ai-brand-automator-frontend/src/lib/` — Utilities

## Definition of Done

A task is **done** when ALL of the following are true:

1. **Tests pass**: `pytest -v` (backend) and `npm test` (frontend) — zero failures
2. **Formatting clean**: `black --check .` and `flake8 .` report zero issues
3. **TypeScript compiles**: `npx tsc --noEmit` exits cleanly
4. **No regressions**: Existing tests still pass after changes
5. **Multi-tenancy safe**: New queries use `Q(tenant=tenant) | Q(tenant__isnull=True)` pattern; new `.objects.create()` calls include `tenant=getattr(request, 'tenant', None)`
6. **Migrations created**: If models changed, `makemigrations` was run
7. **Branch is clean**: Changes committed to a feature/bug branch (never directly to `main`)

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

### When Asked About the Codebase

1. Use `semantic_search` to find relevant code
2. Read the `ARCHITECTURE.md` for data flow understanding
3. Check `.github/copilot-instructions.md` for conventions
4. Cite specific file paths and line numbers in responses
