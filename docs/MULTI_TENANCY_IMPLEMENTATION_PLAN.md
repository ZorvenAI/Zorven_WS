# Multi-Tenancy Complete Implementation Plan

> Created: 2026-02-09
> Status: In Progress
> Branch: `feature/multi-tenancy-complete`

---

## Current State Assessment

| Area | Status | Details |
|------|--------|---------|
| **django-tenants installed** | Partial | `TenantMixin`, `DomainMixin` in place, but only `files` app in `TENANT_APPS` — everything else in `SHARED_APPS` using FK filtering |
| **Tenant model** | Exists | Has `name`, `schema_name`, `subscription_status`, `max_users`, `storage_limit_gb` |
| **Tenant REST API** | Missing | No views, serializers, or URLs — tenants can only be created via scripts/admin |
| **GCS buckets** | Shared | Single raw bucket (`onboarding-bucket1`) and single curated bucket (`brandsol-curation-bucket`) shared across all tenants — paths are tenant-prefixed but buckets are shared |
| **Kafka messages** | Partial | Pipeline apps include `tenant_id` in payloads and use it as partition key, but `tenant_id` type is inconsistent (`str` vs `UUID`) |
| **Redis keys** | Not namespaced | Dedup/status keys use `event_id`/`trace_id` only — no tenant prefix except curation config cache |
| **Automation app** | No tenant FK | All 12 models use `user` FK only — no tenant isolation |
| **API views** | Inconsistent | 11+ places use bare `request.tenant` (will crash), others fall through to `.all()` exposing cross-tenant data |
| **Celery tasks** | Not scoped | `publish_scheduled_posts` queries all `ContentCalendar` globally |

### Critical Gaps Identified

1. **No Tenant DRF API** — cannot provision tenants via REST
2. **No per-tenant GCS buckets** — current design shares buckets with path-based isolation only
3. **Automation models missing tenant FK** — social profiles, content calendar, tasks all lack tenant isolation
4. **13 `request.tenant` violations** — direct access without `getattr` will `AttributeError`
5. **`.all()` fallback** in 3 ViewSets — exposes all tenants' data when no tenant context
6. **Redis dedup/status keys not tenant-scoped** — information leakage possible
7. **`tenant_id` type mismatch** — `str` in data_ingestion, `UUID` in media_curation
8. **Celery tasks not tenant-scoped** — scheduler publishes all posts globally

---

## Phase 1: Tenant DRF API (Foundation) ✅

**Goal**: Create a full DRF-based tenant management API (NOT a separate Django app — use the existing `tenants` app).

| Task | File | Change |
|------|------|--------|
| 1.1 | `tenants/serializers.py` | Create `TenantSerializer`, `TenantCreateSerializer`, `TenantUpdateSerializer`, `DomainSerializer` |
| 1.2 | `tenants/views.py` | Create `TenantViewSet` (CRUD), `DomainViewSet` — admin-only access with `IsAdminUser` permission |
| 1.3 | `tenants/urls.py` | Register with `DefaultRouter` under `tenants/` prefix |
| 1.4 | `brand_automator/urls.py` | Add `path("tenants/", include("tenants.urls"))` under `/api/v1/` |
| 1.5 | `tenants/admin.py` | Fix `TenantAdmin.fieldsets` bug (references non-existent `domain` field) |
| 1.6 | `tenants/tests/` | Add tests for all CRUD operations, permissions, schema_name auto-generation |

**Key Design**: Tenant creation triggers schema creation via `django-tenants` built-in `save()`. The serializer validates `name` uniqueness and generates `schema_name`.

---

## Phase 2: Fix All Defensive Tenant Access Patterns

**Goal**: Eliminate all `request.tenant` direct access and `.all()` fallback patterns.

| Task | File | Lines | Fix |
|------|------|-------|-----|
| 2.1 | `ai_services/views.py` | 11 occurrences | Replace `request.tenant` → `getattr(request, 'tenant', None)` with public tenant fallback |
| 2.2 | `onboarding/views.py` | L41-L46, L160-L174, L1008-L1011 | Change `.all()` fallback → `.none()` (match ai_services pattern) |
| 2.3 | `onboarding/views.py` | L1015 | Fix `current()` action — `getattr(request, 'tenant', None)` |
| 2.4 | All ViewSets | Every `get_queryset` | Audit: ensure `tenant` filtering + `.none()` fallback |
| 2.5 | Tests | All affected files | Update/add tests for tenant-filtered querysets |

---

## Phase 3: Add Tenant FK to Automation Models

**Goal**: Add `tenant` ForeignKey to all automation models and scope queries by tenant.

| Task | File | Change |
|------|------|--------|
| 3.1 | `automation/models.py` | Add `tenant = ForeignKey("tenants.Tenant", null=True, blank=True, on_delete=CASCADE)` to: `SocialProfile`, `AutomationTask`, `ContentCalendar`, `OAuthState`, `GoogleBusinessProfile` |
| 3.2 | `automation/views.py` | Update all ViewSets: `get_queryset()` → filter by `tenant` AND `user`; `perform_create()` → attach tenant |
| 3.3 | `automation/serializers.py` | Add `tenant` as `read_only` field |
| 3.4 | `automation/tasks.py` | `publish_scheduled_posts` → filter by tenant if available; `publish_single_post` → add tenant validation |
| 3.5 | Migration | `python manage.py makemigrations automation` |
| 3.6 | Tests | Update all 149+ automation tests to include tenant fixture |

**Design Decision**: Keep dual scoping (`user` + `tenant`) — a user's social profiles within a specific tenant are isolated from other tenants. The `user` FK remains for direct ownership, `tenant` FK adds organizational isolation.

---

## Phase 4: Per-Tenant GCS Buckets

**Goal**: Create and manage separate GCS buckets for each tenant (raw + curated).

| Task | File | Change |
|------|------|--------|
| 4.1 | `tenants/models.py` | Add fields: `gcs_raw_bucket = CharField(max_length=63, blank=True)`, `gcs_curated_bucket = CharField(max_length=63, blank=True)` |
| 4.2 | `tenants/services.py` | Create `TenantGCSService` class: `create_tenant_buckets(tenant)` — creates `{project}-{schema_name}-raw` and `{project}-{schema_name}-curated` GCS buckets with lifecycle policies |
| 4.3 | `tenants/signals.py` | On `Tenant.post_save`, call `TenantGCSService.create_tenant_buckets()` to auto-provision buckets |
| 4.4 | `data_ingestion/factory.py` | Modify `create_gcs_adapter()` to accept `tenant_id` → look up tenant's `gcs_raw_bucket` |
| 4.5 | `data_ingestion/domain/path_generator.py` | Update `generate_raw_path()` to use tenant-specific bucket from domain model |
| 4.6 | `media_curation/factory.py` | Modify factory to accept `tenant_id` → look up tenant's `gcs_curated_bucket` |
| 4.7 | `media_curation/adapters/gcs_adapter.py` | Accept `bucket_name` per-operation (not just at init) |
| 4.8 | `files/services.py` | Update `GCSService` to accept optional `bucket_name` override from tenant context |
| 4.9 | Migration | `python manage.py makemigrations tenants` |
| 4.10 | Tests | Mock GCS bucket creation, test path generation with tenant buckets |

**Design**:
- Bucket naming: `{project_id}-{schema_name}-raw` and `{project_id}-{schema_name}-curated`
- GCS bucket names must be globally unique, ≤63 chars, lowercase
- Fallback: if tenant has no buckets configured, fall back to shared buckets (backward compat)
- Buckets created on tenant creation, NOT on-demand (predictable infra)

---

## Phase 5: Kafka Multi-Tenancy

**Goal**: Standardize `tenant_id` in all Kafka messages and add tenant context to consumer processing.

| Task | File | Change |
|------|------|--------|
| 5.1 | `data_ingestion/domain/models.py` | Standardize `tenant_id` as `str` (not UUID) — matches Django `Tenant.id` (integer) cast to string |
| 5.2 | `media_curation/domain/models.py` | Change `tenant_id: UUID` → `tenant_id: str` to match data_ingestion |
| 5.3 | `media_curation/adapters/kafka_adapter.py` | Remove `_parse_tenant_id()` UUID conversion — accept `str` directly |
| 5.4 | `data_ingestion/adapters/kafka_adapter.py` | Verify `tenant_id` is always in event payload and used as partition key (already done — validate) |
| 5.5 | `media_curation/adapters/kafka_adapter.py` | Same verification |
| 5.6 | `rag_index/services/sync_orchestrator.py` | Same verification |
| 5.7 | `kafka_service/consumer.py` | Add optional `tenant_id` extraction from message headers/payload for audit logging |
| 5.8 | `onboarding/services.py` | Ensure `_build_ingestion_event()` and `_publish_curation_event()` always include correct `tenant_id` as string |
| 5.9 | `data_ingestion/management/commands/run_ingestion.py` | Add tenant context logging to consumer — log which tenant's asset is being processed |
| 5.10 | `media_curation/management/commands/run_curation_consumer.py` | Same — log tenant context |
| 5.11 | Tests | Update all Kafka event fixture data to include `tenant_id` |

---

## Phase 6: Redis Tenant Namespacing

**Goal**: Add tenant prefixes to all Redis keys to prevent cross-tenant information leakage.

| Task | File | Change |
|------|------|--------|
| 6.1 | `data_ingestion/adapters/redis_adapter.py` | Change key patterns: `ingestion:dedupe:{event_id}` → `ingestion:{tenant_id}:dedupe:{event_id}`, `ingestion:status:{trace_id}` → `ingestion:{tenant_id}:status:{trace_id}` |
| 6.2 | `media_curation/adapters/redis_adapter.py` | Same: `curation:{tenant_id}:dedupe:{event_id}`, `curation:{tenant_id}:status:{trace_id}` |
| 6.3 | `rag_index/adapters/redis_adapter.py` | Same: `rag_sync:{tenant_id}:status:{event_id}`, `rag_sync:{tenant_id}:rate:{key}` |
| 6.4 | `onboarding/services.py` | `pipeline:tenant:{id}:config` — already tenant-scoped, verify key prefix consistency |
| 6.5 | All pipeline services | Pass `tenant_id` to Redis adapter methods |
| 6.6 | Tests | Update Redis mock assertions for new key patterns |

**Principle**: Every Redis key that stores per-event/per-asset data must include `tenant_id` in the key. Infrastructure keys (rate limiters, global config) can remain tenant-free.

---

## Phase 7: Tenant-Scoped Celery Tasks

**Goal**: Ensure all Celery tasks respect tenant isolation.

| Task | File | Change |
|------|------|--------|
| 7.1 | `automation/tasks.py` | `publish_scheduled_posts()` — add `tenant_id` parameter; when provided, filter `ContentCalendar.objects.filter(tenant_id=tenant_id)` |
| 7.2 | `automation/tasks.py` | `publish_single_post()` — validate tenant ownership before publishing |
| 7.3 | `data_ingestion/tasks.py` | `_update_asset_after_ingestion()` — add `tenant_id` param, filter `BrandAsset.objects.filter(id=asset_id, tenant_id=tenant_id)` |
| 7.4 | `onboarding/tasks.py` | Verify `export_company_for_rag()` and `batch_export_companies_for_rag()` have proper tenant filtering (already partial) |
| 7.5 | `brand_automator/settings.py` | Add Celery task routes per tenant queue (optional — for priority separation) |
| 7.6 | Tests | Add tests verifying tasks don't cross tenant boundaries |

---

## Phase 8: Integration Testing & Documentation

**Goal**: End-to-end validation and docs update.

| Task | File | Change |
|------|------|--------|
| 8.1 | `tenants/tests/` | Full test suite: tenant CRUD API, bucket provisioning, tenant isolation |
| 8.2 | `test_multitenancy.py` | Update the existing e2e test to cover: tenant creation → bucket creation → asset upload → pipeline flow → tenant isolation verification |
| 8.3 | `conftest.py` | Add `tenant_with_buckets` fixture (creates tenant with mocked GCS buckets) |
| 8.4 | `ARCHITECTURE.md` | Update multi-tenancy section with per-tenant bucket architecture |
| 8.5 | `.github/skills/tenant-debugging/SKILL.md` | Update with new bucket debugging and Redis key patterns |
| 8.6 | Run full test suite | `pytest -v` — all 1400+ tests must pass |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| GCS bucket limits (Hundreds of buckets per project) | Google Cloud allows ~100 bucket creations/second and no hard limit on total — but monitor. Consider folder-based isolation as fallback for scale. |
| Migration on production DB | All new fields are nullable or have defaults — zero downtime migration. Run `migrate_schemas --shared --noinput`. |
| Existing data without tenant | Migration script to assign existing data to public tenant. All new fields are `null=True`. |
| Kafka consumer backward compatibility | New fields in domain models have defaults. Old messages without `tenant_id` will use `"public"` fallback. |
| Redis key migration | Old keys without tenant prefix will TTL out naturally. No migration needed. |
| Breaking automation tests | Phase 3 adds nullable FK — existing tests won't break, new tests will enforce tenant isolation. |

---

## Phase Execution Order

```
Phase 1 (Tenant API)  ──► Phase 2 (Fix access patterns) ──► Phase 3 (Automation tenant FK)
                                                                        │
Phase 4 (Per-tenant GCS)  ◄────────────────────────────────────────────┘
        │
Phase 5 (Kafka tenancy) ──► Phase 6 (Redis namespacing) ──► Phase 7 (Celery tasks)
                                                                        │
                                                            Phase 8 (Testing & docs) ◄┘
```

Phases 1-3 can be done first and deployed independently. Phases 4-7 are the pipeline changes. Phase 8 validates everything end-to-end.
