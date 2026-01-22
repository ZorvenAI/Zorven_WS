"""
Integration tests for the automation app.

Tests end-to-end flows including:
- OAuth connection flows
- Content scheduling and publishing pipeline
- API endpoint interactions
- Cross-model workflows
"""

import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from automation.models import (
    SocialProfile,
    ContentCalendar,
    AutomationTask,
    OAuthState,
)
from automation.constants import (
    TEST_ACCESS_TOKEN,
    TEST_REFRESH_TOKEN,
    TWITTER_TEST_ACCESS_TOKEN,
    TWITTER_TEST_REFRESH_TOKEN,
    FACEBOOK_TEST_ACCESS_TOKEN,
    FACEBOOK_TEST_PAGE_TOKEN,
    INSTAGRAM_TEST_ACCESS_TOKEN,
)

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client with tenant middleware support."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def user(db):
    """Create test user."""
    return User.objects.create_user(
        username="integration_test_user",
        email="integration@example.com",
        password="testpass123",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def linkedin_profile(user):
    """Create a connected LinkedIn profile."""
    profile = SocialProfile.objects.create(
        user=user,
        platform="linkedin",
        profile_id="linkedin_user_123",
        profile_name="Test LinkedIn User",
        profile_url="https://linkedin.com/in/testuser",
        status="connected",
        token_expires_at=timezone.now() + timedelta(days=60),
    )
    profile.access_token = TEST_ACCESS_TOKEN
    profile.refresh_token = TEST_REFRESH_TOKEN
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
    profile.refresh_token = TWITTER_TEST_REFRESH_TOKEN
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


@pytest.fixture
def all_profiles(
    linkedin_profile, twitter_profile, facebook_profile, instagram_profile
):
    """Create all social profiles for a user."""
    return {
        "linkedin": linkedin_profile,
        "twitter": twitter_profile,
        "facebook": facebook_profile,
        "instagram": instagram_profile,
    }


# =============================================================================
# OAuth Flow Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestOAuthFlowIntegration:
    """Integration tests for OAuth connection flows."""

    def test_linkedin_oauth_state_creation(self, user):
        """Test OAuth state is properly created and validated."""
        import uuid

        state_token = str(uuid.uuid4())
        OAuthState.objects.create(
            user=user,
            state=state_token,
            platform="linkedin",
        )

        # Verify state can be retrieved
        retrieved = OAuthState.objects.get(state=state_token)
        assert retrieved.user == user
        assert retrieved.platform == "linkedin"
        assert retrieved.is_expired() is False

    def test_twitter_oauth_state_with_pkce(self, user):
        """Test Twitter OAuth state includes PKCE code verifier."""
        import uuid
        import secrets

        state_token = str(uuid.uuid4())
        code_verifier = secrets.token_urlsafe(32)

        OAuthState.objects.create(
            user=user,
            state=state_token,
            platform="twitter",
            code_verifier=code_verifier,
        )

        retrieved = OAuthState.objects.get(state=state_token)
        assert retrieved.code_verifier == code_verifier

    def test_oauth_state_expiration(self, user):
        """Test OAuth state properly expires after 10 minutes."""
        import uuid

        state_token = str(uuid.uuid4())
        oauth_state = OAuthState.objects.create(
            user=user,
            state=state_token,
            platform="linkedin",
        )

        # Initially not expired
        assert oauth_state.is_expired() is False

        # Manually set to 15 minutes ago
        oauth_state.created_at = timezone.now() - timedelta(minutes=15)
        oauth_state.save()

        # Now should be expired
        assert oauth_state.is_expired() is True

    def test_oauth_state_cleanup_on_reconnect(self, user):
        """Test old OAuth states are cleaned up on reconnect attempt."""
        import uuid

        # Create initial state
        old_state = str(uuid.uuid4())
        OAuthState.objects.create(
            user=user,
            state=old_state,
            platform="linkedin",
        )

        # Simulate reconnect - should clean up old states
        OAuthState.objects.filter(user=user, platform="linkedin").delete()
        new_state = str(uuid.uuid4())
        OAuthState.objects.create(
            user=user,
            state=new_state,
            platform="linkedin",
        )

        # Only new state should exist
        assert OAuthState.objects.filter(user=user, platform="linkedin").count() == 1
        assert OAuthState.objects.filter(state=old_state).exists() is False
        assert OAuthState.objects.filter(state=new_state).exists() is True


# =============================================================================
# Content Publishing Pipeline Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestContentPublishingPipeline:
    """Integration tests for the content publishing pipeline."""

    def test_schedule_content_for_single_platform(self, user, linkedin_profile):
        """Test scheduling content for a single platform."""
        scheduled_time = timezone.now() + timedelta(hours=1)

        content = ContentCalendar.objects.create(
            user=user,
            title="Single Platform Post",
            content="This is a test post for LinkedIn",
            platforms=["linkedin"],
            scheduled_date=scheduled_time,
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        assert content.status == "scheduled"
        assert content.social_profiles.count() == 1
        assert content.published_at is None

    def test_schedule_content_for_multiple_platforms(self, user, all_profiles):
        """Test scheduling content for multiple platforms."""
        scheduled_time = timezone.now() + timedelta(hours=2)

        content = ContentCalendar.objects.create(
            user=user,
            title="Multi-Platform Post",
            content="Cross-posting to all platforms!",
            platforms=["linkedin", "twitter", "facebook"],
            scheduled_date=scheduled_time,
            status="scheduled",
        )
        content.social_profiles.add(
            all_profiles["linkedin"],
            all_profiles["twitter"],
            all_profiles["facebook"],
        )

        assert len(content.platforms) == 3
        assert content.social_profiles.count() == 3

    def test_publish_content_updates_status(self, user, linkedin_profile):
        """Test publishing content updates status correctly."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Test Publish",
            content="Content to publish",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(minutes=5),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        # Simulate publishing
        content.status = "published"
        content.published_at = timezone.now()
        content.post_results = {
            "linkedin": {
                "id": "urn:li:share:123456",
                "status": "success",
            }
        }
        content.save()

        content.refresh_from_db()
        assert content.status == "published"
        assert content.published_at is not None
        assert "linkedin" in content.post_results

    def test_failed_publish_records_error(self, user, linkedin_profile):
        """Test failed publishing records error details."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Failed Post",
            content="This will fail",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(minutes=5),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        # Simulate failure
        content.status = "failed"
        content.post_results = {
            "linkedin": {
                "error": "API rate limit exceeded",
                "status": "failed",
            }
        }
        content.save()

        content.refresh_from_db()
        assert content.status == "failed"
        assert "error" in content.post_results["linkedin"]

    def test_cancel_scheduled_content(self, user, linkedin_profile):
        """Test cancelling scheduled content."""
        content = ContentCalendar.objects.create(
            user=user,
            title="To Be Cancelled",
            content="This will be cancelled",
            platforms=["linkedin"],
            scheduled_date=timezone.now() + timedelta(hours=1),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        content.status = "cancelled"
        content.save()

        content.refresh_from_db()
        assert content.status == "cancelled"


# =============================================================================
# Publish Helpers Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestPublishHelpersIntegration:
    """Integration tests for publish helper functions."""

    def test_publish_content_in_test_mode(self, user, linkedin_profile):
        """Test publish_content works in test mode."""
        from automation.publish_helpers import publish_content

        content = ContentCalendar.objects.create(
            user=user,
            title="Test Mode Post",
            content="Testing in test mode",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(minutes=1),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        results, errors = publish_content(content)

        assert "linkedin" in results
        assert results["linkedin"].get("test_mode") is True
        assert len(errors) == 0

    def test_update_content_status_on_success(self, user, linkedin_profile):
        """Test update_content_status marks content as published on success."""
        from automation.publish_helpers import update_content_status

        content = ContentCalendar.objects.create(
            user=user,
            title="Success Post",
            content="This will succeed",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
            status="scheduled",
        )

        results = {"linkedin": {"id": "post_123"}}
        errors = []

        final_status = update_content_status(content, results, errors)

        assert final_status == "published"
        content.refresh_from_db()
        assert content.status == "published"
        assert content.published_at is not None

    def test_update_content_status_on_failure(self, user, linkedin_profile):
        """Test update_content_status marks content as failed on errors."""
        from automation.publish_helpers import update_content_status

        content = ContentCalendar.objects.create(
            user=user,
            title="Failed Post",
            content="This will fail",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
            status="scheduled",
        )

        results = {}
        errors = ["linkedin: API Error"]

        final_status = update_content_status(content, results, errors)

        assert final_status == "failed"
        content.refresh_from_db()
        assert content.status == "failed"

    def test_update_content_status_partial_success(
        self, user, linkedin_profile, twitter_profile
    ):
        """Test update_content_status handles partial success."""
        from automation.publish_helpers import update_content_status

        content = ContentCalendar.objects.create(
            user=user,
            title="Partial Success",
            content="Partial success test",
            platforms=["linkedin", "twitter"],
            scheduled_date=timezone.now(),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile, twitter_profile)

        # One success, one failure
        results = {"linkedin": {"id": "post_123"}}
        errors = ["twitter: Rate limit exceeded"]

        final_status = update_content_status(content, results, errors)

        # Should still be marked as published if at least one succeeded
        assert final_status == "published"


# =============================================================================
# Celery Tasks Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestCeleryTasksIntegration:
    """Integration tests for Celery tasks."""

    def test_publish_scheduled_posts_task(self, user, linkedin_profile):
        """Test publish_scheduled_posts processes due posts."""
        from automation.tasks import publish_scheduled_posts

        # Create a post due for publishing
        content = ContentCalendar.objects.create(
            user=user,
            title="Due Post",
            content="This is due for publishing",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(minutes=5),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        result = publish_scheduled_posts()

        assert result["published"] >= 1
        content.refresh_from_db()
        assert content.status == "published"

    def test_publish_scheduled_posts_ignores_future_posts(self, user, linkedin_profile):
        """Test publish_scheduled_posts ignores posts scheduled for future."""
        from automation.tasks import publish_scheduled_posts

        # Create a post scheduled for the future
        content = ContentCalendar.objects.create(
            user=user,
            title="Future Post",
            content="Not due yet",
            platforms=["linkedin"],
            scheduled_date=timezone.now() + timedelta(hours=1),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        publish_scheduled_posts()

        content.refresh_from_db()
        assert content.status == "scheduled"  # Still scheduled, not published

    def test_publish_single_post_task(self, user, linkedin_profile):
        """Test publish_single_post publishes a specific post."""
        from automation.tasks import publish_single_post

        content = ContentCalendar.objects.create(
            user=user,
            title="Single Post",
            content="Publishing single post",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(minutes=1),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        result = publish_single_post(content.id)

        assert result["status"] == "published"
        assert "linkedin" in result["results"]

    def test_publish_single_post_not_found(self):
        """Test publish_single_post handles non-existent content."""
        from automation.tasks import publish_single_post

        result = publish_single_post(99999)
        assert "error" in result
        assert result["error"] == "Content not found"

    def test_publish_single_post_already_published(self, user, linkedin_profile):
        """Test publish_single_post handles already published content."""
        from automation.tasks import publish_single_post

        content = ContentCalendar.objects.create(
            user=user,
            title="Already Published",
            content="Already published",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(hours=1),
            status="published",
            published_at=timezone.now() - timedelta(minutes=30),
        )
        content.social_profiles.add(linkedin_profile)

        result = publish_single_post(content.id)

        assert "error" in result
        assert "not scheduled" in result["error"]


# =============================================================================
# Cross-Model Workflow Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestCrossModelWorkflows:
    """Integration tests for workflows spanning multiple models."""

    def test_disconnect_profile_does_not_affect_published_content(
        self, user, linkedin_profile
    ):
        """Test disconnecting profile doesn't affect already published content."""
        # Create published content
        content = ContentCalendar.objects.create(
            user=user,
            title="Published Post",
            content="Already published",
            platforms=["linkedin"],
            scheduled_date=timezone.now() - timedelta(hours=1),
            status="published",
            published_at=timezone.now() - timedelta(minutes=30),
        )
        content.social_profiles.add(linkedin_profile)

        # Disconnect profile
        linkedin_profile.disconnect()

        # Content should still be published
        content.refresh_from_db()
        assert content.status == "published"
        assert content.social_profiles.count() == 1

    def test_automation_task_tracks_publish_operation(self, user, linkedin_profile):
        """Test automation task can track publishing operations."""
        content = ContentCalendar.objects.create(
            user=user,
            title="Tracked Post",
            content="Tracked by automation task",
            platforms=["linkedin"],
            scheduled_date=timezone.now(),
            status="scheduled",
        )
        content.social_profiles.add(linkedin_profile)

        # Create task to track the operation
        task = AutomationTask.objects.create(
            user=user,
            social_profile=linkedin_profile,
            task_type="social_post",
            status="pending",
            payload={"content_id": content.id},
        )

        # Simulate task execution
        task.status = "in_progress"
        task.started_at = timezone.now()
        task.save()

        # Simulate publishing
        content.status = "published"
        content.published_at = timezone.now()
        content.save()

        # Complete task
        task.status = "completed"
        task.completed_at = timezone.now()
        task.result = {"post_id": "urn:li:share:123"}
        task.save()

        assert task.status == "completed"
        assert content.status == "published"

    def test_user_can_have_multiple_profiles_and_content(self, user, all_profiles):
        """Test user can manage multiple profiles and content simultaneously."""
        # Create content for each platform
        contents = []
        for platform, profile in all_profiles.items():
            content = ContentCalendar.objects.create(
                user=user,
                title=f"{platform.title()} Post",
                content=f"Post for {platform}",
                platforms=[platform],
                scheduled_date=timezone.now() + timedelta(hours=1),
                status="scheduled",
            )
            content.social_profiles.add(profile)
            contents.append(content)

        # Verify
        assert SocialProfile.objects.filter(user=user).count() == 4
        assert ContentCalendar.objects.filter(user=user).count() == 4

        # Each content should have exactly one profile
        for content in contents:
            assert content.social_profiles.count() == 1


# =============================================================================
# Token Refresh Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestTokenRefreshIntegration:
    """Integration tests for token refresh workflows."""

    def test_get_valid_access_token_returns_current_when_valid(self, linkedin_profile):
        """Test get_valid_access_token returns current token when valid."""
        # Token expires in the future
        linkedin_profile.token_expires_at = timezone.now() + timedelta(hours=1)
        linkedin_profile.save()

        token = linkedin_profile.get_valid_access_token()
        assert token == TEST_ACCESS_TOKEN

    def test_refresh_token_if_needed_for_facebook_returns_page_token(
        self, facebook_profile
    ):
        """Test Facebook profile returns page token for posting."""
        facebook_profile.token_expires_at = timezone.now() + timedelta(hours=1)
        facebook_profile.save()

        token = facebook_profile.refresh_token_if_needed()
        assert token == FACEBOOK_TEST_PAGE_TOKEN

    def test_disconnected_profile_raises_on_token_access(self, linkedin_profile):
        """Test disconnected profile raises error on token refresh."""
        linkedin_profile.disconnect()

        with pytest.raises(ValueError, match="not connected"):
            linkedin_profile.refresh_token_if_needed()


# =============================================================================
# Webhook Event Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestWebhookEventIntegration:
    """Integration tests for webhook event handling."""

    def test_create_and_retrieve_twitter_webhook_events(self, user):
        """Test creating and retrieving Twitter webhook events."""
        from automation.models import TwitterWebhookEvent

        # Create multiple events
        events = []
        for i in range(5):
            event = TwitterWebhookEvent.objects.create(
                event_type="mention",
                for_user_id="twitter_user_123",
                payload={"tweet_id": f"tweet_{i}"},
            )
            events.append(event)

        # Retrieve unread events
        unread = TwitterWebhookEvent.objects.filter(
            for_user_id="twitter_user_123",
            read=False,
        )
        assert unread.count() == 5

        # Mark as read
        unread.update(read=True)

        # Verify all marked as read
        still_unread = TwitterWebhookEvent.objects.filter(
            for_user_id="twitter_user_123",
            read=False,
        )
        assert still_unread.count() == 0

    def test_create_and_retrieve_linkedin_webhook_events(self, user):
        """Test creating and retrieving LinkedIn webhook events."""
        from automation.models import LinkedInWebhookEvent

        event = LinkedInWebhookEvent.objects.create(
            event_type="share_reaction",
            for_user_id="urn:li:person:abc123",
            resource_urn="urn:li:share:xyz789",
            payload={"reaction": {"type": "LIKE"}},
        )

        retrieved = LinkedInWebhookEvent.objects.get(id=event.id)
        assert retrieved.event_type == "share_reaction"
        assert retrieved.resource_urn == "urn:li:share:xyz789"
