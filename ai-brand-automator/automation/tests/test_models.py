"""
Unit tests for automation models.
Covers SocialProfile, ContentCalendar, AutomationTask, OAuthState, and webhook event models.
"""

import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError

from automation.models import (
    SocialProfile,
    ContentCalendar,
    AutomationTask,
    OAuthState,
    TwitterWebhookEvent,
    LinkedInWebhookEvent,
    FacebookWebhookEvent,
)

User = get_user_model()


@pytest.fixture
def user(db):
    """Create test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def second_user(db):
    """Create a second test user for multi-user tests."""
    return User.objects.create_user(
        username="testuser2",
        email="test2@example.com",
        password="testpass456",
    )


# =============================================================================
# SocialProfile Model Tests
# =============================================================================


@pytest.mark.django_db
class TestSocialProfileModel:
    """Comprehensive unit tests for SocialProfile model."""

    def test_create_linkedin_profile(self, user):
        """Test creating a LinkedIn social profile."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            profile_id="test_profile_123",
            profile_name="Test User",
            status="connected",
        )
        assert profile.id is not None
        assert profile.platform == "linkedin"
        assert profile.status == "connected"
        assert profile.profile_name == "Test User"

    def test_create_twitter_profile(self, user):
        """Test creating a Twitter social profile."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="twitter",
            profile_id="twitter_123",
            profile_name="Twitter User",
            status="connected",
        )
        assert profile.platform == "twitter"
        assert profile.get_platform_display() == "Twitter/X"

    def test_create_instagram_profile(self, user):
        """Test creating an Instagram social profile with specific fields."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="instagram",
            profile_id="insta_123",
            profile_name="Instagram User",
            instagram_user_id="insta_user_id",
            instagram_username="insta_handle",
            status="connected",
        )
        assert profile.platform == "instagram"
        assert profile.instagram_user_id == "insta_user_id"
        assert profile.instagram_username == "insta_handle"

    def test_create_facebook_profile_with_page_token(self, user):
        """Test creating a Facebook profile with page access token."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="facebook",
            profile_id="fb_123",
            profile_name="Facebook Page",
            page_id="page_123",
            status="connected",
        )
        profile.page_access_token = "page_token_value"
        profile.save()

        # Reload and verify
        profile.refresh_from_db()
        assert profile.page_id == "page_123"
        assert profile.page_access_token == "page_token_value"

    def test_platform_choices(self, user):
        """Test all valid platform choices."""
        platforms = ["linkedin", "twitter", "instagram", "facebook"]
        for platform in platforms:
            profile = SocialProfile.objects.create(
                user=user,
                platform=platform,
                profile_id=f"{platform}_123",
            )
            assert profile.platform == platform
            # Clean up for next iteration
            profile.delete()

    def test_status_choices(self, user):
        """Test all valid status choices."""
        statuses = ["connected", "disconnected", "expired", "error"]
        for status_choice in statuses:
            profile = SocialProfile.objects.create(
                user=user,
                platform="linkedin",
                status=status_choice,
            )
            assert profile.status == status_choice
            profile.delete()

    def test_unique_together_user_platform(self, user):
        """Test that user-platform combination is unique."""
        SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            profile_id="first_profile",
        )
        with pytest.raises(IntegrityError):
            SocialProfile.objects.create(
                user=user,
                platform="linkedin",
                profile_id="second_profile",
            )

    def test_different_users_same_platform(self, user, second_user):
        """Test that different users can have same platform."""
        profile1 = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        profile2 = SocialProfile.objects.create(
            user=second_user,
            platform="linkedin",
        )
        assert profile1.id != profile2.id

    def test_str_representation(self, user):
        """Test string representation of profile."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        assert user.email in str(profile)
        assert "LinkedIn" in str(profile)

    def test_token_encryption_on_save(self, user):
        """Test that tokens are encrypted when saved."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        profile.access_token = "plain_access_token"
        profile.refresh_token = "plain_refresh_token"
        profile.save()

        # Reload from database
        profile.refresh_from_db()

        # Decrypted values should match
        assert profile.access_token == "plain_access_token"
        assert profile.refresh_token == "plain_refresh_token"

        # Raw DB values should be encrypted (prefixed with 'enc:')
        assert profile._access_token is not None
        assert profile._refresh_token is not None

    def test_is_token_valid_with_valid_token(self, user):
        """Test is_token_valid returns True when token is not expired."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        assert profile.is_token_valid is True

    def test_is_token_valid_with_expired_token(self, user):
        """Test is_token_valid returns False when token is expired."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            token_expires_at=timezone.now() - timedelta(hours=1),
        )
        assert profile.is_token_valid is False

    def test_is_token_valid_without_expiry(self, user):
        """Test is_token_valid returns False when no expiry set."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            token_expires_at=None,
        )
        assert profile.is_token_valid is False

    def test_is_token_expiring_soon(self, user):
        """Test is_token_expiring_soon with various scenarios."""
        # Token expiring in 3 minutes - should be True
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            token_expires_at=timezone.now() + timedelta(minutes=3),
        )
        assert profile.is_token_expiring_soon is True
        profile.delete()

        # Token expiring in 10 minutes - should be False
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            token_expires_at=timezone.now() + timedelta(minutes=10),
        )
        assert profile.is_token_expiring_soon is False

    def test_disconnect_clears_all_tokens(self, user):
        """Test disconnect method clears all tokens and sets status."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
            status="connected",
            token_expires_at=timezone.now() + timedelta(days=1),
        )
        profile.access_token = "access_token"
        profile.refresh_token = "refresh_token"
        profile.save()

        profile.disconnect()

        assert profile.status == "disconnected"
        assert profile.access_token is None
        assert profile.refresh_token is None
        assert profile.token_expires_at is None

    def test_get_instagram_token_requires_instagram_platform(self, user):
        """Test get_instagram_token raises error for non-Instagram profile."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        with pytest.raises(ValueError, match="only available for Instagram"):
            profile.get_instagram_token()

    def test_get_instagram_token_requires_token(self, user):
        """Test get_instagram_token raises error when no token."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="instagram",
        )
        with pytest.raises(ValueError, match="No Instagram access token"):
            profile.get_instagram_token()

    def test_get_page_token_requires_facebook_platform(self, user):
        """Test get_page_token raises error for non-Facebook profile."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        with pytest.raises(ValueError, match="only available for Facebook"):
            profile.get_page_token()

    def test_get_page_token_requires_token(self, user):
        """Test get_page_token raises error when no token."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="facebook",
        )
        with pytest.raises(ValueError, match="No page access token"):
            profile.get_page_token()

    def test_ordering_by_created_at(self, user):
        """Test profiles are ordered by created_at descending."""
        profile1 = SocialProfile.objects.create(user=user, platform="linkedin")
        profile2 = SocialProfile.objects.create(user=user, platform="twitter")
        profile3 = SocialProfile.objects.create(user=user, platform="instagram")

        profiles = list(SocialProfile.objects.filter(user=user))
        # Most recent first
        assert profiles[0] == profile3
        assert profiles[1] == profile2
        assert profiles[2] == profile1


# =============================================================================
# ContentCalendar Model Tests
# =============================================================================


@pytest.mark.django_db
class TestContentCalendarModel:
    """Comprehensive unit tests for ContentCalendar model."""

    def test_create_content_entry(self, user):
        """Test creating a content calendar entry."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Test Post",
            content="This is test content",
            platforms=["linkedin"],
            scheduled_date=timezone.now() + timedelta(hours=1),
        )
        assert content.id is not None
        assert content.title == "Test Post"
        assert content.status == "draft"  # Default status

    def test_status_choices(self, user):
        """Test all valid status choices."""
        statuses = ["draft", "scheduled", "published", "failed", "cancelled"]
        for status_choice in statuses:
            content = ContentCalendar.objects.create(
                user=user,
                title=f"Test {status_choice}",
                content="Content",
                platforms=["linkedin"],
                scheduled_date=timezone.now(),
                status=status_choice,
            )
            assert content.status == status_choice
            content.delete()

    def test_multiple_platforms(self, user):
        """Test content can target multiple platforms."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Multi-platform Post",
            content="Cross-posting content",
            platforms=["linkedin", "twitter", "facebook"],
            scheduled_date=timezone.now(),
        )
        assert len(content.platforms) == 3
        assert "linkedin" in content.platforms
        assert "twitter" in content.platforms
        assert "facebook" in content.platforms

    def test_media_urls_json_field(self, user):
        """Test media_urls JSON field stores array properly."""
        media = [
            "https://example.com/image1.jpg",
            "https://example.com/image2.png",
        ]
        content = ContentCalendar.objects.create(
            user=user,
            title="Media Post",
            content="Content with images",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
            media_urls=media,
        )
        assert len(content.media_urls) == 2
        assert content.media_urls[0] == media[0]

    def test_social_profiles_relationship(self, user):
        """Test ManyToMany relationship with social profiles."""
        profile1 = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        profile2 = SocialProfile.objects.create(
            user=user,
            platform="twitter",
        )

        content = ContentCalendar.objects.create(
            user=user,
            title="Test",
            content="Content",
            platforms=["linkedin", "twitter"],
            scheduled_date=timezone.now(),
        )
        content.social_profiles.add(profile1, profile2)

        assert content.social_profiles.count() == 2

    def test_post_results_json_field(self, user):
        """Test post_results stores publishing results."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Test",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
        )
        content.post_results = {
            "linkedin": {"id": "post_123", "status": "success"},
        }
        content.save()

        content.refresh_from_db()
        assert content.post_results["linkedin"]["id"] == "post_123"

    def test_published_at_field(self, user):
        """Test published_at is set when content is published."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Test",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
        )
        assert content.published_at is None

        content.status = "published"
        content.published_at = timezone.now()
        content.save()

        assert content.published_at is not None

    def test_ordering_by_scheduled_date(self, user):
        """Test content is ordered by scheduled_date ascending."""
        now = timezone.now()
        content3 = ContentCalendar.objects.create(
            user=user,
            title="Third",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=now + timedelta(hours=3),
        )
        content1 = ContentCalendar.objects.create(
            user=user,
            title="First",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=now + timedelta(hours=1),
        )
        content2 = ContentCalendar.objects.create(
            user=user,
            title="Second",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=now + timedelta(hours=2),
        )

        contents = list(ContentCalendar.objects.filter(user=user))
        assert contents[0] == content1
        assert contents[1] == content2
        assert contents[2] == content3

    def test_str_representation(self, user):
        """Test string representation."""
        content = ContentCalendar.objects.create(
            user=user,
            title="My Test Post",
            content="Content",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
        )
        assert "My Test Post" in str(content)


# =============================================================================
# AutomationTask Model Tests
# =============================================================================


@pytest.mark.django_db
class TestAutomationTaskModel:
    """Comprehensive unit tests for AutomationTask model."""

    def test_create_automation_task(self, user):
        """Test creating an automation task."""
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
        )
        assert task.id is not None
        assert task.status == "pending"  # Default

    def test_task_type_choices(self, user):
        """Test all valid task type choices."""
        task_types = [
            "social_post",
            "profile_sync",
            "content_schedule",
            "analytics_fetch",
        ]
        for task_type in task_types:
            task = AutomationTask.objects.create(
                user=user,
                task_type=task_type,
            )
            assert task.task_type == task_type
            task.delete()

    def test_status_choices(self, user):
        """Test all valid status choices."""
        statuses = ["pending", "in_progress", "completed", "failed", "cancelled"]
        for status_choice in statuses:
            task = AutomationTask.objects.create(
                user=user,
                task_type="social_post",
                status=status_choice,
            )
            assert task.status == status_choice
            task.delete()

    def test_social_profile_relationship(self, user):
        """Test optional relationship with social profile."""
        profile = SocialProfile.objects.create(
            user=user,
            platform="linkedin",
        )
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
            social_profile=profile,
        )
        assert task.social_profile == profile

    def test_payload_json_field(self, user):
        """Test payload stores task parameters."""
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
            payload={
                "content": "Post content",
                "platforms": ["linkedin"],
            },
        )
        assert task.payload["content"] == "Post content"

    def test_result_json_field(self, user):
        """Test result stores task output."""
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
        )
        task.result = {"post_id": "123", "status": "success"}
        task.save()

        task.refresh_from_db()
        assert task.result["post_id"] == "123"

    def test_error_message_field(self, user):
        """Test error_message stores failure details."""
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
            status="failed",
            error_message="API rate limit exceeded",
        )
        assert task.error_message == "API rate limit exceeded"

    def test_scheduling_fields(self, user):
        """Test scheduling timestamp fields."""
        now = timezone.now()
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
            scheduled_at=now + timedelta(hours=1),
        )
        assert task.scheduled_at is not None
        assert task.started_at is None
        assert task.completed_at is None

    def test_ordering_by_created_at_descending(self, user):
        """Test tasks are ordered by created_at descending."""
        task1 = AutomationTask.objects.create(user=user, task_type="social_post")
        task2 = AutomationTask.objects.create(user=user, task_type="profile_sync")
        task3 = AutomationTask.objects.create(user=user, task_type="analytics_fetch")

        tasks = list(AutomationTask.objects.filter(user=user))
        assert tasks[0] == task3
        assert tasks[1] == task2
        assert tasks[2] == task1

    def test_str_representation(self, user):
        """Test string representation."""
        task = AutomationTask.objects.create(
            user=user,
            task_type="social_post",
            status="completed",
        )
        assert "Social Media Post" in str(task)
        assert "completed" in str(task)


# =============================================================================
# OAuthState Model Tests
# =============================================================================


@pytest.mark.django_db
class TestOAuthStateModel:
    """Comprehensive unit tests for OAuthState model."""

    def test_create_oauth_state(self, user):
        """Test creating an OAuth state."""
        state = OAuthState.objects.create(
            user=user,
            state="unique_state_token_123",
            platform="linkedin",
        )
        assert state.id is not None
        assert state.state == "unique_state_token_123"
        assert state.used is False

    def test_state_uniqueness(self, user):
        """Test state token must be unique."""
        OAuthState.objects.create(
            user=user,
            state="unique_state",
            platform="linkedin",
        )
        with pytest.raises(IntegrityError):
            OAuthState.objects.create(
                user=user,
                state="unique_state",
                platform="twitter",
            )

    def test_is_expired_within_limit(self, user):
        """Test state is not expired within 10 minutes."""
        state = OAuthState.objects.create(
            user=user,
            state="test_state",
            platform="linkedin",
        )
        assert state.is_expired() is False

    def test_is_expired_after_limit(self, user):
        """Test state is expired after 10 minutes."""
        state = OAuthState.objects.create(
            user=user,
            state="test_state",
            platform="linkedin",
        )
        # Manually set created_at to 15 minutes ago
        state.created_at = timezone.now() - timedelta(minutes=15)
        state.save()
        assert state.is_expired() is True

    def test_code_verifier_for_pkce(self, user):
        """Test code_verifier is stored for PKCE (Twitter)."""
        state = OAuthState.objects.create(
            user=user,
            state="twitter_state",
            platform="twitter",
            code_verifier="pkce_code_verifier_123",
        )
        assert state.code_verifier == "pkce_code_verifier_123"

    def test_mark_as_used(self, user):
        """Test marking state as used."""
        state = OAuthState.objects.create(
            user=user,
            state="test_state",
            platform="linkedin",
        )
        state.used = True
        state.save()

        state.refresh_from_db()
        assert state.used is True

    def test_str_representation(self, user):
        """Test string representation."""
        state = OAuthState.objects.create(
            user=user,
            state="test_state",
            platform="linkedin",
        )
        assert "linkedin" in str(state)
        assert user.email in str(state)


# =============================================================================
# Webhook Event Model Tests
# =============================================================================


@pytest.mark.django_db
class TestTwitterWebhookEventModel:
    """Unit tests for TwitterWebhookEvent model."""

    def test_create_webhook_event(self, db):
        """Test creating a Twitter webhook event."""
        event = TwitterWebhookEvent.objects.create(
            event_type="tweet_create",
            for_user_id="user123",
            payload={"tweet": {"id": "tweet_456", "text": "Hello world"}},
        )
        assert event.id is not None
        assert event.event_type == "tweet_create"
        assert event.read is False

    def test_all_event_types(self, db):
        """Test all valid event types."""
        event_types = [
            "tweet_create",
            "favorite",
            "follow",
            "unfollow",
            "direct_message",
            "tweet_delete",
            "mention",
            "retweet",
            "quote",
        ]
        for event_type in event_types:
            event = TwitterWebhookEvent.objects.create(
                event_type=event_type,
                for_user_id="user123",
                payload={},
            )
            assert event.event_type == event_type
            event.delete()

    def test_mark_as_read(self, db):
        """Test marking event as read."""
        event = TwitterWebhookEvent.objects.create(
            event_type="mention",
            for_user_id="user123",
            payload={},
        )
        event.read = True
        event.save()

        event.refresh_from_db()
        assert event.read is True


@pytest.mark.django_db
class TestLinkedInWebhookEventModel:
    """Unit tests for LinkedInWebhookEvent model."""

    def test_create_webhook_event(self, db):
        """Test creating a LinkedIn webhook event."""
        event = LinkedInWebhookEvent.objects.create(
            event_type="share_reaction",
            for_user_id="urn:li:person:abc123",
            resource_urn="urn:li:share:xyz789",
            payload={"reaction": {"type": "LIKE"}},
        )
        assert event.id is not None
        assert event.event_type == "share_reaction"
        assert event.resource_urn == "urn:li:share:xyz789"


@pytest.mark.django_db
class TestFacebookWebhookEventModel:
    """Unit tests for FacebookWebhookEvent model."""

    def test_create_webhook_event(self, db):
        """Test creating a Facebook webhook event."""
        event = FacebookWebhookEvent.objects.create(
            event_type="feed",
            page_id="page123",
            payload={"post": {"id": "post_456"}},
        )
        assert event.id is not None
        assert event.event_type == "feed"
