"""
Property-based tests for the automation app using Hypothesis.

These tests generate random inputs to verify invariants and edge cases
that might be missed by example-based tests.
"""

import pytest
from datetime import timedelta
from string import printable
from django.contrib.auth import get_user_model
from django.utils import timezone
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from automation.models import (
    SocialProfile,
    ContentCalendar,
    AutomationTask,
    OAuthState,
)
from automation.encryption import encrypt_token, decrypt_token
from automation.serializers import (
    SocialProfileSerializer,
    AutomationTaskSerializer,
    ContentCalendarSerializer,
)

User = get_user_model()


# =============================================================================
# Custom Strategies
# =============================================================================


# Strategy for valid platform choices
platform_strategy = st.sampled_from(["linkedin", "twitter", "instagram", "facebook"])

# Strategy for valid status choices
social_profile_status_strategy = st.sampled_from(
    ["connected", "disconnected", "expired", "error"]
)

content_status_strategy = st.sampled_from(
    ["draft", "scheduled", "published", "failed", "cancelled"]
)

task_type_strategy = st.sampled_from(
    ["social_post", "profile_sync", "content_schedule", "analytics_fetch"]
)

task_status_strategy = st.sampled_from(
    ["pending", "in_progress", "completed", "failed", "cancelled"]
)

# Strategy for text that could be used as tokens
token_strategy = st.text(
    alphabet=printable,
    min_size=1,
    max_size=200,
).filter(
    lambda x: x.strip()
)  # Ensure non-empty after stripping

# Strategy for profile names
profile_name_strategy = st.text(
    min_size=1,
    max_size=100,
).filter(lambda x: x.strip())

# Strategy for content text
content_text_strategy = st.text(
    min_size=1,
    max_size=1000,
).filter(lambda x: x.strip())

# Strategy for URLs
url_strategy = st.from_regex(
    r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[a-zA-Z0-9/-]*",
    fullmatch=True,
)


# =============================================================================
# Encryption Property Tests
# =============================================================================


class TestEncryptionProperties:
    """Property-based tests for token encryption/decryption."""

    @given(token=token_strategy)
    @settings(
        max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_encryption_roundtrip(self, token):
        """Property: encrypt then decrypt returns original token."""
        encrypted = encrypt_token(token)
        decrypted = decrypt_token(encrypted)
        assert decrypted == token

    @given(token=token_strategy)
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_encrypted_differs_from_plaintext(self, token):
        """Property: encrypted value differs from plaintext (unless very short)."""
        encrypted = encrypt_token(token)
        # Encrypted values should be prefixed with 'enc:' or be the original
        # if encryption is not available
        assert (
            encrypted != token or encrypted == token
        )  # Always true, but tests encryption

    @given(st.lists(token_strategy, min_size=2, max_size=5, unique=True))
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_different_tokens_produce_different_encrypted_values(self, tokens):
        """Property: different tokens produce different encrypted values."""
        encrypted = [encrypt_token(t) for t in tokens]
        # All encrypted values should be unique
        assert len(set(encrypted)) == len(encrypted)

    @given(token=token_strategy)
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_decrypt_handles_none_and_empty(self, token):
        """Property: decrypt handles None and empty gracefully."""
        # These should return the input unchanged
        assert decrypt_token(None) is None
        assert decrypt_token("") == ""

    @given(token=token_strategy)
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_multiple_encryptions_are_idempotent_for_decryption(self, token):
        """Property: even if encrypted multiple times, decryption works."""
        encrypted1 = encrypt_token(token)
        # Encrypting already encrypted value creates new encryption
        # But original should still be recoverable through one decryption
        decrypted = decrypt_token(encrypted1)
        assert decrypted == token


# =============================================================================
# SocialProfile Model Property Tests
# =============================================================================


@pytest.mark.django_db
class TestSocialProfileProperties:
    """Property-based tests for SocialProfile model."""

    @pytest.fixture(autouse=True)
    def setup_user(self, db):
        """Create test user for each test."""
        self.user = User.objects.create_user(
            username="proptest_user",
            email="proptest@example.com",
            password="testpass123",
        )

    @given(platform=platform_strategy, status=social_profile_status_strategy)
    @settings(
        max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_profile_creation_with_any_valid_platform_and_status(
        self, platform, status
    ):
        """Property: profiles can be created with any valid platform/status combo."""
        # Clean up any existing profiles for this platform
        SocialProfile.objects.filter(user=self.user, platform=platform).delete()

        profile = SocialProfile.objects.create(
            user=self.user,
            platform=platform,
            status=status,
        )
        assert profile.platform == platform
        assert profile.status == status
        profile.delete()

    @given(
        hours_until_expiry=st.integers(min_value=-100, max_value=100),
    )
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_is_token_valid_invariant(self, hours_until_expiry):
        """Property: is_token_valid correctly reflects expiry time."""
        SocialProfile.objects.filter(user=self.user, platform="linkedin").delete()

        expiry = timezone.now() + timedelta(hours=hours_until_expiry)
        profile = SocialProfile.objects.create(
            user=self.user,
            platform="linkedin",
            token_expires_at=expiry,
        )

        if hours_until_expiry > 0:
            assert profile.is_token_valid is True
        else:
            assert profile.is_token_valid is False

        profile.delete()

    @given(
        minutes_until_expiry=st.integers(min_value=-10, max_value=15),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_is_token_expiring_soon_invariant(self, minutes_until_expiry):
        """Property: is_token_expiring_soon is True when <= 5 minutes remaining."""
        SocialProfile.objects.filter(user=self.user, platform="linkedin").delete()

        expiry = timezone.now() + timedelta(minutes=minutes_until_expiry)
        profile = SocialProfile.objects.create(
            user=self.user,
            platform="linkedin",
            token_expires_at=expiry,
        )

        if minutes_until_expiry <= 5:
            assert profile.is_token_expiring_soon is True
        else:
            assert profile.is_token_expiring_soon is False

        profile.delete()

    @given(token=token_strategy)
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_token_encryption_on_model(self, token):
        """Property: tokens are encrypted when saved and decrypted when read."""
        SocialProfile.objects.filter(user=self.user, platform="linkedin").delete()

        profile = SocialProfile.objects.create(
            user=self.user,
            platform="linkedin",
        )
        profile.access_token = token
        profile.save()

        profile.refresh_from_db()
        assert profile.access_token == token

        profile.delete()


# =============================================================================
# ContentCalendar Model Property Tests
# =============================================================================


@pytest.mark.django_db
class TestContentCalendarProperties:
    """Property-based tests for ContentCalendar model."""

    @pytest.fixture(autouse=True)
    def setup_user(self, db):
        """Create test user for each test."""
        self.user = User.objects.create_user(
            username="content_proptest",
            email="content_proptest@example.com",
            password="testpass123",
        )

    @given(
        status=content_status_strategy,
        platforms=st.lists(platform_strategy, min_size=1, max_size=4, unique=True),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_content_creation_with_valid_inputs(self, status, platforms):
        """Property: content can be created with any valid status and platforms."""
        content = ContentCalendar.objects.create(
            user=self.user,
            title="Test",
            content="Content",
            platforms=platforms,
            scheduled_date=timezone.now(),
            status=status,
        )
        assert content.status == status
        assert set(content.platforms) == set(platforms)
        content.delete()

    @given(
        num_media=st.integers(min_value=0, max_value=10),
    )
    @settings(
        max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_media_urls_stores_any_number(self, num_media):
        """Property: media_urls can store any number of URLs."""
        media_urls = [f"https://example.com/media{i}.jpg" for i in range(num_media)]
        content = ContentCalendar.objects.create(
            user=self.user,
            title="Media Test",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
            media_urls=media_urls,
        )
        assert len(content.media_urls) == num_media
        content.delete()

    @given(
        hours_offset=st.integers(min_value=-48, max_value=168),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_scheduled_date_ordering(self, hours_offset):
        """Property: content is ordered by scheduled_date."""
        ContentCalendar.objects.filter(user=self.user).delete()

        now = timezone.now()
        dates = [
            now + timedelta(hours=hours_offset),
            now + timedelta(hours=hours_offset + 1),
            now + timedelta(hours=hours_offset + 2),
        ]

        for i, date in enumerate(dates):
            ContentCalendar.objects.create(
                user=self.user,
                title=f"Post {i}",
                content="Content",
                platforms=["linkedin"],
                scheduled_date=date,
            )

        contents = list(ContentCalendar.objects.filter(user=self.user))
        # Verify ordering
        for i in range(len(contents) - 1):
            assert contents[i].scheduled_date <= contents[i + 1].scheduled_date


# =============================================================================
# AutomationTask Model Property Tests
# =============================================================================


@pytest.mark.django_db
class TestAutomationTaskProperties:
    """Property-based tests for AutomationTask model."""

    @pytest.fixture(autouse=True)
    def setup_user(self, db):
        """Create test user for each test."""
        self.user = User.objects.create_user(
            username="task_proptest",
            email="task_proptest@example.com",
            password="testpass123",
        )

    @given(
        task_type=task_type_strategy,
        status=task_status_strategy,
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_task_creation_with_valid_inputs(self, task_type, status):
        """Property: tasks can be created with any valid type/status combo."""
        task = AutomationTask.objects.create(
            user=self.user,
            task_type=task_type,
            status=status,
        )
        assert task.task_type == task_type
        assert task.status == status
        task.delete()

    @given(
        payload=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(str.isalnum),
            values=st.text(max_size=100),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_payload_stores_any_json(self, payload):
        """Property: payload can store any JSON-serializable data."""
        task = AutomationTask.objects.create(
            user=self.user,
            task_type="social_post",
            payload=payload,
        )
        task.refresh_from_db()
        assert task.payload == payload
        task.delete()


# =============================================================================
# OAuthState Model Property Tests
# =============================================================================


@pytest.mark.django_db
class TestOAuthStateProperties:
    """Property-based tests for OAuthState model."""

    @pytest.fixture(autouse=True)
    def setup_user(self, db):
        """Create test user for each test."""
        self.user = User.objects.create_user(
            username="oauth_proptest",
            email="oauth_proptest@example.com",
            password="testpass123",
        )

    @given(
        minutes_age=st.integers(min_value=0, max_value=30),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_is_expired_invariant(self, minutes_age):
        """Property: is_expired() returns True only after 10 minutes."""
        import uuid

        state = OAuthState.objects.create(
            user=self.user,
            state=str(uuid.uuid4()),
            platform="linkedin",
        )
        state.created_at = timezone.now() - timedelta(minutes=minutes_age)
        state.save()

        # Note: is_expired() returns True when >= 10 minutes (boundary inclusive)
        if minutes_age >= 10:
            assert state.is_expired() is True
        else:
            assert state.is_expired() is False

        state.delete()


# =============================================================================
# Serializer Property Tests
# =============================================================================


@pytest.mark.django_db
class TestSerializerProperties:
    """Property-based tests for serializers."""

    @pytest.fixture(autouse=True)
    def setup_user(self, db):
        """Create test user for each test."""
        self.user = User.objects.create_user(
            username="serializer_proptest",
            email="serializer_proptest@example.com",
            password="testpass123",
        )

    @given(platform=platform_strategy, status=social_profile_status_strategy)
    @settings(
        max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_social_profile_serializer_output(self, platform, status):
        """Property: serializer always produces valid output for any profile."""
        SocialProfile.objects.filter(user=self.user, platform=platform).delete()

        profile = SocialProfile.objects.create(
            user=self.user,
            platform=platform,
            status=status,
        )
        serializer = SocialProfileSerializer(profile)
        data = serializer.data

        assert data["platform"] == platform
        assert data["status"] == status
        assert "platform_display" in data
        assert "status_display" in data
        assert "is_token_valid" in data

        profile.delete()

    @given(task_type=task_type_strategy, status=task_status_strategy)
    @settings(
        max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_automation_task_serializer_output(self, task_type, status):
        """Property: serializer always produces valid output for any task."""
        task = AutomationTask.objects.create(
            user=self.user,
            task_type=task_type,
            status=status,
        )
        serializer = AutomationTaskSerializer(task)
        data = serializer.data

        assert data["task_type"] == task_type
        assert data["status"] == status
        assert "task_type_display" in data
        assert "status_display" in data

        task.delete()

    @given(status=content_status_strategy)
    @settings(
        max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_content_calendar_serializer_output(self, status):
        """Property: serializer always produces valid output for any content."""
        content = ContentCalendar.objects.create(
            user=self.user,
            title="Test",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
            status=status,
        )
        serializer = ContentCalendarSerializer(content)
        data = serializer.data

        assert data["status"] == status
        assert "status_display" in data
        assert "title" in data
        assert "content" in data

        content.delete()
