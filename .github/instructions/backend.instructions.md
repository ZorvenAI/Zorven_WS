---
applyTo: "ai-brand-automator/**/*.py"
---

# Backend Instructions

## Code Style

- **Formatter**: Black with 88-char line length
- **Linter**: Flake8
- **Imports**: stdlib → third-party → local, separated by blank lines
- **Type hints**: Use where practical (function signatures, complex return types)
- **Docstrings**: Google style — one-line summary, then Args/Returns/Raises

## Django Conventions

### Models

- Always include `created_at` and `updated_at` auto-fields
- Always add `tenant` FK (nullable) for multi-tenancy
- Use `related_name="%(class)ss"` for tenant FKs
- Define `Meta.ordering` explicitly
- Add `__str__` method on every model
- Use `UniqueConstraint` over `unique_together` (modern Django)

### ViewSets

- Use `select_related()` for FK queries in `get_queryset()`
- Override `get_serializer_class()` for action-specific serializers
- Override `perform_create()` to attach tenant: `serializer.save(tenant=getattr(self.request, 'tenant', None))`
- Return structured error responses, never raw exceptions

### Serializers

- Use `read_only_fields` for computed or auto-populated fields
- Validate at field level with `validate_<field>()` methods
- Use `SerializerMethodField` for computed outputs

### URLs

- Prefix all routes with `/api/v1/`
- Use DRF `DefaultRouter` for ViewSet routing
- Use `path()` with trailing slashes

## Security

- Sanitize user text input with `sanitize_text_input()` from `brand_automator/validators.py`
- Sanitize AI prompts with `sanitize_ai_prompt()`
- Validate file uploads with `validate_file_upload()`
- Never use `os.environ` — always `decouple.config()` with defaults and type casts
- Never access `request.tenant` directly — always `getattr(request, 'tenant', None)`

## Testing

- Use `pytest` markers: `@pytest.mark.django_db` for DB tests
- Set `client.defaults["SERVER_NAME"] = "localhost"` for tenant middleware
- Mock external services (Kafka, GCS, Gemini, Stripe)
- Use `factory_boy` or fixtures from `conftest.py`
- Test both happy path and error cases
