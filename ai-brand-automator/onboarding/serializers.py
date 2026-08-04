from rest_framework import serializers
from .models import Company, BrandAsset, OnboardingProgress


class CompanySerializer(serializers.ModelSerializer):
    """Serializer for Company model"""

    class Meta:
        model = Company
        fields = [
            "id",
            "tenant",
            "name",
            "description",
            "industry",
            "target_audience",
            "demographics",
            "psychographics",
            "pain_points",
            "desired_outcomes",
            "core_problem",
            "website",
            "address",
            "city",
            "state_province",
            "postal_code",
            "country",
            "brand_voice",
            "vision_statement",
            "mission_statement",
            "values",
            "positioning_statement",
            "tagline",
            "value_proposition",
            "elevator_pitch",
            "color_palette_desc",
            "font_recommendations",
            "messaging_guide",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_at", "updated_at"]


class BrandAssetSerializer(serializers.ModelSerializer):
    """Serializer for BrandAsset model"""

    class Meta:
        model = BrandAsset
        fields = [
            "id",
            "tenant",
            "company",
            "file_name",
            "file_type",
            "file_size",
            "gcs_path",
            "gcs_bucket",
            "uploaded_at",
            "processed",
            "pipeline_status",
            "pipeline_error",
            "pipeline_trace_id",
            "summary",
            # B-02 (Design §10.1). Every one is optional, so a client that
            # has never heard of them keeps working unchanged (AC-4).
            "usage_tag",
            "onboarding_session",
            "ocr_text",
            "ocr_confidence",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "uploaded_at",
            "processed",
            "pipeline_status",
            "pipeline_error",
            "pipeline_trace_id",
            "summary",
            # Written by H-03's OCR pass, never by a client: accepting them
            # would let a caller write unredacted text into a column whose
            # whole contract is that it holds redacted text only (PG-08).
            "ocr_text",
            "ocr_confidence",
        ]


class OnboardingProgressSerializer(serializers.ModelSerializer):
    """Serializer for OnboardingProgress model"""

    completion_percentage = serializers.ReadOnlyField()

    class Meta:
        model = OnboardingProgress
        fields = [
            "id",
            "tenant",
            "company",
            "current_step",
            "completed_steps",
            "is_completed",
            "started_at",
            "completed_at",
            "last_updated",
            "completion_percentage",
        ]
        read_only_fields = ["id", "tenant", "started_at", "last_updated"]


class CompanyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new company during onboarding"""

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "description",
            "industry",
            "target_audience",
            "core_problem",
            "website",
            "address",
            "city",
            "state_province",
            "postal_code",
            "country",
            "brand_voice",
        ]
        read_only_fields = ["id"]
        # Tenant is set in the viewset's perform_create method


class CompanyUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating company after onboarding (brand strategy)"""

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "description",
            "industry",
            "target_audience",
            "demographics",
            "psychographics",
            "pain_points",
            "desired_outcomes",
            "core_problem",
            "website",
            "address",
            "city",
            "state_province",
            "postal_code",
            "country",
            "brand_voice",
            "vision_statement",
            "mission_statement",
            "values",
            "positioning_statement",
            "tagline",
            "value_proposition",
            "elevator_pitch",
            "color_palette_desc",
            "font_recommendations",
            "messaging_guide",
        ]
        read_only_fields = ["id"]


class BrandAssetUploadSerializer(serializers.Serializer):
    """Serializer for file upload"""

    file = serializers.FileField()
    file_type = serializers.ChoiceField(
        choices=[
            ("image", "Image"),
            ("video", "Video"),
            ("document", "Document"),
            ("other", "Other"),
        ]
    )

    def validate_file(self, value):
        # Basic file validation
        max_size = 50 * 1024 * 1024  # 50MB
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 50MB")

        # Centralized allowed types from brand_automator.validators
        from brand_automator.validators import (
            ALLOWED_DOCUMENT_TYPES,
            ALLOWED_IMAGE_TYPES,
            ALLOWED_VIDEO_TYPES,
        )

        allowed_types = {
            "image": ALLOWED_IMAGE_TYPES,
            "video": ALLOWED_VIDEO_TYPES,
            "document": ALLOWED_DOCUMENT_TYPES,
        }

        file_type = self.initial_data.get("file_type")
        content_type = value.content_type

        # Fall back to extension-based MIME guess when the browser sends a
        # generic content type (e.g. application/octet-stream for .docx)
        if content_type in (
            "application/octet-stream",
            "application/x-unknown",
            "",
            None,
        ):
            import mimetypes

            guessed, _ = mimetypes.guess_type(value.name)
            if guessed:
                content_type = guessed

        if file_type in allowed_types and content_type not in allowed_types[file_type]:
            raise serializers.ValidationError(f"Invalid file type for {file_type}")

        return value
