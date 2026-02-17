# CLAUDE.md — AI Brand Automator

> Model-specific configuration for Claude (Anthropic). This file is a direct manual for Claude models, complementing `.github/copilot-instructions.md`.

## Context Window Strategy

This project has **1890+ backend tests** and a large codebase. Use these strategies to work efficiently within the context window:

### Progressive Loading

1. **Start narrow**: Read only the specific file being discussed
2. **Expand on demand**: Use `grep_search` to find related code before reading full files
3. **Batch reads**: When you need multiple files, read them in parallel
4. **Use summaries**: Check `ARCHITECTURE.md` for system overview before diving into code

### File Priority Order

When investigating an issue, load files in this order:
1. The file mentioned by the user
2. Its test file (same app, `tests/` directory)
3. Related serializer/view if it's a model change
4. `conftest.py` only if test infrastructure is relevant

## Reasoning Approach

### For Bug Fixes

Use structured reasoning:
1. **Symptom**: What error/behavior is reported?
2. **Hypothesis**: What could cause this? (List 2-3 possibilities)
3. **Evidence**: Search codebase for each hypothesis
4. **Root cause**: Identify the actual cause with file + line reference
5. **Fix**: Implement with minimal changes
6. **Verify**: Run relevant tests

### For Architecture Questions

Think in layers:
```
User Request → Frontend (Next.js) → API Client → Kong Gateway → Django View
                                                                    ↓
                                                              Serializer → Model → DB
                                                                    ↓
                                                    Celery Task / Kafka Event → Pipeline
```

### For Multi-File Changes

Use `manage_todo_list` to track progress across files. Mark each task as you go:
```
1. ✅ Update model
2. ✅ Create migration
3. 🔄 Update serializer (in progress)
4. ⬜ Update view
5. ⬜ Add tests
```

## Output Preferences

### Code Generation

- **Python**: Follow Black formatting (88 char lines), include type hints where practical
- **TypeScript**: Use strict types, prefer interfaces over type aliases for object shapes
- **Comments**: Only for non-obvious logic. Never comment self-evident code
- **Docstrings**: Google style for Python, JSDoc for complex TypeScript functions

### Error Messages

When surfacing errors, always include:
- The file path and line number
- The actual error text (not paraphrased)
- A one-line explanation of why it happened

### Commit Messages

Use conventional commits format:
```
feat: add LinkedIn analytics caching
fix: JWT refresh URL mismatch causing 60min logouts
refactor: move MIME type constants to module scope
test: add signed URL force-download coverage
docs: update ARCHITECTURE.md with pipeline flow
chore: update dependencies
```

## Django-Specific Patterns

### When Creating Models

```python
# Always include tenant FK (nullable for shared schema)
tenant = models.ForeignKey(
    "tenants.Tenant",
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="%(class)ss",
)

# Always add to Meta
class Meta:
    ordering = ["-created_at"]
```

### When Creating Views

```python
# Always use defensive tenant access with backward-compatible Q() filter
from django.db.models import Q

def get_queryset(self):
    tenant = getattr(self.request, 'tenant', None)
    qs = super().get_queryset()
    if tenant:
        return qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))
    return qs.filter(tenant__isnull=True)
```

### When Creating Tests

```python
# Always set SERVER_NAME for tenant middleware
@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client
```

## React/Next.js Patterns

### When Creating Components

```tsx
// Always use 'use client' for interactive pages
'use client';

// Always protect routes
import { useAuth } from '@/hooks/useAuth';
export default function MyPage() {
  useAuth();
  // ...
}

// Always use apiClient for API calls
import { apiClient } from '@/lib/api';

// Always use design system classes
<div className="glass-card p-6">
  <h2 className="text-brand-silver font-heading">Title</h2>
  <button className="btn-primary">Action</button>
</div>

// Guard role-dependent UI against hydration mismatches
const [hasMounted, setHasMounted] = useState(false);
useEffect(() => { setHasMounted(true); }, []);
const canEdit = hasMounted ? tenantRole.canEdit : false;
if (!hasMounted) return <LoadingSpinner />;
```

## Hexagonal Architecture (Pipeline Apps)

When working in `data_ingestion/`, `media_curation/`, or `rag_index/`:

```
domain/          → Pydantic BaseModel (NOT Django ORM)
ports/           → Abstract Base Classes (interfaces)
adapters/        → Concrete implementations
services/        → Business logic orchestration
factory.py       → Dependency injection wiring
```

**Never use Django ORM models in these apps.** Domain models are pure Pydantic for portability and testability.

## Performance Considerations

- Use `select_related()` for FK joins in querysets
- Use `prefetch_related()` for reverse FK / M2M relationships
- Kafka is optional — always handle `KafkaException` gracefully
- GCS operations should be wrapped in try/except with logging
- AI (Gemini) calls should have timeouts and fallback responses
