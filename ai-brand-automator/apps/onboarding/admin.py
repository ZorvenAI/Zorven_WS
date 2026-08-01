"""Django admin for the OIA session models (AC-4).

Querysets are tenant-scoped for everyone except superusers. The admin is a
direct path to the ORM, so the same rule that governs the API applies here:
a queryset that does not filter by tenant is the likeliest source of a
cross-tenant leak, and no permission mixin intercepts it at this layer.
"""

from __future__ import annotations

from django.contrib import admin

from .models import OnboardingSession, Question, Questionnaire


class TenantScopedAdmin(admin.ModelAdmin):
    """Restricts rows to the staff user's tenant memberships."""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        # Mirrors the defensive pattern used across the fleet: never read
        # request.tenant directly, and keep pre-tenant rows visible.
        tenant = getattr(request, "tenant", None)
        return queryset.filter(tenant=tenant) if tenant else queryset.none()


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
class QuestionAdmin(admin.ModelAdmin):
    """Question has no tenant column of its own.

    It is reached through Questionnaire, so scoping happens one level up;
    filtering here would mean a join that adds nothing the parent does not
    already enforce.
    """

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
