from django.contrib import admin

# from django.contrib.auth.admin import UserAdmin
# from django_tenants.admin import TenantAdminMixin  # Temporarily disabled
from .models import Tenant, Domain

# from .models import User


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
        ("Basic Information", {"fields": ("name", "description", "schema_name")}),
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
            "Metadata",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain", "tenant__name")


# Custom User admin temporarily disabled
# @admin.register(User)
# class CustomUserAdmin(UserAdmin):
#     list_display = ('username', 'email', 'tenant', 'role', 'is_active')
#     list_filter = ('tenant', 'role', 'is_active', 'is_staff')
#     search_fields = ('username', 'email', 'first_name', 'last_name')
#
#     fieldsets = UserAdmin.fieldsets + (
#         ('Tenant Information', {
#             'fields': ('tenant', 'role', 'avatar', 'phone')
#         }),
#     )
#
#     add_fieldsets = UserAdmin.add_fieldsets + (
#         ('Tenant Information', {
#             'fields': ('tenant', 'role', 'avatar', 'phone')
#         }),
#     )
