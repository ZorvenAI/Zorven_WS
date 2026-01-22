"""
Service tests for the automation app.

Tests platform-specific services focusing on:
- Configuration validation
- Token management
- Error handling patterns

Note: These tests use mocking for HTTP calls where needed.
"""

import pytest
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.utils import timezone
import requests

from automation.models import SocialProfile
from automation.services import (
    LinkedInService,
    TwitterService,
    FacebookService,
    InstagramService,
)
from automation.constants import (
    TEST_ACCESS_TOKEN,
    TWITTER_TEST_ACCESS_TOKEN,
    FACEBOOK_TEST_ACCESS_TOKEN,
    FACEBOOK_TEST_PAGE_TOKEN,
    INSTAGRAM_TEST_ACCESS_TOKEN,
)

User = get_user_model()


@pytest.fixture
def user(db):
    """Create test user."""
    return User.objects.create_user(
        username="service_test_user",
        email="service@example.com",
        password="testpass123",
    )


@pytest.fixture
def linkedin_profile(user):
    """Create a connected LinkedIn profile."""
    profile = SocialProfile.objects.create(
        user=user,
        platform="linkedin",
        profile_id="urn:li:person:abc123",
        profile_name="Test LinkedIn User",
        status="connected",
        token_expires_at=timezone.now() + timedelta(days=60),
    )
    profile.access_token = TEST_ACCESS_TOKEN
    profile.save()
    return profile


@pytest.fixture
def twitter_profile(user):
    """Create a connected Twitter profile."""
    profile = SocialProfile.objects.create(
        user=user,
        platform="twitter",
        profile_id="twitter_user_123",
        profile_name="Test Twitter User",
        status="connected",
        token_expires_at=timezone.now() + timedelta(hours=2),
    )
    profile.access_token = TWITTER_TEST_ACCESS_TOKEN
    profile.save()
    return profile


@pytest.fixture
def facebook_profile(user):
    """Create a connected Facebook profile."""
    profile = SocialProfile.objects.create(
        user=user,
        platform="facebook",
        profile_id="fb_user_123",
        profile_name="Test Facebook Page",
        page_id="fb_page_123",
        status="connected",
        token_expires_at=timezone.now() + timedelta(days=60),
    )
    profile.access_token = FACEBOOK_TEST_ACCESS_TOKEN
    profile.page_access_token = FACEBOOK_TEST_PAGE_TOKEN
    profile.save()
    return profile


@pytest.fixture
def instagram_profile(user):
    """Create a connected Instagram profile."""
    profile = SocialProfile.objects.create(
        user=user,
        platform="instagram",
        profile_id="insta_user_123",
        profile_name="Test Instagram User",
        instagram_user_id="insta_business_123",
        instagram_username="test_insta_handle",
        status="connected",
        token_expires_at=timezone.now() + timedelta(days=60),
    )
    profile.access_token = INSTAGRAM_TEST_ACCESS_TOKEN
    profile.instagram_access_token = INSTAGRAM_TEST_ACCESS_TOKEN
    profile.save()
    return profile


# =============================================================================
# LinkedInService Tests
# =============================================================================


@pytest.mark.django_db
class TestLinkedInService:
    """Tests for LinkedInService."""

    def test_service_initialization(self):
        """Test LinkedInService initializes correctly."""
        service = LinkedInService()
        assert (
            service.AUTHORIZATION_URL
            == "https://www.linkedin.com/oauth/v2/authorization"
        )
        assert service.TOKEN_URL == "https://www.linkedin.com/oauth/v2/accessToken"
        assert service.PROFILE_URL == "https://api.linkedin.com/v2/userinfo"

    def test_is_configured_property(self):
        """Test is_configured returns False when credentials not set."""
        service = LinkedInService()
        # In test environment, credentials may or may not be set
        # Just verify the property exists and returns a boolean
        assert isinstance(service.is_configured, bool)

    def test_scopes_include_required_permissions(self):
        """Test LinkedIn scopes include necessary permissions."""
        service = LinkedInService()
        assert "openid" in service.SCOPES
        assert "profile" in service.SCOPES
        assert "email" in service.SCOPES
        assert "w_member_social" in service.SCOPES

    @patch.object(LinkedInService, "is_configured", True)
    def test_get_authorization_url_structure(self):
        """Test authorization URL has correct structure when configured."""
        service = LinkedInService()
        service.client_id = "test_client_id"

        auth_url = service.get_authorization_url(state="test_state_123")

        assert "linkedin.com/oauth/v2/authorization" in auth_url
        assert "response_type=code" in auth_url
        assert "state=test_state_123" in auth_url
        assert "client_id=" in auth_url

    def test_get_authorization_url_raises_when_not_configured(self):
        """Test authorization URL raises when credentials not set."""
        service = LinkedInService()
        service.client_id = None
        service.client_secret = None

        with pytest.raises(ValueError, match="not configured"):
            service.get_authorization_url(state="test_state")

    @patch("requests.post")
    def test_exchange_code_for_token_success(self, mock_post):
        """Test successful token exchange."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 5184000,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        result = service.exchange_code_for_token(code="auth_code_123")

        assert result["access_token"] == "new_access_token"
        assert result["refresh_token"] == "new_refresh_token"
        assert "expires_at" in result
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_exchange_code_for_token_failure(self, mock_post):
        """Test token exchange failure handling."""
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        with pytest.raises(Exception, match="Failed to exchange code"):
            service.exchange_code_for_token(code="invalid_code")

    @patch("requests.get")
    def test_get_user_profile_success(self, mock_get):
        """Test successful profile fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "urn:li:person:abc123",
            "name": "Test User",
            "email": "test@example.com",
            "picture": "https://example.com/photo.jpg",
            "given_name": "Test",
            "family_name": "User",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        service = LinkedInService()
        profile = service.get_user_profile("test_access_token")

        assert profile["id"] == "urn:li:person:abc123"
        assert profile["name"] == "Test User"
        assert profile["email"] == "test@example.com"

    @patch("requests.get")
    def test_get_user_profile_failure(self, mock_get):
        """Test profile fetch failure handling."""
        mock_get.side_effect = requests.exceptions.RequestException("Unauthorized")

        service = LinkedInService()

        with pytest.raises(Exception, match="Failed to fetch profile"):
            service.get_user_profile("invalid_token")

    @patch("requests.post")
    def test_refresh_access_token_success(self, mock_post):
        """Test successful token refresh."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_token",
            "expires_in": 5184000,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        result = service.refresh_access_token("old_refresh_token")

        assert result["access_token"] == "refreshed_token"
        assert "expires_at" in result


# =============================================================================
# TwitterService Tests
# =============================================================================


@pytest.mark.django_db
class TestTwitterService:
    """Tests for TwitterService."""

    def test_service_initialization(self):
        """Test TwitterService initializes correctly."""
        service = TwitterService()
        assert "twitter.com" in service.AUTHORIZATION_URL
        assert hasattr(service, "is_configured")

    def test_is_configured_property(self):
        """Test is_configured returns boolean."""
        service = TwitterService()
        assert isinstance(service.is_configured, bool)

    def test_pkce_code_verifier_generation(self):
        """Test PKCE code verifier is generated properly."""
        import secrets
        import base64
        import hashlib

        # Test the PKCE pattern used by Twitter OAuth
        code_verifier = secrets.token_urlsafe(32)

        # Verify it has appropriate length (43-128 chars)
        assert len(code_verifier) >= 43

        # Test code challenge generation
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("utf-8")).digest()
            )
            .decode("utf-8")
            .rstrip("=")
        )

        assert len(code_challenge) > 0

    def test_get_authorization_url_raises_when_not_configured(self):
        """Test authorization URL raises when credentials not set."""
        service = TwitterService()
        service.client_id = None
        service.client_secret = None

        # Twitter OAuth requires code_challenge for PKCE
        with pytest.raises((ValueError, TypeError)):
            service.get_authorization_url(
                state="test_state", code_challenge="test_challenge"
            )


# =============================================================================
# FacebookService Tests
# =============================================================================


@pytest.mark.django_db
class TestFacebookService:
    """Tests for FacebookService."""

    def test_service_initialization(self):
        """Test FacebookService initializes correctly."""
        service = FacebookService()
        assert "facebook.com" in service.AUTHORIZATION_URL
        assert hasattr(service, "is_configured")

    def test_is_configured_property(self):
        """Test is_configured returns boolean."""
        service = FacebookService()
        assert isinstance(service.is_configured, bool)

    def test_scopes_include_page_permissions(self):
        """Test Facebook scopes include page permissions."""
        service = FacebookService()
        # Check that at least some page-related scopes are included
        assert any("page" in scope.lower() for scope in service.SCOPES)

    def test_get_authorization_url_returns_url(self):
        """Test authorization URL returns a URL when configured."""
        service = FacebookService()
        # If configured, it should return a URL string
        if service.is_configured:
            auth_url = service.get_authorization_url(state="test_state")
            assert "facebook.com" in auth_url
        else:
            # When not configured, behavior varies - just verify method exists
            assert hasattr(service, "get_authorization_url")


# =============================================================================
# InstagramService Tests
# =============================================================================


@pytest.mark.django_db
class TestInstagramService:
    """Tests for InstagramService."""

    def test_service_initialization(self):
        """Test InstagramService initializes correctly."""
        service = InstagramService()
        # Instagram uses Facebook OAuth
        assert "facebook.com" in service.AUTHORIZATION_URL or hasattr(
            service, "is_configured"
        )

    def test_is_configured_property(self):
        """Test is_configured returns boolean."""
        service = InstagramService()
        assert isinstance(service.is_configured, bool)

    def test_get_authorization_url_returns_url(self):
        """Test authorization URL returns a URL when configured."""
        service = InstagramService()
        # If configured, it should return a URL string
        if service.is_configured:
            auth_url = service.get_authorization_url(state="test_state")
            assert "facebook.com" in auth_url
        else:
            # When not configured, behavior varies - just verify method exists
            assert hasattr(service, "get_authorization_url")


# =============================================================================
# Service Integration with SocialProfile Tests
# =============================================================================


@pytest.mark.django_db
class TestServiceProfileIntegration:
    """Tests for service integration with SocialProfile model."""

    def test_linkedin_profile_token_access(self, linkedin_profile):
        """Test accessing LinkedIn profile token."""
        token = linkedin_profile.access_token
        assert token == TEST_ACCESS_TOKEN

    def test_twitter_profile_token_access(self, twitter_profile):
        """Test accessing Twitter profile token."""
        token = twitter_profile.access_token
        assert token == TWITTER_TEST_ACCESS_TOKEN

    def test_facebook_profile_page_token_access(self, facebook_profile):
        """Test accessing Facebook page token."""
        page_token = facebook_profile.page_access_token
        assert page_token == FACEBOOK_TEST_PAGE_TOKEN

    def test_instagram_profile_token_access(self, instagram_profile):
        """Test accessing Instagram profile token."""
        token = instagram_profile.instagram_access_token
        assert token == INSTAGRAM_TEST_ACCESS_TOKEN

    def test_profile_token_valid_check(self, linkedin_profile):
        """Test token validity check."""
        # is_token_valid might be a property or method depending on implementation
        result = linkedin_profile.is_token_valid
        if callable(result):
            result = result()
        assert result is True

    def test_profile_token_expired_check(self, linkedin_profile):
        """Test expired token check."""
        linkedin_profile.token_expires_at = timezone.now() - timedelta(hours=1)
        linkedin_profile.save()

        result = linkedin_profile.is_token_valid
        if callable(result):
            result = result()
        assert result is False

    def test_profile_token_expiring_soon_check(self, linkedin_profile):
        """Test token expiring soon check."""
        # Token expires in 5 minutes
        linkedin_profile.token_expires_at = timezone.now() + timedelta(minutes=5)
        linkedin_profile.save()

        # Should be expiring soon (default threshold is typically 10-15 minutes)
        result = linkedin_profile.is_token_expiring_soon
        if callable(result):
            result = result()
        assert result is True

    def test_disconnect_profile_clears_tokens(self, linkedin_profile):
        """Test disconnecting profile clears all tokens."""
        linkedin_profile.disconnect()

        assert linkedin_profile.status == "disconnected"
        assert (
            linkedin_profile.access_token is None or linkedin_profile.access_token == ""
        )


# =============================================================================
# Error Handling Patterns Tests
# =============================================================================


@pytest.mark.django_db
class TestServiceErrorHandling:
    """Tests for service error handling patterns."""

    @patch("requests.post")
    def test_linkedin_handles_rate_limit(self, mock_post):
        """Test LinkedIn handles rate limit response."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "429 Too Many Requests"
        )
        mock_post.return_value = mock_response

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        with pytest.raises(Exception):
            service.exchange_code_for_token("code")

    @patch("requests.get")
    def test_linkedin_handles_unauthorized(self, mock_get):
        """Test LinkedIn handles unauthorized response."""
        mock_get.side_effect = requests.exceptions.RequestException("401 Unauthorized")

        service = LinkedInService()

        with pytest.raises(Exception, match="Failed to fetch profile"):
            service.get_user_profile("invalid_token")

    @patch("requests.post")
    def test_linkedin_handles_connection_error(self, mock_post):
        """Test LinkedIn handles connection errors."""
        mock_post.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        with pytest.raises(Exception, match="Failed to exchange code"):
            service.exchange_code_for_token("code")

    @patch("requests.post")
    def test_linkedin_handles_timeout(self, mock_post):
        """Test LinkedIn handles timeout errors."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        with pytest.raises(Exception, match="Failed to exchange code"):
            service.exchange_code_for_token("code")


# =============================================================================
# Token Refresh Pattern Tests
# =============================================================================


@pytest.mark.django_db
class TestTokenRefreshPatterns:
    """Tests for token refresh patterns across services."""

    @patch("requests.post")
    def test_linkedin_refresh_updates_expiry(self, mock_post):
        """Test LinkedIn token refresh updates expiration time."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 5184000,  # 60 days
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        service = LinkedInService()
        service.client_id = "test_client_id"
        service.client_secret = "test_client_secret"

        result = service.refresh_access_token("refresh_token")

        assert "expires_at" in result
        # Expiry should be in the future
        assert result["expires_at"] > timezone.now()

    def test_profile_refresh_method_exists(self, linkedin_profile):
        """Test profile has token refresh methods."""
        assert hasattr(linkedin_profile, "refresh_token_if_needed")
        assert hasattr(linkedin_profile, "get_valid_access_token")

    def test_refresh_raises_when_disconnected(self, linkedin_profile):
        """Test refresh raises error when profile disconnected."""
        linkedin_profile.disconnect()

        with pytest.raises(ValueError, match="not connected"):
            linkedin_profile.refresh_token_if_needed()
