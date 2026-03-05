from django.contrib import admin

from .models import Domain, Membership, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):  # TenantAdminMixin temporarily disabled
    list_display = (
        "name",
        "get_primary_domain",
        "subscription_status",
        "created_at",
    )
    list_filter = ("subscription_status", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def get_primary_domain(self, obj):
        return obj.get_primary_domain()

    get_primary_domain.short_description = "Domain"
    get_primary_domain.admin_order_field = "domains__domain"

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "slug", "description", "schema_name")},
        ),
        (
            "Subscription",
            {"fields": ("subscription_status", "stripe_customer_id")},
        ),
        ("Limits", {"fields": ("max_users", "storage_limit_gb")}),
        (
            "Storage (GCS)",
            {
                "fields": ("gcs_raw_bucket", "gcs_curated_bucket"),
                "classes": ("collapse",),
                "description": "Leave blank to use shared default buckets.",
            },
        ),
        (
            "Vertex AI (RAG)",
            {
                "fields": ("vertex_ai_data_store_id",),
                "classes": ("collapse",),
                "description": "Leave blank to use shared default data store.",
            },
        ),
        (
            "Metadata",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain", "tenant__name")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active", "invited_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "user__username", "tenant__name")
    raw_id_fields = ("user", "tenant", "invited_by")
    readonly_fields = ("invited_at",)
