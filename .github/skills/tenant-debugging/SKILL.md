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

AI Brand Automator uses **`django-tenants`** with schema-based multi-tenancy. Most apps run in the **shared (public) schema** with tenant isolation enforced via FK filtering, while the `files` app is configured as a `TENANT_APP` and runs in per-tenant schemas.

```python
# Current approach for shared-schema apps: models have a nullable tenant FK
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
| `tenants/models.py` | Tenant and Domain models (incl. `gcs_raw_bucket`, `gcs_curated_bucket`) |
| `brand_automator/settings.py` | `TENANT_MODEL`, `TENANT_DOMAIN_MODEL`, `SHARED_APPS` config |
| `brand_automator/middleware.py` | Custom middleware (runs after tenant middleware) |
| `create_public_tenant.py` | Script to initialize the public tenant |
| `conftest.py` | Test fixtures for tenant setup (`tenant_with_buckets`, `mock_request_tenant`) |
| `tests/test_tenant_isolation.py` | Cross-tenant isolation test suite (20 tests) |

## Per-Tenant GCS Buckets

Each tenant can override the global GCS buckets:

```python
# Tenant model fields
gcs_raw_bucket      = CharField(max_length=255, blank=True, default="")
gcs_curated_bucket   = CharField(max_length=255, blank=True, default="")

# Property accessors (fall back to global settings)
tenant.get_raw_bucket()      # → tenant.gcs_raw_bucket or settings.GCS_RAW_BUCKET
tenant.get_curated_bucket()  # → tenant.gcs_curated_bucket or settings.GCS_CURATED_BUCKET
```

**Debug**: If files go to the wrong bucket:
```python
from tenants.models import Tenant
t = Tenant.objects.get(schema_name="my_tenant")
print(f"Raw: {t.get_raw_bucket()}, Curated: {t.get_curated_bucket()}")
```

## Redis Key Namespacing

All pipeline Redis keys are tenant-prefixed when `tenant_id` is available:

```
Pattern: {tenant_id}:{app}:{type}:{id}

data_ingestion:
  {tenant_id}:ingestion:dedupe:{event_id}
  {tenant_id}:ingestion:status:{trace_id}

media_curation:
  {tenant_id}:curation:status:{trace_id}
  {tenant_id}:curation:dedupe:{event_id}
  curation:tenant:{tenant_id}              ← already tenant-scoped

rag_index:
  {tenant_id}:rag_sync:status:{event_id}
  rag_sync:rate:{key}                      ← intentionally global (rate limiting)
```

**Debug**: If status lookups return stale/wrong data, check key prefix:
```bash
# In redis-cli
KEYS *ingestion:dedupe:*        # Find all dedupe keys
KEYS tenant-42:*                # Find all keys for tenant-42
```

## Celery Tenant Scoping

- `publish_scheduled_posts`: Uses `select_related("tenant")` and logs `tenant_id` per post.
- `_update_asset_after_ingestion` / `_update_asset_status`: Filter `BrandAsset` by `tenant_id` (integer FK) with safe `int()` conversion — non-integer tenant_ids skip the FK filter.

**Debug**: If Celery tasks update the wrong asset:
```python
# Check if BrandAsset.tenant_id matches the event's tenant_id
from onboarding.models import BrandAsset
asset = BrandAsset.objects.get(id=123)
print(f"Asset tenant: {asset.tenant_id}, Expected: {event_tenant_id}")
```
