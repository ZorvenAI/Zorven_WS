"""
Serializers for the Intelligence Loop app.

Two groups:
1. Read serializers (JWT-authenticated UI endpoints): list/detail of
   CampaignIntelligence, LearningRecord and WF2RerunRequest.
2. Ingest serializers (X-Service-Token endpoints called by the
   intelligence-loop-agent-svc microservice): payloads written by ILA
   when it persists an extraction run.
"""

from rest_framework import serializers

from .models import (
    CampaignIntelligence,
    LearningDocument,
    LearningRecord,
    WF2RerunRequest,
)


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------


class LearningRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningRecord
        fields = [
            "id",
            "learning_id",
            "category",
            "headline",
            "detail",
            "confidence",
            "impact",
            "target_workflow",
            "target_agent",
            "status",
            "rag_document_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CampaignIntelligenceListSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(
        source="campaign.campaign_name", read_only=True
    )
    learnings_count = serializers.SerializerMethodField()
    high_confidence_count = serializers.SerializerMethodField()

    class Meta:
        model = CampaignIntelligence
        fields = [
            "id",
            "intelligence_id",
            "campaign",
            "campaign_name",
            "mode",
            "trigger_source",
            "auto_reruns_triggered",
            "rag_writes",
            "learnings_count",
            "high_confidence_count",
            "brand_context_id",
            "created_at",
        ]

    def get_learnings_count(self, obj):
        return obj.learnings.count()

    def get_high_confidence_count(self, obj):
        return obj.learnings.filter(confidence__gte=85).count()


class CampaignIntelligenceDetailSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(
        source="campaign.campaign_name", read_only=True
    )
    learnings = LearningRecordSerializer(many=True, read_only=True)

    class Meta:
        model = CampaignIntelligence
        fields = [
            "id",
            "intelligence_id",
            "campaign",
            "campaign_name",
            "job_id",
            "mode",
            "trigger_source",
            "intelligence_report",
            "auto_reruns_triggered",
            "contradictions",
            "rag_writes",
            "brand_context_id",
            "learnings",
            "created_at",
            "updated_at",
        ]


class WF2RerunRequestSerializer(serializers.ModelSerializer):
    learning_headline = serializers.CharField(
        source="learning.headline", read_only=True
    )
    decided_by_email = serializers.SerializerMethodField()
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = WF2RerunRequest
        fields = [
            "id",
            "request_id",
            "learning",
            "learning_headline",
            "requested_agent",
            "rationale",
            "status",
            "requested_by",
            "decided_by",
            "decided_by_email",
            "decided_at",
            "rejection_reason",
            "expires_at",
            "is_expired",
            "job_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_decided_by_email(self, obj):
        return getattr(obj.decided_by, "email", "") or ""


# ---------------------------------------------------------------------------
# Action serializers (UI → Django)
# ---------------------------------------------------------------------------


class ApplyLearningSerializer(serializers.Serializer):
    """POST /learnings/<id>/apply/ — manually dispatch a re-run."""

    note = serializers.CharField(required=False, allow_blank=True, default="")


class RejectWF2RequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class TriggerExtractionSerializer(serializers.Serializer):
    """POST /trigger/ — manual on-demand ILA run."""

    campaign_id = serializers.UUIDField()
    mode = serializers.ChoiceField(
        choices=["store_only", "auto_trigger"],
        default="store_only",
    )


# ---------------------------------------------------------------------------
# Ingest serializers (ILA service → Django, X-Service-Token)
# ---------------------------------------------------------------------------


class _IngestLearningSerializer(serializers.Serializer):
    learning_id = serializers.UUIDField(required=False)
    category = serializers.ChoiceField(
        choices=[c[0] for c in LearningRecord.CATEGORY_CHOICES]
    )
    headline = serializers.CharField(max_length=500)
    detail = serializers.DictField(required=False, default=dict)
    confidence = serializers.IntegerField(min_value=0, max_value=100)
    impact = serializers.ChoiceField(
        choices=[c[0] for c in LearningRecord.IMPACT_CHOICES]
    )
    target_workflow = serializers.ChoiceField(
        choices=[c[0] for c in LearningRecord.WORKFLOW_CHOICES]
    )
    target_agent = serializers.CharField(max_length=16)


class IngestIntelligenceReportSerializer(serializers.Serializer):
    """Payload from ILA microservice creating a CampaignIntelligence row."""

    tenant_id = serializers.CharField(allow_blank=True, required=False)
    campaign_id = serializers.UUIDField(
        help_text="optimization.CampaignRegistry.campaign_id"
    )
    job_id = serializers.CharField(max_length=64)
    mode = serializers.ChoiceField(
        choices=[c[0] for c in CampaignIntelligence.MODE_CHOICES]
    )
    trigger_source = serializers.ChoiceField(
        choices=[c[0] for c in CampaignIntelligence.TRIGGER_SOURCE_CHOICES]
    )
    intelligence_report = serializers.DictField(required=False, default=dict)
    auto_reruns_triggered = serializers.IntegerField(min_value=0, default=0)
    contradictions = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    rag_writes = serializers.IntegerField(min_value=0, default=0)
    brand_context_id = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    learnings = serializers.ListField(
        child=_IngestLearningSerializer(),
        required=False,
        default=list,
    )


class IngestRagLearningSerializer(serializers.Serializer):
    """Payload from ILA creating a LearningDocument row (one per learning)."""

    tenant_id = serializers.CharField(allow_blank=True, required=False)
    learning_id = serializers.UUIDField()
    content = serializers.CharField()
    metadata = serializers.DictField(required=False, default=dict)


class AutoTriggerSerializer(serializers.Serializer):
    """Service-token payload from ILA requesting an auto-trigger re-run."""

    learning_id = serializers.UUIDField()
    note = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )


class IngestWF2RequestSerializer(serializers.Serializer):
    """Payload from ILA creating a pending WF2 approval row."""

    tenant_id = serializers.CharField(allow_blank=True, required=False)
    learning_id = serializers.UUIDField()
    requested_agent = serializers.CharField(max_length=16)
    rationale = serializers.CharField()
    expires_in_hours = serializers.IntegerField(default=72, min_value=1)


# Used by views to serialize a created LearningDocument back to ILA
class LearningDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningDocument
        fields = [
            "id",
            "learning",
            "content",
            "metadata",
            "vector_doc_id",
            "created_at",
        ]
        read_only_fields = fields
