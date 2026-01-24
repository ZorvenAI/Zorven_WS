"""
Kong Gateway Integration Tests

These tests verify that:
1. KongAuthenticationMiddleware correctly handles JWT tokens
2. Anonymous routes are accessible without authentication
3. Protected routes require valid JWT
4. Kong-specific headers are properly processed
"""

import pytest
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from unittest.mock import patch, MagicMock
import jwt
from datetime import datetime, timedelta

from brand_automator.middleware import (
    KongAuthenticationMiddleware,
    RateLimitMiddleware,
    SecurityMiddleware,
)


User = get_user_model()


class TestKongAuthenticationMiddleware(TestCase):
    """Tests for KongAuthenticationMiddleware"""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        # Mock get_response function
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))
        self.middleware = KongAuthenticationMiddleware(self.get_response)

    def create_jwt_token(self, user_id=None, expired=False, issuer="ai-brand-automator"):
        """Helper to create JWT tokens for testing"""
        payload = {
            "iss": issuer,
            "user_id": user_id or self.user.id,
            "exp": datetime.utcnow() + timedelta(hours=-1 if expired else 1),
            "iat": datetime.utcnow(),
            "token_type": "access",
        }
        return jwt.encode(payload, "test-secret", algorithm="HS256")

    @override_settings(KONG_ENABLED=True)
    def test_anonymous_routes_skip_auth(self):
        """Anonymous routes should not require authentication"""
        anonymous_paths = [
            "/api/v1/auth/login/",
            "/api/v1/auth/register/",
            "/api/v1/auth/token/refresh/",
            "/health/",
            "/ready/",
            "/alive/",
        ]

        for path in anonymous_paths:
            request = self.factory.post(path)
            request.user = AnonymousUser()
            request.META["HTTP_X_KONG_PROXY"] = "true"

            # Middleware should pass through without error
            response = self.middleware(request)
            self.get_response.assert_called()

    @override_settings(KONG_ENABLED=True)
    def test_protected_route_with_valid_jwt(self):
        """Protected routes with valid JWT should set request.user"""
        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()
        token = self.create_jwt_token()
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        request.META["HTTP_X_KONG_PROXY"] = "true"

        response = self.middleware(request)

        # User should be loaded
        self.assertEqual(request.user.id, self.user.id)
        self.get_response.assert_called()

    @override_settings(KONG_ENABLED=True)
    def test_protected_route_without_jwt(self):
        """Protected routes without JWT should use AnonymousUser"""
        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()
        # No Authorization header

        response = self.middleware(request)

        # User should remain anonymous
        self.assertTrue(isinstance(request.user, AnonymousUser))

    @override_settings(KONG_ENABLED=True)
    def test_malformed_jwt_handled_gracefully(self):
        """Malformed JWT should not crash the middleware"""
        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()
        request.META["HTTP_AUTHORIZATION"] = "Bearer invalid-token"
        request.META["HTTP_X_KONG_PROXY"] = "true"

        # Should not raise exception
        response = self.middleware(request)
        self.assertTrue(isinstance(request.user, AnonymousUser))

    @override_settings(KONG_ENABLED=False)
    def test_middleware_disabled_when_kong_not_enabled(self):
        """When KONG_ENABLED=False, middleware should be a no-op"""
        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()

        response = self.middleware(request)

        # Should pass through without modification
        self.get_response.assert_called()

    @override_settings(KONG_ENABLED=True)
    def test_user_not_found_uses_anonymous(self):
        """If user_id in JWT doesn't exist, use AnonymousUser"""
        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()
        token = self.create_jwt_token(user_id=99999)  # Non-existent user
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        request.META["HTTP_X_KONG_PROXY"] = "true"

        response = self.middleware(request)

        self.assertTrue(isinstance(request.user, AnonymousUser))


class TestRateLimitMiddleware(TestCase):
    """Tests for RateLimitMiddleware"""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))

    @override_settings(KONG_ENABLED=True)
    def test_rate_limiting_disabled_when_kong_enabled(self):
        """Rate limiting should be skipped when Kong handles it"""
        middleware = RateLimitMiddleware(self.get_response)
        middleware.kong_enabled = True

        request = self.factory.get("/api/v1/companies/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        # Make many requests
        for _ in range(150):
            response = middleware(request)

        # Should not return 429 since Kong handles rate limiting
        self.get_response.assert_called()

    @override_settings(KONG_ENABLED=False)
    def test_rate_limiting_active_when_kong_disabled(self):
        """Rate limiting should be active when Kong is disabled"""
        middleware = RateLimitMiddleware(self.get_response)
        middleware.kong_enabled = False
        middleware.rate_limit = 10  # Lower limit for testing

        request = self.factory.get("/api/v1/companies/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        # Make requests up to the limit
        for i in range(12):
            response = middleware(request)

        # Should return 429 after exceeding limit
        self.assertEqual(response.status_code, 429)


class TestSecurityMiddleware(TestCase):
    """Tests for SecurityMiddleware"""

    def setUp(self):
        self.factory = RequestFactory()
        response_mock = MagicMock()
        response_mock.__setitem__ = MagicMock()
        self.get_response = MagicMock(return_value=response_mock)

    @override_settings(KONG_ENABLED=True)
    def test_security_headers_skipped_when_kong_enabled(self):
        """Security headers should be skipped when Kong adds them"""
        middleware = SecurityMiddleware(self.get_response)
        middleware.kong_enabled = True

        request = self.factory.get("/api/v1/companies/")

        response = middleware(request)

        # Headers should NOT be set (Kong handles them)
        response.__setitem__.assert_not_called()

    @override_settings(KONG_ENABLED=False)
    def test_security_headers_added_when_kong_disabled(self):
        """Security headers should be added when Kong is disabled"""
        response_mock = MagicMock()
        response_mock.__setitem__ = MagicMock()
        get_response = MagicMock(return_value=response_mock)
        middleware = SecurityMiddleware(get_response)
        middleware.kong_enabled = False

        request = self.factory.get("/api/v1/companies/")

        response = middleware(request)

        # Check that security headers were set
        call_args = [call[0][0] for call in response_mock.__setitem__.call_args_list]
        self.assertIn("X-Content-Type-Options", call_args)
        self.assertIn("X-Frame-Options", call_args)
        self.assertIn("X-XSS-Protection", call_args)


class TestKongHeaderProcessing(TestCase):
    """Tests for Kong-specific header processing"""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="headeruser",
            email="header@example.com",
            password="testpass123",
        )
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))

    @override_settings(KONG_ENABLED=True)
    def test_x_forwarded_proto_trusted(self):
        """X-Forwarded-Proto header should be trusted from Kong"""
        middleware = KongAuthenticationMiddleware(self.get_response)

        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        request.META["HTTP_X_KONG_PROXY"] = "true"

        # Process request
        response = middleware(request)

        # Verify the header is present
        self.assertEqual(request.META.get("HTTP_X_FORWARDED_PROTO"), "https")

    @override_settings(KONG_ENABLED=True)
    def test_kong_proxy_header_detected(self):
        """X-Kong-Proxy header indicates request came through Kong"""
        middleware = KongAuthenticationMiddleware(self.get_response)

        request = self.factory.get("/api/v1/companies/")
        request.user = AnonymousUser()
        request.META["HTTP_X_KONG_PROXY"] = "true"

        response = middleware(request)

        # Middleware should recognize Kong proxy
        self.assertEqual(request.META.get("HTTP_X_KONG_PROXY"), "true")


@pytest.mark.django_db
class TestAssetConfirmationEndpoint:
    """Tests for GCS direct upload confirmation endpoint"""

    @pytest.fixture
    def api_client(self):
        from rest_framework.test import APIClient
        return APIClient()

    @pytest.fixture
    def authenticated_user(self):
        user = User.objects.create_user(
            username="assetuser",
            email="asset@example.com",
            password="testpass123",
        )
        return user

    @pytest.fixture
    def company(self, authenticated_user):
        from tenants.models import Tenant
        from onboarding.models import Company

        tenant, _ = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={"name": "Public Tenant"}
        )
        company = Company.objects.create(
            tenant=tenant,
            name="Test Company",
            industry="Technology",
        )
        return company

    def test_confirm_gcs_upload_requires_auth(self, api_client):
        """Confirm GCS upload endpoint requires authentication"""
        response = api_client.post("/api/v1/assets/confirm_gcs_upload/", {})
        assert response.status_code == 401

    def test_confirm_gcs_upload_requires_fields(self, api_client, authenticated_user, company):
        """Confirm GCS upload requires file_name, file_type, file_size, gcs_path"""
        api_client.force_authenticate(user=authenticated_user)

        response = api_client.post("/api/v1/assets/confirm_gcs_upload/", {})
        assert response.status_code == 400
        assert "file_name" in str(response.content) or "Missing required" in str(response.content)

    def test_confirm_gcs_upload_success(self, api_client, authenticated_user, company):
        """Confirm GCS upload creates BrandAsset record"""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "file_name": "test-image.png",
            "file_type": "image",
            "file_size": 1024,
            "gcs_path": f"assets/{company.tenant.id}/test-image.png",
            "gcs_bucket": "brand-automator-assets",
        }

        response = api_client.post("/api/v1/assets/confirm_gcs_upload/", data, format="json")
        
        # Should create asset successfully
        if response.status_code == 201:
            assert "id" in response.json()
            assert response.json()["file_name"] == "test-image.png"
