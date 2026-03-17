"""Internal service-to-service endpoints for the social agent.

These endpoints are authenticated via X-Service-Token (same pattern
as orchestrator callbacks) and are NOT exposed through Kong.
"""

import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import Membership
from .models import ContentCalendar, SocialProfile
from .publish_helpers import publish_to_platform

logger = logging.getLogger(__name__)


def _verify_service_token(request):
    """Verify X-Service-Token header against configured secret.

    Returns None on success, or an error Response on failure.
    """
    token = request.META.get("HTTP_X_SERVICE_TOKEN", "")
    expected = getattr(settings, "ORCHESTRATOR_SERVICE_TOKEN", "")
    if not expected or token != expected:
        return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
    return None


def _get_tenant_id(request):
    """Extract tenant ID from X-Tenant-ID header."""
    return request.META.get("HTTP_X_TENANT_ID", "")


class InternalSocialProfilesView(APIView):
    """GET connected social profiles for a tenant.

    Used by social-agent-svc to discover which platforms are available.
    Does NOT return tokens — publishing is delegated back to Django.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        auth_error = _verify_service_token(request)
        if auth_error:
            return auth_error

        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response(
                {"error": "X-Tenant-ID header required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optional: prefer profiles owned by this user
        preferred_user_id = request.query_params.get("user_id")

        # Include profiles linked to this tenant OR unlinked profiles
        # whose owner is an active member of this tenant.
        member_user_ids = Membership.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
        ).values_list("user_id", flat=True)

        profiles = list(
            SocialProfile.objects.filter(
                Q(tenant_id=tenant_id)
                | Q(tenant__isnull=True, user_id__in=member_user_ids),
                status="connected",
            )
            .order_by("platform", "id")
            .values(
                "id",
                "platform",
                "status",
                "profile_name",
                "profile_url",
                "user_id",
                "tenant_id",
            )
        )

        # Deduplicate: one profile per platform.
        # Priority: preferred user's profile > tenant-linked > other members.
        def _sort_key(p):
            is_preferred = (
                0
                if (preferred_user_id and str(p["user_id"]) == str(preferred_user_id))
                else 1
            )
            # Tenant-linked profiles rank above unlinked (tenant__isnull=True)
            is_tenant_linked = 0 if p.get("tenant_id") else 1
            return (p["platform"], is_preferred, is_tenant_linked)

        profiles.sort(key=_sort_key)

        seen_platforms = set()
        result = []
        for p in profiles:
            if p["platform"] in seen_platforms:
                continue
            seen_platforms.add(p["platform"])
            result.append(
                {
                    "id": p["id"],
                    "platform": p["platform"],
                    "status": p["status"],
                    "profile_name": p["profile_name"] or "",
                    "is_token_valid": True,
                }
            )

        return Response({"profiles": result})


class InternalPublishView(APIView):
    """POST publish content to social platforms.

    RBAC enforcement:
    - editor  -> creates ContentCalendar entry with status=draft
    - admin/owner -> creates ContentCalendar + publishes immediately
    - viewer -> rejected
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        auth_error = _verify_service_token(request)
        if auth_error:
            return auth_error

        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response(
                {"error": "X-Tenant-ID header required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        platforms = request.data.get("platforms", [])
        content_text = request.data.get("content", "")
        title = request.data.get("title", "Social post")
        media_urls = request.data.get("media_urls", [])
        user_role = request.data.get("user_role", "editor")
        job_id = request.data.get("job_id", "")
        user_id = request.data.get("user_id")
        scheduled_date_str = request.data.get("scheduled_date")

        if not platforms or not content_text:
            return Response(
                {"error": "platforms and content are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user_role == "viewer":
            return Response(
                {"error": "Viewers cannot publish content"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get connected profiles for the requested platforms.
        # Include tenant-linked AND unlinked profiles owned by tenant members.
        # Deduplicate: one profile per platform, prefer requesting user's profile.
        member_user_ids = Membership.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
        ).values_list("user_id", flat=True)

        all_profiles = list(
            SocialProfile.objects.filter(
                Q(tenant_id=tenant_id)
                | Q(tenant__isnull=True, user_id__in=member_user_ids),
                status="connected",
                platform__in=platforms,
            )
        )

        # Sort: preferred user's profiles first, then tenant-linked, then others
        def _sort_key(p):
            is_preferred = 0 if (user_id and str(p.user_id) == str(user_id)) else 1
            is_tenant_linked = 0 if p.tenant_id else 1
            return (p.platform, is_preferred, is_tenant_linked)

        all_profiles.sort(key=_sort_key)

        seen = set()
        profiles = []
        for p in all_profiles:
            if p.platform not in seen:
                seen.add(p.platform)
                profiles.append(p)

        if not profiles:
            return Response(
                {"error": "No connected profiles for requested platforms"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Strip markdown — social platforms render plain text, not markdown
        from automation.utils import strip_markdown

        clean_title = strip_markdown(title)
        clean_content = strip_markdown(content_text)

        # Parse optional scheduled_date from the request.  When provided
        # and in the future, the post is created as "scheduled" and the
        # Celery beat task (publish_scheduled_posts) will publish it later.
        from django.utils.dateparse import parse_datetime

        schedule_for_later = False
        parsed_scheduled_date = timezone.now()

        if scheduled_date_str:
            parsed = parse_datetime(str(scheduled_date_str))
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed)
                parsed_scheduled_date = parsed
                if parsed > timezone.now():
                    schedule_for_later = True

        # Create ContentCalendar entry
        calendar_entry = ContentCalendar.objects.create(
            tenant_id=tenant_id,
            user=profiles[0].user,
            title=clean_title,
            content=clean_content,
            media_urls=media_urls or [],
            platforms=[p.platform for p in profiles],
            scheduled_date=parsed_scheduled_date,
            status="draft" if user_role == "editor" else "scheduled",
        )
        calendar_entry.social_profiles.set(profiles)

        # Editor -> store as draft only
        if user_role == "editor":
            return Response(
                {
                    "status": "draft",
                    "content_id": calendar_entry.id,
                    "message": "Content saved as draft for admin approval",
                }
            )

        # Admin/Owner with future schedule -> store as scheduled (Celery will publish)
        if schedule_for_later:
            return Response(
                {
                    "status": "scheduled",
                    "content_id": calendar_entry.id,
                    "scheduled_date": parsed_scheduled_date.isoformat(),
                    "message": (
                        f"Content scheduled for " f"{parsed_scheduled_date.isoformat()}"
                    ),
                }
            )

        # Admin/Owner -> publish immediately
        results = {}
        errors = []

        for profile in profiles:
            result, error = publish_to_platform(
                profile=profile,
                content_text=clean_content,
                content_title=clean_title,
                media_urls=media_urls,
                log_prefix=f"[social-agent][job:{job_id}]",
            )
            if result:
                results[profile.platform] = result
            if error:
                errors.append(f"{profile.platform}: {error}")

        # Update calendar entry status
        if results:
            calendar_entry.status = "published"
            calendar_entry.published_at = timezone.now()
            calendar_entry.post_results = results
        else:
            calendar_entry.status = "failed"

        calendar_entry.save(
            update_fields=["status", "published_at", "post_results", "updated_at"]
        )

        return Response(
            {
                "status": "published" if results else "failed",
                "content_id": calendar_entry.id,
                "results": results,
                "errors": errors,
            }
        )


class InternalUserRoleView(APIView):
    """GET user's membership role for a tenant.

    Falls back to tenant owner's role if no user_id provided.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        auth_error = _verify_service_token(request)
        if auth_error:
            return auth_error

        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response(
                {"error": "X-Tenant-ID header required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = request.query_params.get("user_id")

        try:
            from tenants.models import Tenant

            tenant = Tenant.objects.get(id=tenant_id)
        except Exception:
            return Response(
                {"error": "Tenant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user_id:
            try:
                membership = tenant.memberships.get(user_id=user_id, is_active=True)
                return Response({"role": membership.role, "user_id": int(user_id)})
            except Exception:
                # Fall through to owner role
                pass

        # Fallback: return owner role
        owner = tenant.get_owner()
        if owner:
            return Response({"role": "owner", "user_id": owner.id})

        return Response({"role": "viewer", "user_id": None})
