"""
Automation models for social media integration and content scheduling.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from .encryption import encrypt_token, decrypt_token

User = get_user_model()


class SocialProfile(models.Model):
    """
    Stores connected social media accounts (LinkedIn, Twitter, Instagram, etc.)

    OAuth tokens are encrypted at rest for security.
    """

    PLATFORM_CHOICES = [
        ("linkedin", "LinkedIn"),
        ("twitter", "Twitter/X"),
        ("instagram", "Instagram"),
        ("facebook", "Facebook"),
    ]

    STATUS_CHOICES = [
        ("connected", "Connected"),
        ("disconnected", "Disconnected"),
        ("expired", "Token Expired"),
        ("error", "Error"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="social_profiles"
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)

    # OAuth tokens (encrypted at rest)
    _access_token = models.TextField(blank=True, null=True, db_column="access_token")
    _refresh_token = models.TextField(blank=True, null=True, db_column="refresh_token")
    token_expires_at = models.DateTimeField(blank=True, null=True)

    # Facebook-specific: Page access token (for posting to pages)
    # This is stored separately because Facebook uses user tokens for auth
    # but requires page tokens for posting to pages
    _page_access_token = models.TextField(
        blank=True, null=True, db_column="page_access_token"
    )
    page_id = models.CharField(max_length=255, blank=True, null=True)

    # Instagram-specific: Business account linked to Facebook Page
    # Instagram requires a Facebook Page connection for the Graph API
    instagram_user_id = models.CharField(
        max_length=255, blank=True, null=True, help_text="Instagram Business Account ID"
    )
    instagram_username = models.CharField(
        max_length=255, blank=True, null=True, help_text="Instagram username (handle)"
    )
    _instagram_access_token = models.TextField(
        blank=True,
        null=True,
        db_column="instagram_access_token",
        help_text="Instagram Graph API access token",
    )

    # Profile information from the platform
    profile_id = models.CharField(max_length=255, blank=True, null=True)
    profile_name = models.CharField(max_length=255, blank=True, null=True)
    profile_url = models.URLField(blank=True, null=True)
    profile_image_url = models.URLField(blank=True, null=True)

    # Connection status
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="disconnected"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ["user", "platform"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.get_platform_display()}"

    # Encrypted token properties
    @property
    def access_token(self):
        """Get the decrypted access token."""
        return decrypt_token(self._access_token) if self._access_token else None

    @access_token.setter
    def access_token(self, value):
        """Set and encrypt the access token."""
        self._access_token = encrypt_token(value) if value else None

    @property
    def refresh_token(self):
        """Get the decrypted refresh token."""
        return decrypt_token(self._refresh_token) if self._refresh_token else None

    @refresh_token.setter
    def refresh_token(self, value):
        """Set and encrypt the refresh token."""
        self._refresh_token = encrypt_token(value) if value else None

    @property
    def page_access_token(self):
        """Get the decrypted page access token (Facebook only)."""
        return (
            decrypt_token(self._page_access_token) if self._page_access_token else None
        )

    @page_access_token.setter
    def page_access_token(self, value):
        """Set and encrypt the page access token (Facebook only)."""
        self._page_access_token = encrypt_token(value) if value else None

    @property
    def instagram_access_token(self):
        """Get the decrypted Instagram access token."""
        return (
            decrypt_token(self._instagram_access_token)
            if self._instagram_access_token
            else None
        )

    @instagram_access_token.setter
    def instagram_access_token(self, value):
        """Set and encrypt the Instagram access token."""
        self._instagram_access_token = encrypt_token(value) if value else None

    def get_instagram_token(self):
        """
        Get the Instagram Graph API access token.
        This is used for posting to Instagram Business accounts.
        """
        if self.platform != "instagram":
            raise ValueError("Instagram token is only available for Instagram")
        if not self.instagram_access_token:
            raise ValueError("No Instagram access token available")
        return self.instagram_access_token

    @property
    def is_token_valid(self):
        """Check if the access token is still valid."""
        if not self.token_expires_at:
            return False
        return timezone.now() < self.token_expires_at

    @property
    def is_token_expiring_soon(self):
        """Check if the token will expire within 5 minutes."""
        if not self.token_expires_at:
            return True
        from datetime import timedelta

        return timezone.now() + timedelta(minutes=5) >= self.token_expires_at

    def refresh_token_if_needed(self):
        """
        Refresh the access token if it's expired or expiring soon.
        Returns the current (or refreshed) access token.
        """
        if self.status != "connected":
            raise ValueError("Profile is not connected")

        if not self.is_token_expiring_soon:
            # For Facebook, return page token for posting
            if self.platform == "facebook" and self.page_access_token:
                return self.page_access_token
            return self.access_token

        # Facebook page tokens don't expire if obtained from long-lived user token
        # They remain valid as long as the page admin doesn't revoke access
        if self.platform == "facebook":
            # For Facebook, we use the page access token which doesn't expire
            if self.page_access_token:
                return self.page_access_token
            # Fall back to user access token if no page token
            return self.access_token

        if not self.refresh_token:
            self.status = "expired"
            self.save()
            raise ValueError("No refresh token available")

        # Import here to avoid circular imports
        from .services import linkedin_service, twitter_service

        try:
            if self.platform == "linkedin":
                token_data = linkedin_service.refresh_access_token(self.refresh_token)
                self.access_token = token_data.get("access_token")
                self.token_expires_at = token_data.get("expires_at")
                if token_data.get("refresh_token"):
                    self.refresh_token = token_data.get("refresh_token")
                self.save()
                return self.access_token
            elif self.platform == "twitter":
                token_data = twitter_service.refresh_access_token(self.refresh_token)
                self.access_token = token_data.get("access_token")
                self.token_expires_at = token_data.get("expires_at")
                if token_data.get("refresh_token"):
                    self.refresh_token = token_data.get("refresh_token")
                self.save()
                return self.access_token
            else:
                raise ValueError(f"Token refresh not implemented for {self.platform}")
        except Exception as e:
            self.status = "error"
            self.save()
            raise ValueError(f"Failed to refresh token: {str(e)}")

    def get_valid_access_token(self):
        """
        Get a valid access token, refreshing if necessary.
        This is the main method to use before making API calls.
        """
        return self.refresh_token_if_needed()

    def get_page_token(self):
        """
        Get the Facebook page access token.
        This is used for posting to Facebook pages.
        """
        if self.platform != "facebook":
            raise ValueError("Page token is only available for Facebook")
        if not self.page_access_token:
            raise ValueError("No page access token available")
        return self.page_access_token

    def disconnect(self):
        """Disconnect the social profile."""
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.status = "disconnected"
        self.save()


class AutomationTask(models.Model):
    """
    Tracks automated tasks like posting, profile creation, etc.
    """

    TASK_TYPE_CHOICES = [
        ("social_post", "Social Media Post"),
        ("profile_sync", "Profile Sync"),
        ("content_schedule", "Content Scheduling"),
        ("analytics_fetch", "Analytics Fetch"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="automation_tasks"
    )
    social_profile = models.ForeignKey(
        SocialProfile,
        on_delete=models.CASCADE,
        related_name="tasks",
        blank=True,
        null=True,
    )

    task_type = models.CharField(max_length=30, choices=TASK_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Task data and results
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, null=True)

    # Scheduling
    scheduled_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.status}"


class ContentCalendar(models.Model):
    """
    Scheduled content for social media posting.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("published", "Published"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="scheduled_content"
    )

    title = models.CharField(max_length=255)
    content = models.TextField()
    media_urls = models.JSONField(default=list, blank=True)  # Array of media URLs

    # Target platforms and profiles
    platforms = models.JSONField(default=list)  # ['linkedin', 'twitter']
    social_profiles = models.ManyToManyField(
        SocialProfile, related_name="scheduled_posts", blank=True
    )

    # Scheduling
    scheduled_date = models.DateTimeField()
    published_at = models.DateTimeField(blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    # Results from posting
    post_results = models.JSONField(default=dict, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_date"]
        verbose_name_plural = "Content Calendar"

    def __str__(self):
        return f"{self.title} - {self.scheduled_date}"


class OAuthState(models.Model):
    """
    Temporary storage for OAuth state tokens.
    Used to validate OAuth callbacks since JWT-based apps don't use sessions.
    """

    state = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="oauth_states"
    )
    platform = models.CharField(max_length=20)  # 'linkedin', 'twitter', etc.
    code_verifier = models.CharField(
        max_length=256, blank=True, null=True
    )  # PKCE code verifier for Twitter
    used = models.BooleanField(default=False)  # Mark as used after callback
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "OAuth State"
        verbose_name_plural = "OAuth States"

    def is_expired(self):
        """State tokens expire after 10 minutes."""
        from datetime import timedelta

        return timezone.now() > self.created_at + timedelta(minutes=10)

    def __str__(self):
        return f"{self.platform} OAuth for {self.user.email}"


class TwitterWebhookEvent(models.Model):
    """
    Stores incoming webhook events from Twitter Account Activity API.

    Events include likes, retweets, mentions, follows, and DMs.
    """

    EVENT_TYPE_CHOICES = [
        ("tweet_create", "Tweet Created"),
        ("favorite", "Like/Favorite"),
        ("follow", "New Follower"),
        ("unfollow", "Unfollowed"),
        ("direct_message", "Direct Message"),
        ("tweet_delete", "Tweet Deleted"),
        ("mention", "Mentioned"),
        ("retweet", "Retweeted"),
        ("quote", "Quote Tweet"),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    for_user_id = models.CharField(
        max_length=50, db_index=True, help_text="Twitter user ID this event is for"
    )
    payload = models.JSONField(
        default=dict, help_text="Full event payload from Twitter"
    )
    read = models.BooleanField(
        default=False, help_text="Whether user has seen this event"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Twitter Webhook Event"
        verbose_name_plural = "Twitter Webhook Events"
        indexes = [
            models.Index(fields=["for_user_id", "-created_at"]),
            models.Index(fields=["for_user_id", "read"]),
        ]

    def __str__(self):
        return f"{self.event_type} for {self.for_user_id} at {self.created_at}"


class LinkedInWebhookEvent(models.Model):
    """
    Stores incoming webhook events from LinkedIn.

    LinkedIn webhooks can notify about:
    - Share reactions (likes)
    - Share comments
    - Profile mentions
    - Connection updates
    - Organization updates (for company pages)

    Docs: https://learn.microsoft.com/en-us/linkedin/
        marketing/integrations/community-management/webhooks
    """

    EVENT_TYPE_CHOICES = [
        ("share_reaction", "Share Reaction (Like)"),
        ("share_comment", "Comment on Share"),
        ("mention", "Mentioned"),
        ("connection_update", "Connection Update"),
        ("organization_update", "Organization Update"),
        ("share_update", "Share/Post Update"),
        ("message", "Message Received"),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    for_user_id = models.CharField(
        max_length=100, db_index=True, help_text="LinkedIn member URN this event is for"
    )
    resource_urn = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="URN of the resource (share, comment, etc.)",
    )
    payload = models.JSONField(
        default=dict, help_text="Full event payload from LinkedIn"
    )
    read = models.BooleanField(
        default=False, help_text="Whether user has seen this event"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "LinkedIn Webhook Event"
        verbose_name_plural = "LinkedIn Webhook Events"
        indexes = [
            models.Index(fields=["for_user_id", "-created_at"]),
            models.Index(fields=["for_user_id", "read"]),
        ]

    def __str__(self):
        return f"{self.event_type} for {self.for_user_id} at {self.created_at}"


class FacebookWebhookEvent(models.Model):
    """
    Stores incoming webhook events from Facebook.

    Facebook sends webhooks for Page events including:
    - Feed posts (new posts, comments, reactions)
    - Page mentions
    - Messaging (if enabled)
    - Ratings and reviews
    - Video status updates

    Docs: https://developers.facebook.com/docs/graph-api/webhooks/
    """

    EVENT_TYPE_CHOICES = [
        ("feed", "Feed Update (Post/Comment/Reaction)"),
        ("mention", "Page Mentioned"),
        ("message", "Message Received"),
        ("messaging_postback", "Messaging Postback"),
        ("rating", "Page Rating"),
        ("video", "Video Status Change"),
        ("leadgen", "Lead Generation"),
        ("conversations", "Conversation Update"),
        ("feed_comment", "Comment on Feed"),
        ("feed_reaction", "Reaction on Feed"),
        ("feed_share", "Post Shared"),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    page_id = models.CharField(
        max_length=100, db_index=True, help_text="Facebook Page ID this event is for"
    )
    sender_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID of the user who triggered the event",
    )
    post_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="ID of the post related to this event",
    )
    payload = models.JSONField(
        default=dict, help_text="Full event payload from Facebook"
    )
    read = models.BooleanField(
        default=False, help_text="Whether user has seen this event"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Facebook Webhook Event"
        verbose_name_plural = "Facebook Webhook Events"
        indexes = [
            models.Index(fields=["page_id", "-created_at"]),
            models.Index(fields=["page_id", "read"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} for page {self.page_id} at {self.created_at}"


class FacebookResumableUpload(models.Model):
    """
    Tracks resumable video upload sessions for Facebook.

    For videos > 1GB, Facebook requires chunked uploads. This model stores
    the state of in-progress uploads so they can be resumed if interrupted.

    Docs: https://developers.facebook.com/docs/graph-api/guides/upload
    """

    STATUS_CHOICES = [
        ("pending", "Pending - Not Started"),
        ("uploading", "Uploading - In Progress"),
        ("processing", "Processing - Upload Complete"),
        ("completed", "Completed - Ready"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="facebook_uploads"
    )
    page_id = models.CharField(max_length=100, help_text="Facebook Page ID")

    # Facebook upload session details
    upload_session_id = models.CharField(
        max_length=200, unique=True, help_text="Facebook upload session ID"
    )
    video_id = models.CharField(
        max_length=100, blank=True, null=True, help_text="Video ID once upload starts"
    )

    # File details
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField(help_text="Total file size in bytes")
    content_type = models.CharField(max_length=100, default="video/mp4")

    # Upload progress
    bytes_uploaded = models.BigIntegerField(
        default=0, help_text="Bytes uploaded so far"
    )
    start_offset = models.BigIntegerField(
        default=0, help_text="Next byte offset to upload from"
    )
    end_offset = models.BigIntegerField(
        default=0, help_text="End offset of last successful chunk"
    )

    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Facebook Resumable Upload"
        verbose_name_plural = "Facebook Resumable Uploads"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["page_id", "-created_at"]),
        ]

    def __str__(self):
        status_display = self.get_status_display()
        progress = f"{self.progress_percent:.1f}%"
        return f"{self.file_name} ({status_display}) - {progress}"

    @property
    def progress_percent(self) -> float:
        """Calculate upload progress as percentage."""
        if self.file_size == 0:
            return 0.0
        return (self.bytes_uploaded / self.file_size) * 100

    @property
    def is_complete(self) -> bool:
        """Check if upload is complete."""
        return self.status == "completed"

    @property
    def is_in_progress(self) -> bool:
        """Check if upload is in progress."""
        return self.status in ("pending", "uploading", "processing")

    def mark_completed(self):
        """Mark upload as completed."""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.bytes_uploaded = self.file_size
        self.save()

    def mark_failed(self, error_message: str = None):
        """Mark upload as failed."""
        self.status = "failed"
        self.error_message = error_message
        self.save()

    def update_progress(self, start_offset: int, end_offset: int):
        """Update upload progress after a successful chunk."""
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.bytes_uploaded = end_offset
        self.status = "uploading"
        self.save()


class InstagramWebhookEvent(models.Model):
    """
    Stores incoming webhook events from Instagram.

    Instagram sends webhooks for:
    - Comments on posts
    - Mentions in comments or captions
    - Story mentions
    - Story replies
    - Message reactions

    Docs: https://developers.facebook.com/docs/instagram-api/webhooks
    """

    EVENT_TYPE_CHOICES = [
        ("comments", "Comment on Post"),
        ("mentions", "Mentioned"),
        ("story_mentions", "Story Mention"),
        ("story_replies", "Story Reply"),
        ("message_reactions", "Message Reaction"),
        ("messages", "Direct Message"),
        ("live_comments", "Live Video Comment"),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    instagram_user_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Instagram Business Account ID this event is for",
    )
    sender_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID of the user who triggered the event",
    )
    media_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="ID of the media (post/story) related to this event",
    )
    payload = models.JSONField(
        default=dict, help_text="Full event payload from Instagram"
    )
    read = models.BooleanField(
        default=False, help_text="Whether user has seen this event"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Instagram Webhook Event"
        verbose_name_plural = "Instagram Webhook Events"
        indexes = [
            models.Index(fields=["instagram_user_id", "-created_at"]),
            models.Index(fields=["instagram_user_id", "read"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.event_type} for IG user {self.instagram_user_id} "
            f"at {self.created_at}"
        )


class InstagramResumableUpload(models.Model):
    """
    Tracks resumable media upload sessions for Instagram.

    For large videos (Reels), Instagram uses a similar chunked upload flow.
    This model stores the state of in-progress uploads.

    Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
    """

    STATUS_CHOICES = [
        ("pending", "Pending - Not Started"),
        ("uploading", "Uploading - In Progress"),
        ("processing", "Processing - Upload Complete"),
        ("completed", "Completed - Ready"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    MEDIA_TYPE_CHOICES = [
        ("IMAGE", "Image Post"),
        ("VIDEO", "Video Post"),
        ("CAROUSEL", "Carousel Post"),
        ("REELS", "Reels Video"),
        ("STORIES", "Story"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="instagram_uploads"
    )
    instagram_user_id = models.CharField(
        max_length=100, help_text="Instagram Business Account ID"
    )

    # Instagram container/media IDs
    container_id = models.CharField(
        max_length=200, blank=True, null=True, help_text="Instagram media container ID"
    )
    media_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Published media ID once upload completes",
    )

    # File details
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField(help_text="Total file size in bytes")
    content_type = models.CharField(max_length=100, default="video/mp4")
    media_type = models.CharField(
        max_length=20, choices=MEDIA_TYPE_CHOICES, default="VIDEO"
    )

    # Upload progress
    bytes_uploaded = models.BigIntegerField(
        default=0, help_text="Bytes uploaded so far"
    )

    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    caption = models.TextField(blank=True, null=True, help_text="Post caption")
    error_message = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Instagram Resumable Upload"
        verbose_name_plural = "Instagram Resumable Uploads"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["instagram_user_id", "-created_at"]),
        ]

    def __str__(self):
        status_display = self.get_status_display()
        progress = f"{self.progress_percent:.1f}%"
        return f"{self.file_name} ({status_display}) - {progress}"

    @property
    def progress_percent(self) -> float:
        """Calculate upload progress as percentage."""
        if self.file_size == 0:
            return 0.0
        return (self.bytes_uploaded / self.file_size) * 100

    @property
    def is_complete(self) -> bool:
        """Check if upload is complete."""
        return self.status == "completed"

    @property
    def is_in_progress(self) -> bool:
        """Check if upload is in progress."""
        return self.status in ("pending", "uploading", "processing")

    def mark_completed(self, media_id: str = None):
        """Mark upload as completed."""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.bytes_uploaded = self.file_size
        if media_id:
            self.media_id = media_id
        self.save()

    def mark_failed(self, error_message: str = None):
        """Mark upload as failed."""
        self.status = "failed"
        self.error_message = error_message
        self.save()

    def update_progress(self, bytes_uploaded: int):
        """Update upload progress after a successful chunk."""
        self.bytes_uploaded = bytes_uploaded
        self.status = "uploading"
        self.save()


class GoogleBusinessProfile(models.Model):
    """
    Stores Google Business Profile connection and OAuth tokens.

    Supports dual-mode operation:
    - Mock Mode: Works without API credentials (for development/testing)
    - Real Mode: Uses actual GBP APIs (requires approved credentials)

    Uses Google Business Profile APIs:
    - Account Management API (accounts)
    - Business Information API (locations)
    """

    STATUS_CHOICES = [
        ("connected", "Connected"),
        ("disconnected", "Disconnected"),
        ("expired", "Token Expired"),
        ("error", "Error"),
        ("pending_verification", "Pending Verification"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="google_business_profiles"
    )

    # OAuth tokens (encrypted at rest)
    _access_token = models.TextField(blank=True, null=True, db_column="access_token")
    _refresh_token = models.TextField(blank=True, null=True, db_column="refresh_token")
    token_expires_at = models.DateTimeField(blank=True, null=True)

    # Google Account Info
    google_account_id = models.CharField(max_length=255, blank=True, null=True)
    google_account_name = models.CharField(max_length=255, blank=True, null=True)
    google_email = models.EmailField(blank=True, null=True)

    # Selected GBP Account (from Account Management API)
    gbp_account_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="accounts/{account_id} resource name",
    )
    gbp_account_name = models.CharField(max_length=255, blank=True, null=True)

    # Connection status
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default="disconnected"
    )

    # Mock mode indicator
    is_mock = models.BooleanField(
        default=False, help_text="True if connected via mock/test mode"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "Google Business Profile"
        verbose_name_plural = "Google Business Profiles"
        # One GBP connection per user
        constraints = [
            models.UniqueConstraint(fields=["user"], name="unique_user_gbp_connection")
        ]

    def __str__(self):
        email = self.google_email or "no email"
        return f"{self.user.email} - GBP ({email}, {self.status})"

    # Encrypted token properties (same pattern as SocialProfile)
    @property
    def access_token(self):
        """Get the decrypted access token."""
        return decrypt_token(self._access_token) if self._access_token else None

    @access_token.setter
    def access_token(self, value):
        """Set and encrypt the access token."""
        self._access_token = encrypt_token(value) if value else None

    @property
    def refresh_token(self):
        """Get the decrypted refresh token."""
        return decrypt_token(self._refresh_token) if self._refresh_token else None

    @refresh_token.setter
    def refresh_token(self, value):
        """Set and encrypt the refresh token."""
        self._refresh_token = encrypt_token(value) if value else None

    @property
    def is_token_valid(self):
        """Check if the access token is still valid."""
        if not self.token_expires_at:
            return False
        return timezone.now() < self.token_expires_at

    @property
    def is_token_expiring_soon(self):
        """Check if the token will expire within 5 minutes."""
        if not self.token_expires_at:
            return True
        from datetime import timedelta

        return timezone.now() + timedelta(minutes=5) >= self.token_expires_at

    def disconnect(self):
        """Disconnect the Google Business Profile."""
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.gbp_account_id = None
        self.gbp_account_name = None
        self.status = "disconnected"
        self.is_mock = False
        self.save()


class GoogleBusinessLocation(models.Model):
    """
    Stores individual business locations from Google Business Profile.

    A user can have multiple locations under one GBP account.
    """

    VERIFICATION_STATUS_CHOICES = [
        ("unverified", "Unverified"),
        ("pending", "Verification Pending"),
        ("verified", "Verified"),
        ("failed", "Verification Failed"),
    ]

    profile = models.ForeignKey(
        GoogleBusinessProfile, on_delete=models.CASCADE, related_name="locations"
    )

    # Location identifier from GBP API
    location_id = models.CharField(
        max_length=255, help_text="locations/{location_id} resource name"
    )

    # Business Information
    business_name = models.CharField(max_length=255)
    primary_category = models.CharField(max_length=255, blank=True)
    primary_category_id = models.CharField(
        max_length=255, blank=True, help_text="categories/gcid:xxx format"
    )
    additional_categories = models.JSONField(default=list, blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="US")  # ISO 3166-1 alpha-2

    # Contact
    phone_number = models.CharField(max_length=20, blank=True)
    website_url = models.URLField(blank=True)

    # Business hours (stored as JSON)
    business_hours = models.JSONField(
        default=dict, blank=True, help_text="Regular business hours by day"
    )
    special_hours = models.JSONField(
        default=list, blank=True, help_text="Special hours for holidays, etc."
    )

    # Verification
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUS_CHOICES, default="unverified"
    )

    # Sync status
    is_synced = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Business Location"
        verbose_name_plural = "Google Business Locations"
        unique_together = ["profile", "location_id"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.city}, {self.state})"

    @property
    def full_address(self):
        """Return formatted full address."""
        parts = [self.address_line1]
        if self.address_line2:
            parts.append(self.address_line2)
        parts.append(f"{self.city}, {self.state} {self.postal_code}")
        parts.append(self.country)
        return ", ".join(filter(None, parts))
