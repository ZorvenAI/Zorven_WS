"""
Custom authentication views with enhanced validation
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
from django.utils.crypto import get_random_string
from brand_automator.validators import validate_password_strength
import logging

logger = logging.getLogger(__name__)


def get_user_tenant(user):
    """Look up the tenant associated with a user.

    Convention: each user owns a tenant whose schema_name is
    ``user_<user.id>``.  Returns ``None`` when no matching tenant exists
    (e.g. superusers who manage the public schema).
    """
    from tenants.models import Tenant

    try:
        return Tenant.objects.get(schema_name=f"user_{user.id}")
    except Tenant.DoesNotExist:
        return None


class TenantAwareRefreshToken(RefreshToken):
    """RefreshToken subclass that injects ``tenant_id`` into the JWT."""

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        tenant = get_user_tenant(user)
        if tenant:
            token["tenant_id"] = tenant.id
        return token


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that accepts email instead of username"""

    username_field = "email"

    @classmethod
    def get_token(cls, user):
        """Override to inject tenant_id into JWT claims."""
        token = super().get_token(user)
        tenant = get_user_tenant(user)
        if tenant:
            token["tenant_id"] = tenant.id
        return token

    def validate(self, attrs):
        # Get email and password from request
        email = attrs.get("email")
        password = attrs.get("password")

        if not email or not password:
            raise serializers.ValidationError("Email and password are required")

        try:
            # Look up user by email
            # Use filter().first() to handle duplicates gracefully
            user = User.objects.filter(email=email).first()

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
    """User registration with password strength validation and email verification"""

    permission_classes = [AllowAny]

    def post(self, request):
        # Extract data
        email = request.data.get("email", "").strip()
        password = request.data.get("password", "")
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()

        # Validation
        errors = {}

        # Email validation
        if not email:
            errors["email"] = "Email is required"
        elif User.objects.filter(email=email).exists():
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
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=True,  # Set to False if email verification required
            )

            # --- Multi-tenancy: create a dedicated tenant for the user ---
            from tenants.models import Tenant, Domain

            tenant = Tenant(
                name=f"{first_name} {last_name}",
                schema_name=f"user_{user.id}",
                subscription_status="trial",
            )
            tenant.save()

            Domain.objects.create(
                domain=f"user-{user.id}.localhost",
                tenant=tenant,
                is_primary=True,
            )

            logger.info(
                f"Tenant '{tenant.name}' (schema={tenant.schema_name}) "
                f"created for user {user.id}"
            )

            # Send verification email
            self._send_verification_email(user)

            # Generate JWT tokens with tenant_id claim
            refresh = TenantAwareRefreshToken.for_user(user)

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
                    "tenant": {
                        "id": tenant.id,
                        "name": tenant.name,
                    },
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

    def _send_verification_email(self, user):
        """Send email verification (placeholder for now)"""
        # TODO: Implement actual email verification with token
        # For MVP, we'll just send a welcome email
        try:
            subject = "Welcome to AI Brand Automator"
            message = f"""
            Hi {user.first_name},

            Welcome to AI Brand Automator! Your account has been created successfully.

            Email: {user.email}

            You can now log in and start building your brand.

            Best regards,
            AI Brand Automator Team
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
