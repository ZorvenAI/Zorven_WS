"""
Views for the Tenants app.

Provides:
  - Admin-only CRUD for Tenant and Domain (``TenantViewSet``, ``DomainViewSet``).
  - User-facing workspace endpoints:
      * ``MyTenantsView`` — list workspaces the user belongs to.
      * ``CreateTenantView`` — create a new brand/workspace.
      * ``TenantSwitchView`` — switch the active workspace (returns new JWT).
      * ``MemberListView`` — list members of a tenant.
      * ``InviteMemberView`` — invite a user by email.
      * ``MemberDetailView`` — update role / remove a member.
"""

import logging
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import connection
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Domain, Membership, Tenant
from .permissions import IsTenantAdmin, IsTenantOwner
from .serializers import (
    DomainSerializer,
    InviteMemberSerializer,
    MembershipSerializer,
    TenantCreateSerializer,
    TenantSerializer,
    TenantSwitchSerializer,
    TenantUpdateSerializer,
    TenantWithRoleSerializer,
)

logger = logging.getLogger(__name__)


class TenantViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for Tenant management.

    Only admin/staff users can manage tenants.
    Tenant creation triggers schema creation via django-tenants.

    Actions:
        list    — GET  /api/v1/tenants/
        create  — POST /api/v1/tenants/
        retrieve — GET /api/v1/tenants/{id}/
        update  — PUT  /api/v1/tenants/{id}/
        partial_update — PATCH /api/v1/tenants/{id}/
        destroy — DELETE /api/v1/tenants/{id}/
        stats   — GET  /api/v1/tenants/{id}/stats/
    """

    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        """Return all tenants with prefetched domains."""
        return Tenant.objects.prefetch_related("domains").all().order_by("-created_at")

    def get_serializer_class(self):
        """Return action-specific serializer."""
        if self.action == "create":
            return TenantCreateSerializer
        if self.action in ("update", "partial_update"):
            return TenantUpdateSerializer
        return TenantSerializer

    def perform_create(self, serializer):
        """Create tenant — schema is auto-created by django-tenants."""
        tenant = serializer.save()
        logger.info("Tenant created: %s (schema: %s)", tenant.name, tenant.schema_name)

    def perform_destroy(self, instance):
        """Delete tenant record.

        Removes the tenant row and associated domains. Schema cleanup
        should be handled separately via a management command.
        The public schema is never deleted.
        """
        if instance.schema_name == "public":
            logger.warning("Attempted to delete the public tenant — blocked.")
            return
        tenant_name = instance.name
        schema_name = instance.schema_name
        instance.delete()
        logger.info("Tenant deleted: %s (schema: %s)", tenant_name, schema_name)

    def destroy(self, request, *args, **kwargs):
        """Override destroy to prevent deletion of the public tenant."""
        instance = self.get_object()
        if instance.schema_name == "public":
            return Response(
                {"detail": "The public tenant cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Return tenant statistics: domain count, subscription status."""
        tenant = self.get_object()
        domain_count = tenant.domains.count()
        # Reset connection to public schema after reading
        connection.set_schema_to_public()
        return Response(
            {
                "id": tenant.id,
                "name": tenant.name,
                "schema_name": tenant.schema_name,
                "subscription_status": tenant.subscription_status,
                "is_subscription_active": tenant.is_subscription_active,
                "domain_count": domain_count,
                "max_users": tenant.max_users,
                "storage_limit_gb": tenant.storage_limit_gb,
            }
        )


class DomainViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for Domain management.

    Domains map hostnames to tenants. Each tenant can have multiple
    domains, but only one primary domain.

    Actions:
        list    — GET  /api/v1/tenants/domains/
        create  — POST /api/v1/tenants/domains/
        retrieve — GET /api/v1/tenants/domains/{id}/
        update  — PUT  /api/v1/tenants/domains/{id}/
        partial_update — PATCH /api/v1/tenants/domains/{id}/
        destroy — DELETE /api/v1/tenants/domains/{id}/
    """

    serializer_class = DomainSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        """Return all domains with their tenant."""
        return Domain.objects.select_related("tenant").all().order_by("domain")

    def perform_create(self, serializer):
        """Create domain — validate tenant exists."""
        domain = serializer.save()
        logger.info("Domain created: %s → tenant %s", domain.domain, domain.tenant.name)


# =====================================================================
# User-facing workspace endpoints
# =====================================================================


class MyTenantsView(APIView):
    """List workspaces (tenants) the current user belongs to.

    GET /api/v1/tenants/me/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return the user's tenant memberships with role info."""
        memberships = (
            Membership.objects.filter(user=request.user, is_active=True)
            .select_related("tenant")
            .order_by("tenant__name")
        )
        tenants = [m.tenant for m in memberships]
        serializer = TenantWithRoleSerializer(
            tenants, many=True, context={"request": request}
        )
        return Response(serializer.data)


class CreateTenantView(APIView):
    """Create a new workspace (tenant) and become its OWNER.

    POST /api/v1/tenants/create/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create a new tenant and OWNER membership for the user."""
        name = request.data.get("name", "").strip()
        if not name:
            return Response(
                {"error": "Tenant name is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Tenant.objects.filter(name__iexact=name).exists():
            return Response(
                {"error": "A workspace with this name already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        tenant = Tenant(
            name=name,
            subscription_status="trial",
        )
        tenant.auto_create_schema = False
        tenant.save()

        Domain.objects.create(
            domain=f"{tenant.slug}.localhost",
            tenant=tenant,
            is_primary=True,
        )

        Membership.objects.create(
            user=request.user,
            tenant=tenant,
            role=Membership.Role.OWNER,
            accepted_at=timezone.now(),
        )

        logger.info(
            "User %s created workspace '%s' (id=%s)",
            request.user.id,
            tenant.name,
            tenant.id,
        )

        serializer = TenantWithRoleSerializer(tenant, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TenantSwitchView(APIView):
    """Switch the user's active workspace and return new JWT tokens.

    POST /api/v1/tenants/switch/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Verify membership and issue new tokens for the target tenant."""
        serializer = TenantSwitchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_id = serializer.validated_data["tenant_id"]

        membership = (
            Membership.objects.filter(
                user=request.user,
                tenant_id=tenant_id,
                is_active=True,
            )
            .select_related("tenant")
            .first()
        )

        if not membership:
            return Response(
                {"error": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from brand_automator.auth_views import TenantAwareRefreshToken

        refresh = TenantAwareRefreshToken.for_user(request.user)
        # Override active_tenant_id to the requested tenant
        refresh["active_tenant_id"] = tenant_id

        return Response(
            {
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
                "active_tenant": {
                    "id": membership.tenant_id,
                    "name": membership.tenant.name,
                    "slug": membership.tenant.slug,
                    "role": membership.role,
                },
            }
        )


class MemberListView(APIView):
    """List members of a tenant.

    GET /api/v1/tenants/<tenant_id>/members/
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def get(self, request, tenant_id):
        """Return all memberships (active + pending) for the tenant."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant.id != tenant_id:
            return Response(
                {"error": "Tenant context mismatch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        memberships = (
            Membership.objects.filter(tenant=tenant)
            .select_related("user")
            .order_by("-is_active", "role", "user__email")
        )
        serializer = MembershipSerializer(memberships, many=True)
        return Response(serializer.data)


class InviteMemberView(APIView):
    """Invite a user to the tenant by email.

    POST /api/v1/tenants/<tenant_id>/members/invite/
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def post(self, request, tenant_id):
        """Invite a member to the workspace.

        If the email belongs to an existing user, the membership is
        created immediately as active.  Otherwise, a placeholder
        membership is created for future acceptance.
        """
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant.id != tenant_id:
            return Response(
                {"error": "Tenant context mismatch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        # Check if user already has a membership
        existing = Membership.objects.filter(user__email=email, tenant=tenant).first()
        # Also check pending invites by invited_email
        if not existing:
            existing = Membership.objects.filter(
                invited_email=email, tenant=tenant, user__isnull=True
            ).first()
        if existing:
            if existing.is_active:
                return Response(
                    {"error": "This user is already a member."},
                    status=status.HTTP_409_CONFLICT,
                )
            # Re-activate a previously removed member
            token = uuid.uuid4()
            existing.role = role
            existing.is_active = bool(existing.user)  # active only if user exists
            existing.invited_by = request.user
            existing.invited_at = timezone.now()
            existing.invite_token = token if not existing.user else None
            if existing.user:
                existing.accepted_at = timezone.now()
            existing.save()

            inviter_name = request.user.get_full_name() or request.user.email
            if existing.user:
                self._send_added_email(
                    email=existing.user.email,
                    tenant_name=tenant.name,
                    inviter_name=inviter_name,
                    role=role,
                )
            else:
                self._send_invite_email(
                    email=existing.invited_email or email,
                    tenant_name=tenant.name,
                    inviter_name=inviter_name,
                    role=role,
                    token=str(token),
                )
            return Response(
                MembershipSerializer(existing).data,
                status=status.HTTP_200_OK,
            )

        # Check if user exists in the system
        target_user = User.objects.filter(email=email).first()

        inviter_name = request.user.get_full_name() or request.user.email

        if target_user:
            # Existing user — create active membership immediately
            membership = Membership.objects.create(
                user=target_user,
                tenant=tenant,
                role=role,
                is_active=True,
                invited_by=request.user,
                invited_at=timezone.now(),
                accepted_at=timezone.now(),
            )
            self._send_added_email(
                email=target_user.email,
                tenant_name=tenant.name,
                inviter_name=inviter_name,
                role=role,
            )
        else:
            # Unknown email — create placeholder membership
            # The user field is nullable for pending invites
            token = uuid.uuid4()
            membership = Membership.objects.create(
                user=None,
                tenant=tenant,
                role=role,
                is_active=False,
                invited_email=email,
                invited_by=request.user,
                invited_at=timezone.now(),
                invite_token=token,
            )
            self._send_invite_email(
                email=email,
                tenant_name=tenant.name,
                inviter_name=inviter_name,
                role=role,
                token=str(token),
            )
            logger.info(
                "Invite sent to %s for workspace '%s' (role=%s)",
                email,
                tenant.name,
                role,
            )

        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _send_invite_email(email, tenant_name, inviter_name, role, token):
        """Send the invitation email with an accept link.

        Uses the console email backend in dev (prints to stdout).
        In production, configure EMAIL_HOST env var for real delivery.
        """
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        accept_url = f"{frontend_url}/invite/accept?token={token}"

        subject = f"You've been invited to {tenant_name}"
        message = (
            f"Hi,\n\n"
            f"{inviter_name} has invited you to join "
            f'"{tenant_name}" as {role}.\n\n'
            f"Click the link below to accept the invitation:\n"
            f"{accept_url}\n\n"
            f"If you don't have an account yet, you'll be able "
            f"to create one when you accept.\n\n"
            f"Best regards,\nAI Brand Automator Team"
        )

        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            logger.info("Invitation email sent to %s", email)
        except Exception as exc:
            logger.warning("Failed to send invitation email to %s: %s", email, exc)

    @staticmethod
    def _send_added_email(email, tenant_name, inviter_name, role):
        """Notify an existing user they've been added to a workspace."""
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        dashboard_url = f"{frontend_url}/dashboard"

        subject = f"You've been added to {tenant_name}"
        message = (
            f"Hi,\n\n"
            f"{inviter_name} has added you to "
            f'"{tenant_name}" as {role}.\n\n'
            f"You can access the workspace from your dashboard:\n"
            f"{dashboard_url}\n\n"
            f"Best regards,\nAI Brand Automator Team"
        )

        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            logger.info("Added-to-workspace email sent to %s", email)
        except Exception as exc:
            logger.warning(
                "Failed to send added-to-workspace email to %s: %s",
                email,
                exc,
            )


class AcceptInviteView(APIView):
    """Accept a workspace invitation via token.

    GET /api/v1/tenants/invite/accept/?token=<uuid>

    Returns the invitation details.  The frontend decides whether to
    redirect the user to login or registration.

    POST /api/v1/tenants/invite/accept/
    Body: {"token": "<uuid>"}

    If the user is authenticated, activates the membership immediately.
    Otherwise returns 401.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """Preview an invitation (unauthenticated ok)."""
        token = request.query_params.get("token")
        if not token:
            return Response(
                {"error": "Token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = (
            Membership.objects.filter(invite_token=token, user__isnull=True)
            .select_related("tenant", "invited_by")
            .first()
        )
        if not membership:
            return Response(
                {"error": "Invalid or expired invitation."},
                status=status.HTTP_404_NOT_FOUND,
            )

        inviter_name = ""
        if membership.invited_by:
            inviter_name = (
                membership.invited_by.get_full_name() or membership.invited_by.email
            )

        return Response(
            {
                "email": membership.invited_email,
                "tenant_name": membership.tenant.name,
                "role": membership.role,
                "inviter_name": inviter_name,
            }
        )

    def post(self, request):
        """Accept an invitation (must be authenticated)."""
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required to accept an invite."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token = request.data.get("token")
        if not token:
            return Response(
                {"error": "Token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = (
            Membership.objects.filter(invite_token=token, user__isnull=True)
            .select_related("tenant")
            .first()
        )
        if not membership:
            return Response(
                {"error": "Invalid or expired invitation."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verify email matches
        if membership.invited_email != request.user.email:
            return Response(
                {"error": "This invitation was sent to a different email."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check for existing active membership
        if Membership.objects.filter(
            user=request.user, tenant=membership.tenant, is_active=True
        ).exists():
            return Response(
                {"error": "You are already a member of this workspace."},
                status=status.HTTP_409_CONFLICT,
            )

        membership.user = request.user
        membership.is_active = True
        membership.accepted_at = timezone.now()
        membership.invite_token = None  # Consumed
        membership.save()

        logger.info(
            "User %s accepted invite to workspace '%s'",
            request.user.email,
            membership.tenant.name,
        )

        return Response(
            {
                "message": "Invitation accepted.",
                "tenant": {
                    "id": membership.tenant.id,
                    "name": membership.tenant.name,
                    "slug": membership.tenant.slug,
                    "role": membership.role,
                },
            },
            status=status.HTTP_200_OK,
        )


class MemberDetailView(APIView):
    """Update or remove a member from a tenant.

    PATCH  /api/v1/tenants/<tenant_id>/members/<membership_id>/
    DELETE /api/v1/tenants/<tenant_id>/members/<membership_id>/
    """

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    def _get_membership(self, request, tenant_id, membership_id):
        """Look up the membership or return an error response."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant.id != tenant_id:
            return None, Response(
                {"error": "Tenant context mismatch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        membership = Membership.objects.filter(id=membership_id, tenant=tenant).first()
        if not membership:
            return None, Response(
                {"error": "Membership not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return membership, None

    def patch(self, request, tenant_id, membership_id):
        """Change a member's role."""
        membership, error_resp = self._get_membership(request, tenant_id, membership_id)
        if error_resp:
            return error_resp

        # Cannot change the owner's role unless you are the owner
        if membership.role == Membership.Role.OWNER:
            user_role = getattr(request, "user_role", None)
            if user_role != "owner":
                return Response(
                    {"error": "Only the owner can change the owner's role."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        new_role = request.data.get("role")
        if not new_role:
            return Response(
                {"error": "Role is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_roles = [c[0] for c in Membership.Role.choices]
        if new_role not in valid_roles:
            return Response(
                {"error": f"Invalid role. Must be one of: {valid_roles}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent promoting to OWNER via this endpoint
        if new_role == Membership.Role.OWNER:
            return Response(
                {
                    "error": "Cannot promote to Owner. "
                    "Use the transfer ownership flow."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership.role = new_role
        membership.save(update_fields=["role"])

        return Response(MembershipSerializer(membership).data)

    def delete(self, request, tenant_id, membership_id):
        """Remove a member from the workspace (soft-delete)."""
        membership, error_resp = self._get_membership(request, tenant_id, membership_id)
        if error_resp:
            return error_resp

        # Cannot remove the owner
        if membership.role == Membership.Role.OWNER:
            return Response(
                {"error": "Cannot remove the workspace owner."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Cannot remove yourself (admins can leave via a different flow)
        if membership.user == request.user:
            return Response(
                {"error": "Cannot remove yourself. Use Leave Workspace."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership.is_active = False
        membership.save(update_fields=["is_active"])

        return Response(status=status.HTTP_204_NO_CONTENT)


class DeleteTenantView(APIView):
    """Delete a workspace. Only the OWNER can do this.

    DELETE /api/v1/tenants/<tenant_id>/delete/
    """

    permission_classes = [IsAuthenticated, IsTenantOwner]

    def delete(self, request, tenant_id):
        """Delete the tenant and all associated data."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant.id != tenant_id:
            return Response(
                {"error": "Tenant context mismatch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if tenant.schema_name == "public":
            return Response(
                {"error": "The public tenant cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant_name = tenant.name
        tenant.delete()
        logger.info("User %s deleted workspace '%s'", request.user.id, tenant_name)

        return Response(
            {"message": f"Workspace '{tenant_name}' has been deleted."},
            status=status.HTTP_200_OK,
        )
