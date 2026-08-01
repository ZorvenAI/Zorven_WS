"""Django admin for the OIA session models (AC-4).

Querysets are tenant-scoped for everyone except superusers. The admin is a
direct path to the ORM, so the same rule that governs the API applies here:
a queryset that does not filter by tenant is the likeliest source of a
cross-tenant leak, and no permission mixin intercepts it at this layer.

The predicate comes from ``models.tenant_scope_q`` rather than being written
again here. An earlier version of this file had its own copy that dropped the
pre-tenant half, so the admin and the manager disagreed about what a tenant
could see — exactly the drift a single definition prevents.
"""

from __future__ import annotations

from django.contrib import admin

from .models import OnboardingSession, Question, Questionnaire, tenant_scope_q


class TenantScopedAdmin(admin.ModelAdmin):
    """Restricts rows to the requesting staff user's tenant.

    ``tenant_field`` is the lookup path to the tenant. It is a class attribute
    because not every model in this app carries a tenant column: Question is
    reached through its questionnaire, and browsing the Question changelist
    directly would otherwise show every tenant's rows.
    """

    tenant_field = "tenant"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        # Never read request.tenant directly — the fleet's defensive pattern.
        tenant = getattr(request, "tenant", None)
        return queryset.filter(tenant_scope_q(tenant, self.tenant_field))


@admin.register(OnboardingSession)
class OnboardingSessionAdmin(TenantScopedAdmin):
    list_display = (
        "id",
        "company",
        "status",
        "escalated_from",
        "questionnaire",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("company__name", "evidence_manifest_hash")
    readonly_fields = ("created_at", "updated_at", "prompt_versions")
    raw_id_fields = ("company", "questionnaire", "created_by", "tenant")

    @admin.display(boolean=True, description="Terminal")
    def is_terminal(self, obj: OnboardingSession) -> bool:
        return obj.is_terminal


@admin.register(Questionnaire)
class QuestionnaireAdmin(TenantScopedAdmin):
    list_display = (
        "id",
        "company",
        "session",
        "status",
        "version",
        "depth",
        "question_count",
        "is_template",
        "approved_at",
    )
    list_filter = ("status", "is_template", "depth")
    search_fields = ("company__name", "source_chat_session_id")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("company", "session", "approved_by", "tenant")


@admin.register(Question)
class QuestionAdmin(TenantScopedAdmin):
    """Question has no tenant column, so it is scoped through its parent.

    Scoping "one level up" only holds while a question is reached through a
    questionnaire. The changelist is reachable on its own, so the filter has
    to be applied here too — via the relation.
    """

    tenant_field = "questionnaire__tenant"

    list_display = (
        "id",
        "questionnaire",
        "order",
        "short_text",
        "origin",
        "workflow_target",
        "status",
        "sufficiency_score",
    )
    list_filter = ("status", "origin", "workflow_target")
    search_fields = ("text", "target_field")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("questionnaire",)

    @admin.display(description="Text")
    def short_text(self, obj: Question) -> str:
        return obj.text[:60] + ("…" if len(obj.text) > 60 else "")
