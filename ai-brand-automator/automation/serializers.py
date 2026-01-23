"""
Serializers for the automation app.
"""

from rest_framework import serializers
from .models import (
    SocialProfile,
    AutomationTask,
    ContentCalendar,
    GoogleBusinessProfile,
    GoogleBusinessLocation,
)


class SocialProfileSerializer(serializers.ModelSerializer):
    """Serializer for social profiles."""

    platform_display = serializers.CharField(
        source="get_platform_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_token_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = SocialProfile
        fields = [
            "id",
            "platform",
            "platform_display",
            "profile_id",
            "profile_name",
            "profile_url",
            "profile_image_url",
            "status",
            "status_display",
            "is_token_valid",
            "created_at",
            "updated_at",
            "last_synced_at",
        ]
        read_only_fields = [
            "id",
            "profile_id",
            "profile_name",
            "profile_url",
            "profile_image_url",
            "status",
            "created_at",
            "updated_at",
            "last_synced_at",
        ]


class AutomationTaskSerializer(serializers.ModelSerializer):
    """Serializer for automation tasks."""

    task_type_display = serializers.CharField(
        source="get_task_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AutomationTask
        fields = [
            "id",
            "social_profile",
            "task_type",
            "task_type_display",
            "status",
            "status_display",
            "payload",
            "result",
            "error_message",
            "scheduled_at",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "result",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class ContentCalendarSerializer(serializers.ModelSerializer):
    """Serializer for content calendar."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ContentCalendar
        fields = [
            "id",
            "title",
            "content",
            "media_urls",
            "platforms",
            "social_profiles",
            "scheduled_date",
            "published_at",
            "status",
            "status_display",
            "post_results",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "published_at",
            "post_results",
            "created_at",
            "updated_at",
        ]


class GoogleBusinessProfileSerializer(serializers.ModelSerializer):
    """Serializer for GoogleBusinessProfile model."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_token_valid = serializers.BooleanField(read_only=True)
    location_count = serializers.SerializerMethodField()

    class Meta:
        model = GoogleBusinessProfile
        fields = [
            "id",
            "google_email",
            "google_account_name",
            "gbp_account_id",
            "gbp_account_name",
            "status",
            "status_display",
            "is_mock",
            "is_token_valid",
            "location_count",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "google_email",
            "google_account_name",
            "gbp_account_id",
            "gbp_account_name",
            "status",
            "is_mock",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]

    def get_location_count(self, obj):
        """Return the number of locations for this profile."""
        return obj.locations.count()


class GoogleBusinessLocationSerializer(serializers.ModelSerializer):
    """Serializer for GoogleBusinessLocation model."""

    verification_status_display = serializers.CharField(
        source="get_verification_status_display", read_only=True
    )
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = GoogleBusinessLocation
        fields = [
            "id",
            "location_id",
            "business_name",
            "primary_category",
            "primary_category_id",
            "additional_categories",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "full_address",
            "phone_number",
            "website_url",
            "business_hours",
            "special_hours",
            "verification_status",
            "verification_status_display",
            "is_synced",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "location_id",
            "verification_status",
            "is_synced",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]


class GoogleBusinessLocationCreateSerializer(serializers.Serializer):
    """Serializer for creating a new GBP location."""

    business_name = serializers.CharField(max_length=255)
    primary_category = serializers.CharField(
        max_length=255, help_text="Display name of the category"
    )
    primary_category_id = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="categories/gcid:xxx format",
    )
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    postal_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=2, default="US")
    phone_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    website_url = serializers.URLField(required=False, allow_blank=True)
    business_hours = serializers.JSONField(required=False, default=dict)


class GoogleBusinessAccountSerializer(serializers.Serializer):
    """Serializer for GBP account data from API."""

    name = serializers.CharField(help_text="Account resource name: accounts/{id}")
    account_name = serializers.CharField(
        source="accountName", help_text="Display name of the account"
    )
    account_type = serializers.CharField(
        source="type", help_text="PERSONAL, LOCATION_GROUP, etc."
    )
    role = serializers.CharField(help_text="User's role: PRIMARY_OWNER, OWNER, etc.")
    state = serializers.JSONField(required=False)


class GoogleBusinessCategorySerializer(serializers.Serializer):
    """Serializer for GBP business category."""

    name = serializers.CharField(help_text="Category ID: categories/gcid:xxx")
    display_name = serializers.CharField(
        source="displayName", help_text="Human-readable category name"
    )
