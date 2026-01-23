"""Tests for Google Business Profile integration."""
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model

from automation.models import GoogleBusinessProfile, GoogleBusinessLocation
from automation.services import google_business_service

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="gbp_test_user",
        email="gbp@test.com",
        password="testpass123"
    )


@pytest.fixture
def gbp_profile(db, user):
    """Create a Google Business Profile for testing."""
    return GoogleBusinessProfile.objects.create(
        user=user,
        google_account_id="accounts/test123",
        google_account_name="Test Account",
        google_email="test@example.com",
        _access_token="test_access_token",
        _refresh_token="test_refresh_token",
        token_expires_at=timezone.now() + timedelta(hours=1),
        status="connected",
    )


@pytest.fixture
def gbp_location(db, gbp_profile):
    """Create a Google Business Location for testing."""
    return GoogleBusinessLocation.objects.create(
        profile=gbp_profile,
        location_id="locations/loc123",
        business_name="Test Business",
        address_line1="123 Test Street",
        city="Test City",
        state="TS",
        postal_code="12345",
        country="US",
        phone_number="+1-555-555-5555",
        primary_category="Restaurant",
        verification_status="verified",
        is_synced=True,
    )


class TestGoogleBusinessProfileModel:
    """Tests for GoogleBusinessProfile model."""

    def test_create_profile(self, db, user):
        """Test creating a Google Business Profile."""
        profile = GoogleBusinessProfile.objects.create(
            user=user,
            google_account_id="accounts/123",
            google_account_name="My Business Account",
            google_email="business@example.com",
        )
        assert profile.id is not None
        assert profile.user == user
        assert profile.google_account_id == "accounts/123"
        assert profile.status == "disconnected"  # Default

    def test_str_representation(self, gbp_profile):
        """Test string representation."""
        expected = f"{gbp_profile.user.email} - GBP (test@example.com, connected)"
        assert str(gbp_profile) == expected

    def test_is_token_valid_with_future_expiry(self, gbp_profile):
        """Test token validity with future expiry."""
        gbp_profile.token_expires_at = timezone.now() + timedelta(hours=1)
        gbp_profile.save()
        assert gbp_profile.is_token_valid is True

    def test_is_token_valid_with_past_expiry(self, gbp_profile):
        """Test token validity with past expiry."""
        gbp_profile.token_expires_at = timezone.now() - timedelta(hours=1)
        gbp_profile.save()
        assert gbp_profile.is_token_valid is False

    def test_is_token_valid_without_expiry(self, db, user):
        """Test token validity without expiry set."""
        profile = GoogleBusinessProfile.objects.create(
            user=user,
            google_account_id="accounts/123",
            google_account_name="Test",
            google_email="test@example.com",
            token_expires_at=None,
        )
        assert profile.is_token_valid is False

    def test_disconnect_clears_tokens(self, gbp_profile):
        """Test that disconnect clears all tokens."""
        gbp_profile.disconnect()
        gbp_profile.refresh_from_db()
        
        assert gbp_profile.status == "disconnected"
        assert gbp_profile._access_token is None
        assert gbp_profile._refresh_token is None
        assert gbp_profile.token_expires_at is None


class TestGoogleBusinessLocationModel:
    """Tests for GoogleBusinessLocation model."""

    def test_create_location(self, db, gbp_profile):
        """Test creating a location."""
        location = GoogleBusinessLocation.objects.create(
            profile=gbp_profile,
            location_id="locations/456",
            business_name="My Restaurant",
            address_line1="456 Main St",
            city="Anytown",
            state="CA",
            postal_code="90210",
            country="US",
        )
        assert location.id is not None
        assert location.profile == gbp_profile
        assert location.business_name == "My Restaurant"

    def test_str_representation(self, gbp_location):
        """Test string representation."""
        assert str(gbp_location) == "Test Business (Test City, TS)"

    def test_full_address_property(self, gbp_location):
        """Test full address property."""
        expected = "123 Test Street, Test City, TS 12345, US"
        assert gbp_location.full_address == expected

    def test_full_address_with_line2(self, db, gbp_profile):
        """Test full address with address line 2."""
        location = GoogleBusinessLocation.objects.create(
            profile=gbp_profile,
            location_id="locations/789",
            business_name="Suite Business",
            address_line1="100 Building Ave",
            address_line2="Suite 200",
            city="Metro City",
            state="NY",
            postal_code="10001",
            country="US",
        )
        expected = "100 Building Ave, Suite 200, Metro City, NY 10001, US"
        assert location.full_address == expected

    def test_cascade_delete_with_profile(self, db, gbp_profile, gbp_location):
        """Test that locations are deleted when profile is deleted."""
        location_id = gbp_location.id
        gbp_profile.delete()
        
        assert not GoogleBusinessLocation.objects.filter(id=location_id).exists()


class TestGoogleBusinessService:
    """Tests for GoogleBusinessService."""

    def test_service_is_singleton(self):
        """Test that service instance is available."""
        assert google_business_service is not None

    def test_is_mock_mode(self):
        """Test that service defaults to mock mode when not configured."""
        # By default, without env vars, should be in mock mode
        assert google_business_service.is_mock_mode is True

    def test_mock_mode_exchange_code(self):
        """Test exchanging code in mock mode."""
        result = google_business_service.exchange_code_for_token("test_code")
        
        assert "access_token" in result
        assert "refresh_token" in result
        assert "expires_in" in result
        assert result["access_token"].startswith("gbp_mock_")

    def test_mock_mode_list_accounts(self):
        """Test listing accounts in mock mode."""
        accounts = google_business_service.list_accounts("mock_token")
        
        assert isinstance(accounts, list)
        assert len(accounts) > 0
        assert "name" in accounts[0]
        assert "accountName" in accounts[0]

    def test_mock_mode_list_locations(self):
        """Test listing locations in mock mode."""
        locations = google_business_service.list_locations(
            "mock_token",
            "accounts/mock123"
        )
        
        assert isinstance(locations, list)
        assert len(locations) > 0
        assert "name" in locations[0]
        assert "title" in locations[0]
        assert "storefrontAddress" in locations[0]

    def test_mock_mode_create_location(self):
        """Test creating location in mock mode."""
        result = google_business_service.create_location(
            "mock_token",
            "accounts/mock123",
            {
                "business_name": "New Business",
                "address_line1": "123 New St",
                "city": "New City",
                "state": "NC",
                "postal_code": "27000",
                "country": "US",
                "phone_number": "+1-555-123-4567",
                "primary_category": "Restaurant"
            }
        )
        
        assert "name" in result
        assert result["title"] == "New Business"

    def test_mock_mode_update_location(self):
        """Test updating location in mock mode."""
        result = google_business_service.update_location(
            "mock_token",
            "locations/mock456",
            {"business_name": "Updated Business"}
        )
        
        assert "name" in result
        # Mock returns the updated title
        assert "title" in result

    def test_mock_mode_delete_location(self):
        """Test deleting location in mock mode."""
        # Should not raise an exception
        google_business_service.delete_location(
            "mock_token",
            "locations/mock789"
        )

    def test_mock_mode_get_user_info(self):
        """Test getting user info in mock mode."""
        result = google_business_service.get_user_info(
            google_business_service.MOCK_ACCESS_TOKEN
        )
        
        assert "email" in result
        assert "sub" in result

    def test_mock_mode_get_location(self):
        """Test getting a specific location in mock mode."""
        result = google_business_service.get_location(
            "mock_token",
            "locations/loc_123456789_001"
        )
        
        assert isinstance(result, dict)
        assert "name" in result or "title" in result


class TestGoogleBusinessServiceOAuth:
    """Tests for OAuth-related service methods."""

    def test_get_authorization_url(self):
        """Test getting OAuth authorization URL."""
        url = google_business_service.get_authorization_url(state="test_state_123")
        
        # In mock mode, returns a mock URL
        assert "state=test_state_123" in url
        # Mock mode returns frontend URL with mock_gbp_auth=true
        if google_business_service.is_mock_mode:
            assert "mock_gbp_auth=true" in url

    def test_authorization_url_contains_state(self):
        """Test that OAuth URL includes state parameter."""
        url = google_business_service.get_authorization_url(state="unique_state")
        
        assert "unique_state" in url

