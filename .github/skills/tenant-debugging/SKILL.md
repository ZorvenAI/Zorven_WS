---
name: tenant-debugging
description: Debug multi-tenancy issues (schema isolation, query filtering, middleware)
triggers:
  - "tenant not found"
  - "wrong data showing"
  - "data leaking between tenants"
  - "AttributeError: tenant"
  - "multi-tenancy issue"
---

# Skill: Tenant Debugging

## When to Use

Use this skill when the user encounters multi-tenancy issues — data from wrong tenant, `AttributeError` on `request.tenant`, tenant middleware failures, or cross-tenant data leakage.

## Architecture

AI Brand Automator uses **`django-tenants`** with schema-based multi-tenancy, but currently runs all apps in the **shared (public) schema**. Tenant isolation is enforced via FK filtering, not separate schemas.

```python
# Current approach: All models have a nullable tenant FK
class SomeModel(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", null=True, on_delete=models.CASCADE)
    # ... other fields
```

## The Golden Rule

```python
# ✅ ALWAYS use this pattern
tenant = getattr(request, 'tenant', None)
qs = Model.objects.filter(tenant=tenant) if tenant else Model.objects.filter(tenant__isnull=True)

# ❌ NEVER do this — crashes in tests and when middleware doesn't set tenant
tenant = request.tenant
```

## Common Issues

### `AttributeError: 'WSGIRequest' object has no attribute 'tenant'`

**Cause**: `DefaultTenantMiddleware` didn't run (test environment, middleware order wrong).
**Fix**: Use `getattr(request, 'tenant', None)` everywhere.
**In tests**: Set `client.defaults["SERVER_NAME"] = "localhost"` so tenant middleware resolves.

### Data from wrong tenant showing up

**Cause**: Query missing tenant filter.
**Debug**:
```python
# Find queries missing tenant filter
grep -rn "objects.all()" ai-brand-automator/ --include="*.py"
grep -rn "objects.filter(" ai-brand-automator/ --include="*.py" | grep -v tenant
```

### Tenant not resolving

**Cause**: Domain not mapped to tenant in `tenants_domain` table.
**Debug**:
```python
from tenants.models import Tenant, Domain
# Check what domains exist
for d in Domain.objects.all():
    print(f"{d.domain} → {d.tenant.name} (primary={d.is_primary})")
```

### Creating public tenant

```bash
python create_public_tenant.py
# Creates: Tenant(name="Public", schema_name="public") + Domain(domain="localhost")
```

## Middleware Order

The tenant middleware MUST be second (after CORS):

```python
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",                  # 1st
    "django_tenants.middleware.default.DefaultTenantMiddleware",  # 2nd — CRITICAL
    "django.middleware.security.SecurityMiddleware",
    # ... rest
]
```

## Test Patterns

```python
@pytest.fixture
def public_tenant(db):
    """Create a public tenant for tests."""
    from tenants.models import Tenant, Domain
    tenant = Tenant.objects.create(name="Test", schema_name="public")
    Domain.objects.create(domain="localhost", tenant=tenant, is_primary=True)
    return tenant

@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"  # Resolves to public tenant
    return client

@pytest.mark.django_db
def test_tenant_isolation(api_client, public_tenant):
    # Create data for tenant A
    # Switch to tenant B
    # Assert tenant B cannot see tenant A's data
    pass
```

## Key Files

| File | Purpose |
|------|---------|
| `tenants/models.py` | Tenant and Domain models |
| `brand_automator/settings.py` | `TENANT_MODEL`, `TENANT_DOMAIN_MODEL`, `SHARED_APPS` config |
| `brand_automator/middleware.py` | Custom middleware (runs after tenant middleware) |
| `create_public_tenant.py` | Script to initialize the public tenant |
| `conftest.py` | Test fixtures for tenant setup |
