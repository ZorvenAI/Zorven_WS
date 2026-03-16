"""
Custom authentication views with enhanced validation.

Supports two registration modes:
  - **Mode A** (Brand Owner): Creates user + tenant + OWNER membership.
  - **Mode B** (Invite): Creates user and accepts pending invitation.

JWT tokens include a ``tenants`` list and ``active_tenant_id`` claim
so the frontend can render a workspace switcher without extra API calls.
"""

from rest_framework import status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.db import models as db_models
from django.utils import timezone
from django.utils.crypto import get_random_string
from brand_automator.validators import validate_password_strength
import logging

logger = logging.getLogger(__name__)


def _build_tenant_list(user):
    """Build the tenant list for JWT claims and API responses.

    Returns a list of dicts with ``id``, ``name``, ``slug``, and ``role``
    for every active membership the user holds.  OWNER memberships sort
    first so the default ``active_tenant_id`` is the user's own brand.
    """
    from tenants.models import Membership

    memberships = (
        Membership.objects.filter(user=user, is_active=True)
        .select_related("tenant")
        .order_by(
            db_models.Case(
                db_models.When(role=Membership.Role.OWNER, then=0),
                default=1,
            ),
            "tenant__name",
        )
    )
    return [
        {
            "id": m.tenant_id,
            "name": m.tenant.name,
            "slug": m.tenant.slug,
            "role": m.role,
        }
        for m in memberships
    ]


class TenantAwareRefreshToken(RefreshToken):
    """RefreshToken subclass that injects ``tenants`` list into the JWT."""

    @classmethod
    def for_user(cls, user):
        """Create a refresh token with tenant membership claims."""
        token = super().for_user(user)

        tenant_list = _build_tenant_list(user)
        token["tenants"] = tenant_list

        # Set active tenant to first owned tenant (or first any)
        if tenant_list:
            token["active_tenant_id"] = tenant_list[0]["id"]

        return token


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that accepts email instead of username."""

    username_field = "email"

    @classmethod
    def get_token(cls, user):
        """Override to inject ``tenants`` list into JWT claims."""
        token = super().get_token(user)

        tenant_list = _build_tenant_list(user)
        token["tenants"] = tenant_list
        if tenant_list:
            token["active_tenant_id"] = tenant_list[0]["id"]

        return token

    def validate(self, attrs):
        # Get email and password from request
        email = attrs.get("email")
        password = attrs.get("password")

        if not email or not password:
            raise serializers.ValidationError("Email and password are required")

        try:
            # Look up user by email (case-insensitive)
            # Use filter().first() to handle duplicates gracefully
            user = User.objects.filter(email__iexact=email).first()

            if not user:
                raise serializers.ValidationError(
                    "No active account found with the given credentials"
                )

            # Replace email with username in attrs and change field name to 'username'
            # This allows parent class to authenticate properly
            attrs_with_username = {"username": user.username, "password": password}

            # Temporarily change username_field to 'username' for parent validation
            original_username_field = self.username_field
            self.username_field = "username"

            try:
                result = super().validate(attrs_with_username)
            finally:
                # Restore original username_field
                self.username_field = original_username_field

            return result

        except User.DoesNotExist:
            raise serializers.ValidationError(
                "No active account found with the given credentials"
            )


class EmailTokenObtainPairView(TokenObtainPairView):
    """Custom JWT login view that accepts email"""

    serializer_class = EmailTokenObtainPairSerializer


class UserRegistrationView(APIView):
    """User registration with password validation.

    Supports two modes:

    **Mode A — Brand Owner** (default):
        POST body includes ``brand_name`` (optional).  Creates a new
        ``Tenant`` + ``Domain`` + ``Membership(role=OWNER)``.

    **Mode B — Team Member** (invite-based):
        POST body includes ``invite_token``.  Looks up pending
        ``Membership`` by email and activates it.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Register a new user."""
        # Extract data
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        brand_name = request.data.get("brand_name", "").strip()
        invite_token = request.data.get("invite_token")

        # Validation
        errors = {}

        # Email validation
        if not email:
            errors["email"] = "Email is required"
        elif User.objects.filter(email__iexact=email).exists():
            errors["email"] = "Email already registered"
        elif "@" not in email or "." not in email.split("@")[-1]:
            errors["email"] = "Invalid email format"

        # Password validation
        if not password:
            errors["password"] = "Password is required"
        else:
            password_validation = validate_password_strength(password)
            if not password_validation["valid"]:
                errors["password"] = password_validation["errors"]

        # Name validation
        if not first_name:
            errors["first_name"] = "First name is required"
        if not last_name:
            errors["last_name"] = "Last name is required"

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        # Create user with email as username
        username = email.split("@")[0] + "_" + get_random_string(6)

        try:
            from tenants.models import Tenant, Domain, Membership

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )

            tenants_response = []

            if invite_token:
                # --------------------------------------------------
                # Mode B: Accept invitation
                # --------------------------------------------------
                membership = self._accept_invitation(user, invite_token)
                if membership:
                    tenants_response.append(
                        {
                            "id": membership.tenant_id,
                            "name": membership.tenant.name,
                            "slug": membership.tenant.slug,
                            "role": membership.role,
                        }
                    )
            else:
                # --------------------------------------------------
                # Mode A: Create brand tenant
                # --------------------------------------------------
                tenant_name = brand_name or f"{first_name}'s Brand"
                tenant = Tenant(
                    name=tenant_name,
                    subscription_status="trial",
                )
                tenant.auto_create_schema = False
                tenant.save()  # slug + schema_name auto-generated

                Domain.objects.create(
                    domain=f"{tenant.slug}.localhost",
                    tenant=tenant,
                    is_primary=True,
                )
                Membership.objects.create(
                    user=user,
                    tenant=tenant,
                    role=Membership.Role.OWNER,
                    accepted_at=timezone.now(),
                )

                tenants_response.append(
                    {
                        "id": tenant.id,
                        "name": tenant.name,
                        "slug": tenant.slug,
                        "role": "owner",
                    }
                )

                logger.info(
                    f"Tenant '{tenant.name}' (schema={tenant.schema_name}) "
                    f"created for user {user.id}"
                )

            # ── Auto-link pending invites by email ──────────────
            # Regardless of Mode A/B, activate any remaining pending
            # invites that match the new user's email address.
            auto_linked = self._auto_link_pending_invites(user, tenants_response)
            if auto_linked:
                logger.info(
                    "Auto-linked %d pending invite(s) for %s",
                    auto_linked,
                    user.email,
                )

            # Send verification email
            self._send_verification_email(user)

            # Generate JWT tokens with tenants claim
            refresh = TenantAwareRefreshToken.for_user(user)

            active_tenant_id = tenants_response[0]["id"] if tenants_response else None

            logger.info(f"New user registered: {email}")

            return Response(
                {
                    "message": "Registration successful",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                    },
                    "tenants": tenants_response,
                    "active_tenant_id": active_tenant_id,
                    "tokens": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"User registration failed: {str(e)}", exc_info=True)
            return Response(
                {"error": "Registration failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _accept_invitation(self, user, invite_token):
        """Accept a pending membership invitation.

        Looks up a ``Membership`` record by ``invite_token`` (UUID).
        Falls back to matching by email for pending invites without
        a token (legacy records).

        Args:
            user: The newly created User.
            invite_token: The invite token from the registration link.

        Returns:
            Membership or None: The activated membership.
        """
        from tenants.models import Membership

        # Primary: look up by invite_token
        pending = (
            Membership.objects.filter(
                invite_token=invite_token,
                user__isnull=True,
                is_active=False,
            )
            .select_related("tenant")
            .first()
        )

        # Fallback: look up by email for legacy invites (case-insensitive)
        if not pending:
            pending = (
                Membership.objects.filter(
                    invited_email__iexact=user.email,
                    user__isnull=True,
                    is_active=False,
                )
                .select_related("tenant")
                .first()
            )

        if pending:
            pending.user = user
            pending.is_active = True
            pending.accepted_at = timezone.now()
            pending.invite_token = None  # Consumed
            pending.save()
            return pending
        return None

    @staticmethod
    def _auto_link_pending_invites(user, tenants_response):
        """Activate all remaining pending invites matching the user's email.

        This handles the case where an admin invites someone who
        hasn't registered yet and they later sign up normally
        (without using the invite link).

        Args:
            user: The newly created User.
            tenants_response: List to append activated tenant info to.

        Returns:
            int: Number of pending invites activated.
        """
        from tenants.models import Membership

        pending = Membership.objects.filter(
            invited_email__iexact=user.email,
            user__isnull=True,
            is_active=False,
        ).select_related("tenant")

        count = 0
        for membership in pending:
            membership.user = user
            membership.is_active = True
            membership.accepted_at = timezone.now()
            membership.invite_token = None
            membership.save()
            tenants_response.append(
                {
                    "id": membership.tenant_id,
                    "name": membership.tenant.name,
                    "slug": membership.tenant.slug,
                    "role": membership.role,
                }
            )
            count += 1
        return count

    def _send_verification_email(self, user):
        """Send email verification (placeholder for now)"""
        # TODO: Implement actual email verification with token
        # For MVP, we'll just send a welcome email
        try:
            subject = "Welcome to Zorven AI"
            message = f"""
            Hi {user.first_name},

            Welcome to Zorven AI! Your account has been created successfully.

            Email: {user.email}

            You can now log in and start building your brand.

            Best regards,
            Zorven AI Team
            """

            # Only send if email backend is configured
            if settings.EMAIL_HOST:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=True,
                )
                logger.info(f"Welcome email sent to {user.email}")
        except Exception as e:
            logger.warning(f"Failed to send welcome email: {str(e)}")


class EmailVerificationView(APIView):
    """Email verification endpoint (placeholder for future implementation)"""

    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get("token")

        if not token:
            return Response(
                {"error": "Verification token required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TODO: Implement token verification
        # For now, return placeholder response
        return Response(
            {
                "message": (
                    "Email verification is not yet implemented. All accounts "
                    "are automatically verified."
                )
            }
        )


class PasswordResetRequestView(APIView):
    """Request password reset (placeholder for future implementation)"""

    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TODO: Implement password reset flow
        return Response({"message": "Password reset functionality coming soon"})
