from decimal import Decimal

from rest_framework import serializers
from .models import Company, BrandAsset, OnboardingProgress


# ── B-03 · declared shapes for the JSON-typed Company fields ─────────
#
# Design §10.1's technical note is explicit: these columns are schemaless,
# but J-02's extraction output has to match something, and "whatever the LLM
# emitted" is not a contract. Each shape below is enforced on write only —
# existing rows are never revalidated, so a pre-existing malformed value can
# still be read back.

#: The Company fields carrying the thirteen approved onboarding values.
ONBOARDING_FIELDS = [
    "competitors",
    "products_services",
    "marketing_budget_range",
    "digital_presence",
    "business_goals",
    "founder_story",
    "brand_asset_status",
    "legal_name",
    "trademark_status",
    "customer_proof",
    "sales_channels",
    "audience_languages",
    "decision_maker",
]


#: ISO 4217 active currency codes. A regex for three uppercase letters
#: accepts "AAA", which is not a currency — and extraction storing a garbage
#: code is a data-quality bug nothing downstream can recover from. Held as
#: data rather than pulled from a library because neither pycountry nor babel
#: is a runtime dependency, and the list changes rarely.
ISO_4217_CODES = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
    BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF
    DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD
    HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW
    KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR
    MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN
    PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN
    SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED
    VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG
    """.split()
)


class CompetitorSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    url = serializers.URLField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ProductServiceSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    price_range = serializers.CharField(required=False, allow_blank=True)


class MarketingBudgetSerializer(serializers.Serializer):
    """A numeric range plus a currency, not a band enum.

    A band ("$1k-$5k") cannot be multi-currency without either a per-currency
    band table or an FX rate baked into the schema. A number and an ISO 4217
    code carry the same information with neither, and compare without string
    parsing — which is what the technical note actually objected to.

    Cross-currency comparison needs an FX rate and is the caller's job; this
    records what the brand owner said.
    """

    PERIODS = ["monthly", "quarterly", "annual"]

    currency = serializers.CharField(
        help_text="ISO 4217, e.g. INR, USD, EUR",
    )
    min = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0")
    )
    max = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        help_text="Omit for an open-ended top band",
    )
    period = serializers.ChoiceField(choices=PERIODS, default="monthly")

    def validate_currency(self, value):
        """Checked against the real code list, not just the shape.

        A three-uppercase-letter regex accepts "AAA"; storing that is a
        data-quality bug no downstream consumer can recover from.
        """
        if value not in ISO_4217_CODES:
            raise serializers.ValidationError(
                f"{value!r} is not an active ISO 4217 currency code."
            )
        return value

    def validate(self, attrs):
        low, high = attrs.get("min"), attrs.get("max")
        if high is not None and low is not None and high < low:
            raise serializers.ValidationError(
                {"max": "max must be greater than or equal to min."}
            )
        return attrs


class DigitalPresenceSerializer(serializers.Serializer):
    """Handles or URLs for the platforms we know about.

    Unknown platforms are allowed through deliberately: refusing an unlisted
    network would lose data the operator actually captured, and this is a
    record rather than an integration.

    That works because DRF *ignores* undeclared keys rather than rejecting
    them, and because ``_validate_object`` below returns the caller's original
    dict rather than ``validated_data`` — so an unlisted platform is validated
    against nothing and stored intact. Both halves are load-bearing: returning
    ``validated_data`` would silently drop it. ``test_an_unlisted_platform_is
    _kept`` holds that in place.
    """

    website = serializers.CharField(required=False, allow_blank=True)
    instagram = serializers.CharField(required=False, allow_blank=True)
    facebook = serializers.CharField(required=False, allow_blank=True)
    linkedin = serializers.CharField(required=False, allow_blank=True)
    x = serializers.CharField(required=False, allow_blank=True)
    youtube = serializers.CharField(required=False, allow_blank=True)
    tiktok = serializers.CharField(required=False, allow_blank=True)
    google_business = serializers.CharField(required=False, allow_blank=True)


class CustomerProofSerializer(serializers.Serializer):
    TYPES = ["testimonial", "review", "case_study", "award"]

    type = serializers.ChoiceField(choices=TYPES)
    text = serializers.CharField()
    source = serializers.CharField(required=False, allow_blank=True)
    date = serializers.CharField(required=False, allow_blank=True)


class SalesChannelSerializer(serializers.Serializer):
    CHANNELS = [
        "online_store",
        "marketplace",
        "retail",
        "wholesale",
        "direct",
        "social",
    ]

    channel = serializers.ChoiceField(choices=CHANNELS)
    notes = serializers.CharField(required=False, allow_blank=True)


class OnboardingFieldShapesMixin:
    """Validates the JSON-typed onboarding fields against their shapes.

    A mixin because all three Company serializers need identical rules:
    CompanyViewSet routes create to CompanyCreateSerializer, update and
    partial_update to CompanyUpdateSerializer, and everything else to
    CompanySerializer. Validating in only one of them would satisfy a read
    test and still let a PATCH — the path FR-PROC-03 says J-02 writes
    through — store an unvalidated shape.
    """

    def _validate_list(self, value, item_serializer, field):
        if value is None:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError(f"{field} must be a list.")
        serializer = item_serializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return value

    def _validate_object(self, value, object_serializer, field):
        if value is None:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError(f"{field} must be an object.")
        serializer = object_serializer(data=value)
        serializer.is_valid(raise_exception=True)
        # The caller's dict, not validated_data: undeclared keys are legal
        # (see DigitalPresenceSerializer) and validated_data would drop them.
        return value

    def validate_competitors(self, value):
        return self._validate_list(value, CompetitorSerializer, "competitors")

    def validate_products_services(self, value):
        return self._validate_list(value, ProductServiceSerializer, "products_services")

    def validate_marketing_budget_range(self, value):
        return self._validate_object(
            value, MarketingBudgetSerializer, "marketing_budget_range"
        )

    def validate_digital_presence(self, value):
        return self._validate_object(
            value, DigitalPresenceSerializer, "digital_presence"
        )

    def validate_customer_proof(self, value):
        return self._validate_list(value, CustomerProofSerializer, "customer_proof")

    def validate_sales_channels(self, value):
        return self._validate_list(value, SalesChannelSerializer, "sales_channels")

    def validate_audience_languages(self, value):
        """BCP-47 tags, matching §10.2.1's config.language ("en-IN")."""
        if value is None:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError("audience_languages must be a list.")
        for tag in value:
            if not isinstance(tag, str) or not tag.strip():
                raise serializers.ValidationError(
                    "Each language must be a non-empty BCP-47 tag, e.g. 'en-IN'."
                )
        return value


class CompanySerializer(OnboardingFieldShapesMixin, serializers.ModelSerializer):
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
            # B-03 · the thirteen approved onboarding fields (Design §10.1).
            *ONBOARDING_FIELDS,
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
            "sensitivity_class",
            "rag_excluded",
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
            "sensitivity_class",
            "rag_excluded",
            # Read-only until an endpoint validates ownership. As a writable
            # PrimaryKeyRelatedField this accepts any session id a caller can
            # guess, including another tenant's, which would attach their
            # asset to that session — a cross-tenant write with no check.
            #
            # It stays read-only rather than gaining a validator because the
            # session is not the client's to choose: the capture endpoint is
            # POST /sessions/{id}/media/ (Design §10.2, stories H-01/F-02), so
            # the session comes from the URL and is set server-side. A body
            # field would be a second, unauthenticated way to say it.
            "onboarding_session",
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


class CompanyCreateSerializer(OnboardingFieldShapesMixin, serializers.ModelSerializer):
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
            # B-03 · optional here too, so a single-call create can carry
            # them. The wizard does not send them (AC-3); Epic J may.
            *ONBOARDING_FIELDS,
        ]
        read_only_fields = ["id"]
        # Tenant is set in the viewset's perform_create method


class CompanyUpdateSerializer(OnboardingFieldShapesMixin, serializers.ModelSerializer):
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
            # B-03 · this is the PATCH path FR-PROC-03 says J-02 writes
            # through, so it matters most that the fields land here.
            *ONBOARDING_FIELDS,
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
