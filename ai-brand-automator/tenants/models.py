from django.db import models
from django.utils.text import slugify
from django_tenants.models import TenantMixin, DomainMixin
from django.utils import timezone


class Tenant(TenantMixin):
    """
    Tenant model for multi-tenancy.
    Each tenant represents an enterprise customer.

    We use shared-schema with FK-based tenant filtering,
    NOT per-tenant PostgreSQL schemas. This flag prevents
    django-tenants from creating separate schemas on save().
    """

    auto_create_schema = False

    name = models.CharField(max_length=100, help_text="Company/Organization name")
    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True,
        help_text="URL-friendly identifier, auto-generated from name",
    )
    description = models.TextField(
        blank=True, help_text="Brief description of the company"
    )

    # Schema name will be auto-generated from name
    schema_name = models.CharField(
        max_length=63,
        unique=True,
        blank=True,
        help_text="Database schema name",
    )

    # Subscription information
    subscription_status = models.CharField(
        max_length=20,
        choices=[
            ("trial", "Trial"),
            ("active", "Active"),
            ("past_due", "Past Due"),
            ("canceled", "Canceled"),
            ("unpaid", "Unpaid"),
        ],
        default="trial",
    )
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)

    # Metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Tenant-specific settings
    max_users = models.PositiveIntegerField(
        default=10, help_text="Maximum number of users allowed"
    )
    storage_limit_gb = models.PositiveIntegerField(
        default=5, help_text="Storage limit in GB"
    )

    # Per-tenant GCS buckets (optional — defaults to shared buckets from settings)
    gcs_raw_bucket = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "GCS bucket for raw/ingestion assets. " "Leave blank for shared default."
        ),
    )
    gcs_curated_bucket = models.CharField(
        max_length=255,
        blank=True,
        help_text="GCS bucket for curated assets. Leave blank for shared default.",
    )

    # Per-tenant Vertex AI data store (optional — defaults to shared data store)
    vertex_ai_data_store_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Vertex AI data store ID. Leave blank for shared default.",
    )

    def get_raw_bucket(self):
        """Resolve GCS raw bucket: tenant-specific or shared default.

        Falls back to GS_BUCKET_NAME (the same bucket the GCS service uses)
        so uploads don't target a non-existent bucket.
        """
        if self.gcs_raw_bucket:
            return self.gcs_raw_bucket
        from django.conf import settings

        # Primary: use the GCS service's bucket (GS_BUCKET_NAME)
        gs_bucket = getattr(settings, "GS_BUCKET_NAME", "")
        if gs_bucket:
            return gs_bucket
        # Fallback: DATA_INGESTION pipeline config
        pipeline_cfg = getattr(settings, "DATA_INGESTION", {})
        return pipeline_cfg.get("GCP_BUCKET_NAME", "onboarding-bucket1")

    def get_curated_bucket(self):
        """Resolve GCS curated bucket: tenant-specific or shared default."""
        if self.gcs_curated_bucket:
            return self.gcs_curated_bucket
        from django.conf import settings

        curation_cfg = getattr(settings, "MEDIA_CURATION", {})
        storage_cfg = curation_cfg.get("STORAGE", {})
        return storage_cfg.get("CURATED_BUCKET", "brandsol-curation-bucket")

    def get_data_store_id(self):
        """Resolve Vertex AI data store: tenant-specific or shared default."""
        if self.vertex_ai_data_store_id:
            return self.vertex_ai_data_store_id
        from django.conf import settings

        return getattr(settings, "VERTEX_AI_DATA_STORE_ID", "zorven-rag-dev")

    def save(self, *args, **kwargs):
        # Auto-generate slug from name if not provided
        if not self.slug:
            base_slug = slugify(self.name)
            if not base_slug:
                base_slug = "workspace"
            slug = base_slug
            counter = 1
            while Tenant.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        # Auto-generate schema_name from slug if not provided
        if not self.schema_name:
            import re

            schema_name = re.sub(r"[^a-zA-Z0-9_]", "_", self.slug)
            schema_name = f"tenant_{schema_name}"
            counter = 1
            original_schema = schema_name
            while Tenant.objects.filter(schema_name=schema_name).exists():
                schema_name = f"{original_schema}_{counter}"
                counter += 1
            self.schema_name = schema_name
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"

    def __str__(self):
        return self.name

    @property
    def is_subscription_active(self):
        return self.subscription_status in ["active", "trial"]

    # --- Membership helper methods ---

    def get_members(self):
        """Return active memberships for this tenant."""
        return self.memberships.filter(is_active=True).select_related("user")

    def get_owner(self):
        """Return the owner's User object, or None."""
        membership = (
            self.memberships.filter(role=Membership.Role.OWNER, is_active=True)
            .select_related("user")
            .first()
        )
        return membership.user if membership else None

    def has_member(self, user):
        """Check if user has an active membership in this tenant."""
        return self.memberships.filter(user=user, is_active=True).exists()

    def get_user_role(self, user):
        """Get user's role in this tenant, or None."""
        membership = self.memberships.filter(user=user, is_active=True).first()
        return membership.role if membership else None


class Domain(DomainMixin):
    """
    Domain model for tenant domains.
    """

    pass


class Membership(models.Model):
    """
    Join table linking Users to Tenants with role-based access.

    One user can belong to many tenants. One tenant can have many users.
    The role determines what the user can do within the tenant.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        EDITOR = "editor", "Editor"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memberships",
        help_text="Null for pending invitations to users not yet registered.",
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
    invited_email = models.EmailField(
        null=True,
        blank=True,
        help_text="Email for pending invites (user not yet registered).",
    )
    invited_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )
    invited_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    invite_token = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        help_text="Unique token for accepting an invitation via link.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"],
                condition=models.Q(user__isnull=False),
                name="unique_membership_per_user_tenant",
            ),
        ]
        ordering = ["-invited_at"]
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __str__(self):
        label = self.user.email if self.user else self.invited_email or "pending"
        return f"{label} \u2192 {self.tenant.name} ({self.role})"
