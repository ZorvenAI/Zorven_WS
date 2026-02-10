# Multi-Tenancy Refactored Implementation Plan

> Created: 2026-02-10
> Status: **Draft — Awaiting Approval**
> Branch: `feature/implement-multi-tenancy` (continuation)
> Previous Plan: `docs/MULTI_TENANCY_IMPLEMENTATION_PLAN.md` (superseded)

---

## Executive Summary

**What's changing**: The current 1-to-1 User→Tenant model (`schema_name=user_{id}`) is being replaced with a Many-to-Many User↔Tenant relationship via a `Membership` join table with role-based access control.

**Why**: The current model assumes one user = one tenant. This doesn't support the core use case: **one consultant managing multiple brands**, or **a team of editors collaborating on the same brand**.

**Key architectural shift**:

| Aspect | Current (v1) | New (v2) |
|--------|-------------|----------|
| Tenant identity | `schema_name=user_{id}` — one per user | `schema_name=tenant_{slug}` — one per brand |
| User→Tenant | Implicit 1-to-1 via naming convention | Explicit Many-to-Many via `Membership` |
| Roles | None | OWNER, ADMIN, EDITOR, VIEWER |
| Tenant resolution | `_get_tenant_id_from_user()` + JWT `tenant_id` | `X-Tenant-ID` header + membership verification |
| JWT claims | Single `tenant_id` | `tenants: [{id, role}]` list + `active_tenant_id` |
| Frontend | Tenant-unaware (delegates to JWT) | Workspace switcher + tenant context provider |
| Registration | Creates User + Tenant + Domain | Creates User only (or User + first Tenant if brand owner) |

---

## Current State Analysis

### What Exists (from Phases 1–9, commit `446d669`)

| Component | Current Implementation | Status |
|-----------|----------------------|--------|
| `Tenant` model | `TenantMixin` with `name`, `schema_name`, subscriptions, GCS buckets | ✅ Keep |
| `Domain` model | `DomainMixin` — `user-{id}.localhost` per user | ⚠️ Rework |
| `JWTTenantMiddleware` | Resolves via `schema_name=user_{user.id}` then JWT fallback | ❌ Replace |
| `get_user_tenant()` | Hardcoded `Tenant.objects.get(schema_name=f"user_{user.id}")` | ❌ Remove |
| `TenantAwareRefreshToken` | Injects single `tenant_id` into JWT | ⚠️ Rework |
| `UserRegistrationView` | Creates Tenant + Domain per user on register | ❌ Rework |
| Views (all apps) | `getattr(request, 'tenant', None)` + FK filtering | ✅ Keep pattern |
| Frontend | Zero tenant awareness, no context provider | ❌ Build |
| `Membership` model | Does not exist | ❌ Create |

### Files That Must Change

| File | Change Type | Impact |
|------|------------|--------|
| `tenants/models.py` | **Add** `Membership` model | New model + migration |
| `brand_automator/auth_views.py` | **Rewrite** registration + JWT logic | Breaking |
| `brand_automator/middleware.py` | **Rewrite** `JWTTenantMiddleware` | Breaking |
| `tenants/views.py` | **Add** tenant switching + membership endpoints | New endpoints |
| `tenants/serializers.py` | **Add** membership serializers | New serializers |
| `tenants/urls.py` | **Add** membership + switching routes | New routes |
| `automation/views.py` | **Add** role-based permission checks | Enhancement |
| `onboarding/views.py` | **Add** role-based permission checks | Enhancement |
| `ai_services/views.py` | **Add** role-based permission checks | Enhancement |
| `subscriptions/views.py` | **Add** OWNER-only billing guard | Enhancement |
| Frontend: `src/contexts/` | **Create** `TenantContext` | New |
| Frontend: `src/components/` | **Create** workspace switcher | New |
| Frontend: `src/lib/api.ts` | **Add** `X-Tenant-ID` header injection | Modification |
| Frontend: `src/hooks/useAuth.ts` | **Rewrite** with tenant awareness | Breaking |
| `scripts/` | **Create** data migration script | One-time |
| `conftest.py` | **Update** fixtures for membership | Test infrastructure |

---

## Phase 1: Membership Model & Database Schema

### 1.1 Create Membership Model

**File**: `tenants/models.py`

```python
class Membership(models.Model):
    """
    Join table linking Users to Tenants with role-based access.
    One user can belong to many tenants. One tenant can have many users.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"       # Full control + billing + delete tenant
        ADMIN = "admin", "Admin"       # Manage users + brand settings
        EDITOR = "editor", "Editor"    # Create/edit assets, run AI, manage content
        VIEWER = "viewer", "Viewer"    # Read-only access

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EDITOR,
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft-disable without removing the record",
    )
    invited_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["user", "tenant"]
        ordering = ["-invited_at"]
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __str__(self):
        return f"{self.user.email} → {self.tenant.name} ({self.role})"
```

### 1.2 Tenant Model Changes

**File**: `tenants/models.py` — Existing `Tenant` model changes:

| Change | Detail |
|--------|--------|
| `schema_name` generation | Change from `user_{id}` to `tenant_{slugify(name)}` |
| Add `slug` field | `SlugField(unique=True)` auto-generated from `name` — used in URLs |
| Remove commented-out `User` model | Clean up dead code at bottom of file |
| Add helper methods | `get_members()`, `get_owner()`, `has_member(user)`, `get_user_role(user)` |

```python
# New methods on Tenant model:

def get_members(self):
    """Return active memberships for this tenant."""
    return self.memberships.filter(is_active=True).select_related("user")

def get_owner(self):
    """Return the owner's User object."""
    membership = self.memberships.filter(
        role=Membership.Role.OWNER, is_active=True
    ).select_related("user").first()
    return membership.user if membership else None

def has_member(self, user):
    """Check if user has an active membership in this tenant."""
    return self.memberships.filter(user=user, is_active=True).exists()

def get_user_role(self, user):
    """Get user's role in this tenant, or None."""
    membership = self.memberships.filter(
        user=user, is_active=True
    ).first()
    return membership.role if membership else None
```

### 1.3 Domain Model Changes

Current: Each user gets `user-{id}.localhost` domain.
New: Each tenant gets `{slug}.localhost` domain. Only needed for `django-tenants` compatibility.

### 1.4 Migration

```bash
python manage.py makemigrations tenants
python manage.py migrate_schemas --shared --noinput
```

### 1.5 Data Migration Script

**File**: `scripts/migrate_to_membership.py`

This script converts the existing 1-to-1 model to the new Membership model:

```
For each existing Tenant with schema_name matching "user_{id}":
  1. Find the User with that id
  2. Create Membership(user=user, tenant=tenant, role=OWNER, is_active=True)
  3. Rename schema_name from "user_{id}" to "tenant_{slugify(tenant.name)}"
  4. Update Domain from "user-{id}.localhost" to "{slug}.localhost"
  5. If tenant has a Company → use company.name as the new tenant.name
```

**Safety**: This is idempotent — skips if Membership already exists for user+tenant pair.

---

## Phase 2: Middleware — X-Tenant-ID Resolution

### 2.1 Rewrite JWTTenantMiddleware

**File**: `brand_automator/middleware.py`

The new middleware resolves tenant from the `X-Tenant-ID` request header and verifies the user has an active membership.

```python
class TenantMembershipMiddleware:
    """
    Resolve tenant from X-Tenant-ID header and verify membership.

    Flow:
    1. Skip if user is not authenticated
    2. Read X-Tenant-ID from request header
    3. If missing: use user's default tenant (first OWNER membership)
    4. Verify user has active Membership for that tenant
    5. Set request.tenant and request.membership
    6. Return 403 if no valid membership
    """

    # Paths that don't require tenant context
    TENANT_EXEMPT_PATHS = [
        "/api/v1/auth/",
        "/api/v1/tenants/me/",       # List user's tenants
        "/api/v1/tenants/switch/",   # Switch active tenant
        "/health",
        "/ready",
        "/alive",
        "/admin",
        "/static",
        "/media",
    ]

    def __call__(self, request):
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return self.get_response(request)

        if self._is_exempt_path(request.path):
            return self.get_response(request)

        tenant_id = self._get_tenant_id(request)
        if tenant_id is None:
            # No tenant specified — use default (first owned tenant)
            tenant_id = self._get_default_tenant_id(request.user)

        if tenant_id is not None:
            membership = self._verify_membership(request.user, tenant_id)
            if membership:
                request.tenant = membership.tenant
                request.membership = membership
                request.user_role = membership.role
            else:
                return JsonResponse(
                    {"error": "You do not have access to this workspace"},
                    status=403,
                )
        else:
            # User has no tenants at all — allow through for
            # tenant creation endpoints
            request.tenant = None
            request.membership = None
            request.user_role = None

        return self.get_response(request)

    def _get_tenant_id(self, request):
        """Extract tenant ID from X-Tenant-ID header."""
        header = request.META.get("HTTP_X_TENANT_ID")
        if header:
            try:
                return int(header)
            except (ValueError, TypeError):
                return None
        return None

    def _get_default_tenant_id(self, user):
        """Get user's default tenant (first owned, then first any)."""
        from tenants.models import Membership
        membership = (
            Membership.objects.filter(user=user, is_active=True)
            .order_by(
                models.Case(
                    models.When(role=Membership.Role.OWNER, then=0),
                    default=1,
                )
            )
            .first()
        )
        return membership.tenant_id if membership else None

    def _verify_membership(self, user, tenant_id):
        """Verify user has active membership for the given tenant."""
        from tenants.models import Membership
        return (
            Membership.objects.filter(
                user=user,
                tenant_id=tenant_id,
                is_active=True,
            )
            .select_related("tenant")
            .first()
        )
```

### 2.2 Settings Update

**File**: `brand_automator/settings.py`

```python
CORS_ALLOW_HEADERS = [
    # ... existing headers ...
    "x-tenant-id",          # NEW: tenant switching header
]
```

### 2.3 Remove Old Functions

| Remove | File |
|--------|------|
| `get_user_tenant()` | `brand_automator/auth_views.py` |
| `_get_tenant_id_from_user()` | `brand_automator/middleware.py` |

---

## Phase 3: JWT & Authentication Changes

### 3.1 Updated JWT Claims

**Current JWT payload**:
```json
{
  "user_id": 20,
  "tenant_id": 24,
  "token_type": "access"
}
```

**New JWT payload**:
```json
{
  "user_id": 20,
  "tenants": [
    {"id": 24, "name": "Bransol", "role": "owner"},
    {"id": 30, "name": "ClientCo", "role": "editor"}
  ],
  "active_tenant_id": 24,
  "token_type": "access"
}
```

### 3.2 Rewrite TenantAwareRefreshToken

**File**: `brand_automator/auth_views.py`

```python
class TenantAwareRefreshToken(RefreshToken):
    """Injects user's tenant memberships into JWT claims."""

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)

        from tenants.models import Membership
        memberships = Membership.objects.filter(
            user=user, is_active=True
        ).select_related("tenant").order_by(
            models.Case(
                models.When(role=Membership.Role.OWNER, then=0),
                default=1,
            ),
            "tenant__name",
        )

        tenant_list = [
            {
                "id": m.tenant_id,
                "name": m.tenant.name,
                "role": m.role,
            }
            for m in memberships
        ]
        token["tenants"] = tenant_list

        # Set active tenant to first owned tenant (or first any)
        if tenant_list:
            token["active_tenant_id"] = tenant_list[0]["id"]

        return token
```

### 3.3 Update EmailTokenObtainPairSerializer

Same pattern as `TenantAwareRefreshToken` — inject `tenants` list and `active_tenant_id` into `get_token()`.

### 3.4 Updated Login Response

```json
{
  "tokens": { "access": "...", "refresh": "..." },
  "user": { "id": 20, "email": "...", "first_name": "...", "last_name": "..." },
  "tenants": [
    { "id": 24, "name": "Bransol", "role": "owner", "slug": "bransol" },
    { "id": 30, "name": "ClientCo", "role": "editor", "slug": "clientco" }
  ],
  "active_tenant_id": 24
}
```

### 3.5 Rewrite Registration Flow

**File**: `brand_automator/auth_views.py` — `UserRegistrationView`

Two registration modes:

**Mode A — Brand Owner Registration** (default):
1. Create `User`
2. Create `Tenant` with `name` from form (or `"{first_name}'s Brand"`)
3. Create `Domain` for the tenant
4. Create `Membership(user, tenant, role=OWNER)`
5. Return JWT with `tenants: [{...}]`

**Mode B — Team Member Registration** (via invite link):
1. Create `User`
2. Accept pending `Membership` invitation (matched by email)
3. Return JWT with `tenants: [{...}]`

```python
class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip()
        password = request.data.get("password", "")
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        brand_name = request.data.get("brand_name", "").strip()
        invite_token = request.data.get("invite_token")

        # ... validation ...

        user = User.objects.create_user(...)

        if invite_token:
            # Mode B: Accept invitation
            membership = self._accept_invitation(user, invite_token)
        else:
            # Mode A: Create brand tenant
            tenant_name = brand_name or f"{first_name}'s Brand"
            tenant = Tenant(
                name=tenant_name,
                schema_name=f"tenant_{slugify(tenant_name)}",
                subscription_status="trial",
            )
            tenant.auto_create_schema = False
            tenant.save()
            Domain.objects.create(
                domain=f"{tenant.slug}.localhost",
                tenant=tenant,
                is_primary=True,
            )
            membership = Membership.objects.create(
                user=user,
                tenant=tenant,
                role=Membership.Role.OWNER,
            )

        refresh = TenantAwareRefreshToken.for_user(user)
        # ... return response with tenants list ...
```

---

## Phase 4: Role-Based Permission System

### 4.1 Permission Classes

**File**: `tenants/permissions.py` (new file)

```python
from rest_framework.permissions import BasePermission


class HasTenantAccess(BasePermission):
    """User must have any active membership in the current tenant."""
    def has_permission(self, request, view):
        return getattr(request, "membership", None) is not None


class IsTenantOwner(BasePermission):
    """User must be tenant OWNER."""
    def has_permission(self, request, view):
        return getattr(request, "user_role", None) == "owner"


class IsTenantAdmin(BasePermission):
    """User must be OWNER or ADMIN."""
    def has_permission(self, request, view):
        return getattr(request, "user_role", None) in ("owner", "admin")


class IsTenantEditor(BasePermission):
    """User must be OWNER, ADMIN, or EDITOR (not VIEWER)."""
    def has_permission(self, request, view):
        return getattr(request, "user_role", None) in ("owner", "admin", "editor")


class IsTenantViewer(BasePermission):
    """User must have any role (even VIEWER). Alias for HasTenantAccess."""
    def has_permission(self, request, view):
        return getattr(request, "membership", None) is not None
```

### 4.2 Role Permission Matrix

| Action | OWNER | ADMIN | EDITOR | VIEWER |
|--------|-------|-------|--------|--------|
| View company/brand data | ✅ | ✅ | ✅ | ✅ |
| View assets & chat history | ✅ | ✅ | ✅ | ✅ |
| Upload/edit brand assets | ✅ | ✅ | ✅ | ❌ |
| Run AI generations | ✅ | ✅ | ✅ | ❌ |
| Create/edit content calendar | ✅ | ✅ | ✅ | ❌ |
| Manage social profiles | ✅ | ✅ | ❌ | ❌ |
| Edit company settings | ✅ | ✅ | ❌ | ❌ |
| Invite/remove members | ✅ | ✅ | ❌ | ❌ |
| Manage subscription/billing | ✅ | ❌ | ❌ | ❌ |
| Delete tenant | ✅ | ❌ | ❌ | ❌ |

### 4.3 Apply Permissions to Views

| View | Permission Class |
|------|-----------------|
| `CompanyViewSet` (list, retrieve) | `IsTenantViewer` |
| `CompanyViewSet` (create, update) | `IsTenantAdmin` |
| `BrandAssetViewSet` (list, retrieve, signed_url) | `IsTenantViewer` |
| `BrandAssetViewSet` (upload, delete) | `IsTenantEditor` |
| `ChatSessionViewSet` (list, retrieve) | `IsTenantViewer` |
| `ChatSessionViewSet` (create) | `IsTenantEditor` |
| `chat_with_ai`, `generate_*` | `IsTenantEditor` |
| `SocialProfileViewSet` | `IsTenantAdmin` |
| `ContentCalendarViewSet` (list, retrieve) | `IsTenantViewer` |
| `ContentCalendarViewSet` (create, update, delete) | `IsTenantEditor` |
| `get_subscription_status` | `IsTenantViewer` |
| `create_checkout_session`, `cancel_subscription` | `IsTenantOwner` |
| `MembershipViewSet` (invite, remove) | `IsTenantAdmin` |
| `TenantViewSet` (delete) | `IsTenantOwner` |

### 4.4 Per-Action Permission Mixin

```python
class RoleBasedPermissionMixin:
    """
    Mixin for ViewSets that need different permissions per action.
    Define role_permissions dict mapping actions to permission classes.
    """
    role_permissions = {}  # Override in subclass

    def get_permissions(self):
        if self.action in self.role_permissions:
            return [perm() for perm in self.role_permissions[self.action]]
        return super().get_permissions()
```

**Example usage**:
```python
class CompanyViewSet(RoleBasedPermissionMixin, ModelViewSet):
    role_permissions = {
        "list": [IsAuthenticated, IsTenantViewer],
        "retrieve": [IsAuthenticated, IsTenantViewer],
        "create": [IsAuthenticated, IsTenantAdmin],
        "update": [IsAuthenticated, IsTenantAdmin],
        "partial_update": [IsAuthenticated, IsTenantAdmin],
    }
```

---

## Phase 5: Tenant Management API

### 5.1 New Endpoints

| Method | Path | Description | Permission |
|--------|------|-------------|------------|
| `GET` | `/api/v1/tenants/me/` | List user's tenant memberships | Authenticated |
| `POST` | `/api/v1/tenants/` | Create new tenant (brand) | Authenticated |
| `POST` | `/api/v1/tenants/switch/` | Set active tenant (returns new JWT) | Authenticated |
| `GET` | `/api/v1/tenants/{id}/members/` | List tenant members | `IsTenantAdmin` |
| `POST` | `/api/v1/tenants/{id}/members/invite/` | Invite member by email | `IsTenantAdmin` |
| `PATCH` | `/api/v1/tenants/{id}/members/{membership_id}/` | Change member role | `IsTenantAdmin` |
| `DELETE` | `/api/v1/tenants/{id}/members/{membership_id}/` | Remove member | `IsTenantAdmin` |
| `POST` | `/api/v1/tenants/accept-invite/` | Accept invite (by token) | Authenticated |

### 5.2 Tenant Switching Endpoint

**POST** `/api/v1/tenants/switch/`

```json
// Request
{ "tenant_id": 30 }

// Response — new JWT pair with updated active_tenant_id
{
  "tokens": { "access": "...", "refresh": "..." },
  "active_tenant": { "id": 30, "name": "ClientCo", "role": "editor" }
}
```

This endpoint:
1. Verifies user has active Membership for the requested tenant
2. Issues a new JWT with `active_tenant_id` set to the requested tenant
3. Frontend stores new tokens and updates `X-Tenant-ID` header

### 5.3 Member Invitation Flow

```
ADMIN calls POST /tenants/{id}/members/invite/
  → Body: { "email": "editor@example.com", "role": "editor" }
  → Backend creates Membership(user=None, email=..., role=..., is_active=False)
  → Sends invitation email with unique token
  → Returns 201

Invitee clicks link → registers (or logs in if existing user)
  → POST /tenants/accept-invite/ { "token": "..." }
  → Backend activates Membership, sets user FK
  → Returns updated tenants list
```

**Pre-existing user scenario**: If the invited email belongs to an existing user:
- Create Membership immediately with `is_active=True`
- No invite token needed — the membership appears in their workspace list on next login

### 5.4 Serializers

**File**: `tenants/serializers.py`

```python
class MembershipSerializer(ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["id", "user_email", "user_name", "role", "is_active",
                  "invited_at", "accepted_at"]

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()


class TenantWithRoleSerializer(ModelSerializer):
    """Tenant info + the requesting user's role."""
    role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "role", "member_count",
                  "subscription_status", "created_at"]

    def get_role(self, obj):
        user = self.context["request"].user
        return obj.get_user_role(user)

    def get_member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()


class InviteMemberSerializer(Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership.Role.choices)
```

---

## Phase 6: Per-Tenant GCS Buckets

### 6.0 Overview

**Goal**: Every tenant gets its own dedicated GCS buckets — one for raw/ingestion assets, one for curated output. This replaces the current single-shared-bucket model where all tenants' files land in the same bucket with path-prefix isolation.

**Current state (3 bucket "worlds" sharing across all tenants)**:

| Purpose | Settings Key | Default Bucket | Used By |
|---------|-------------|----------------|---------|
| Direct file uploads | `GS_BUCKET_NAME` | `brand-automator-assets` | `files/services.py` (`GCSService` singleton) |
| Ingestion pipeline (raw) | `DATA_INGESTION["GCP_BUCKET_NAME"]` | `onboarding-bucket1` | `data_ingestion/factory.py`, `onboarding/services.py` |
| Curation pipeline (curated) | `MEDIA_CURATION["STORAGE"]["CURATED_BUCKET"]` | `brandsol-curation-bucket` | `media_curation/factory.py` |

**Target state**: Each tenant resolves to its own pair of GCS buckets. The shared defaults remain as a fallback for tenants that don't have custom buckets (e.g. the public tenant).

```
Tenant "Bransol" (slug: bransol)
  ├── Raw bucket:     bransol-raw
  └── Curated bucket: bransol-curated

Tenant "ClientCo" (slug: clientco)
  ├── Raw bucket:     clientco-raw
  └── Curated bucket: clientco-curated
```

### 6.1 Tenant Model — Fields Already Exist

The `Tenant` model already has `gcs_raw_bucket` and `gcs_curated_bucket` fields (added earlier), with fallback helpers:

```python
# tenants/models.py — already implemented
def get_raw_bucket(self):
    if self.gcs_raw_bucket:
        return self.gcs_raw_bucket
    return settings.DATA_INGESTION.get("GCP_BUCKET_NAME", "onboarding-bucket1")

def get_curated_bucket(self):
    if self.gcs_curated_bucket:
        return self.gcs_curated_bucket
    return settings.MEDIA_CURATION["STORAGE"].get("CURATED_BUCKET", "brandsol-curation-bucket")
```

**No model changes needed** — the schema is ready. We need to wire these methods into every GCS touchpoint.

### 6.2 TenantGCSService — Bucket Provisioning

**File**: `tenants/services.py` (new)

Create a service that provisions GCS buckets for a tenant on creation. Bucket naming convention: `{slug}-raw` and `{slug}-curated`.

```python
class TenantGCSService:
    """Provision and manage per-tenant GCS buckets."""

    PROJECT_ID_KEY = "GCP_PROJECT_ID"
    LOCATION = "us-central1"

    def __init__(self, credentials_path=None):
        from google.cloud import storage as gcs
        self.client = gcs.Client(project=self._get_project_id())

    def create_tenant_buckets(self, tenant):
        """Create raw + curated GCS buckets for a tenant.

        Idempotent: skips if bucket already exists.
        Updates the Tenant record with bucket names.
        """
        raw_name = f"{tenant.slug}-raw"
        curated_name = f"{tenant.slug}-curated"

        self._ensure_bucket(raw_name)
        self._ensure_bucket(curated_name)

        tenant.gcs_raw_bucket = raw_name
        tenant.gcs_curated_bucket = curated_name
        tenant.save(update_fields=["gcs_raw_bucket", "gcs_curated_bucket"])

    def delete_tenant_buckets(self, tenant):
        """Delete a tenant's GCS buckets (used on tenant deletion).

        Only deletes if the bucket matches the expected naming pattern.
        """
        for bucket_name in [tenant.gcs_raw_bucket, tenant.gcs_curated_bucket]:
            if bucket_name:
                self._delete_bucket(bucket_name)

    def _ensure_bucket(self, bucket_name):
        """Create a bucket if it doesn't exist."""
        bucket = self.client.bucket(bucket_name)
        if not bucket.exists():
            bucket.storage_class = "STANDARD"
            self.client.create_bucket(bucket, location=self.LOCATION)
            # Set lifecycle: delete objects older than 365 days (optional)
            bucket.add_lifecycle_delete_rule(age=365)
            bucket.patch()

    def _delete_bucket(self, bucket_name):
        """Delete a bucket and all its contents."""
        try:
            bucket = self.client.bucket(bucket_name)
            bucket.delete(force=True)
        except Exception:
            logger.warning("Failed to delete bucket %s", bucket_name)

    @staticmethod
    def _get_project_id():
        from decouple import config
        return config("GCP_PROJECT_ID", default="brandsol")
```

### 6.3 Tenant Signal — Auto-Provision on Creation

**File**: `tenants/signals.py` (update existing)

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Tenant


@receiver(post_save, sender=Tenant)
def provision_tenant_buckets(sender, instance, created, **kwargs):
    """Auto-provision GCS buckets when a new tenant is created.

    Skips the public tenant and tenants that already have buckets set.
    Only runs when GCS provisioning is enabled (not in tests).
    """
    if not created:
        return
    if instance.schema_name == "public":
        return
    if instance.gcs_raw_bucket and instance.gcs_curated_bucket:
        return  # Already provisioned

    from decouple import config
    if not config("GCS_AUTO_PROVISION", default=False, cast=bool):
        return

    try:
        from .services import TenantGCSService
        service = TenantGCSService()
        service.create_tenant_buckets(instance)
    except Exception:
        logger.warning(
            "Failed to auto-provision GCS buckets for tenant %s",
            instance.slug,
        )
```

**New env var**: `GCS_AUTO_PROVISION=true` (disabled in dev/test, enabled in production).

### 6.4 Wire GCSService to Accept Tenant Bucket

**File**: `files/services.py`

The `GCSService` singleton currently uses one global `bucket_name`. Add a method that accepts an explicit bucket override:

| Change | Detail |
|--------|--------|
| Add `get_bucket(bucket_name=None)` method | Returns the specified bucket or falls back to the default |
| Update `upload_file()` | Accept optional `bucket_name` parameter |
| Update `generate_signed_url()` | Accept optional `bucket_name` parameter |
| Update `delete_file()` | Accept optional `bucket_name` parameter |

```python
# files/services.py — changes

class GCSService:
    def get_bucket(self, bucket_name=None):
        """Return a GCS bucket object.

        If bucket_name is provided, return that bucket.
        Otherwise, return the default bucket.
        """
        name = bucket_name or self.bucket_name
        return self.client.bucket(name)

    def upload_file(self, file_obj, destination_path, content_type=None, bucket_name=None):
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(destination_path)
        blob.upload_from_file(file_obj, content_type=content_type)
        return blob.public_url

    def generate_signed_url(self, blob_path, expiration_minutes=60, bucket_name=None):
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob.generate_signed_url(
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )

    def delete_file(self, blob_path, bucket_name=None):
        bucket = self.get_bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.delete()
```

### 6.5 Wire Onboarding Views to Tenant Bucket

**File**: `onboarding/views.py` — `BrandAssetViewSet`

| Action | Current | New |
|--------|---------|-----|
| `upload` | `gcs_service.bucket_name` | `tenant.get_raw_bucket()` |
| `confirm_gcs_upload` | Hardcoded `"brand-automator-assets"` | `tenant.get_raw_bucket()` |
| `signed_url` | `gcs_service.generate_signed_url(path)` — ignores `asset.gcs_bucket` | `gcs_service.generate_signed_url(path, bucket_name=asset.gcs_bucket)` |
| `destroy` | `gcs_service.delete_file(path)` — may use wrong bucket | `gcs_service.delete_file(path, bucket_name=asset.gcs_bucket)` |

```python
# onboarding/views.py — upload action (key change)

tenant = getattr(request, "tenant", None)
raw_bucket = tenant.get_raw_bucket() if tenant else gcs_service.bucket_name

# Use raw_bucket for upload
bucket = gcs_service.get_bucket(raw_bucket)
blob = bucket.blob(gcs_path)
blob.upload_from_file(file, content_type=content_type)

# Store on asset
asset.gcs_bucket = raw_bucket
asset.gcs_path = gcs_path
asset.save()
```

### 6.6 Wire Onboarding Services to Tenant Bucket

**File**: `onboarding/services.py`

| Method | Current | New |
|--------|---------|-----|
| `_get_default_bucket()` | `DATA_INGESTION["GCP_BUCKET_NAME"]` | Accept `tenant` param → `tenant.get_raw_bucket()` |
| `_build_ingestion_event()` | Falls back to default bucket | Falls back to `tenant.get_raw_bucket()` |

```python
def _get_default_bucket(self, tenant=None):
    if tenant:
        return tenant.get_raw_bucket()
    return self.pipeline_config.get("GCP_BUCKET_NAME", "onboarding-bucket1")
```

### 6.7 Wire Data Ingestion Factory

**File**: `data_ingestion/factory.py`

```python
def create_gcs_adapter(tenant=None):
    """Create a GCS storage adapter.

    If tenant is provided, use the tenant's raw bucket.
    Otherwise, fall back to the global default.
    """
    if tenant:
        default_bucket = tenant.get_raw_bucket()
    else:
        default_bucket = settings.DATA_INGESTION.get(
            "GCP_BUCKET_NAME", "onboarding-bucket1"
        )
    return GCSStorageAdapter(default_bucket=default_bucket)
```

### 6.8 Wire Media Curation Factory

**File**: `media_curation/factory.py`

```python
def create_storage_adapter(tenant=None):
    """Create a GCS storage adapter for curated output.

    If tenant is provided, use the tenant's curated bucket.
    Otherwise, fall back to the global default.
    """
    if tenant:
        curated_bucket = tenant.get_curated_bucket()
    else:
        curated_bucket = settings.MEDIA_CURATION["STORAGE"].get(
            "CURATED_BUCKET", "brandsol-curation-bucket"
        )
    return GCSStorageAdapter(default_bucket=curated_bucket)

def create_curation_service(tenant=None):
    storage = create_storage_adapter(tenant)
    output_bucket = tenant.get_curated_bucket() if tenant else (
        settings.MEDIA_CURATION["STORAGE"].get("CURATED_BUCKET", "brandsol-curation-bucket")
    )
    return CurationService(storage_adapter=storage, output_bucket=output_bucket)
```

### 6.9 Wire Tenant Context Through Pipelines

The data ingestion and media curation pipelines are triggered via **Kafka events** or **Celery tasks**. The tenant context must be passed through:

| Trigger | Current Payload | New Payload |
|---------|----------------|-------------|
| Kafka ingestion event | `file_path`, `company_id` | + `tenant_id`, `raw_bucket` |
| Kafka curation event | `source_gcs_uri` | + `tenant_id`, `curated_bucket` |
| Celery task args | `asset_id` | + `tenant_id` |

```python
# onboarding/services.py — _build_ingestion_event()
def _build_ingestion_event(self, asset, tenant=None):
    raw_bucket = tenant.get_raw_bucket() if tenant else self._get_default_bucket()
    return {
        "file_path": f"gs://{raw_bucket}/{asset.gcs_path}",
        "company_id": asset.company_id,
        "tenant_id": tenant.id if tenant else None,
        "raw_bucket": raw_bucket,
        "curated_bucket": tenant.get_curated_bucket() if tenant else None,
        # ... existing fields ...
    }
```

Consumers (`data_ingestion/consumers/`, `media_curation/consumers/`) will read `tenant_id` from the event, load the `Tenant`, and pass it to the factory functions.

### 6.10 Backfill Existing Tenants

**File**: `scripts/provision_tenant_buckets.py` (new)

One-time script to create GCS buckets for all existing tenants that don't yet have them:

```python
"""
Provision GCS buckets for all existing tenants.

Usage:
    python scripts/provision_tenant_buckets.py --dry-run
    python scripts/provision_tenant_buckets.py --apply
"""
for tenant in Tenant.objects.exclude(schema_name="public"):
    if not tenant.gcs_raw_bucket or not tenant.gcs_curated_bucket:
        service.create_tenant_buckets(tenant)
        print(f"Provisioned: {tenant.slug} → {tenant.gcs_raw_bucket}, {tenant.gcs_curated_bucket}")
```

### 6.11 Tests

| Test | Description |
|------|-------------|
| `test_create_tenant_provisions_buckets` | Signal creates buckets when `GCS_AUTO_PROVISION=true` |
| `test_no_provision_in_tests` | Signal skips when `GCS_AUTO_PROVISION=false` |
| `test_get_raw_bucket_custom` | `Tenant.get_raw_bucket()` returns custom bucket |
| `test_get_raw_bucket_default` | `Tenant.get_raw_bucket()` returns settings default when field is blank |
| `test_upload_uses_tenant_bucket` | `BrandAssetViewSet.upload` stores `tenant.get_raw_bucket()` as `asset.gcs_bucket` |
| `test_signed_url_uses_asset_bucket` | `signed_url` action passes `asset.gcs_bucket` to GCS |
| `test_ingestion_event_includes_tenant_bucket` | Kafka event payload has `raw_bucket` and `curated_bucket` |
| `test_curation_factory_uses_tenant_bucket` | `create_curation_service(tenant)` uses tenant's curated bucket |
| `test_backfill_script_idempotent` | Running twice doesn't duplicate buckets |

---

## Phase 7: Frontend Changes

### 6.1 Tenant Context Provider

**File**: `src/contexts/TenantContext.tsx` (new)

```tsx
interface TenantInfo {
  id: number;
  name: string;
  slug: string;
  role: 'owner' | 'admin' | 'editor' | 'viewer';
}

interface TenantContextValue {
  tenants: TenantInfo[];
  activeTenant: TenantInfo | null;
  switchTenant: (tenantId: number) => Promise<void>;
  isLoading: boolean;
}
```

Stored in `localStorage`:
- `tenants` — JSON array of `TenantInfo`
- `active_tenant_id` — current workspace ID

### 6.2 API Client Update

**File**: `src/lib/api.ts`

```typescript
// Inject X-Tenant-ID header on every request
const activeTenantId = localStorage.getItem('active_tenant_id');
if (activeTenantId) {
  headers['X-Tenant-ID'] = activeTenantId;
}
```

### 6.3 Workspace Switcher Component

**File**: `src/components/layout/WorkspaceSwitcher.tsx` (new)

Location: Top of sidebar (or header dropdown)

```
┌─────────────────────────┐
│ 🏢 Bransol          ▼  │  ← Active workspace
├─────────────────────────┤
│   Bransol    (Owner)    │  ← Current (highlighted)
│   ClientCo   (Editor)   │
│   ─────────────────     │
│   + Create New Brand    │
└─────────────────────────┘
```

Behavior:
- Shows active tenant name in a dropdown trigger
- Lists all user's tenants with their role badge
- Clicking a tenant calls `POST /api/v1/tenants/switch/`, stores new tokens
- "Create New Brand" opens a modal → `POST /api/v1/tenants/`

### 6.4 Registration Page Update

**File**: `src/components/auth/RegisterForm.tsx`

Add optional `brand_name` field:

```
┌─────────────────────────┐
│ First Name              │
│ Last Name               │
│ Email                   │
│ Password                │
│ Brand Name (optional)   │  ← NEW
│                         │
│ [Create Account]        │
└─────────────────────────┘
```

If `brand_name` is provided, backend creates the brand tenant. If omitted, uses `"{first_name}'s Brand"` as default.

### 6.5 Team Management Page

**File**: `src/app/dashboard/team/page.tsx` (new)

Only visible to OWNER and ADMIN roles:

```
┌─────────────────────────────────────────┐
│ Team Members                    [Invite]│
├─────────────────────────────────────────┤
│ naveen@gmail.com    Owner    [─]        │
│ editor@gmail.com    Editor   [🔧] [✕]  │
│ viewer@gmail.com    Viewer   [🔧] [✕]  │
└─────────────────────────────────────────┘
```

- `[Invite]` — opens invite modal (email + role picker)
- `[🔧]` — change role dropdown
- `[✕]` — remove member (with confirmation)
- OWNER row cannot be removed or demoted

### 6.6 Role-Based UI Guards

```tsx
// src/hooks/useTenantRole.ts
export function useTenantRole() {
  const { activeTenant } = useTenantContext();
  return {
    role: activeTenant?.role,
    isOwner: activeTenant?.role === 'owner',
    isAdmin: ['owner', 'admin'].includes(activeTenant?.role ?? ''),
    isEditor: ['owner', 'admin', 'editor'].includes(activeTenant?.role ?? ''),
    canEdit: ['owner', 'admin', 'editor'].includes(activeTenant?.role ?? ''),
    canManageTeam: ['owner', 'admin'].includes(activeTenant?.role ?? ''),
    canManageBilling: activeTenant?.role === 'owner',
  };
}
```

Hide/disable UI elements based on role:
- Sidebar: Hide "Team" and "Billing" for non-admin/non-owner
- Upload button: Hidden for VIEWER
- AI generation buttons: Hidden for VIEWER
- Settings page: Read-only for EDITOR/VIEWER

---

## Phase 8: Data Migration

### 8.1 Migration Script

**File**: `scripts/migrate_to_membership.py`

```python
"""
One-time migration: Convert user_{id} tenants to membership-based model.

For each Tenant with schema_name matching "user_{N}":
  1. Find User N
  2. Create Membership(user=N, tenant=T, role=OWNER)
  3. If tenant has a Company → rename tenant to company.name
  4. Regenerate schema_name as tenant_{slug}
  5. Update Domain record

Idempotent: skips if Membership already exists.
"""
```

### 8.2 Expected Data Changes

Current state (48 users, ~50 tenants):

| Before | After |
|--------|-------|
| `Tenant(schema_name="user_20", name="Naveen Hanuman")` | `Tenant(schema_name="tenant_bransol", name="Bransol", slug="bransol")` |
| No Membership records | `Membership(user=20, tenant=24, role=OWNER)` |
| Domain `user-20.localhost` | Domain `bransol.localhost` |

### 8.3 Rollback Strategy

- Keep old `schema_name` in a backup field (`old_schema_name`) during migration
- Migration script is reversible — can recreate `user_{id}` convention from backup field
- No actual PostgreSQL schemas are affected (we use shared-schema FK filtering)

---

## Phase 9: Fix Existing Bugs

While refactoring, address these known issues:

| Bug | File | Fix |
|-----|------|-----|
| Direct `request.tenant` access | `ai_services/serializers.py` L30 | Change to `getattr(self.context["request"], "tenant", None)` |
| Missing `perform_create` | `automation/views.py` `SocialProfileViewSet` | Add tenant attachment on create |
| Register doesn't auto-login | Frontend `RegisterForm.tsx` | Store returned tokens + redirect to dashboard |

---

## Phase 10: Testing Strategy

### 10.1 New Test Fixtures

**File**: `conftest.py`

```python
@pytest.fixture
def membership_owner(tenant, user):
    """User as OWNER of tenant."""
    return Membership.objects.create(
        user=user, tenant=tenant, role=Membership.Role.OWNER
    )

@pytest.fixture
def membership_editor(tenant):
    """A different user as EDITOR of tenant."""
    editor = User.objects.create_user(
        username="editor", email="editor@test.com", password="testpass123!"
    )
    return Membership.objects.create(
        user=editor, tenant=tenant, role=Membership.Role.EDITOR
    )

@pytest.fixture
def membership_viewer(tenant):
    """A different user as VIEWER of tenant."""
    viewer = User.objects.create_user(
        username="viewer", email="viewer@test.com", password="testpass123!"
    )
    return Membership.objects.create(
        user=viewer, tenant=tenant, role=Membership.Role.VIEWER
    )
```

### 10.2 Test Categories

| Category | Tests | Description |
|----------|-------|-------------|
| Membership CRUD | 10+ | Create, update role, deactivate, delete membership |
| Tenant switching | 5+ | Switch via API, verify JWT updated, verify no cross-tenant leak |
| Role enforcement | 20+ | Each role × each action = verify 403 for unauthorized |
| Data isolation | 10+ | User in Tenant A cannot see Tenant B data regardless of header |
| GCS bucket isolation | 10+ | Upload uses tenant bucket, signed URLs use asset bucket, pipeline events carry correct buckets |
| Registration modes | 5+ | Brand owner signup, invite-based signup, existing user invite |
| Migration | 3+ | Test data migration script idempotency and correctness |
| Frontend | 5+ | Workspace switcher renders, tenant context updates, role guards |

### 10.3 Critical Test Scenarios

1. **Cross-tenant data isolation**: User with EDITOR role in Tenant A sends `X-Tenant-ID: B` (where they have no membership) → gets 403
2. **Role downgrade**: VIEWER tries to upload asset → gets 403
3. **Multi-tenant user**: User is OWNER of Tenant A and EDITOR of Tenant B → can create content in both, can only manage billing in A
4. **Invite flow**: ADMIN invites email → person registers → automatically gains membership → sees the tenant in their workspace list
5. **Owner protection**: Cannot remove the last OWNER of a tenant → 400 error

---

## Phase 11: Deployment Updates

### 11.1 Migration Commands

Add to startup scripts:
```bash
python manage.py migrate_schemas --shared --noinput
python scripts/migrate_to_membership.py       # One-time, idempotent
python scripts/provision_tenant_buckets.py     # One-time — creates GCS buckets for existing tenants
```

### 11.2 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `X-Tenant-ID` header | N/A | Application-level tenant switching (no env var needed) |
| `GCS_AUTO_PROVISION` | `false` | Set to `true` in production to auto-create GCS buckets on tenant creation |
| `GCP_PROJECT_ID` | `brandsol` | GCP project for bucket provisioning |

### 11.3 Kong Gateway

Add `X-Tenant-ID` to Kong's allowed headers (pass-through to backend):

```yaml
# deployment/config/kong/kong.yml
plugins:
  - name: cors
    config:
      headers:
        - Authorization
        - Content-Type
        - X-Tenant-ID     # NEW
```

---

## Phase Execution Order

```
Phase 1 (Membership Model)           ✅ Done
    │
    ▼
Phase 2 (Middleware — X-Tenant-ID)   ✅ Done
    │
    ▼
Phase 3 (JWT & Auth Changes) ──────► Phase 8 (Data Migration)
    │         ✅ Done                       │
    ▼                                       ▼
Phase 4 (Role-Based Permissions)     Run migration on DB
    │         ✅ Done
    ▼
Phase 5 (Tenant Management API)      ✅ Done
    │
    ▼
Phase 6 (Per-Tenant GCS Buckets)
    │
    ▼
Phase 7 (Frontend Changes)
    │
    ▼
Phase 9 (Fix Existing Bugs)
    │
    ▼
Phase 10 (Testing)
    │
    ▼
Phase 11 (Deployment)
```

**Phases 1–3** are foundational and must be done in order. ✅ Complete.
**Phases 4–5** build on the new model. ✅ Complete.
**Phase 6** (GCS) wires tenant-aware bucket routing into all upload/pipeline code.
**Phase 7** (frontend) can start after Phase 6 — needs to pass `X-Tenant-ID` which determines buckets.
**Phase 8** (data migration) can run anytime after Phase 1 but before Phase 7.
**Phases 9–11** are polish, testing, and deployment.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Existing JWTs invalid after migration | Old JWTs still have `tenant_id` — middleware falls back to default tenant if `X-Tenant-ID` missing. Grace period before old tokens expire (7 days). |
| Data migration breaks production | Script is idempotent + has dry-run mode. Backup DB before running. |
| Role enforcement breaks existing users | All existing users become OWNER of their tenant — no permission loss. |
| Frontend breaks during transition | `X-Tenant-ID` is optional — middleware uses default tenant if missing. Gradual rollout. |
| Performance: Membership query per request | Single indexed query (`user_id + tenant_id + is_active`) — <1ms. Cache in request lifecycle. |
| `unique_together` on Membership | Prevents duplicate memberships. Upsert pattern for invitations. |

---

## Estimated Effort

| Phase | Effort | Dependencies | Status |
|-------|--------|-------------|--------|
| Phase 1: Membership Model | 2-3 hours | None | ✅ Done |
| Phase 2: Middleware | 1-2 hours | Phase 1 | ✅ Done |
| Phase 3: JWT & Auth | 2-3 hours | Phase 1 | ✅ Done |
| Phase 4: Permissions | 2-3 hours | Phase 2 | ✅ Done |
| Phase 5: Tenant API | 3-4 hours | Phase 1, 4 | ✅ Done |
| Phase 6: Per-Tenant GCS Buckets | 4-5 hours | Phase 5 | ⬜ Next |
| Phase 7: Frontend | 4-6 hours | Phase 3, 5, 6 | ⬜ |
| Phase 8: Data Migration | 1-2 hours | Phase 1, 6 | ⬜ |
| Phase 9: Bug Fixes | 1 hour | Any time | ⬜ |
| Phase 10: Testing | 3-4 hours | All phases | ⬜ |
| Phase 11: Deployment | 1-2 hours | All phases | ⬜ |
| **Total** | **~25-35 hours** | | |

---

## Appendix: Files Changed Summary

### New Files
- `tenants/models.py` — `Membership` class (addition)
- `tenants/permissions.py` — Role-based permission classes
- `tenants/services.py` — `TenantGCSService` for bucket provisioning
- `scripts/migrate_to_membership.py` — Data migration
- `scripts/provision_tenant_buckets.py` — Backfill GCS buckets for existing tenants
- Frontend: `src/contexts/TenantContext.tsx`
- Frontend: `src/components/layout/WorkspaceSwitcher.tsx`
- Frontend: `src/app/dashboard/team/page.tsx`
- Frontend: `src/hooks/useTenantRole.ts`

### Modified Files
- `tenants/models.py` — Tenant.slug, helper methods
- `tenants/serializers.py` — Membership + TenantWithRole serializers
- `tenants/views.py` — Membership endpoints, tenant switching
- `tenants/urls.py` — New routes
- `tenants/signals.py` — Auto-provision GCS buckets on tenant creation
- `brand_automator/auth_views.py` — Registration + JWT rewrite
- `brand_automator/middleware.py` — TenantMembershipMiddleware replaces JWTTenantMiddleware
- `brand_automator/settings.py` — CORS headers, middleware name
- `files/services.py` — `GCSService` accepts optional `bucket_name` override
- `onboarding/views.py` — Permission classes + tenant-aware bucket routing
- `onboarding/services.py` — `_get_default_bucket()` accepts tenant param
- `ai_services/views.py` — Permission classes
- `ai_services/serializers.py` — Fix direct `request.tenant` bug
- `automation/views.py` — Permission classes + fix missing `perform_create`
- `subscriptions/views.py` — OWNER-only billing guards
- `data_ingestion/factory.py` — `create_gcs_adapter()` accepts tenant param
- `media_curation/factory.py` — `create_storage_adapter()` / `create_curation_service()` accept tenant param
- `conftest.py` — Membership fixtures
- Frontend: `src/lib/api.ts` — X-Tenant-ID header
- Frontend: `src/hooks/useAuth.ts` — Tenant-aware auth
- Frontend: `src/components/auth/RegisterForm.tsx` — Brand name field
- Frontend: `src/components/auth/LoginForm.tsx` — Store tenant data
