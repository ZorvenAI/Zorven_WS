from rest_framework import serializers
from .models import ChatSession, AIGeneration


class ChatSessionSerializer(serializers.ModelSerializer):
    """Serializer for ChatSession model"""

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
        ]
        read_only_fields = [
            "id",
            "tenant",
            "created_at",
            "updated_at",
            "last_activity",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["tenant"] = getattr(request, "tenant", None)
        return super().create(validated_data)


class ChatMessageSerializer(serializers.Serializer):
    """Serializer for chat messages"""

    message = serializers.CharField(required=True)
    session_id = serializers.CharField(required=False, allow_blank=True)


class AIGenerationSerializer(serializers.ModelSerializer):
    """Serializer for AI generations"""

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
    """Serializer for brand strategy generation requests"""

    company_id = serializers.IntegerField(required=True)


class BrandIdentityRequestSerializer(serializers.Serializer):
    """Serializer for brand identity generation requests"""

    company_id = serializers.IntegerField(required=True)


class MarketAnalysisRequestSerializer(serializers.Serializer):
    """Serializer for market analysis requests"""

    company_id = serializers.IntegerField(required=True)
