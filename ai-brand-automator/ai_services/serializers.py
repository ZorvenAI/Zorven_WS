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
        return SessionAttachmentSerializer(obj.attachments.all(), many=True).data


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
        # Prefer annotated value from queryset to avoid N+1
        annotated = getattr(obj, "_last_message_preview", None)
        if annotated:
            return annotated[:80]
        # Fallback: single query
        last_msg = (
            ChatMessage.objects.filter(session=obj)
            .order_by("-created_at")
            .values_list("content", flat=True)
            .first()
        )
        return last_msg[:80] if last_msg else ""

    def get_message_count(self, obj):
        # Prefer annotated count from queryset to avoid N+1
        annotated = getattr(obj, "_message_count", None)
        if annotated is not None:
            return annotated
        return ChatMessage.objects.filter(session=obj).count()

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["tenant"] = getattr(request, "tenant", None)
        return super().create(validated_data)


class SessionAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for SessionAttachment model."""

    thumbnail_url = serializers.SerializerMethodField()

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
            "thumbnail_url",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_thumbnail_url(self, obj):
        if obj.file_type != "image" or obj.asset_id is None:
            return None
        try:
            asset = obj.asset
            if not asset or not asset.gcs_path:
                return None
            from files.services import gcs_service

            result = gcs_service.generate_signed_url(
                asset.gcs_path,
                expiration_minutes=15,
                bucket_name=asset.gcs_bucket,
            )
            return result.get("url")
        except Exception:
            return None


class ChatInputSerializer(serializers.Serializer):
    """Serializer for chat input (message + optional session_id)."""

    message = serializers.CharField(required=True)
    session_id = serializers.CharField(required=False, allow_blank=True)
    attachment_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )


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


class SaveResponseToRAGSerializer(serializers.Serializer):
    """Serializer for saving AI chat responses to the RAG knowledge base."""

    content = serializers.CharField(
        required=True,
        max_length=500_000,
    )
    title = serializers.CharField(
        required=True,
        max_length=200,
    )
