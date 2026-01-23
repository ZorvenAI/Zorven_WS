"""Tests for Google Business Profile integration."""

import pytest
import uuid
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from hypothesis import (
    given,
    strategies as st,
    settings as hypothesis_settings,
    HealthCheck,
)

from automation.models import GoogleBusinessProfile, GoogleBusinessLocation, OAuthState
from automation.services import google_business_service
from automation.serializers import (
    GoogleBusinessProfileSerializer,
    GoogleBusinessLocationSerializer,
    GoogleBusinessLocationCreateSerializer,
    GoogleBusinessAccountSerializer,
    GoogleBusinessCategorySerializer,
)

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="gbp_test_user", email="gbp@test.com", password="testpass123"
    )


@pytest.fixture
def api_client():
    """Create API client with tenant middleware support."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def authenticated_client(api_client, user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


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
        gbp_account_id="accounts/123456789",
        gbp_account_name="My Business Account",
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
            "mock_token", "accounts/mock123"
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
                "primary_category": "Restaurant",
            },
        )

        assert "name" in result
        assert result["title"] == "New Business"

    def test_mock_mode_update_location(self):
        """Test updating location in mock mode."""
        result = google_business_service.update_location(
            "mock_token", "locations/mock456", {"business_name": "Updated Business"}
        )

        assert "name" in result
        # Mock returns the updated title
        assert "title" in result

    def test_mock_mode_delete_location(self):
        """Test deleting location in mock mode."""
        # Should not raise an exception
        google_business_service.delete_location("mock_token", "locations/mock789")

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
            "mock_token", "locations/loc_123456789_001"
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


# =============================================================================
# SERIALIZER UNIT TESTS
# =============================================================================


class TestGoogleBusinessProfileSerializer:
    """Tests for GoogleBusinessProfileSerializer."""

    def test_serialize_profile(self, gbp_profile):
        """Test serializing a profile."""
        serializer = GoogleBusinessProfileSerializer(gbp_profile)
        data = serializer.data

        assert data["id"] == gbp_profile.id
        assert data["google_email"] == "test@example.com"
        assert data["status"] == "connected"
        assert data["status_display"] == "Connected"
        assert data["is_token_valid"] is True
        assert "location_count" in data

    def test_location_count(self, gbp_profile, gbp_location):
        """Test location_count is correct."""
        serializer = GoogleBusinessProfileSerializer(gbp_profile)
        assert serializer.data["location_count"] == 1

    def test_read_only_fields(self, gbp_profile):
        """Test that read-only fields cannot be modified."""
        serializer = GoogleBusinessProfileSerializer(
            gbp_profile, data={"google_email": "hacker@evil.com"}, partial=True
        )
        # Serializer is valid because read-only fields are ignored
        assert serializer.is_valid()
        # But the field doesn't change
        serializer.save()
        gbp_profile.refresh_from_db()
        assert gbp_profile.google_email == "test@example.com"


class TestGoogleBusinessLocationSerializer:
    """Tests for GoogleBusinessLocationSerializer."""

    def test_serialize_location(self, gbp_location):
        """Test serializing a location."""
        serializer = GoogleBusinessLocationSerializer(gbp_location)
        data = serializer.data

        assert data["id"] == gbp_location.id
        assert data["business_name"] == "Test Business"
        assert data["full_address"] == "123 Test Street, Test City, TS 12345, US"
        assert data["verification_status"] == "verified"
        assert data["verification_status_display"] == "Verified"

    def test_read_only_fields(self, gbp_location):
        """Test read-only fields in location serializer."""
        serializer = GoogleBusinessLocationSerializer(
            gbp_location, data={"location_id": "hacked"}, partial=True
        )
        assert serializer.is_valid()
        serializer.save()
        gbp_location.refresh_from_db()
        assert gbp_location.location_id == "locations/loc123"


class TestGoogleBusinessLocationCreateSerializer:
    """Tests for GoogleBusinessLocationCreateSerializer."""

    def test_valid_location_data(self):
        """Test validation with valid location data."""
        data = {
            "business_name": "My Restaurant",
            "primary_category": "Restaurant",
            "address_line1": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94102",
            "country": "US",
        }
        serializer = GoogleBusinessLocationCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_required_fields(self):
        """Test validation fails with missing required fields."""
        data = {"business_name": "Incomplete Business"}
        serializer = GoogleBusinessLocationCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "primary_category" in serializer.errors
        assert "address_line1" in serializer.errors
        assert "city" in serializer.errors

    def test_optional_fields(self):
        """Test optional fields are truly optional."""
        data = {
            "business_name": "Minimal Business",
            "primary_category": "Store",
            "address_line1": "1 Simple St",
            "city": "Town",
            "state": "ST",
            "postal_code": "00001",
        }
        serializer = GoogleBusinessLocationCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        # Check defaults
        assert serializer.validated_data.get("country") == "US"
        assert serializer.validated_data.get("business_hours") == {}

    def test_invalid_website_url(self):
        """Test validation fails with invalid URL."""
        data = {
            "business_name": "Bad URL Business",
            "primary_category": "Store",
            "address_line1": "1 Main St",
            "city": "Town",
            "state": "ST",
            "postal_code": "00001",
            "website_url": "not-a-valid-url",
        }
        serializer = GoogleBusinessLocationCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "website_url" in serializer.errors

    def test_valid_website_url(self):
        """Test validation passes with valid URL."""
        data = {
            "business_name": "Good URL Business",
            "primary_category": "Store",
            "address_line1": "1 Main St",
            "city": "Town",
            "state": "ST",
            "postal_code": "00001",
            "website_url": "https://example.com",
        }
        serializer = GoogleBusinessLocationCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors


class TestGoogleBusinessAccountSerializer:
    """Tests for GoogleBusinessAccountSerializer."""

    def test_serialize_account_output(self):
        """Test serializing account data for output (not input validation)."""
        # GoogleBusinessAccountSerializer uses source= mapping for output serialization
        # It's designed to serialize API response data, not validate input
        account_data = {
            "name": "accounts/123456789",
            "accountName": "My Business Account",
            "type": "LOCATION_GROUP",
            "role": "PRIMARY_OWNER",
        }
        serializer = GoogleBusinessAccountSerializer(account_data)
        output = serializer.data

        assert output["name"] == "accounts/123456789"
        assert output["account_name"] == "My Business Account"
        assert output["account_type"] == "LOCATION_GROUP"
        assert output["role"] == "PRIMARY_OWNER"


class TestGoogleBusinessCategorySerializer:
    """Tests for GoogleBusinessCategorySerializer."""

    def test_serialize_category_output(self):
        """Test serializing category data for output."""
        # GoogleBusinessCategorySerializer uses source= mapping for output serialization
        category_data = {
            "name": "categories/gcid:restaurant",
            "displayName": "Restaurant",
        }
        serializer = GoogleBusinessCategorySerializer(category_data)
        output = serializer.data

        assert output["name"] == "categories/gcid:restaurant"
        assert output["display_name"] == "Restaurant"


# =============================================================================
# API INTEGRATION TESTS
# =============================================================================


class TestGoogleBusinessConnectAPI:
    """Integration tests for Google Business Connect endpoint."""

    def test_connect_returns_auth_url(self, authenticated_client, user):
        """Test connect endpoint returns authorization URL."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/connect/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "authorization_url" in response.data
        assert "is_mock_mode" in response.data
        assert response.data["is_mock_mode"] is True

    def test_connect_returns_mock_mode_info(self, authenticated_client, user):
        """Test connect endpoint returns mock mode info when API not configured."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/connect/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_mock_mode"] is True
        assert response.data["requires_approval"] is True
        assert "message" in response.data
        assert "approval_url" in response.data
        # In mock mode, authorization_url is None
        assert response.data["authorization_url"] is None

    def test_connect_requires_authentication(self, api_client):
        """Test connect endpoint requires authentication."""
        response = api_client.get("/api/v1/automation/google-business/connect/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessDisconnectAPI:
    """Integration tests for Google Business Disconnect endpoint."""

    def test_disconnect_success(self, authenticated_client, user, gbp_profile):
        """Test disconnecting a profile."""
        response = authenticated_client.delete(
            "/api/v1/automation/google-business/disconnect/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "message" in response.data

        gbp_profile.refresh_from_db()
        assert gbp_profile.status == "disconnected"

    def test_disconnect_not_connected(self, authenticated_client, user):
        """Test disconnect when no profile exists."""
        response = authenticated_client.delete(
            "/api/v1/automation/google-business/disconnect/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_disconnect_requires_authentication(self, api_client):
        """Test disconnect endpoint requires authentication."""
        response = api_client.delete("/api/v1/automation/google-business/disconnect/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessTestConnectAPI:
    """Integration tests for Google Business Test Connect endpoint."""

    def test_test_connect_creates_mock_profile(self, authenticated_client, user):
        """Test test-connect creates a mock profile."""
        response = authenticated_client.post(
            "/api/v1/automation/google-business/test-connect/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "profile" in response.data
        assert response.data["profile"]["is_mock"] is True

        profile = GoogleBusinessProfile.objects.get(user=user)
        assert profile.status == "connected"
        assert profile.is_mock is True

    def test_test_connect_requires_authentication(self, api_client):
        """Test test-connect requires authentication."""
        response = api_client.post("/api/v1/automation/google-business/test-connect/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessStatusAPI:
    """Integration tests for Google Business Status endpoint."""

    def test_status_connected(self, authenticated_client, user, gbp_profile):
        """Test status when connected."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/status/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["connected"] is True
        assert response.data["profile"]["google_email"] == "test@example.com"

    def test_status_not_connected(self, authenticated_client, user):
        """Test status when not connected."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/status/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["connected"] is False
        assert response.data["profile"] is None

    def test_status_requires_authentication(self, api_client):
        """Test status requires authentication."""
        response = api_client.get("/api/v1/automation/google-business/status/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessAccountsAPI:
    """Integration tests for Google Business Accounts endpoint."""

    def test_list_accounts(self, authenticated_client, user, gbp_profile):
        """Test listing accounts."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/accounts/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "accounts" in response.data
        assert isinstance(response.data["accounts"], list)

    def test_list_accounts_not_connected(self, authenticated_client, user):
        """Test listing accounts when not connected."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/accounts/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_accounts_requires_authentication(self, api_client):
        """Test listing accounts requires authentication."""
        response = api_client.get("/api/v1/automation/google-business/accounts/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessSelectAccountAPI:
    """Integration tests for Google Business Select Account endpoint."""

    def test_select_account(self, authenticated_client, user, gbp_profile):
        """Test selecting an account."""
        # Mock service returns accounts with name like "accounts/123456789"
        # Use just the ID part - view checks both formats
        url = "/api/v1/automation/google-business/accounts/123456789/select/"
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert "profile" in response.data

    def test_select_account_not_found(self, authenticated_client, user, gbp_profile):
        """Test selecting non-existent account."""
        response = authenticated_client.post(
            "/api/v1/automation/google-business/accounts/nonexistent999/select/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_select_account_requires_authentication(self, api_client):
        """Test selecting account requires authentication."""
        response = api_client.post(
            "/api/v1/automation/google-business/accounts/123/select/"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessLocationsAPI:
    """Integration tests for Google Business Locations endpoint."""

    def test_list_locations(
        self, authenticated_client, user, gbp_profile, gbp_location
    ):
        """Test listing locations."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/locations/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "locations" in response.data
        assert response.data["count"] == 1
        assert response.data["locations"][0]["business_name"] == "Test Business"

    def test_list_locations_not_connected(self, authenticated_client, user):
        """Test listing locations when not connected."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/locations/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_locations_no_account_selected(self, authenticated_client, user, db):
        """Test listing locations when no account selected."""
        GoogleBusinessProfile.objects.create(
            user=user,
            status="connected",
            google_email="test@example.com",
            gbp_account_id=None,  # No account selected
        )
        response = authenticated_client.get(
            "/api/v1/automation/google-business/locations/"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_location(self, authenticated_client, user, gbp_profile):
        """Test creating a location."""
        data = {
            "business_name": "New Location",
            "primary_category": "Restaurant",
            "address_line1": "456 New St",
            "city": "New City",
            "state": "NC",
            "postal_code": "27000",
            "country": "US",
        }
        response = authenticated_client.post(
            "/api/v1/automation/google-business/locations/", data, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["location"]["business_name"] == "New Location"

        # Verify in database
        assert GoogleBusinessLocation.objects.filter(
            profile=gbp_profile, business_name="New Location"
        ).exists()

    def test_create_location_validation_error(
        self, authenticated_client, user, gbp_profile
    ):
        """Test creating location with invalid data."""
        data = {"business_name": "Incomplete"}  # Missing required fields
        response = authenticated_client.post(
            "/api/v1/automation/google-business/locations/", data, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "primary_category" in response.data

    def test_locations_require_authentication(self, api_client):
        """Test locations endpoint requires authentication."""
        response = api_client.get("/api/v1/automation/google-business/locations/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessLocationDetailAPI:
    """Integration tests for Google Business Location Detail endpoint."""

    def test_get_location_detail(
        self, authenticated_client, user, gbp_profile, gbp_location
    ):
        """Test getting location details."""
        response = authenticated_client.get(
            f"/api/v1/automation/google-business/locations/{gbp_location.id}/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["business_name"] == "Test Business"

    def test_get_location_not_found(self, authenticated_client, user, gbp_profile):
        """Test getting non-existent location."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/locations/99999/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_location(
        self, authenticated_client, user, gbp_profile, gbp_location
    ):
        """Test updating a location."""
        data = {"business_name": "Updated Business"}
        response = authenticated_client.patch(
            f"/api/v1/automation/google-business/locations/{gbp_location.id}/",
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        gbp_location.refresh_from_db()
        assert gbp_location.business_name == "Updated Business"

    def test_delete_location(
        self, authenticated_client, user, gbp_profile, gbp_location
    ):
        """Test deleting a location."""
        location_id = gbp_location.id
        response = authenticated_client.delete(
            f"/api/v1/automation/google-business/locations/{location_id}/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert not GoogleBusinessLocation.objects.filter(id=location_id).exists()

    def test_location_detail_requires_authentication(self, api_client, gbp_location):
        """Test location detail requires authentication."""
        response = api_client.get(
            f"/api/v1/automation/google-business/locations/{gbp_location.id}/"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGoogleBusinessCategoriesAPI:
    """Integration tests for Google Business Categories endpoint."""

    def test_list_categories(self, authenticated_client, user):
        """Test listing categories."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/categories/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "categories" in response.data
        assert isinstance(response.data["categories"], list)

    def test_search_categories(self, authenticated_client, user):
        """Test searching categories."""
        response = authenticated_client.get(
            "/api/v1/automation/google-business/categories/?q=restaurant"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "categories" in response.data

    def test_categories_require_authentication(self, api_client):
        """Test categories require authentication."""
        response = api_client.get("/api/v1/automation/google-business/categories/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================


@pytest.mark.django_db(transaction=True)
class TestGoogleBusinessPropertyTests:
    """Property-based tests using Hypothesis."""

    @given(
        address_line1=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        city=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        state=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
        postal_code=st.text(min_size=1, max_size=10).filter(lambda x: x.strip()),
        country=st.text(min_size=2, max_size=2).filter(lambda x: x.strip()),
    )
    @hypothesis_settings(
        max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_full_address_never_empty(
        self, db, gbp_profile, address_line1, city, state, postal_code, country
    ):
        """Test that full_address property always returns non-empty string."""
        location = GoogleBusinessLocation.objects.create(
            profile=gbp_profile,
            location_id=f"locations/{uuid.uuid4()}",
            business_name="Test",
            address_line1=address_line1,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
        )

        assert location.full_address
        assert isinstance(location.full_address, str)
        assert len(location.full_address) > 0

        # Cleanup
        location.delete()

    @given(hours_offset=st.integers(min_value=-100, max_value=100))
    @hypothesis_settings(
        max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_token_expiry_logic_consistent(self, db, user, hours_offset):
        """Test token validity is consistent with expiry time."""
        expiry_time = timezone.now() + timedelta(hours=hours_offset)

        profile = GoogleBusinessProfile.objects.create(
            user=user,
            google_account_id=f"accounts/{uuid.uuid4()}",
            google_email=f"test-{uuid.uuid4()}@example.com",
            token_expires_at=expiry_time,
        )

        if hours_offset > 0:
            assert profile.is_token_valid is True
        else:
            assert profile.is_token_valid is False

        # Cleanup
        profile.delete()

    @given(
        business_name=st.text(min_size=1, max_size=255).filter(lambda x: x.strip()),
        category=st.text(min_size=1, max_size=255).filter(lambda x: x.strip()),
    )
    @hypothesis_settings(max_examples=10)
    def test_location_create_serializer_requires_address(self, business_name, category):
        """Test that location create serializer always requires address fields."""
        data = {
            "business_name": business_name,
            "primary_category": category,
        }
        serializer = GoogleBusinessLocationCreateSerializer(data=data)

        assert not serializer.is_valid()
        # Must have address_line1, city, state, postal_code errors
        assert "address_line1" in serializer.errors
        assert "city" in serializer.errors

    @given(st.integers(min_value=1, max_value=5))
    @hypothesis_settings(
        max_examples=5,
        deadline=2000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_disconnect_idempotent(self, db, user, times):
        """Test that calling disconnect multiple times is safe."""
        profile = GoogleBusinessProfile.objects.create(
            user=user,
            google_account_id=f"accounts/{uuid.uuid4()}",
            google_email=f"test-{uuid.uuid4()}@example.com",
            status="connected",
            _access_token="token",
            _refresh_token="refresh",
        )

        # Call disconnect multiple times
        for _ in range(times):
            profile.disconnect()
            profile.refresh_from_db()

        # Should always end up disconnected
        assert profile.status == "disconnected"
        assert profile._access_token is None

        # Cleanup
        profile.delete()


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestGoogleBusinessEdgeCases:
    """Edge case tests for Google Business Profile."""

    def test_profile_with_empty_tokens(self, db, user):
        """Test profile with no tokens set."""
        profile = GoogleBusinessProfile.objects.create(
            user=user,
            google_account_id="accounts/empty",
            google_email="empty@example.com",
        )

        assert profile.access_token is None
        assert profile.refresh_token is None
        assert profile.is_token_valid is False

    def test_location_with_minimal_address(self, db, gbp_profile):
        """Test location with only required address fields."""
        location = GoogleBusinessLocation.objects.create(
            profile=gbp_profile,
            location_id="locations/minimal",
            business_name="Minimal",
            address_line1="1 St",
            city="A",
            state="B",
            postal_code="1",
            country="US",
        )

        assert location.full_address == "1 St, A, B 1, US"

    def test_location_with_special_characters(self, db, gbp_profile):
        """Test location with special characters in address."""
        location = GoogleBusinessLocation.objects.create(
            profile=gbp_profile,
            location_id="locations/special",
            business_name="Café & Bistro's Place",
            address_line1="123 O'Brien St",
            address_line2="Suite #200",
            city="San José",
            state="CA",
            postal_code="95101",
            country="US",
        )

        assert "O'Brien" in location.full_address
        assert "San José" in location.full_address

    def test_multiple_locations_same_profile(self, db, gbp_profile):
        """Test multiple locations for the same profile."""
        for i in range(5):
            GoogleBusinessLocation.objects.create(
                profile=gbp_profile,
                location_id=f"locations/multi_{i}",
                business_name=f"Location {i}",
                address_line1=f"{i} Test St",
                city="Test City",
                state="TS",
                postal_code="12345",
                country="US",
            )

        assert gbp_profile.locations.count() == 5

    def test_cascade_delete_multiple_locations(self, db, user):
        """Test cascade delete removes all locations."""
        profile = GoogleBusinessProfile.objects.create(
            user=user,
            google_account_id="accounts/cascade",
            google_email="cascade@example.com",
        )

        for i in range(3):
            GoogleBusinessLocation.objects.create(
                profile=profile,
                location_id=f"locations/cascade_{i}",
                business_name=f"Business {i}",
                address_line1="1 St",
                city="City",
                state="ST",
                postal_code="00000",
                country="US",
            )

        profile_id = profile.id
        profile.delete()

        assert not GoogleBusinessLocation.objects.filter(profile_id=profile_id).exists()

    def test_user_cannot_access_other_users_profile(
        self, authenticated_client, user, db
    ):
        """Test user cannot access another user's profile locations."""
        # Create another user with a profile
        other_user = User.objects.create_user(
            username="other_user", email="other@example.com", password="pass123"
        )
        other_profile = GoogleBusinessProfile.objects.create(
            user=other_user,
            google_account_id="accounts/other",
            google_email="other@example.com",
            status="connected",
            gbp_account_id="accounts/other123",
        )
        other_location = GoogleBusinessLocation.objects.create(
            profile=other_profile,
            location_id="locations/other",
            business_name="Other Business",
            address_line1="1 Other St",
            city="Other City",
            state="OT",
            postal_code="00000",
            country="US",
        )

        # Authenticated as 'user', try to access other_user's location
        response = authenticated_client.get(
            f"/api/v1/automation/google-business/locations/{other_location.id}/"
        )

        # Should not find it (404) because it belongs to different user
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_oauth_state_expiry(self, db, user):
        """Test OAuth state expiry logic."""
        # Create an expired state
        expired_state = OAuthState.objects.create(
            state="expired123",
            user=user,
            platform="google_business",
        )
        # Manually set created_at to past
        OAuthState.objects.filter(id=expired_state.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        expired_state.refresh_from_db()

        assert expired_state.is_expired() is True

        # Create a fresh state
        fresh_state = OAuthState.objects.create(
            state="fresh123",
            user=user,
            platform="google_business",
        )

        assert fresh_state.is_expired() is False
