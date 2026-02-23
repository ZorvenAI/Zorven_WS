from rest_framework import serializers
from .models import ChatSession, ChatMessage, SessionAttachment, AIGeneration


class ChatMessageModelSerializer(serializers.ModelSerializer):
    """Serializer for ChatMessage model (individual messages)."""

    attachments = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = [
            "id",
            "role",
            "content",
            "metadata",
            "thinking",
            "created_at",
            "attachments",
        ]
        read_only_fields = ["id", "created_at"]

    def get_attachments(self, obj):
        atts = obj.attachments.all()
        if not atts.exists():
            return []
        return SessionAttachmentSerializer(atts, many=True).data


class ChatSessionSerializer(serializers.ModelSerializer):
    """Serializer for ChatSession model."""

    last_message_preview = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = [
            "id",
            "tenant",
            "session_id",
            "title",
            "messages",
            "context",
            "created_at",
            "updated_at",
            "last_activity",
            "last_message_preview",
            "message_count",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "created_at",
            "updated_at",
            "last_activity",
        ]

    def get_last_message_preview(self, obj):
        last_msg = (
            ChatMessage.objects.filter(session=obj)
            .order_by("-created_at")
            .values_list("content", flat=True)
            .first()
        )
        if last_msg:
            return last_msg[:80]
        return ""

    def get_message_count(self, obj):
        return ChatMessage.objects.filter(session=obj).count()

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["tenant"] = getattr(request, "tenant", None)
        return super().create(validated_data)


class SessionAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for SessionAttachment model."""

    class Meta:
        model = SessionAttachment
        fields = [
            "id",
            "message",
            "asset",
            "file_name",
            "file_type",
            "file_size",
            "pipeline_status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ChatInputSerializer(serializers.Serializer):
    """Serializer for chat input (message + optional session_id)."""

    message = serializers.CharField(required=True)
    session_id = serializers.CharField(required=False, allow_blank=True)


class AIGenerationSerializer(serializers.ModelSerializer):
    """Serializer for AI generations."""

    class Meta:
        model = AIGeneration
        fields = [
            "id",
            "tenant",
            "content_type",
            "prompt",
            "response",
            "tokens_used",
            "model_used",
            "created_at",
            "processing_time",
        ]
        read_only_fields = ["id", "tenant", "created_at"]


class BrandStrategyRequestSerializer(serializers.Serializer):
    """Serializer for brand strategy generation requests."""

    company_id = serializers.IntegerField(required=True)


class BrandIdentityRequestSerializer(serializers.Serializer):
    """Serializer for brand identity generation requests."""

    company_id = serializers.IntegerField(required=True)


class MarketAnalysisRequestSerializer(serializers.Serializer):
    """Serializer for market analysis requests."""

    company_id = serializers.IntegerField(required=True)
