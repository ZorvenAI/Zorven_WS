"""
Serializers for the automation app.
"""
from rest_framework import serializers
from .models import SocialProfile, AutomationTask, ContentCalendar


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
