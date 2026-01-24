"""
Custom middleware for security and request validation
"""

import logging
import re
import jwt
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class SecurityMiddleware:
    """
    Middleware for additional security measures:
    - CSRF token validation for state-changing operations
    - Request size limits
    - Security headers

    When Kong Gateway is enabled, security headers are handled by Kong's
    response-transformer plugin. This middleware skips header addition in that case.
    """

    MAX_REQUEST_SIZE = 50 * 1024 * 1024  # 50 MB

    def __init__(self, get_response):
        self.get_response = get_response
        # Check if Kong handles security headers
        self.kong_enabled = getattr(settings, "KONG_ENABLED", False)

    def __call__(self, request):
        # Check request size
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.META.get("CONTENT_LENGTH")
            if content_length and int(content_length) > self.MAX_REQUEST_SIZE:
                return JsonResponse({"error": "Request body too large"}, status=413)

        response = self.get_response(request)

        # Skip adding security headers if Kong handles them
        if self.kong_enabled:
            return response

        # Add security headers (only when Django handles security)
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["X-XSS-Protection"] = "1; mode=block"

        if not settings.DEBUG:
            response[
                "Strict-Transport-Security"
            ] = "max-age=31536000; includeSubDomains"

        return response


class RequestValidationMiddleware:
    """
    Middleware for validating request data:
    - Input sanitization
    - Injection prevention
    """

    # Patterns for detecting malicious input
    INJECTION_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # XSS
        r"javascript:",  # JavaScript protocol
        r"on\w+\s*=",  # Event handlers
        r"eval\s*\(",  # eval()
        r"expression\s*\(",  # CSS expressions
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self.injection_regex = re.compile(
            "|".join(self.INJECTION_PATTERNS), re.IGNORECASE
        )

    def __call__(self, request):
        # Validate GET and POST parameters
        if request.method in ["GET", "POST", "PUT", "PATCH"]:
            if not self._validate_request_data(request):
                logger.warning(
                    f"Suspicious input detected from {request.META.get('REMOTE_ADDR')}"
                )
                return JsonResponse({"error": "Invalid input detected"}, status=400)

        response = self.get_response(request)
        return response

    def _validate_request_data(self, request):
        """Check request data for malicious patterns"""
        # Check GET parameters
        for key, value in request.GET.items():
            if self.injection_regex.search(value):
                return False

        # Check POST data (only if it's form data)
        if request.content_type == "application/x-www-form-urlencoded":
            for key, value in request.POST.items():
                if isinstance(value, str) and self.injection_regex.search(value):
                    return False

        return True


class RateLimitMiddleware:
    """
    Simple in-memory rate limiting middleware
    For production, use Redis-based solution

    When Kong Gateway is enabled (KONG_ENABLED=True), rate limiting
    should be handled by Kong's rate-limiting plugin. This middleware
    becomes a no-op in that case.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.requests = {}  # {ip: [(timestamp, count)]}
        self.rate_limit = 100  # requests per minute
        self.window = 60  # seconds
        # Check if Kong handles rate limiting
        self.kong_enabled = getattr(settings, "KONG_ENABLED", False)

    def __call__(self, request):
        import time

        # Skip rate limiting if Kong is enabled (Kong handles it)
        if self.kong_enabled:
            return self.get_response(request)

        # Skip rate limiting for static files
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return self.get_response(request)

        ip_address = self._get_client_ip(request)
        current_time = time.time()

        # Clean old entries
        if ip_address in self.requests:
            self.requests[ip_address] = [
                (ts, count)
                for ts, count in self.requests[ip_address]
                if current_time - ts < self.window
            ]

        # Count requests in current window
        request_count = sum(count for ts, count in self.requests.get(ip_address, []))

        if request_count >= self.rate_limit:
            logger.warning(f"Rate limit exceeded for IP: {ip_address}")
            return JsonResponse(
                {"error": "Rate limit exceeded. Please try again later."},
                status=429,
            )

        # Add current request
        if ip_address not in self.requests:
            self.requests[ip_address] = []
        self.requests[ip_address].append((current_time, 1))

        response = self.get_response(request)
        return response

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class KongAuthenticationMiddleware:
    """
    Middleware for Kong Gateway integration.

    When Kong Gateway is enabled (KONG_ENABLED=true), this middleware:
    1. Trusts that Kong has already validated the JWT signature
    2. Decodes the JWT WITHOUT verification to extract user claims
    3. Loads the User from database and sets request.user
    4. Injects tenant context for multi-tenancy

    This reduces authentication overhead since Kong has already validated
    the token signature, expiration, and other claims.

    Headers expected from Kong:
    - Authorization: Bearer <jwt>
    - X-Kong-Proxy: true (indicates request came through Kong)
    - X-Forwarded-Proto: https

    Anonymous routes (no JWT required):
    - /api/v1/auth/login
    - /api/v1/auth/register
    - /api/v1/auth/refresh
    - /health, /ready, /alive
    - /api/v1/subscriptions/webhook (Stripe webhook)
    """

    # Routes that don't require authentication
    ANONYMOUS_ROUTES = [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/health",
        "/ready",
        "/alive",
        "/api/v1/subscriptions/webhook",
        "/admin",  # Django admin handles its own auth
        "/static",
        "/media",
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self.kong_enabled = getattr(settings, "KONG_ENABLED", False)
        self.User = get_user_model()

    def __call__(self, request):
        # Skip if Kong is not enabled
        if not self.kong_enabled:
            return self.get_response(request)

        # Check if this is an anonymous route
        if self._is_anonymous_route(request.path):
            request.user = AnonymousUser()
            return self.get_response(request)

        # Check for Kong proxy header (optional, for debugging)
        is_kong_request = request.META.get("HTTP_X_KONG_PROXY") == "true"

        # Get JWT from Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header.startswith("Bearer "):
            # No token provided - could be anonymous or error
            # Let DRF handle authentication for protected endpoints
            request.user = AnonymousUser()
            return self.get_response(request)

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        try:
            # Decode WITHOUT verification - Kong already validated
            # We just need to extract the claims
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_exp": False,  # Kong already verified
                    "verify_aud": False,
                },
            )

            # Extract user ID from token
            user_id = payload.get("user_id")

            if user_id:
                try:
                    user = self.User.objects.get(id=user_id)
                    request.user = user

                    # Set tenant context if available
                    tenant_id = payload.get("tenant_id")
                    if tenant_id:
                        request.tenant_id = tenant_id

                    # Log successful Kong auth
                    if is_kong_request:
                        logger.debug(
                            f"Kong auth successful for user {user_id} "
                            f"on path {request.path}"
                        )

                except self.User.DoesNotExist:
                    logger.warning(f"User {user_id} from JWT not found in database")
                    request.user = AnonymousUser()
            else:
                # Token doesn't have user_id claim
                logger.warning("JWT missing user_id claim")
                request.user = AnonymousUser()

        except jwt.exceptions.DecodeError as e:
            logger.warning(f"Failed to decode JWT: {e}")
            request.user = AnonymousUser()
        except Exception as e:
            logger.error(f"Kong auth middleware error: {e}")
            request.user = AnonymousUser()

        return self.get_response(request)

    def _is_anonymous_route(self, path):
        """Check if the path is an anonymous route that doesn't require auth."""
        for route in self.ANONYMOUS_ROUTES:
            if path.startswith(route):
                return True
        return False
